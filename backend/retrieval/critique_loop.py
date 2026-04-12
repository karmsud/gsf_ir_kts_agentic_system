"""Phase 9.2 — Directed Sequential Critique Loop + Dual-Model Architecture.

Core directed critique loop orchestrator.  After the initial LLM answer,
loads critique questions for all retrieved documents and runs them
sequentially through a fixed low-cost LLM.  If a gap is found the gap
is translated into a retrieval query, new chunks are fetched, the answer
is re-synthesised and the full critique restarts from Q1 (regression).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.common.models import CritiqueQuestion, CritiqueResult
from backend.retrieval.critique_prompts import (
    build_critique_prompt,
    build_gap_to_query_prompt,
    build_resynthesis_prompt,
)

logger = logging.getLogger(__name__)

# ── Safety keyword constants ──────────────────────────────────────

SAFETY_KEYWORDS: dict[str, str] = {
    "CAUTION": "CAUTION annotation",
    "WARNING": "WARNING annotation",
    "\u26a0": "warning symbol",
    "NOTE:": "NOTE callout",
    "IMPORTANT:": "IMPORTANT callout",
    "DO NOT": "prohibition statement",
    "MUST NOT": "prohibition statement",
}


# ── Deterministic helpers ─────────────────────────────────────────

def trigger_matches(question: CritiqueQuestion, chunks: list[dict]) -> bool:
    """Deterministic keyword check — zero LLM cost.

    Returns True if the question should be evaluated given the chunks.
    """
    if question.trigger_logic == "always":
        return True

    all_text = " ".join(c.get("content", c.get("text", "")) for c in chunks).lower()
    keywords = [kw.lower() for kw in question.trigger_keywords]

    if not keywords:
        return False

    if question.trigger_logic == "any_in_source":
        return any(kw in all_text for kw in keywords)
    elif question.trigger_logic == "all_in_source":
        return all(kw in all_text for kw in keywords)

    return False  # unknown logic → skip


def keyword_safety_check(answer: str, source_chunks: list[dict]) -> list[dict]:
    """Deterministic check: source has safety keyword → answer missing it → gap.

    Returns list of synthetic gap dicts to inject into critique queue.
    """
    source_text = " ".join(c.get("content", c.get("text", "")) for c in source_chunks)
    missing: list[dict] = []
    for keyword, label in SAFETY_KEYWORDS.items():
        if keyword in source_text and keyword not in answer:
            missing.append({
                "pass": False,
                "gap_description": (
                    f"Source contains {label} ('{keyword}') "
                    f"but the answer does not include it."
                ),
                "source": "keyword_safety_net",
            })
    return missing


# ── Answer Tracker ────────────────────────────────────────────────

class AnswerTracker:
    """Track answer quality across critique rounds.

    Returns the highest-confidence answer, not necessarily the latest.
    """

    def __init__(self) -> None:
        self.history: list[dict[str, Any]] = []

    def record(self, answer: str, confidence: float, round_num: int, gaps_remaining: int = 0) -> None:
        self.history.append({
            "answer": answer,
            "confidence": confidence,
            "round": round_num,
            "gaps_remaining": gaps_remaining,
        })

    @property
    def best(self) -> dict[str, Any]:
        """Return the answer with highest confidence."""
        if not self.history:
            raise ValueError("No answers recorded")
        return max(self.history, key=lambda h: h["confidence"])

    @property
    def improved(self) -> bool:
        """Did any iteration improve over the initial answer?"""
        if len(self.history) < 2:
            return False
        return self.best["confidence"] > self.history[0]["confidence"]

    @property
    def regression_detected(self) -> bool:
        """Did the latest answer score lower than a previous one?"""
        if len(self.history) < 2:
            return False
        return self.history[-1]["confidence"] < self.best["confidence"]


# ── Gap → Query Translator ────────────────────────────────────────

class GapToQueryTranslator:
    """Convert critique gap descriptions into retrieval queries."""

    @staticmethod
    def translate(gap_description: str, user_query: str, critique_llm: Any) -> str:
        """Translate a gap into a retrieval query using the critique LLM."""
        prompt = build_gap_to_query_prompt(gap_description, user_query)
        return critique_llm(prompt).strip()

    @classmethod
    def translate_with_fallback(
        cls,
        gap_description: str,
        user_query: str,
        critique_llm: Any | None = None,
    ) -> str:
        """Translate with keyword-extraction fallback."""
        if critique_llm is not None:
            try:
                query = cls.translate(gap_description, user_query, critique_llm)
                if query and 3 <= len(query.split()) <= 15:
                    return query
            except Exception:
                pass
        return cls._keyword_extract(gap_description)

    @staticmethod
    def _keyword_extract(text: str) -> str:
        """Simple keyword extraction fallback."""
        words = text.split()
        keywords = [w for w in words if len(w) > 1 and (w[0].isupper() or len(w) > 5)]
        return " ".join(keywords[:8]) if keywords else text[:60]


# ── Directed Critique Loop ────────────────────────────────────────

class DirectedCritiqueLoop:
    """Sequential critique loop with full restart on gap detection.

    Uses a fixed low-cost LLM for critique checks and the caller-
    specified model for answer re-synthesis.  Tracks best answer
    across all iterations.
    """

    def __init__(
        self,
        config: Any | None = None,
        critique_llm: Any | None = None,
        generation_llm: Any | None = None,
        retriever: Any | None = None,
    ):
        self.config = config
        self.critique_llm = critique_llm        # callable(prompt) -> str
        self.generation_llm = generation_llm    # callable(prompt) -> str
        self.retriever = retriever              # callable(query, exclude_ids) -> list[dict]
        self.max_rounds = getattr(config, "critique_max_rounds", 3) if config else 3
        self.restart_on_gap = getattr(config, "critique_restart_on_gap", True) if config else True
        self.confidence_exit = getattr(config, "critique_confidence_exit", 0.90) if config else 0.90

    # ── Main entry point ──────────────────────────────────────────

    def run(
        self,
        query: str,
        initial_answer: str,
        initial_chunks: list[dict],
        critique_questions: list[CritiqueQuestion],
        *,
        initial_confidence: float = 0.5,
    ) -> CritiqueResult:
        """Execute the directed critique loop.

        Parameters
        ----------
        query : str
            Original user query.
        initial_answer : str
            Answer from the user's selected LLM.
        initial_chunks : list[dict]
            Initially retrieved chunks.
        critique_questions : list[CritiqueQuestion]
            Ordered list of active (filtered) questions.
        initial_confidence : float
            Confidence of the initial answer.

        Returns
        -------
        CritiqueResult
        """
        tracker = AnswerTracker()
        current_answer = initial_answer
        current_confidence = initial_confidence
        all_chunks = list(initial_chunks)
        seen_ids: set[str] = {c.get("id", "") for c in initial_chunks if c.get("id")}
        total_evaluated = 0
        total_gaps = 0
        total_fixed = 0
        re_queries: list[str] = []

        # Record initial answer
        tracker.record(current_answer, current_confidence, 0)

        # Prepend safety gaps
        safety_gaps = keyword_safety_check(current_answer, all_chunks)

        for round_num in range(1, self.max_rounds + 1):
            gap_found_this_round = False

            # Evaluate safety gaps first (only on round 1)
            if round_num == 1 and safety_gaps:
                for sgap in safety_gaps:
                    total_evaluated += 1
                    total_gaps += 1
                    re_q = GapToQueryTranslator.translate_with_fallback(
                        sgap["gap_description"], query, self.critique_llm,
                    )
                    re_queries.append(re_q)
                    new_chunks = self._re_retrieve(re_q, seen_ids)
                    if new_chunks:
                        all_chunks.extend(new_chunks)
                        seen_ids.update(c.get("id", "") for c in new_chunks)
                        current_answer = self._re_synthesize(
                            query, current_answer, sgap["gap_description"], new_chunks,
                        )
                        total_fixed += 1
                    current_confidence = self._compute_confidence(
                        total_evaluated, total_gaps - total_fixed,
                    )
                    tracker.record(current_answer, current_confidence, round_num)
                    if self.restart_on_gap:
                        gap_found_this_round = True
                        break
                if gap_found_this_round:
                    continue

            # Evaluate each critique question
            for i, question in enumerate(critique_questions):
                # Trigger pre-filter
                if question.trigger_logic != "always":
                    if not trigger_matches(question, all_chunks):
                        continue

                # Early exit check: high confidence + only tail questions
                remaining = critique_questions[i:]
                if self._should_early_exit(current_confidence, remaining):
                    return self._build_result(
                        tracker, round_num, total_evaluated, total_gaps,
                        total_fixed, re_queries, converged=True,
                    )

                # Evaluate question
                total_evaluated += 1
                verdict = self._evaluate_question(question, current_answer, all_chunks)

                if verdict.get("pass", True):
                    continue

                # Gap found
                total_gaps += 1
                gap_desc = verdict.get("gap_description", "Unknown gap")
                re_q = GapToQueryTranslator.translate_with_fallback(
                    gap_desc, query, self.critique_llm,
                )
                re_queries.append(re_q)
                new_chunks = self._re_retrieve(re_q, seen_ids)
                if new_chunks:
                    all_chunks.extend(new_chunks)
                    seen_ids.update(c.get("id", "") for c in new_chunks)
                    current_answer = self._re_synthesize(
                        query, current_answer, gap_desc, new_chunks,
                    )
                    total_fixed += 1
                current_confidence = self._compute_confidence(
                    total_evaluated, total_gaps - total_fixed,
                )
                tracker.record(current_answer, current_confidence, round_num)

                if self.restart_on_gap:
                    gap_found_this_round = True
                    break  # restart from Q1

            if not gap_found_this_round:
                # All questions passed → converged
                return self._build_result(
                    tracker, round_num, total_evaluated, total_gaps,
                    total_fixed, re_queries, converged=True,
                )

        # Max rounds exhausted
        return self._build_result(
            tracker, self.max_rounds, total_evaluated, total_gaps,
            total_fixed, re_queries, converged=False,
        )

    # ── Internal methods ──────────────────────────────────────────

    def _evaluate_question(
        self, question: CritiqueQuestion, answer: str, chunks: list[dict],
    ) -> dict:
        """Ask the critique LLM to evaluate a single question."""
        if self.critique_llm is None:
            return {"pass": True}
        prompt = build_critique_prompt(question.question, answer, chunks)
        try:
            raw = self.critique_llm(prompt)
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
            return json.loads(text)
        except Exception:
            # Optimistic: treat invalid response as pass
            return {"pass": True}

    def _re_retrieve(self, query: str, exclude_ids: set[str]) -> list[dict]:
        """Re-retrieve new chunks, excluding already-seen ones."""
        if self.retriever is None:
            return []
        try:
            return self.retriever(query, exclude_ids)
        except Exception:
            return []

    def _re_synthesize(
        self,
        query: str,
        current_answer: str,
        gap_description: str,
        new_chunks: list[dict],
    ) -> str:
        """Re-synthesize the answer using the generation LLM."""
        if self.generation_llm is None:
            return current_answer
        prompt = build_resynthesis_prompt(query, current_answer, gap_description, new_chunks)
        try:
            return self.generation_llm(prompt)
        except Exception:
            return current_answer

    def _should_early_exit(
        self, confidence: float, remaining: list[CritiqueQuestion],
    ) -> bool:
        """Exit early if confidence high and remaining are tail questions."""
        if confidence < self.confidence_exit:
            return False
        return all(
            getattr(q, "_source_doc_chunk_count", 0) <= 1
            for q in remaining
        )

    @staticmethod
    def _compute_confidence(questions_evaluated: int, unfixed_gaps: int) -> float:
        """Compute confidence score after critique evaluation."""
        if questions_evaluated == 0:
            return 0.5
        base = (questions_evaluated - max(unfixed_gaps, 0)) / questions_evaluated
        penalty = 0.1 * max(unfixed_gaps, 0)
        return max(0.0, min(1.0, base - penalty))

    @staticmethod
    def _build_result(
        tracker: AnswerTracker,
        rounds: int,
        evaluated: int,
        gaps: int,
        fixed: int,
        re_queries: list[str],
        converged: bool,
    ) -> CritiqueResult:
        best = tracker.best
        return CritiqueResult(
            answer=best["answer"],
            confidence=best["confidence"],
            rounds_executed=rounds,
            questions_evaluated=evaluated,
            gaps_found=gaps,
            gaps_fixed=fixed,
            re_queries=re_queries,
            converged=converged,
            answer_history=[(h["answer"], h["confidence"]) for h in tracker.history],
        )
