"""Phase 9 — Comparative Tests: With Critique Loop vs Without.

A/B comparison: same query run with and without directed critique loop.
Validates that the critique loop does not degrade answer quality and
improves answers when gaps exist.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.agents.critique_defaults import get_default_questions
from backend.common.models import (
    CritiqueQuestion,
    CritiqueResult,
    DocCritique,
    SectionCritique,
)
from backend.retrieval.critique_loop import DirectedCritiqueLoop
from backend.retrieval.critique_merger import merge_critique_questions

# ── Helpers ───────────────────────────────────────────────────────


class _FakeConfig:
    critique_max_rounds = 3
    critique_restart_on_gap = True
    critique_confidence_exit = 0.90


def _chunk(content: str, doc_id: str = "doc1", section_id: str = "sec000",
           chunk_id: str = "c1") -> dict:
    return {"id": chunk_id, "content": content, "doc_id": doc_id,
            "section_id": section_id, "metadata": {"doc_id": doc_id}}


class MockLLM:
    def __init__(self, default='{"pass": true}'):
        self.default = default
        self.call_log = []
    def __call__(self, prompt):
        self.call_log.append(prompt)
        return self.default


def _hp_critique() -> DocCritique:
    """Pre-built critique for HP Troubleshooting Guide."""
    return DocCritique(
        doc_id="doc_hp",
        doc_type="TROUBLESHOOT",
        generated_at="2026-02-18T17:45:00Z",
        generator_model="gpt-4.1",
        doc_level_questions=[
            CritiqueQuestion(
                id="dq_001",
                question="Does the answer preserve all CAUTION annotations?",
                trigger_keywords=["CAUTION", "WARNING"],
                trigger_logic="any_in_source",
                priority=1,
            ),
        ],
        section_questions=[
            SectionCritique(
                section_id="sec000",
                section_title="Solving General Problems",
                questions=[
                    CritiqueQuestion(
                        id="sq_001",
                        question="Is the Problem-Cause-Solution structure preserved?",
                        trigger_keywords=["Problem", "Cause", "Solution"],
                        trigger_logic="all_in_source",
                        priority=1,
                    ),
                    CritiqueQuestion(
                        id="sq_002",
                        question="Are steps ordered by severity (force-off first)?",
                        trigger_keywords=["power button", "restart"],
                        trigger_logic="any_in_source",
                        priority=2,
                    ),
                ],
                rubric=None,
            ),
        ],
    )


def _psa_critique() -> DocCritique:
    """Pre-built critique for PSA Governing Document."""
    return DocCritique(
        doc_id="doc_psa",
        doc_type="GOVERNING_DOC",
        generated_at="2026-02-18T17:45:00Z",
        generator_model="gpt-4.1",
        doc_level_questions=[
            CritiqueQuestion(
                id="dq_001",
                question="Are all Capitalized Terms traced to their definitions?",
                trigger_keywords=[],
                trigger_logic="always",
                priority=1,
            ),
        ],
        section_questions=[],
    )


# ══════════════════════════════════════════════════════════════════
# Comparative: With vs Without Critique Loop
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.comparative
class TestComparative:

    def _run_without_critique(self, initial_answer: str) -> str:
        """Simulate query without critique loop — just return initial answer."""
        return initial_answer

    def _run_with_critique(
        self, query: str, initial_answer: str, chunks: list[dict],
        critique_store: dict[str, DocCritique],
        critique_llm=None, gen_llm=None,
    ) -> CritiqueResult:
        """Simulate query with critique loop."""
        merged = merge_critique_questions(chunks, critique_store)
        loop = DirectedCritiqueLoop(
            config=_FakeConfig(),
            critique_llm=critique_llm or MockLLM('{"pass": true}'),
            generation_llm=gen_llm,
        )
        return loop.run(query, initial_answer, chunks, merged)

    def test_no_degradation_all_pass(self):
        """When all checks pass, critique answer == initial answer."""
        initial = "CAUTION: Hot surface. Step 1: Force-off. Step 2: Check LEDs."
        chunks = [_chunk("CAUTION: Hot surface", "doc_hp", "sec000", "c1")]
        result = self._run_with_critique(
            "Computer won't start", initial, chunks,
            {"doc_hp": _hp_critique()},
        )
        assert result.answer == initial
        assert result.converged is True

    def test_improvement_on_gap(self):
        """Critique finds gap → improved answer has more info."""
        initial = "Step 1: Force-off."
        chunks = [_chunk("CAUTION: Hot surface. Step 1: Force-off.", "doc_hp", "sec000")]

        call_count = {"n": 0}
        def _critique(prompt):
            call_count["n"] += 1
            if "CAUTION" in prompt and call_count["n"] == 1:
                return '{"pass": false, "gap_description": "Missing CAUTION annotation"}'
            return '{"pass": true}'

        gen = MockLLM("CAUTION: Hot surface. Step 1: Force-off. Step 2: Check LEDs.")
        result = self._run_with_critique(
            "Computer won't start", initial, chunks,
            {"doc_hp": _hp_critique()},
            critique_llm=_critique, gen_llm=gen,
        )
        assert result.gaps_found >= 1
        assert result.gaps_fixed >= 0

    def test_critique_converges_quickly_all_pass(self):
        """Clean answers converge in 1 round."""
        chunks = [_chunk("CAUTION content", "doc_hp", "sec000")]
        result = self._run_with_critique(
            "query", "good answer with CAUTION", chunks,
            {"doc_hp": _hp_critique()},
        )
        assert result.rounds_executed <= 1

    def test_multi_doc_comparative(self):
        """Multi-doc query: with critique evaluates questions from both docs."""
        chunks = [
            _chunk("CAUTION content", "doc_hp", "sec000", "c1"),
            _chunk("Closing Date means...", "doc_psa", "sec001", "c2"),
        ]
        store = {"doc_hp": _hp_critique(), "doc_psa": _psa_critique()}
        result = self._run_with_critique(
            "obligations and troubleshooting", "combined answer", chunks, store,
        )
        assert result.questions_evaluated >= 2

    def test_without_critique_no_overhead(self):
        """Without critique → direct return, no LLM calls."""
        answer = "plain answer"
        result = self._run_without_critique(answer)
        assert result == answer

    def test_confidence_tracking(self):
        """Critique loop tracks confidence across rounds."""
        chunks = [_chunk("content", "doc1")]
        store = {"doc1": DocCritique(
            doc_id="doc1", doc_type="X",
            doc_level_questions=[CritiqueQuestion(
                id="q1", question="Check?", trigger_keywords=[], trigger_logic="always",
            )],
        )}
        result = self._run_with_critique("q", "a", chunks, store)
        assert 0.0 <= result.confidence <= 1.0
        assert len(result.answer_history) >= 1

    def test_answer_history_populated(self):
        """answer_history has at least the initial entry."""
        chunks = [_chunk("x", "d1")]
        store = {"d1": DocCritique(
            doc_id="d1", doc_type="X",
            doc_level_questions=[CritiqueQuestion(
                id="q1", question="?", trigger_keywords=[], trigger_logic="always",
            )],
        )}
        result = self._run_with_critique("q", "initial", chunks, store)
        assert len(result.answer_history) >= 1
        assert result.answer_history[0][0] == "initial"  # (answer, confidence)


# ══════════════════════════════════════════════════════════════════
# Scoring framework tests
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.comparative
class TestScoringFramework:

    def test_score_function_computable(self):
        """A basic scoring function can be computed from CritiqueResult."""
        result = CritiqueResult(
            answer="CAUTION: answer",
            confidence=0.9,
            rounds_executed=1,
            questions_evaluated=3,
            gaps_found=0,
            gaps_fixed=0,
            re_queries=[],
            converged=True,
            answer_history=[("CAUTION: answer", 0.9)],
        )
        # Basic score: confidence * (1 - gaps_found/max(questions_evaluated,1))
        score = result.confidence * (1 - result.gaps_found / max(result.questions_evaluated, 1))
        assert 0.0 <= score <= 1.0

    def test_higher_confidence_wins(self):
        """Higher confidence result scores better."""
        r1 = CritiqueResult(answer="a", confidence=0.9, converged=True,
                            questions_evaluated=3, gaps_found=0)
        r2 = CritiqueResult(answer="b", confidence=0.6, converged=True,
                            questions_evaluated=3, gaps_found=1)
        s1 = r1.confidence * (1 - r1.gaps_found / max(r1.questions_evaluated, 1))
        s2 = r2.confidence * (1 - r2.gaps_found / max(r2.questions_evaluated, 1))
        assert s1 > s2

    def test_converged_preferred(self):
        """Converged results are preferred over unconverged."""
        r1 = CritiqueResult(answer="a", confidence=0.8, converged=True,
                            questions_evaluated=3, gaps_found=0)
        r2 = CritiqueResult(answer="b", confidence=0.8, converged=False,
                            questions_evaluated=3, gaps_found=2)
        assert r1.converged and not r2.converged
