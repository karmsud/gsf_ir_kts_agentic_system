"""Phase 9.1 — Critique question generator for ingest-time question creation.

Generates document-specific binary critique questions at ingestion time.
Uses a fixed low-cost LLM (GPT-4.1) to analyze the full document and
produce section-level yes/no critique questions with trigger keywords.
These questions are stored as critique_questions.json and consumed at
query time by the directed critique loop (9.2).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.agents.critique_defaults import get_default_questions
from backend.common.models import (
    CritiqueQuestion,
    DocCritique,
    SectionCritique,
)

logger = logging.getLogger(__name__)


# ── Module-level convenience function (spec: prepare_doc_for_critique_gen) ─

def prepare_doc_for_critique_gen(
    doc_text: str,
    sections: list[dict],
    max_tokens: int = 100_000,
) -> str:
    """Prepare document content for critique question generation.

    Module-level wrapper around ``CritiqueQuestionGenerator._prepare_doc_content``
    for callers that do not need the full generator instance.
    """
    return CritiqueQuestionGenerator._prepare_doc_content(doc_text, sections, max_tokens)


# ── Prompt for generating critique questions ──────────────────────

GENERATION_PROMPT = """System: You are a document quality analyst. Your task is to generate \
critique questions that can verify whether an AI-generated answer about \
this document is complete and accurate.

Document type: {doc_type}
Document title: {doc_title}

Full document text (or structured summary):
{doc_content}

Sections identified:
{section_list}

Instructions:
1. Generate 2-4 doc-level critique questions that apply to ANY query \
against this document. Focus on universal answer quality requirements \
(citations, safety annotations, terminology accuracy).

2. For each section, generate 1-4 section-level critique questions that \
verify answer completeness when that section's content is retrieved.

3. For each question, provide trigger keywords — terms that must appear \
in the source chunks for the question to be relevant. Use "always" logic \
for questions that should always be asked.

Output ONLY valid JSON matching this schema:
{{
  "doc_level_questions": [
    {{"id": "dq_001", "question": "...", "trigger_keywords": [], "trigger_logic": "always", "priority": 1}}
  ],
  "section_questions": [
    {{
      "section_id": "sec000",
      "section_title": "...",
      "questions": [
        {{"id": "sq_001", "question": "...", "trigger_keywords": ["kw1"], "trigger_logic": "any_in_source", "priority": 1}}
      ],
      "rubric": null
    }}
  ]
}}
"""


class CritiqueQuestionGenerator:
    """Generate, save, load, and validate doc-specific critique questions."""

    def __init__(self, config: Any | None = None):
        self.config = config
        self.max_questions = getattr(config, "critique_max_questions_per_doc", 15) if config else 15

    # ── Core generation ───────────────────────────────────────────

    def generate(
        self,
        doc_text: str,
        doc_type: str,
        sections: list[dict],
        *,
        doc_id: str = "",
        doc_title: str = "",
        llm_callable: Any | None = None,
    ) -> DocCritique:
        """Generate critique questions for a document.

        Parameters
        ----------
        doc_text : str
            Full document text (or summary for very long docs).
        doc_type : str
            Document type (GOVERNING_DOC, TROUBLESHOOT, etc.).
        sections : list[dict]
            Section dicts with ``section_id`` and ``title`` keys.
        doc_id : str
            Document identifier.
        doc_title : str
            Document title.
        llm_callable : callable, optional
            A callable ``llm_callable(prompt: str) -> str`` that calls the
            fixed critique LLM.  If ``None``, returns default questions.

        Returns
        -------
        DocCritique
        """
        if llm_callable is None:
            return self._build_defaults(doc_id, doc_type)

        content = self._prepare_doc_content(doc_text, sections)
        section_list = "\n".join(
            f"- {s.get('section_id', 'sec000')}: {s.get('title', 'Untitled')}"
            for s in sections
        ) or "(no sections)"

        prompt = GENERATION_PROMPT.format(
            doc_type=doc_type,
            doc_title=doc_title or doc_id,
            doc_content=content,
            section_list=section_list,
        )

        try:
            raw = llm_callable(prompt)
            critique = self._parse_response(raw, doc_id, doc_type)
        except Exception as exc:
            logger.warning("Critique generation failed for %s: %s — using defaults", doc_id, exc)
            critique = self._build_defaults(doc_id, doc_type)

        # Enforce question cap
        self._truncate(critique)

        errors = self.validate(critique)
        if errors:
            logger.warning("Critique validation errors for %s: %s — using defaults", doc_id, errors)
            critique = self._build_defaults(doc_id, doc_type)

        return critique

    # ── Persistence ───────────────────────────────────────────────

    def save(self, critique: DocCritique, kts_path: str | Path) -> Path:
        """Save DocCritique to ``{kts_path}/documents/{doc_id}/critique_questions.json``."""
        kts = Path(kts_path)
        doc_dir = kts / "documents" / critique.doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        out = doc_dir / "critique_questions.json"
        out.write_text(json.dumps(asdict(critique), indent=2, default=str), encoding="utf-8")
        logger.info("Saved critique questions to %s", out)
        return out

    def load(self, doc_id: str, kts_path: str | Path) -> DocCritique | None:
        """Load critique questions for *doc_id*.  Returns ``None`` if missing/corrupt."""
        path = Path(kts_path) / "documents" / doc_id / "critique_questions.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return self._dict_to_critique(data)
        except Exception as exc:
            logger.warning("Failed to load critique questions from %s: %s", path, exc)
            return None

    # ── Validation ────────────────────────────────────────────────

    @staticmethod
    def validate(critique: DocCritique) -> list[str]:
        """Return list of validation error strings (empty = valid)."""
        errors: list[str] = []
        valid_logics = {"always", "any_in_source", "all_in_source"}

        def _check(q: CritiqueQuestion) -> None:
            if not q.question.strip().endswith("?"):
                errors.append(f"{q.id}: Question doesn't end with '?'")
            if q.trigger_logic not in valid_logics:
                errors.append(f"{q.id}: Invalid trigger_logic '{q.trigger_logic}'")
            if q.trigger_logic != "always" and not q.trigger_keywords:
                errors.append(f"{q.id}: Non-always trigger has no keywords")

        for q in critique.doc_level_questions:
            _check(q)
        for sc in critique.section_questions:
            for q in sc.questions:
                _check(q)
            if len(sc.questions) > 15:
                errors.append(f"Section {sc.section_id}: {len(sc.questions)} questions exceeds max (15)")
        return errors

    # ── Internal helpers ──────────────────────────────────────────

    @staticmethod
    def _prepare_doc_content(
        doc_text: str,
        sections: list[dict],
        max_tokens: int = 100_000,
    ) -> str:
        """Prepare document content; truncate for very long docs."""
        estimated_tokens = len(doc_text) // 4
        if estimated_tokens <= max_tokens:
            return doc_text

        parts = [f"[DOCUMENT BEGINNING — first 3000 tokens]\n{doc_text[:12_000]}"]
        for section in sections:
            title = section.get("title", "Untitled")
            content = section.get("content", "")[:2_000]
            parts.append(f"\n[SECTION: {title}]\n{content}")
        parts.append(f"\n[DOCUMENT END — last 1000 tokens]\n{doc_text[-4_000:]}")
        return "\n".join(parts)

    def _parse_response(self, raw: str, doc_id: str, doc_type: str) -> DocCritique:
        """Parse LLM JSON response into a DocCritique."""
        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        data = json.loads(text)

        doc_qs = [
            CritiqueQuestion(**q) for q in data.get("doc_level_questions", [])
        ]
        sec_qs = []
        for s in data.get("section_questions", []):
            questions = [CritiqueQuestion(**q) for q in s.get("questions", [])]
            sec_qs.append(SectionCritique(
                section_id=s.get("section_id", "sec000"),
                section_title=s.get("section_title", ""),
                questions=questions,
                rubric=s.get("rubric"),
            ))

        return DocCritique(
            doc_id=doc_id,
            doc_type=doc_type,
            generated_at=datetime.now(timezone.utc).isoformat(),
            generator_model=getattr(self.config, "critique_generator_model", "gpt-4.1") if self.config else "gpt-4.1",
            doc_level_questions=doc_qs,
            section_questions=sec_qs,
        )

    def _build_defaults(self, doc_id: str, doc_type: str) -> DocCritique:
        """Build a DocCritique from the static default library."""
        return DocCritique(
            doc_id=doc_id,
            doc_type=doc_type,
            generated_at=datetime.now(timezone.utc).isoformat(),
            generator_model="default",
            doc_level_questions=list(get_default_questions(doc_type)),
            section_questions=[],
        )

    def _truncate(self, critique: DocCritique) -> None:
        """Truncate total question count to self.max_questions."""
        total = len(critique.doc_level_questions)
        for sc in critique.section_questions:
            total += len(sc.questions)
        if total <= self.max_questions:
            return
        # Keep doc-level, trim section-level proportionally
        remaining = self.max_questions - len(critique.doc_level_questions)
        if remaining <= 0:
            critique.doc_level_questions = critique.doc_level_questions[: self.max_questions]
            critique.section_questions = []
            return
        for sc in critique.section_questions:
            keep = max(1, remaining // max(len(critique.section_questions), 1))
            sc.questions = sc.questions[:keep]
            remaining -= len(sc.questions)
            if remaining <= 0:
                break

    @staticmethod
    def _dict_to_critique(data: dict) -> DocCritique:
        """Convert a raw dict (from JSON) back to a DocCritique."""
        doc_qs = [CritiqueQuestion(**q) for q in data.get("doc_level_questions", [])]
        sec_qs = []
        for s in data.get("section_questions", []):
            questions = [CritiqueQuestion(**q) for q in s.get("questions", [])]
            sec_qs.append(SectionCritique(
                section_id=s.get("section_id", "sec000"),
                section_title=s.get("section_title", ""),
                questions=questions,
                rubric=s.get("rubric"),
            ))
        return DocCritique(
            doc_id=data.get("doc_id", ""),
            doc_type=data.get("doc_type", ""),
            generated_at=data.get("generated_at", ""),
            generator_model=data.get("generator_model", ""),
            doc_level_questions=doc_qs,
            section_questions=sec_qs,
        )
