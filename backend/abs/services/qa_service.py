"""
QAService — grounded Q&A and the Explainability Traceback.

``ask``       — retrieve page-cited chunks, pull in resolved definitions for any
                capitalized terms, and answer strictly from that evidence.
``explain``   — the traceback feature: for a target value (e.g. "Class A-1
                interest for 2024-09") assemble a full evidence ladder — relevant
                SEP artifacts, governing-doc clauses, resolved definitions,
                payment-model output and source excerpts — then produce a
                step-by-step grounded narrative with citations at every hop.

Stateless + async. Retrieval here is keyword-based over the stored, page-cited
chunks; it composes with the existing dense/BM25 retrievers when available.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from backend.abs.services.base import ABSService, ServiceContext, ServiceResult
from backend.abs.services.llm_client import LLMClient
from backend.abs.store import DealStore

_STOP = frozenset(
    "the a an and or of to for in on at is are be by with as it this that "
    "what why how when where which who whom does do did will shall may from".split()
)
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]*")
_CAP_PHRASE_RE = re.compile(r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,4})\b")
# Leading determiners/prepositions to strip so "The Trustee" -> "Trustee".
_LEADING_DROP = frozenset({"The", "A", "An", "On", "In", "Of", "For", "To", "By", "And", "Or", "If"})

_QA_SYSTEM = (
    "You are a structured-finance analyst. Answer ONLY from the provided evidence. "
    "Cite the section/page for every claim using the bracketed citations given. If the "
    "evidence is insufficient, say so. Never invent figures."
)
_EXPLAIN_SYSTEM = (
    "You are a structured-finance explainability engine. Explain how a value is derived, "
    "step by step, strictly from the provided evidence (payment model, extracted artifacts, "
    "governing-document clauses, resolved definitions, and source excerpts). Show the "
    "calculation, and cite the section/page at each step. If a link is missing, state it."
)


def _tokenize(text: str) -> list[str]:
    return [w for w in _WORD_RE.findall((text or "").lower()) if w not in _STOP and len(w) > 1]


def capitalized_terms(text: str) -> set[str]:
    """Return candidate capitalized (multi-word) phrases from text.

    A leading determiner/preposition (e.g. sentence-initial "The") is stripped
    so phrases match stored defined-term names like "Trustee".
    """
    out: set[str] = set()
    for m in _CAP_PHRASE_RE.finditer(text or ""):
        phrase = m.group(1).strip()
        words = phrase.split()
        if len(words) > 1 and words[0] in _LEADING_DROP:
            words = words[1:]
        if words:
            out.add(" ".join(words))
    return out


class QAService(ABSService):
    """Grounded Q&A + explainability traceback."""

    name = "qa"

    def __init__(self, deals_root: Path) -> None:
        self.deals_root = Path(deals_root)
        from backend.abs.services.retrieval_service import RetrievalService

        self.retrieval = RetrievalService(self.deals_root)

    def context(self, deal_id: str) -> ServiceContext:
        return ServiceContext(deal_id=deal_id, deals_root=self.deals_root)

    # ------------------------------------------------------------------
    # Q&A
    # ------------------------------------------------------------------
    async def ask(self, deal_id: str, question: str, llm: LLMClient, *, top_k: int = 8) -> ServiceResult:
        return await self.guard(self._ask(deal_id, question, llm, top_k))

    async def _ask(self, deal_id: str, question: str, llm: LLMClient, top_k: int) -> dict[str, Any]:
        search_res = await self.retrieval.search(deal_id, question, top_k=top_k)
        retrieved = search_res.data if search_res.ok else []
        joined = question + " " + " ".join(c.get("text", "") for c in retrieved)
        defs = await self._to_thread(self._resolved_defs_for_text, deal_id, joined)
        prompt = self._qa_prompt(question, retrieved, defs)
        result = await llm.complete(prompt, system=_QA_SYSTEM, temperature=0.0, max_tokens=900)
        return {
            "answer": result.text.strip(),
            "citations": [
                {"chunk_id": c["chunk_id"], "citation": c.get("citation", ""),
                 "section_id": c.get("section_id"), "page": c.get("page_start"),
                 "signals": c.get("signals", {})}
                for c in retrieved
            ],
            "resolved_terms_used": list(defs.keys()),
        }

    # ------------------------------------------------------------------
    # Explainability traceback
    # ------------------------------------------------------------------
    async def explain(self, deal_id: str, target: str, llm: LLMClient, *, top_k: int = 6) -> ServiceResult:
        return await self.guard(self._explain(deal_id, target, llm, top_k))

    async def _explain(self, deal_id: str, target: str, llm: LLMClient, top_k: int) -> dict[str, Any]:
        search_res = await self.retrieval.search(deal_id, target, top_k=top_k)
        source_excerpts = search_res.data if search_res.ok else []
        bundle = await self._to_thread(self._evidence_bundle, deal_id, target)
        bundle["source_excerpts"] = source_excerpts
        prompt = self._explain_prompt(target, bundle)
        result = await llm.complete(prompt, system=_EXPLAIN_SYSTEM, temperature=0.0, max_tokens=1200)
        return {
            "target": target,
            "answer": result.text.strip(),
            "evidence": bundle,
            "citations": [c.get("citation", "") for c in source_excerpts],
        }

    # ------------------------------------------------------------------
    # Evidence assembly (sync, off-thread)
    # ------------------------------------------------------------------
    def _resolved_defs_for_text(self, deal_id: str, text: str) -> dict[str, str]:
        store = self.context(deal_id).store(init=False)
        wanted = capitalized_terms(text)
        out: dict[str, str] = {}
        for term in wanted:
            row = store.find_definition_by_name(deal_id, term)
            if row:
                out[term] = (row.get("resolved_definition") or row.get("raw_definition") or "")[:400]
        return out

    def _evidence_bundle(self, deal_id: str, target: str) -> dict[str, Any]:
        store = self.context(deal_id).store(init=False)
        t_terms = set(_tokenize(target))

        # Relevant SEP artifacts (any profile) by keyword overlap.
        artifacts = store.list_sep_artifacts(deal_id)
        def art_score(a: dict[str, Any]) -> int:
            blob = f"{a.get('field_path','')} {a.get('value','')}".lower()
            return sum(1 for t in t_terms if t in blob)
        rel_artifacts = sorted(artifacts, key=art_score, reverse=True)
        rel_artifacts = [a for a in rel_artifacts if art_score(a) > 0][:8]

        # Relevant governing clauses.
        clauses = store.list_governing_clauses(deal_id)
        def clause_score(c: dict[str, Any]) -> int:
            blob = f"{c.get('verbatim','')} {c.get('plain_english','')}".lower()
            return sum(1 for t in t_terms if t in blob)
        rel_clauses = sorted(clauses, key=clause_score, reverse=True)
        rel_clauses = [c for c in rel_clauses if clause_score(c) > 0][:6]

        return {
            "target": target,
            "payment_model": store.get_latest_payment_model(deal_id),
            "monthly_runs": store.list_monthly_runs(deal_id)[:1],
            "sep_artifacts": rel_artifacts,
            "governing_clauses": rel_clauses,
            "resolved_definitions": self._resolved_defs_for_text(deal_id, target),
            "source_excerpts": [],  # filled by the async caller via RetrievalService
        }

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------
    def _qa_prompt(self, question: str, chunks: list[dict[str, Any]], defs: dict[str, str]) -> str:
        ctx = "\n\n".join(f"[{c.get('citation','')}]\n{c.get('text','')}" for c in chunks) or "(no evidence found)"
        parts = [f"QUESTION: {question}\n", "EVIDENCE:", ctx]
        if defs:
            parts.append("\nRESOLVED DEFINED TERMS:")
            for term, meaning in defs.items():
                parts.append(f'- "{term}": {meaning}')
        parts.append("\nAnswer with citations:")
        return "\n".join(parts)

    def _explain_prompt(self, target: str, bundle: dict[str, Any]) -> str:
        import json as _json

        parts = [f"EXPLAIN: {target}\n"]
        model = bundle.get("payment_model")
        if model and model.get("python_source"):
            parts.append("PAYMENT MODEL (excerpt):")
            parts.append((model["python_source"] or "")[:1500])
        if bundle["monthly_runs"]:
            parts.append("\nLATEST RUN RESULTS:")
            parts.append((bundle["monthly_runs"][0].get("results") or "")[:1000])
        if bundle["sep_artifacts"]:
            parts.append("\nEXTRACTED ARTIFACTS:")
            for a in bundle["sep_artifacts"]:
                parts.append(f"- [{a.get('sep_name')}] {a.get('value')}  (cite: {a.get('citation')})")
        if bundle["governing_clauses"]:
            parts.append("\nGOVERNING CLAUSES:")
            for c in bundle["governing_clauses"]:
                parts.append(f"- {c.get('plain_english')}  | formula: {c.get('math_formula')}  (cite: {c.get('citation')})")
        if bundle["resolved_definitions"]:
            parts.append("\nRESOLVED DEFINITIONS:")
            for term, meaning in bundle["resolved_definitions"].items():
                parts.append(f'- "{term}": {meaning}')
        if bundle["source_excerpts"]:
            parts.append("\nSOURCE EXCERPTS:")
            for c in bundle["source_excerpts"]:
                parts.append(f"[{c.get('citation','')}]\n{c.get('text','')}")
        parts.append("\nProvide a step-by-step, fully cited explanation tracing back to the source document:")
        return "\n".join(parts)
