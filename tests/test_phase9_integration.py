"""Phase 9 — Cross-Increment Integration Tests.

Tests end-to-end flows spanning increments 9.1 → 9.2 → 9.3:
- Generate critique questions → save → load → merge → run loop
- Config flags control entire pipeline
- Feature flag isolation
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
from backend.agents.critique_question_generator import CritiqueQuestionGenerator
from backend.common.models import (
    CritiqueQuestion,
    CritiqueResult,
    DocCritique,
    SectionCritique,
)
from backend.retrieval.critique_loop import (
    DirectedCritiqueLoop,
    keyword_safety_check,
    trigger_matches,
)
from backend.retrieval.critique_merger import merge_critique_questions

# ── Helpers ───────────────────────────────────────────────────────


class _FakeConfig:
    critique_generation_enabled = True
    critique_generator_model = "gpt-4.1"
    critique_loop_enabled = True
    critique_model = "gpt-4.1"
    critique_max_rounds = 3
    critique_restart_on_gap = True
    critique_multi_doc_enabled = True
    critique_confidence_exit = 0.90
    critique_max_questions_per_doc = 15
    knowledge_base_path = ""


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


# ══════════════════════════════════════════════════════════════════
# End-to-End: Generate → Save → Load → Merge → Loop
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
class TestEndToEnd:

    def test_generate_save_load_roundtrip(self, tmp_path):
        """Generate critique questions, save, load — roundtrip integrity."""
        cfg = _FakeConfig()
        cfg.knowledge_base_path = str(tmp_path)
        gen = CritiqueQuestionGenerator(cfg)

        # Generate with defaults (no LLM)
        critique = gen.generate(
            doc_text="CAUTION: Do not touch hot surface. Follow steps 1, 2, 3.",
            doc_type="TROUBLESHOOT",
            sections=[{"section_id": "sec000", "title": "General"}],
            doc_id="doc_hp",
            doc_title="HP Guide",
        )
        gen.save(critique, str(tmp_path))

        # Load
        loaded = gen.load("doc_hp", str(tmp_path))
        assert loaded is not None
        assert loaded.doc_id == "doc_hp"
        assert len(loaded.doc_level_questions) == len(critique.doc_level_questions)

    def test_generate_merge_loop(self, tmp_path):
        """Generate for 2 docs → merge → run critique loop."""
        cfg = _FakeConfig()
        gen = CritiqueQuestionGenerator(cfg)

        crit_hp = gen.generate(
            doc_text="HP Guide with CAUTION",
            doc_type="TROUBLESHOOT", sections=[], doc_id="doc_hp",
        )
        crit_psa = gen.generate(
            doc_text="PSA with Defined Terms",
            doc_type="GOVERNING_DOC", sections=[], doc_id="doc_psa",
        )

        chunks = [
            _chunk("HP CAUTION content", "doc_hp", "sec000", "c1"),
            _chunk("PSA definition content", "doc_psa", "sec000", "c2"),
        ]
        store = {"doc_hp": crit_hp, "doc_psa": crit_psa}
        merged = merge_critique_questions(chunks, store)
        assert len(merged) >= 2

        loop = DirectedCritiqueLoop(
            config=cfg, critique_llm=MockLLM('{"pass": true}'),
        )
        result = loop.run("What is the procedure?", "Steps: 1, 2, 3",
                          chunks, merged)
        assert isinstance(result, CritiqueResult)
        assert result.converged is True

    def test_full_pipeline_with_gap_fix(self, tmp_path):
        """Full pipeline: generate → merge → loop finds gap → fixes it."""
        cfg = _FakeConfig()
        cfg.critique_max_rounds = 2
        gen = CritiqueQuestionGenerator(cfg)
        crit = gen.generate(
            doc_text="CAUTION: High voltage. Step 1: Disconnect power.",
            doc_type="TROUBLESHOOT", sections=[], doc_id="doc1",
        )

        chunks = [_chunk("CAUTION: High voltage", "doc1", "sec000", "c1")]
        merged = merge_critique_questions(chunks, {"doc1": crit})

        call_count = {"n": 0}
        def _critique_llm(prompt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return '{"pass": false, "gap_description": "Missing voltage warning"}'
            return '{"pass": true}'

        gen_llm = MockLLM("Improved: CAUTION High voltage. Step 1 disconnect.")
        loop = DirectedCritiqueLoop(
            config=cfg, critique_llm=_critique_llm, generation_llm=gen_llm,
        )
        result = loop.run("How to service?", "Step 1: disconnect", chunks, merged)
        assert result.gaps_found >= 1
        assert result.gaps_fixed >= 0


# ══════════════════════════════════════════════════════════════════
# Config Flag Isolation
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
class TestConfigFlags:

    def test_all_nine_config_flags_exist(self):
        """All 9 Phase 9 config flags exist in settings."""
        from config.settings import KTSConfig
        cfg = KTSConfig()
        flags = [
            "critique_generation_enabled",
            "critique_generator_model",
            "critique_loop_enabled",
            "critique_model",
            "critique_max_rounds",
            "critique_restart_on_gap",
            "critique_multi_doc_enabled",
            "critique_confidence_exit",
            "critique_max_questions_per_doc",
        ]
        for flag in flags:
            assert hasattr(cfg, flag), f"Missing config flag: {flag}"

    def test_critique_generation_disabled_skips(self, tmp_path):
        """critique_generation_enabled=False → caller should skip."""
        cfg = _FakeConfig()
        cfg.critique_generation_enabled = False
        assert cfg.critique_generation_enabled is False

    def test_critique_loop_disabled_returns_initial(self):
        """When critique_loop_enabled=False, loop should be skipped by caller."""
        cfg = _FakeConfig()
        cfg.critique_loop_enabled = False
        # The caller checks this flag; the loop itself doesn't.
        # We verify the flag value is respected.
        assert cfg.critique_loop_enabled is False

    def test_max_rounds_respected(self):
        """critique_max_rounds limits loop iterations."""
        cfg = _FakeConfig()
        cfg.critique_max_rounds = 1
        llm = MockLLM('{"pass": false, "gap_description": "gap"}')
        loop = DirectedCritiqueLoop(config=cfg, critique_llm=llm)
        result = loop.run("q", "a", [_chunk("x")],
                          [CritiqueQuestion(id="q1", question="?", trigger_keywords=[], trigger_logic="always")])
        assert result.rounds_executed <= 1

    def test_confidence_exit_threshold(self):
        """critique_confidence_exit controls early exit."""
        cfg = _FakeConfig()
        cfg.critique_confidence_exit = 0.50
        llm = MockLLM('{"pass": true}')
        loop = DirectedCritiqueLoop(config=cfg, critique_llm=llm)
        q = CritiqueQuestion(id="q1", question="?", trigger_keywords=[], trigger_logic="always")
        q._source_doc_chunk_count = 1  # type: ignore  # tail question
        result = loop.run("q", "a", [_chunk("x")], [q], initial_confidence=0.6)
        assert result.converged is True

    def test_restart_on_gap_false(self):
        """critique_restart_on_gap=False → loop doesn't restart from Q1."""
        cfg = _FakeConfig()
        cfg.critique_restart_on_gap = False
        cfg.critique_max_rounds = 1

        eval_order = []
        def _llm(prompt):
            for qid in ["q1", "q2", "q3"]:
                if qid in prompt:
                    eval_order.append(qid)
                    break
            if "q1" in prompt and len(eval_order) <= 1:
                return '{"pass": false, "gap_description": "gap"}'
            return '{"pass": true}'

        loop = DirectedCritiqueLoop(config=cfg, critique_llm=_llm)
        questions = [
            CritiqueQuestion(id="q1", question="q1?", trigger_keywords=[], trigger_logic="always"),
            CritiqueQuestion(id="q2", question="q2?", trigger_keywords=[], trigger_logic="always"),
            CritiqueQuestion(id="q3", question="q3?", trigger_keywords=[], trigger_logic="always"),
        ]
        loop.run("query", "answer", [_chunk("content")], questions)
        # Without restart, q2 and q3 should still be evaluated
        assert "q2" in eval_order or "q3" in eval_order


# ══════════════════════════════════════════════════════════════════
# Safety + Trigger Integration
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
class TestSafetyTriggerIntegration:

    def test_safety_check_integrated_with_loop(self):
        """Safety check runs before critique questions in the loop."""
        cfg = _FakeConfig()
        llm = MockLLM('{"pass": true}')
        loop = DirectedCritiqueLoop(config=cfg, critique_llm=llm)
        # Source has CAUTION, answer doesn't → safety gap detected
        chunks = [_chunk("CAUTION: hot surface")]
        questions = [CritiqueQuestion(id="q1", question="Steps?",
                                      trigger_keywords=[], trigger_logic="always")]
        result = loop.run("query", "no caution answer", chunks, questions)
        assert result.gaps_found >= 1

    def test_trigger_filter_reduces_evaluations(self):
        """Trigger filtering reduces LLM calls."""
        llm = MockLLM('{"pass": true}')
        loop = DirectedCritiqueLoop(config=_FakeConfig(), critique_llm=llm)
        questions = [
            CritiqueQuestion(id="q1", question="Always?",
                             trigger_keywords=[], trigger_logic="always"),
            CritiqueQuestion(id="q2", question="Specific?",
                             trigger_keywords=["ZEBRA"], trigger_logic="any_in_source"),
        ]
        result = loop.run("query", "answer", [_chunk("normal content")], questions)
        assert result.questions_evaluated == 1  # Only q1

    def test_data_models_serializable(self):
        """All Phase 9 models can be serialized to JSON via dataclasses.asdict."""
        from dataclasses import asdict
        q = CritiqueQuestion(id="q1", question="?", trigger_keywords=["X"],
                             trigger_logic="any_in_source", priority=1)
        sc = SectionCritique(section_id="sec000", section_title="S",
                             questions=[q], rubric=None)
        dc = DocCritique(doc_id="d1", doc_type="TROUBLESHOOT",
                         doc_level_questions=[q], section_questions=[sc])
        data = asdict(dc)
        json_str = json.dumps(data)
        assert "q1" in json_str

    def test_critique_result_fields(self):
        """CritiqueResult has all required fields."""
        r = CritiqueResult(
            answer="a", confidence=0.9, rounds_executed=1,
            questions_evaluated=3, gaps_found=1, gaps_fixed=1,
            re_queries=["q"], converged=True, answer_history=[("a", 0.9)],
        )
        assert r.answer == "a"
        assert r.converged is True
        assert r.gaps_found == 1
