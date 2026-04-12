"""Phase 9.3 — Multi-Doc Provenance-Filtered Merging Tests.

Covers: merge_critique_questions, should_early_exit, provenance filtering,
ordering, deduplication, multi-doc full loop integration.
~19 tests per testing plan.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.common.models import (
    CritiqueQuestion,
    CritiqueResult,
    DocCritique,
    SectionCritique,
)
from backend.retrieval.critique_merger import (
    merge_critique_questions,
    should_early_exit,
)
from backend.retrieval.critique_loop import DirectedCritiqueLoop

# ── Helpers ───────────────────────────────────────────────────────

def _q(qid: str, question: str, keywords: list[str] | None = None,
       logic: str = "always", priority: int = 1) -> CritiqueQuestion:
    return CritiqueQuestion(
        id=qid, question=question,
        trigger_keywords=keywords or [], trigger_logic=logic,
        priority=priority,
    )


def _chunk(content: str, doc_id: str, section_id: str = "sec000",
           chunk_id: str | None = None) -> dict:
    cid = chunk_id or f"{doc_id}_{section_id}_c"
    return {
        "id": cid, "content": content, "doc_id": doc_id,
        "section_id": section_id,
        "metadata": {"doc_id": doc_id, "section_id": section_id},
    }


def _make_critique(
    doc_id: str,
    doc_type: str = "TROUBLESHOOT",
    doc_qs: list[CritiqueQuestion] | None = None,
    sections: list[SectionCritique] | None = None,
) -> DocCritique:
    return DocCritique(
        doc_id=doc_id,
        doc_type=doc_type,
        generated_at="2026-01-01T00:00:00Z",
        generator_model="gpt-4.1",
        doc_level_questions=doc_qs or [_q(f"{doc_id}_dq1", f"Doc-level for {doc_id}?")],
        section_questions=sections or [],
    )


class _FakeConfig:
    critique_max_rounds = 3
    critique_restart_on_gap = True
    critique_confidence_exit = 0.90


class MockLLM:
    def __init__(self, default='{"pass": true}'):
        self.default = default
        self.call_log = []
    def __call__(self, prompt):
        self.call_log.append(prompt)
        return self.default


# ══════════════════════════════════════════════════════════════════
# 2.3.1 Unit Tests — Provenance Filtering
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.multi_doc
class TestProvenanceFiltering:

    def test_single_doc_single_section(self):
        """#1: 3 chunks from doc_A/sec001 → only sec001 questions active."""
        chunks = [
            _chunk("c1", "docA", "sec001", "c1"),
            _chunk("c2", "docA", "sec001", "c2"),
            _chunk("c3", "docA", "sec001", "c3"),
        ]
        store = {
            "docA": _make_critique("docA", sections=[
                SectionCritique("sec001", "S1", [_q("sq1", "sec001 q?")]),
                SectionCritique("sec002", "S2", [_q("sq2", "sec002 q?")]),
            ]),
        }
        result = merge_critique_questions(chunks, store)
        texts = [q.question for q in result]
        assert "sec001 q?" in texts
        assert "sec002 q?" not in texts

    def test_single_doc_multi_section(self):
        """#2: Chunks from sec001 + sec003 → sec001 + sec003; sec002 excluded."""
        chunks = [
            _chunk("c1", "docA", "sec001", "c1"),
            _chunk("c2", "docA", "sec003", "c2"),
        ]
        store = {
            "docA": _make_critique("docA", sections=[
                SectionCritique("sec001", "S1", [_q("sq1", "sec001?")]),
                SectionCritique("sec002", "S2", [_q("sq2", "sec002?")]),
                SectionCritique("sec003", "S3", [_q("sq3", "sec003?")]),
            ]),
        }
        result = merge_critique_questions(chunks, store)
        texts = [q.question for q in result]
        assert "sec001?" in texts
        assert "sec003?" in texts
        assert "sec002?" not in texts

    def test_multi_doc_provenance_filter(self):
        """#3: Chunks from docA/sec001 + docB/sec002 → only those sections."""
        chunks = [
            _chunk("c1", "docA", "sec001", "c1"),
            _chunk("c2", "docB", "sec002", "c2"),
        ]
        store = {
            "docA": _make_critique("docA", sections=[
                SectionCritique("sec001", "S1", [_q("sqA1", "docA sec001?")]),
                SectionCritique("sec003", "S3", [_q("sqA3", "docA sec003?")]),
            ]),
            "docB": _make_critique("docB", sections=[
                SectionCritique("sec002", "S2", [_q("sqB2", "docB sec002?")]),
            ]),
        }
        result = merge_critique_questions(chunks, store)
        texts = [q.question for q in result]
        assert "docA sec001?" in texts
        assert "docB sec002?" in texts
        assert "docA sec003?" not in texts

    def test_doc_level_always_included(self):
        """#4: Doc-level questions from both docs are always included."""
        chunks = [
            _chunk("c1", "docA", "sec001", "c1"),
            _chunk("c2", "docB", "sec001", "c2"),
        ]
        store = {
            "docA": _make_critique("docA", doc_qs=[_q("dqA", "Doc A level?")]),
            "docB": _make_critique("docB", doc_qs=[_q("dqB", "Doc B level?")]),
        }
        result = merge_critique_questions(chunks, store)
        texts = [q.question for q in result]
        assert "Doc A level?" in texts
        assert "Doc B level?" in texts

    def test_unretrieved_sections_excluded(self):
        """#5: Doc A has 4 sections, only sec001 retrieved → others excluded."""
        chunks = [_chunk("c1", "docA", "sec001", "c1")]
        store = {
            "docA": _make_critique("docA", sections=[
                SectionCritique(f"sec{i:03d}", f"S{i}", [_q(f"sq{i}", f"sec{i:03d}?")])
                for i in range(4)
            ]),
        }
        result = merge_critique_questions(chunks, store)
        sec_texts = [q.question for q in result if q.question.startswith("sec")]
        assert "sec001?" in sec_texts
        assert "sec002?" not in sec_texts
        assert "sec003?" not in sec_texts

    def test_no_critique_store_for_doc(self):
        """#6: doc_C has no critique store → no questions from it."""
        chunks = [
            _chunk("c1", "docA", "sec001", "c1"),
            _chunk("c2", "docC", "sec001", "c2"),
        ]
        store = {
            "docA": _make_critique("docA", doc_qs=[_q("dqA", "Doc A?")]),
        }
        result = merge_critique_questions(chunks, store)
        texts = [q.question for q in result]
        assert "Doc A?" in texts
        # docC has no store so no questions from it
        assert not any("docC" in t for t in texts)


# ══════════════════════════════════════════════════════════════════
# 2.3.2 Unit Tests — Ordering
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.multi_doc
class TestOrdering:

    def test_doc_level_before_section(self):
        """#7: Doc-level questions appear before section-level."""
        chunks = [_chunk("c1", "docA", "sec001", "c1")]
        store = {
            "docA": _make_critique("docA",
                                   doc_qs=[_q("dq1", "Doc level?")],
                                   sections=[
                                       SectionCritique("sec001", "S1", [_q("sq1", "Section level?")])
                                   ]),
        }
        result = merge_critique_questions(chunks, store)
        texts = [q.question for q in result]
        doc_idx = texts.index("Doc level?")
        sec_idx = texts.index("Section level?")
        assert doc_idx < sec_idx

    def test_high_chunk_doc_first(self):
        """#8: Doc A (5 chunks) section questions appear before Doc B (1 chunk)."""
        chunks = [
            *[_chunk(f"cA{i}", "docA", "sec001", f"cA{i}") for i in range(5)],
            _chunk("cB0", "docB", "sec001", "cB0"),
        ]
        store = {
            "docA": _make_critique("docA", doc_qs=[],
                                   sections=[SectionCritique("sec001", "S1", [_q("sqA", "docA section?")])]),
            "docB": _make_critique("docB", doc_qs=[],
                                   sections=[SectionCritique("sec001", "S1", [_q("sqB", "docB section?")])]),
        }
        result = merge_critique_questions(chunks, store)
        texts = [q.question for q in result]
        if "docA section?" in texts and "docB section?" in texts:
            assert texts.index("docA section?") < texts.index("docB section?")

    def test_within_group_priority_order(self):
        """#9: Within section questions, sorted by priority."""
        chunks = [_chunk("c1", "docA", "sec001", "c1")]
        store = {
            "docA": _make_critique("docA", doc_qs=[], sections=[
                SectionCritique("sec001", "S1", [
                    _q("sq3", "Priority 3?", priority=3),
                    _q("sq1", "Priority 1?", priority=1),
                    _q("sq2", "Priority 2?", priority=2),
                ]),
            ]),
        }
        result = merge_critique_questions(chunks, store)
        priorities = [q.priority for q in result]
        assert priorities == sorted(priorities)

    def test_equal_chunk_count_stable_order(self):
        """#10: Two docs with equal chunks → stable order (no random shuffling)."""
        chunks = [
            _chunk("cA", "docA", "sec001", "cA"),
            _chunk("cB", "docB", "sec001", "cB"),
        ]
        store = {
            "docA": _make_critique("docA", doc_qs=[_q("dqA", "A?")]),
            "docB": _make_critique("docB", doc_qs=[_q("dqB", "B?")]),
        }
        result1 = [q.question for q in merge_critique_questions(chunks, store)]
        result2 = [q.question for q in merge_critique_questions(chunks, store)]
        assert result1 == result2


# ══════════════════════════════════════════════════════════════════
# 2.3.3 Unit Tests — Deduplication
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.multi_doc
class TestDeduplication:

    def test_duplicate_questions_deduped(self):
        """#11: Same question text from two docs → kept once."""
        chunks = [
            _chunk("c1", "docA", "sec001", "c1"),
            _chunk("c2", "docB", "sec001", "c2"),
        ]
        store = {
            "docA": _make_critique("docA", doc_qs=[_q("dqA", "Same question?")]),
            "docB": _make_critique("docB", doc_qs=[_q("dqB", "Same question?")]),
        }
        result = merge_critique_questions(chunks, store)
        texts = [q.question for q in result]
        assert texts.count("Same question?") == 1

    def test_similar_not_deduped(self):
        """#12: Slightly different wording → both kept."""
        chunks = [
            _chunk("c1", "docA", "sec001", "c1"),
            _chunk("c2", "docB", "sec001", "c2"),
        ]
        store = {
            "docA": _make_critique("docA", doc_qs=[_q("dqA", "Is CAUTION preserved?")]),
            "docB": _make_critique("docB", doc_qs=[_q("dqB", "Are CAUTION annotations present?")]),
        }
        result = merge_critique_questions(chunks, store)
        texts = [q.question for q in result]
        assert "Is CAUTION preserved?" in texts
        assert "Are CAUTION annotations present?" in texts


# ══════════════════════════════════════════════════════════════════
# 2.3.4 Unit Tests — Confidence-Based Early Exit
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.multi_doc
class TestEarlyExit:

    def test_early_exit_high_confidence_tail(self):
        """#13: Confidence 0.95, remaining from 1-chunk doc → True."""
        q = _q("q1", "Tail?")
        q._source_doc_chunk_count = 1  # type: ignore
        assert should_early_exit(0.95, [q]) is True

    def test_no_exit_low_confidence(self):
        """#14: Confidence 0.70, remaining from 1-chunk doc → False."""
        q = _q("q1", "?")
        q._source_doc_chunk_count = 1  # type: ignore
        assert should_early_exit(0.70, [q]) is False

    def test_no_exit_high_confidence_important(self):
        """#15: Confidence 0.95, remaining from 5-chunk doc → False."""
        q = _q("q1", "?")
        q._source_doc_chunk_count = 5  # type: ignore
        assert should_early_exit(0.95, [q]) is False

    def test_early_exit_empty_remaining(self):
        """Empty remaining list → True (nothing left to check)."""
        assert should_early_exit(0.99, []) is True

    def test_early_exit_custom_threshold(self):
        """Custom threshold: 0.80 → exits at 0.85."""
        q = _q("q1", "?")
        q._source_doc_chunk_count = 1  # type: ignore
        assert should_early_exit(0.85, [q], threshold=0.80) is True


# ══════════════════════════════════════════════════════════════════
# 2.3.5 Integration Tests — Multi-Doc Full Loop
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.multi_doc
class TestMultiDocLoop:

    def test_multi_doc_loop_evaluates_both(self):
        """#16: Critique questions from both docs evaluated."""
        chunks = [
            _chunk("HP guide content", "docHP", "sec001", "c1"),
            _chunk("PSA content", "docPSA", "sec001", "c2"),
        ]
        store = {
            "docHP": _make_critique("docHP", doc_qs=[_q("dqHP", "CAUTION preserved?")]),
            "docPSA": _make_critique("docPSA", doc_qs=[_q("dqPSA", "Terms defined?")]),
        }
        merged = merge_critique_questions(chunks, store)
        assert len(merged) >= 2

        llm = MockLLM('{"pass": true}')
        loop = DirectedCritiqueLoop(
            config=_FakeConfig(), critique_llm=llm,
        )
        result = loop.run("query", "answer", chunks, merged)
        assert result.questions_evaluated >= 2

    def test_multi_doc_gap_in_secondary_doc(self):
        """#17: Primary passes, secondary has gap → gap detected."""
        chunks = [
            _chunk("HP content", "docHP", "sec001", "c1"),
            _chunk("PSA content", "docPSA", "sec001", "c2"),
        ]
        store = {
            "docHP": _make_critique("docHP", doc_qs=[_q("dqHP", "HP check?")]),
            "docPSA": _make_critique("docPSA", doc_qs=[_q("dqPSA", "PSA check?")]),
        }
        merged = merge_critique_questions(chunks, store)

        def _llm(prompt):
            if "PSA check?" in prompt:
                return '{"pass": false, "gap_description": "Missing PSA terms"}'
            return '{"pass": true}'

        loop = DirectedCritiqueLoop(config=_FakeConfig(), critique_llm=_llm)
        result = loop.run("query", "answer", chunks, merged)
        assert result.gaps_found >= 1

    def test_multi_doc_early_exit_on_tail(self):
        """#18: Primary done, secondary is 1-chunk → early exit possible."""
        chunks = [
            *[_chunk(f"c{i}", "docPrimary", "sec001", f"p{i}") for i in range(5)],
            _chunk("c0", "docSecondary", "sec001", "s0"),
        ]
        store = {
            "docPrimary": _make_critique("docPrimary", doc_qs=[_q("dqP", "Primary?")]),
            "docSecondary": _make_critique("docSecondary", doc_qs=[_q("dqS", "Secondary?")]),
        }
        merged = merge_critique_questions(chunks, store)
        # Tag secondary question as tail
        for q in merged:
            if q.id == "dqS":
                q._source_doc_chunk_count = 1  # type: ignore

        llm = MockLLM('{"pass": true}')
        cfg = _FakeConfig()
        cfg.critique_confidence_exit = 0.90
        loop = DirectedCritiqueLoop(config=cfg, critique_llm=llm)
        result = loop.run("query", "good answer", chunks, merged, initial_confidence=0.95)
        assert result.converged is True

    def test_merge_with_empty_chunks(self):
        """Edge case: empty chunks → empty question list."""
        result = merge_critique_questions([], {})
        assert result == []

    def test_merge_with_empty_store(self):
        """Chunks present but no critique stores → empty question list."""
        chunks = [_chunk("c1", "docA", "sec001", "c1")]
        result = merge_critique_questions(chunks, {})
        assert result == []
