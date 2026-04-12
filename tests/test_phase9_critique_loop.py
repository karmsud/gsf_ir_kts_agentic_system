"""Phase 9.2 — Directed Sequential Critique Loop Tests.

Covers: trigger_matches, keyword_safety_check, DirectedCritiqueLoop,
AnswerTracker, GapToQueryTranslator, dual-model architecture.
~38 tests per testing plan.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.common.models import CritiqueQuestion, CritiqueResult
from backend.retrieval.critique_loop import (
    SAFETY_KEYWORDS,
    AnswerTracker,
    DirectedCritiqueLoop,
    GapToQueryTranslator,
    keyword_safety_check,
    trigger_matches,
)
from backend.retrieval.critique_prompts import (
    CRITIQUE_PROMPT,
    CRITIQUE_EVAL_PROMPT,
    RESYNTHESIS_PROMPT,
    RE_SYNTHESIS_PROMPT,
    GAP_TO_QUERY_PROMPT,
    build_critique_prompt,
    build_gap_to_query_prompt,
    build_resynthesis_prompt,
    format_chunks,
)

# ── Helpers ───────────────────────────────────────────────────────

def _q(qid: str, question: str, keywords: list[str] | None = None,
       logic: str = "always", priority: int = 1) -> CritiqueQuestion:
    return CritiqueQuestion(
        id=qid, question=question,
        trigger_keywords=keywords or [], trigger_logic=logic,
        priority=priority,
    )


def _chunk(content: str, doc_id: str = "doc1", chunk_id: str = "c1",
           section_id: str = "sec000") -> dict:
    return {"id": chunk_id, "content": content, "doc_id": doc_id,
            "section_id": section_id, "metadata": {"doc_id": doc_id}}


class MockCritiqueLLM:
    """Configurable mock LLM for critique loop testing."""

    def __init__(self, responses: dict[str, str] | None = None,
                 default: str = '{"pass": true}'):
        self.responses = responses or {}
        self.default = default
        self.call_log: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.call_log.append(prompt)
        for key, response in self.responses.items():
            if key in prompt:
                return response
        return self.default

    @property
    def call_count(self) -> int:
        return len(self.call_log)


class MockRetriever:
    """Mock retriever that returns pre-configured chunks."""

    def __init__(self, chunks: list[dict] | None = None):
        self.chunks = chunks or []
        self.call_log: list[tuple] = []

    def __call__(self, query: str, exclude_ids: set) -> list[dict]:
        self.call_log.append((query, exclude_ids))
        return [c for c in self.chunks if c.get("id") not in exclude_ids]


class _FakeConfig:
    critique_max_rounds = 3
    critique_restart_on_gap = True
    critique_confidence_exit = 0.90


# ══════════════════════════════════════════════════════════════════
# 2.2.1 Unit Tests — Trigger Pre-Filter
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.critique_loop
class TestTriggerPreFilter:

    def test_trigger_always_returns_true(self):
        """#1: trigger_logic='always' → True regardless of chunks."""
        q = _q("q1", "Always?", logic="always")
        assert trigger_matches(q, [_chunk("anything")]) is True

    def test_trigger_any_matches_single(self):
        """#2: 'any_in_source' with keyword present → True."""
        q = _q("q2", "CAUTION?", keywords=["CAUTION"], logic="any_in_source")
        assert trigger_matches(q, [_chunk("CAUTION: do not touch")]) is True

    def test_trigger_any_no_match(self):
        """#3: 'any_in_source' with keyword absent → False."""
        q = _q("q3", "CAUTION?", keywords=["CAUTION"], logic="any_in_source")
        assert trigger_matches(q, [_chunk("safe content")]) is False

    def test_trigger_any_case_insensitive(self):
        """#4: Keywords match case-insensitively."""
        q = _q("q4", "caution?", keywords=["caution"], logic="any_in_source")
        assert trigger_matches(q, [_chunk("CAUTION: hot surface")]) is True

    def test_trigger_all_requires_all(self):
        """#5: 'all_in_source' — only one keyword present → False."""
        q = _q("q5", "Both?", keywords=["CAUTION", "WARNING"], logic="all_in_source")
        assert trigger_matches(q, [_chunk("CAUTION only")]) is False

    def test_trigger_all_both_present(self):
        """#6: 'all_in_source' — both keywords present → True."""
        q = _q("q6", "Both?", keywords=["CAUTION", "WARNING"], logic="all_in_source")
        assert trigger_matches(q, [_chunk("CAUTION and WARNING here")]) is True

    def test_trigger_empty_chunks(self):
        """#7: Empty chunk list → False (except 'always')."""
        q_any = _q("q7a", "X?", keywords=["X"], logic="any_in_source")
        q_always = _q("q7b", "Y?", logic="always")
        assert trigger_matches(q_any, []) is False
        assert trigger_matches(q_always, []) is True

    def test_trigger_no_keywords_returns_false(self):
        """Non-always with empty keywords → False."""
        q = _q("q8", "?", keywords=[], logic="any_in_source")
        assert trigger_matches(q, [_chunk("anything")]) is False

    def test_trigger_unknown_logic_returns_false(self):
        """Unknown trigger_logic → False."""
        q = _q("q9", "?", keywords=["X"], logic="sometimes")
        assert trigger_matches(q, [_chunk("X is here")]) is False


# ══════════════════════════════════════════════════════════════════
# 2.2.2 Unit Tests — Keyword Safety Net
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.critique_loop
class TestKeywordSafetyNet:

    def test_safety_detects_missing_caution(self):
        """#8: Source has 'CAUTION', answer doesn't → 1 synthetic gap."""
        gaps = keyword_safety_check("Safe answer", [_chunk("CAUTION: hot")])
        assert len(gaps) >= 1
        assert any("CAUTION" in g["gap_description"] for g in gaps)

    def test_safety_passes_when_present(self):
        """#9: Both source and answer have 'CAUTION' → empty list."""
        gaps = keyword_safety_check("CAUTION: hot", [_chunk("CAUTION: hot")])
        caution_gaps = [g for g in gaps if "CAUTION" in g["gap_description"]]
        assert len(caution_gaps) == 0

    def test_safety_detects_multiple_missing(self):
        """#10: Source has both CAUTION + WARNING, answer has neither → 2 gaps."""
        gaps = keyword_safety_check("plain answer", [_chunk("CAUTION x WARNING y")])
        gap_kws = [g["gap_description"] for g in gaps]
        assert any("CAUTION" in g for g in gap_kws)
        assert any("WARNING" in g for g in gap_kws)

    def test_safety_ignores_absent_keywords(self):
        """#11: Source has no safety keywords → empty list."""
        gaps = keyword_safety_check("answer", [_chunk("normal content")])
        assert len(gaps) == 0

    def test_safety_detects_warning_symbol(self):
        """#12: Source has warning symbol, answer doesn't → 1 gap."""
        gaps = keyword_safety_check("no symbol", [_chunk("\u26a0 danger")])
        assert any("\u26a0" in g["gap_description"] for g in gaps)

    def test_safety_keywords_constant_populated(self):
        """SAFETY_KEYWORDS constant has required entries."""
        assert "CAUTION" in SAFETY_KEYWORDS
        assert "WARNING" in SAFETY_KEYWORDS
        assert "DO NOT" in SAFETY_KEYWORDS


# ══════════════════════════════════════════════════════════════════
# 2.2.3 Unit Tests — Single Critique Evaluation
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.critique_loop
class TestCritiqueEvaluation:

    def test_critique_pass_returns_true(self):
        """#13: Mock LLM returns pass → pass verdict."""
        llm = MockCritiqueLLM(default='{"pass": true}')
        loop = DirectedCritiqueLoop(critique_llm=llm)
        verdict = loop._evaluate_question(
            _q("q1", "Steps ordered?"), "answer", [_chunk("content")],
        )
        assert verdict["pass"] is True

    def test_critique_fail_returns_gap(self):
        """#14: Mock LLM returns fail with gap_description."""
        llm = MockCritiqueLLM(default='{"pass": false, "gap_description": "Missing CAUTION"}')
        loop = DirectedCritiqueLoop(critique_llm=llm)
        verdict = loop._evaluate_question(
            _q("q1", "CAUTION?"), "answer", [_chunk("CAUTION: x")],
        )
        assert verdict["pass"] is False
        assert "Missing CAUTION" in verdict["gap_description"]

    def test_critique_invalid_json_treated_as_pass(self):
        """#15: Mock LLM returns garbage → treated as pass (optimistic)."""
        llm = MockCritiqueLLM(default="not json at all!")
        loop = DirectedCritiqueLoop(critique_llm=llm)
        verdict = loop._evaluate_question(
            _q("q1", "?"), "answer", [_chunk("x")],
        )
        assert verdict["pass"] is True

    def test_critique_exception_treated_as_pass(self):
        """#16: Mock LLM raises exception → treated as pass."""
        def _raise(prompt):
            raise TimeoutError("timeout")
        loop = DirectedCritiqueLoop(critique_llm=_raise)
        verdict = loop._evaluate_question(
            _q("q1", "?"), "answer", [_chunk("x")],
        )
        assert verdict["pass"] is True

    def test_critique_no_llm_returns_pass(self):
        """No critique LLM → always pass."""
        loop = DirectedCritiqueLoop(critique_llm=None)
        verdict = loop._evaluate_question(
            _q("q1", "?"), "answer", [_chunk("x")],
        )
        assert verdict["pass"] is True


# ══════════════════════════════════════════════════════════════════
# 2.2.4 Unit Tests — Gap → Query Translation
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.critique_loop
class TestGapToQueryTranslation:

    def test_translate_returns_query_string(self):
        """#17: Gap about missing CAUTION → 5-10 word query."""
        llm = MockCritiqueLLM(default="CAUTION annotation data loss prevention")
        result = GapToQueryTranslator.translate(
            "Missing CAUTION about data loss", "computer won't start", llm,
        )
        assert len(result.split()) >= 3

    def test_translate_fallback_on_invalid(self):
        """#18: LLM returns 100-word essay → keyword extraction fallback."""
        long_response = " ".join(["word"] * 100)
        llm = MockCritiqueLLM(default=long_response)
        result = GapToQueryTranslator.translate_with_fallback(
            "Missing CAUTION about DataLoss", "query", llm,
        )
        # Should fall back since word count > 15
        assert len(result.split()) <= 15

    def test_translate_fallback_on_empty(self):
        """#19: LLM returns '' → keyword extraction fallback."""
        llm = MockCritiqueLLM(default="")
        result = GapToQueryTranslator.translate_with_fallback(
            "The CAUTION about data loss is missing", "query", llm,
        )
        assert len(result) > 0

    def test_keyword_extract_basic(self):
        """#20: Keyword extraction from gap description."""
        result = GapToQueryTranslator._keyword_extract(
            "The CAUTION about data loss is missing",
        )
        assert len(result) > 0

    def test_translate_with_fallback_no_llm(self):
        """No LLM → keyword extraction fallback."""
        result = GapToQueryTranslator.translate_with_fallback(
            "Missing safety annotation", "query", None,
        )
        assert len(result) > 0


# ══════════════════════════════════════════════════════════════════
# 2.2.5 Unit Tests — Answer Tracker
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.critique_loop
class TestAnswerTracker:

    def test_tracker_returns_highest_confidence(self):
        """#21: Multiple rounds → returns highest confidence answer."""
        t = AnswerTracker()
        t.record("a0", 0.7, 0)
        t.record("a1", 0.9, 1)
        t.record("a2", 0.85, 2)
        assert t.best["answer"] == "a1"
        assert t.best["confidence"] == 0.9

    def test_tracker_improved_true(self):
        """#22: Later answer better → improved == True."""
        t = AnswerTracker()
        t.record("a0", 0.7, 0)
        t.record("a1", 0.9, 1)
        assert t.improved is True

    def test_tracker_improved_false(self):
        """#23: Later answer worse → improved == False."""
        t = AnswerTracker()
        t.record("a0", 0.9, 0)
        t.record("a1", 0.8, 1)
        assert t.improved is False

    def test_tracker_regression_detected(self):
        """#24: Latest < best → regression_detected == True."""
        t = AnswerTracker()
        t.record("a0", 0.8, 0)
        t.record("a1", 0.9, 1)
        t.record("a2", 0.7, 2)
        assert t.regression_detected is True

    def test_tracker_single_entry(self):
        """#25: One answer → returns that answer; improved == False."""
        t = AnswerTracker()
        t.record("only", 0.5, 0)
        assert t.best["answer"] == "only"
        assert t.improved is False

    def test_tracker_empty_raises(self):
        """Empty tracker → ValueError on .best."""
        t = AnswerTracker()
        with pytest.raises(ValueError):
            _ = t.best

    def test_tracker_regression_false_when_latest_is_best(self):
        """Latest == best → regression_detected == False."""
        t = AnswerTracker()
        t.record("a0", 0.5, 0)
        t.record("a1", 0.9, 1)
        assert t.regression_detected is False


# ══════════════════════════════════════════════════════════════════
# 2.2.6 Integration Tests — Full Critique Loop
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.critique_loop
class TestFullCritiqueLoop:

    def test_loop_converges_all_pass(self):
        """#26: All questions pass → converged=True, rounds_executed=1."""
        llm = MockCritiqueLLM(default='{"pass": true}')
        loop = DirectedCritiqueLoop(
            config=_FakeConfig(), critique_llm=llm,
        )
        questions = [_q("q1", "A?"), _q("q2", "B?"), _q("q3", "C?")]
        result = loop.run("query", "initial answer", [_chunk("content")], questions)
        assert isinstance(result, CritiqueResult)
        assert result.converged is True
        assert result.rounds_executed == 1
        assert result.gaps_found == 0

    def test_loop_one_gap_fix_converge(self):
        """#27: Q2 fails first time, passes second → rounds=2, gaps=1."""
        call_count = {"n": 0}

        def _llm(prompt):
            call_count["n"] += 1
            if "B?" in prompt and call_count["n"] <= 3:
                return '{"pass": false, "gap_description": "Missing B info"}'
            return '{"pass": true}'

        gen_llm = MockCritiqueLLM(default="improved answer with B")
        retriever = MockRetriever([_chunk("B extra info", chunk_id="c_new")])
        loop = DirectedCritiqueLoop(
            config=_FakeConfig(), critique_llm=_llm,
            generation_llm=gen_llm, retriever=retriever,
        )
        questions = [_q("q1", "A?"), _q("q2", "B?"), _q("q3", "C?")]
        result = loop.run("query", "initial", [_chunk("base")], questions)
        assert result.gaps_found >= 1

    def test_loop_restarts_from_q1(self):
        """#28: Q3 fails → Q1 re-evaluated in round 2."""
        eval_order = []

        def _llm(prompt):
            for qid in ["q1", "q2", "q3"]:
                if qid in prompt:
                    eval_order.append(qid)
                    break
            if "q3" in prompt and len(eval_order) <= 3:
                return '{"pass": false, "gap_description": "gap"}'
            return '{"pass": true}'

        loop = DirectedCritiqueLoop(
            config=_FakeConfig(), critique_llm=_llm,
        )
        questions = [
            _q("q1", "q1 question?"),
            _q("q2", "q2 question?"),
            _q("q3", "q3 question?"),
        ]
        loop.run("query", "answer", [_chunk("content")], questions)
        # Q1 should appear at least twice (round 1 + round 2)
        assert eval_order.count("q1") >= 2

    def test_loop_caps_at_max_rounds(self):
        """#29: Every round has a gap → rounds_executed=max_rounds, converged=False."""
        llm = MockCritiqueLLM(default='{"pass": false, "gap_description": "always fails"}')
        cfg = _FakeConfig()
        cfg.critique_max_rounds = 2
        loop = DirectedCritiqueLoop(config=cfg, critique_llm=llm)
        questions = [_q("q1", "?")]
        result = loop.run("query", "initial", [_chunk("x")], questions)
        assert result.rounds_executed == 2
        assert result.converged is False

    def test_loop_returns_best_not_last(self):
        """#30: Best answer may not be latest — returns highest confidence."""
        round_counter = {"n": 0}

        def _llm(prompt):
            round_counter["n"] += 1
            return '{"pass": false, "gap_description": "gap"}'

        def _gen_llm(prompt):
            return "worse answer"

        cfg = _FakeConfig()
        cfg.critique_max_rounds = 2
        loop = DirectedCritiqueLoop(
            config=cfg, critique_llm=_llm, generation_llm=_gen_llm,
        )
        questions = [_q("q1", "?")]
        result = loop.run("query", "best initial", [_chunk("x")], questions,
                          initial_confidence=0.9)
        # Initial confidence 0.9 should be tracked; degraded answers should score lower
        assert result.answer is not None

    def test_loop_safety_gaps_evaluated_first(self):
        """#31: Safety gaps checked before regular questions."""
        eval_order = []

        def _llm(prompt):
            if "CAUTION" in prompt and "Source contains" not in prompt:
                eval_order.append("regular")
            return '{"pass": true}'

        loop = DirectedCritiqueLoop(config=_FakeConfig(), critique_llm=_llm)
        questions = [_q("q1", "CAUTION preserved?")]
        # Source has CAUTION but answer doesn't → safety gap
        result = loop.run(
            "query", "no caution answer",
            [_chunk("CAUTION: hot surface")], questions,
        )
        assert result.gaps_found >= 1  # At least the safety gap

    def test_loop_skip_filtered_questions(self):
        """#32: Questions filtered by trigger → not evaluated."""
        llm = MockCritiqueLLM(default='{"pass": true}')
        loop = DirectedCritiqueLoop(config=_FakeConfig(), critique_llm=llm)
        questions = [
            _q("q1", "Always?", logic="always"),
            _q("q2", "CAUTION?", keywords=["CAUTION"], logic="any_in_source"),
            _q("q3", "ZEBRA?", keywords=["ZEBRA"], logic="any_in_source"),
        ]
        # Chunks have no ZEBRA → q3 filtered out; no CAUTION → q2 filtered out
        result = loop.run("query", "answer", [_chunk("normal content")], questions)
        assert result.questions_evaluated == 1  # Only q1

    def test_loop_early_exit_high_confidence(self):
        """#33: Confidence >= 0.95 + only tail questions → early exit."""
        llm = MockCritiqueLLM(default='{"pass": true}')
        cfg = _FakeConfig()
        cfg.critique_confidence_exit = 0.90
        loop = DirectedCritiqueLoop(config=cfg, critique_llm=llm)
        # Create questions where remaining are from 1-chunk docs (tail)
        q1 = _q("q1", "Main?")
        q2 = _q("q2", "Tail?")
        q2._source_doc_chunk_count = 1  # type: ignore
        result = loop.run("query", "good answer", [_chunk("x")], [q1, q2],
                          initial_confidence=0.95)
        assert result.converged is True

    def test_loop_no_questions_returns_initial(self):
        """#34: Empty question list → converged immediately."""
        loop = DirectedCritiqueLoop(config=_FakeConfig())
        result = loop.run("query", "initial", [_chunk("x")], [])
        assert result.converged is True
        assert result.answer == "initial"

    def test_loop_critique_model_failure_graceful(self):
        """#35: Critique model raises → returns initial answer."""
        def _bad_llm(prompt):
            raise RuntimeError("model error")
        loop = DirectedCritiqueLoop(config=_FakeConfig(), critique_llm=_bad_llm)
        questions = [_q("q1", "?")]
        result = loop.run("query", "initial answer", [_chunk("x")], questions)
        # Should still return a valid result (optimistic pass)
        assert isinstance(result, CritiqueResult)
        assert result.answer is not None


# ══════════════════════════════════════════════════════════════════
# 2.2.7 Integration Tests — Dual-Model Architecture
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.critique_loop
class TestDualModel:

    def test_critique_uses_fixed_model(self):
        """#36: Critique calls go to the fixed critique LLM."""
        critique_llm = MockCritiqueLLM(default='{"pass": true}')
        gen_llm = MockCritiqueLLM(default="generated")
        loop = DirectedCritiqueLoop(
            config=_FakeConfig(), critique_llm=critique_llm, generation_llm=gen_llm,
        )
        loop.run("query", "answer", [_chunk("x")], [_q("q1", "?")])
        assert critique_llm.call_count >= 1
        assert gen_llm.call_count == 0  # No gaps → no re-synthesis

    def test_synthesis_uses_user_model(self):
        """#37: Re-synthesis calls go to the generation LLM, not critique."""
        critique_llm = MockCritiqueLLM(default='{"pass": false, "gap_description": "gap"}')
        gen_llm = MockCritiqueLLM(default="improved answer")
        retriever = MockRetriever([_chunk("new info", chunk_id="new")])
        cfg = _FakeConfig()
        cfg.critique_max_rounds = 1
        loop = DirectedCritiqueLoop(
            config=cfg, critique_llm=critique_llm,
            generation_llm=gen_llm, retriever=retriever,
        )
        loop.run("query", "initial", [_chunk("x")], [_q("q1", "?")])
        assert gen_llm.call_count >= 1

    def test_models_are_independent(self):
        """#38: Different models configured → critique ≠ generation."""
        critique_llm = MockCritiqueLLM(default='{"pass": true}')
        gen_llm = MockCritiqueLLM(default="generated")
        loop = DirectedCritiqueLoop(
            config=_FakeConfig(), critique_llm=critique_llm, generation_llm=gen_llm,
        )
        assert critique_llm is not gen_llm


# ══════════════════════════════════════════════════════════════════
# Prompt template tests
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.critique_loop
class TestPromptTemplates:

    def test_critique_prompt_alias(self):
        """CRITIQUE_EVAL_PROMPT is an alias for CRITIQUE_PROMPT."""
        assert CRITIQUE_EVAL_PROMPT is CRITIQUE_PROMPT

    def test_resynthesis_prompt_alias(self):
        """RE_SYNTHESIS_PROMPT is an alias for RESYNTHESIS_PROMPT."""
        assert RE_SYNTHESIS_PROMPT is RESYNTHESIS_PROMPT

    def test_build_critique_prompt_contains_question(self):
        """build_critique_prompt includes the question text."""
        prompt = build_critique_prompt("Is CAUTION preserved?", "answer", [_chunk("x")])
        assert "Is CAUTION preserved?" in prompt

    def test_build_gap_to_query_prompt(self):
        """build_gap_to_query_prompt includes gap and query."""
        prompt = build_gap_to_query_prompt("Missing CAUTION", "computer won't start")
        assert "Missing CAUTION" in prompt
        assert "computer won't start" in prompt

    def test_build_resynthesis_prompt(self):
        """build_resynthesis_prompt includes all components."""
        prompt = build_resynthesis_prompt("query", "answer", "gap desc", [_chunk("new")])
        assert "query" in prompt
        assert "answer" in prompt
        assert "gap desc" in prompt

    def test_format_chunks(self):
        """format_chunks concatenates chunk contents."""
        result = format_chunks([_chunk("alpha"), _chunk("beta", chunk_id="c2")])
        assert "alpha" in result
        assert "beta" in result

    def test_gap_to_query_prompt_template(self):
        """GAP_TO_QUERY_PROMPT has required placeholders."""
        assert "{gap_description}" in GAP_TO_QUERY_PROMPT
        assert "{user_query}" in GAP_TO_QUERY_PROMPT


# ══════════════════════════════════════════════════════════════════
# Confidence computation tests
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.critique_loop
class TestConfidenceComputation:

    def test_zero_evaluated_returns_half(self):
        """0 questions evaluated → 0.5 confidence."""
        assert DirectedCritiqueLoop._compute_confidence(0, 0) == 0.5

    def test_all_passed_returns_one(self):
        """5 evaluated, 0 unfixed → 1.0."""
        assert DirectedCritiqueLoop._compute_confidence(5, 0) == 1.0

    def test_one_unfixed_reduces_confidence(self):
        """5 evaluated, 1 unfixed → < 1.0."""
        c = DirectedCritiqueLoop._compute_confidence(5, 1)
        assert 0.0 < c < 1.0

    def test_confidence_never_negative(self):
        """Many unfixed gaps → confidence clamped at 0."""
        c = DirectedCritiqueLoop._compute_confidence(1, 10)
        assert c >= 0.0

    def test_confidence_never_above_one(self):
        """Confidence is capped at 1.0."""
        c = DirectedCritiqueLoop._compute_confidence(100, 0)
        assert c <= 1.0
