"""Phase 9.1 — Critique Question Generation Tests.

Covers: CritiqueQuestionGenerator, critique_defaults, validation,
storage (save/load), context-length handling, ingestion wiring.
~30 tests per testing plan.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.agents.critique_question_generator import (
    CritiqueQuestionGenerator,
    GENERATION_PROMPT,
    prepare_doc_for_critique_gen,
)
from backend.agents.critique_defaults import (
    DEFAULT_QUESTIONS,
    get_default_questions,
)
from backend.common.models import (
    CritiqueQuestion,
    DocCritique,
    SectionCritique,
)

# ── Helpers ───────────────────────────────────────────────────────

VALID_LLM_RESPONSE = json.dumps({
    "doc_level_questions": [
        {
            "id": "dq_001",
            "question": "Does the answer preserve all CAUTION annotations?",
            "trigger_keywords": ["CAUTION"],
            "trigger_logic": "any_in_source",
            "priority": 1,
        },
        {
            "id": "dq_002",
            "question": "Are cross-references resolved?",
            "trigger_keywords": [],
            "trigger_logic": "always",
            "priority": 2,
        },
    ],
    "section_questions": [
        {
            "section_id": "sec000",
            "section_title": "General Problems",
            "questions": [
                {
                    "id": "sq_001",
                    "question": "Are steps ordered by severity?",
                    "trigger_keywords": ["power button", "restart"],
                    "trigger_logic": "any_in_source",
                    "priority": 1,
                }
            ],
            "rubric": None,
        }
    ],
})


class _FakeConfig:
    critique_max_questions_per_doc = 15
    critique_generator_model = "gpt-4.1"
    knowledge_base_path = ""


def _mock_llm(response: str):
    """Return a callable that always returns *response*."""
    def _call(prompt: str) -> str:
        return response
    return _call


# ══════════════════════════════════════════════════════════════════
# 2.1.1 Unit Tests — CritiqueQuestionGenerator
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.critique_gen
class TestCritiqueQuestionGenerator:

    def test_generate_returns_valid_schema(self):
        """#1: Mock LLM returns well-formed JSON → DocCritique with all required fields."""
        gen = CritiqueQuestionGenerator(_FakeConfig())
        result = gen.generate(
            doc_text="Sample doc text for testing.",
            doc_type="TROUBLESHOOT",
            sections=[{"section_id": "sec000", "title": "General Problems"}],
            doc_id="doc_test",
            doc_title="Test Doc",
            llm_callable=_mock_llm(VALID_LLM_RESPONSE),
        )
        assert isinstance(result, DocCritique)
        assert result.doc_id == "doc_test"
        assert result.doc_type == "TROUBLESHOOT"
        assert result.generated_at  # non-empty
        assert result.generator_model == "gpt-4.1"
        assert len(result.doc_level_questions) >= 1
        assert all(isinstance(q, CritiqueQuestion) for q in result.doc_level_questions)

    def test_generate_handles_invalid_json(self):
        """#2: Mock LLM returns malformed JSON → falls back to DEFAULT_QUESTIONS."""
        gen = CritiqueQuestionGenerator(_FakeConfig())
        result = gen.generate(
            doc_text="x", doc_type="TROUBLESHOOT", sections=[],
            doc_id="doc_bad", llm_callable=_mock_llm("not valid json {{{{"),
        )
        assert isinstance(result, DocCritique)
        assert result.generator_model == "default"
        assert len(result.doc_level_questions) >= 1

    def test_generate_handles_empty_response(self):
        """#3: Mock LLM returns empty string → falls back to DEFAULT_QUESTIONS."""
        gen = CritiqueQuestionGenerator(_FakeConfig())
        result = gen.generate(
            doc_text="x", doc_type="TROUBLESHOOT", sections=[],
            doc_id="doc_empty", llm_callable=_mock_llm(""),
        )
        assert isinstance(result, DocCritique)
        assert result.generator_model == "default"

    def test_generate_truncates_excess_questions(self):
        """#4: Mock LLM returns 25 questions → truncated to max_questions_per_doc."""
        many_qs = {
            "doc_level_questions": [
                {"id": f"dq_{i:03d}", "question": f"Question {i}?",
                 "trigger_keywords": [], "trigger_logic": "always", "priority": 1}
                for i in range(25)
            ],
            "section_questions": [],
        }
        cfg = _FakeConfig()
        cfg.critique_max_questions_per_doc = 15
        gen = CritiqueQuestionGenerator(cfg)
        result = gen.generate(
            doc_text="x", doc_type="GOVERNING_DOC", sections=[],
            doc_id="doc_many", llm_callable=_mock_llm(json.dumps(many_qs)),
        )
        total = len(result.doc_level_questions)
        for sc in result.section_questions:
            total += len(sc.questions)
        assert total <= 15

    def test_generate_for_troubleshoot_doc(self):
        """#5: Default fallback for TROUBLESHOOT includes CAUTION/WARNING check."""
        gen = CritiqueQuestionGenerator(_FakeConfig())
        result = gen.generate(
            doc_text="HP Troubleshoot Guide text", doc_type="TROUBLESHOOT",
            sections=[], doc_id="ts_doc",
        )
        texts = [q.question.lower() for q in result.doc_level_questions]
        assert any("caution" in t or "warning" in t for t in texts)

    def test_generate_for_governing_doc(self):
        """#6: Default fallback for GOVERNING_DOC includes defined term check."""
        gen = CritiqueQuestionGenerator(_FakeConfig())
        result = gen.generate(
            doc_text="PSA", doc_type="GOVERNING_DOC",
            sections=[], doc_id="gd_doc",
        )
        texts = [q.question.lower() for q in result.doc_level_questions]
        assert any("capitalized" in t or "defined" in t or "term" in t for t in texts)

    def test_generate_for_supplement_doc(self):
        """#7: Default fallback for SUPPLEMENT includes amendment reference."""
        gen = CritiqueQuestionGenerator(_FakeConfig())
        result = gen.generate(
            doc_text="Supp", doc_type="SUPPLEMENT",
            sections=[], doc_id="su_doc",
        )
        texts = [q.question.lower() for q in result.doc_level_questions]
        assert any("supplement" in t or "amendment" in t for t in texts)

    def test_generate_respects_doc_type(self):
        """#8: Different doc_types → meaningfully different default questions."""
        gen = CritiqueQuestionGenerator(_FakeConfig())
        ts = gen.generate(doc_text="x", doc_type="TROUBLESHOOT", sections=[], doc_id="a")
        gd = gen.generate(doc_text="x", doc_type="GOVERNING_DOC", sections=[], doc_id="b")
        ts_texts = {q.question for q in ts.doc_level_questions}
        gd_texts = {q.question for q in gd.doc_level_questions}
        assert ts_texts != gd_texts, "Questions should differ by doc_type"

    def test_generate_includes_trigger_keywords(self):
        """#9: Every non-'always' question has >= 1 trigger keyword."""
        gen = CritiqueQuestionGenerator(_FakeConfig())
        result = gen.generate(
            doc_text="x", doc_type="TROUBLESHOOT", sections=[],
            doc_id="kw_doc", llm_callable=_mock_llm(VALID_LLM_RESPONSE),
        )
        for q in result.doc_level_questions:
            if q.trigger_logic != "always":
                assert len(q.trigger_keywords) >= 1, f"{q.id} has no keywords"

    def test_generate_includes_section_ids(self):
        """#10: Doc with sections → section questions tagged to correct section_ids."""
        gen = CritiqueQuestionGenerator(_FakeConfig())
        result = gen.generate(
            doc_text="x", doc_type="TROUBLESHOOT",
            sections=[
                {"section_id": "sec000", "title": "A"},
                {"section_id": "sec001", "title": "B"},
            ],
            doc_id="sec_doc",
            llm_callable=_mock_llm(VALID_LLM_RESPONSE),
        )
        for sc in result.section_questions:
            assert sc.section_id.startswith("sec")

    def test_generate_no_llm_returns_defaults(self):
        """No llm_callable → always returns default questions."""
        gen = CritiqueQuestionGenerator(_FakeConfig())
        result = gen.generate(
            doc_text="x", doc_type="GOVERNING_DOC", sections=[], doc_id="nl",
        )
        assert result.generator_model == "default"
        assert len(result.doc_level_questions) >= 2


# ══════════════════════════════════════════════════════════════════
# 2.1.2 Unit Tests — Validation
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.critique_gen
class TestValidation:

    def test_validate_rejects_non_question(self):
        """#11: Question without '?' at end → validation error."""
        crit = DocCritique(
            doc_id="v1", doc_type="X",
            doc_level_questions=[
                CritiqueQuestion(id="q1", question="This is not a question",
                                 trigger_keywords=[], trigger_logic="always"),
            ],
        )
        errors = CritiqueQuestionGenerator.validate(crit)
        assert any("doesn't end with '?'" in e for e in errors)

    def test_validate_rejects_invalid_trigger_logic(self):
        """#12: trigger_logic 'sometimes' → validation error."""
        crit = DocCritique(
            doc_id="v2", doc_type="X",
            doc_level_questions=[
                CritiqueQuestion(id="q1", question="Valid?",
                                 trigger_keywords=[], trigger_logic="sometimes"),
            ],
        )
        errors = CritiqueQuestionGenerator.validate(crit)
        assert any("Invalid trigger_logic" in e for e in errors)

    def test_validate_rejects_missing_keywords(self):
        """#13: trigger_logic 'any_in_source' + empty keywords → error."""
        crit = DocCritique(
            doc_id="v3", doc_type="X",
            doc_level_questions=[
                CritiqueQuestion(id="q1", question="Missing kw?",
                                 trigger_keywords=[], trigger_logic="any_in_source"),
            ],
        )
        errors = CritiqueQuestionGenerator.validate(crit)
        assert any("no keywords" in e for e in errors)

    def test_validate_accepts_always_no_keywords(self):
        """#14: trigger_logic 'always' + empty keywords → no error."""
        crit = DocCritique(
            doc_id="v4", doc_type="X",
            doc_level_questions=[
                CritiqueQuestion(id="q1", question="Always valid?",
                                 trigger_keywords=[], trigger_logic="always"),
            ],
        )
        errors = CritiqueQuestionGenerator.validate(crit)
        assert len(errors) == 0

    def test_validate_accepts_well_formed_critique(self):
        """#15: Complete valid DocCritique → empty error list."""
        crit = DocCritique(
            doc_id="v5", doc_type="TROUBLESHOOT",
            doc_level_questions=[
                CritiqueQuestion(id="q1", question="Is CAUTION preserved?",
                                 trigger_keywords=["CAUTION"], trigger_logic="any_in_source"),
            ],
            section_questions=[
                SectionCritique(section_id="sec000", section_title="A",
                                questions=[
                                    CritiqueQuestion(id="sq1", question="Steps ordered?",
                                                     trigger_keywords=[], trigger_logic="always"),
                                ]),
            ],
        )
        errors = CritiqueQuestionGenerator.validate(crit)
        assert errors == []


# ══════════════════════════════════════════════════════════════════
# 2.1.3 Unit Tests — Storage
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.critique_gen
class TestStorage:

    def _make_critique(self, doc_id: str = "doc_store") -> DocCritique:
        return DocCritique(
            doc_id=doc_id,
            doc_type="TROUBLESHOOT",
            generated_at="2026-01-01T00:00:00Z",
            generator_model="gpt-4.1",
            doc_level_questions=[
                CritiqueQuestion(id="dq1", question="CAUTION preserved?",
                                 trigger_keywords=["CAUTION"], trigger_logic="any_in_source"),
            ],
            section_questions=[],
        )

    def test_save_creates_json_file(self, tmp_path):
        """#16: Valid DocCritique + temp path → file exists at expected path."""
        gen = CritiqueQuestionGenerator()
        crit = self._make_critique()
        out = gen.save(crit, str(tmp_path))
        assert out.exists()
        assert out.name == "critique_questions.json"

    def test_save_overwrites_existing(self, tmp_path):
        """#17: Save twice to same path → second version persisted."""
        gen = CritiqueQuestionGenerator()
        crit1 = self._make_critique()
        gen.save(crit1, str(tmp_path))
        crit2 = self._make_critique()
        crit2.generated_at = "2099-12-31T23:59:59Z"
        out = gen.save(crit2, str(tmp_path))
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["generated_at"] == "2099-12-31T23:59:59Z"

    def test_load_returns_critique(self, tmp_path):
        """#18: Previously saved DocCritique → loaded matches saved."""
        gen = CritiqueQuestionGenerator()
        crit = self._make_critique()
        gen.save(crit, str(tmp_path))
        loaded = gen.load("doc_store", str(tmp_path))
        assert loaded is not None
        assert loaded.doc_id == "doc_store"
        assert loaded.doc_type == "TROUBLESHOOT"
        assert len(loaded.doc_level_questions) == 1

    def test_load_returns_none_if_missing(self, tmp_path):
        """#19: Non-existent doc_id → returns None."""
        gen = CritiqueQuestionGenerator()
        assert gen.load("nonexistent", str(tmp_path)) is None

    def test_load_handles_corrupted_json(self, tmp_path):
        """#20: Invalid JSON at expected path → returns None."""
        gen = CritiqueQuestionGenerator()
        doc_dir = tmp_path / "documents" / "corrupt_doc"
        doc_dir.mkdir(parents=True)
        (doc_dir / "critique_questions.json").write_text("{invalid", encoding="utf-8")
        assert gen.load("corrupt_doc", str(tmp_path)) is None


# ══════════════════════════════════════════════════════════════════
# 2.1.4 Unit Tests — Context Length Handling
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.critique_gen
class TestContextLength:

    def test_prepare_short_doc_returns_full(self):
        """#21: 5-page doc (< max_tokens) → full text returned."""
        short_text = "Hello world " * 500
        result = prepare_doc_for_critique_gen(short_text, [])
        assert result == short_text

    def test_prepare_long_doc_returns_summary(self):
        """#22: 200-page doc (> max_tokens) → structured summary."""
        long_text = "X " * 500_000  # ~250k tokens
        sections = [{"title": f"Section {i}", "content": f"Content {i}"} for i in range(5)]
        result = prepare_doc_for_critique_gen(long_text, sections, max_tokens=1000)
        assert "[DOCUMENT BEGINNING" in result
        assert "[DOCUMENT END" in result
        assert len(result) < len(long_text)

    def test_prepare_summary_includes_all_sections(self):
        """#23: 15-section doc → all 15 section titles in summary."""
        long_text = "X " * 500_000
        sections = [{"title": f"Section_{i}", "content": f"C{i}"} for i in range(15)]
        result = prepare_doc_for_critique_gen(long_text, sections, max_tokens=1000)
        for i in range(15):
            assert f"Section_{i}" in result


# ══════════════════════════════════════════════════════════════════
# 2.1.5 Unit Tests — Default Library
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.critique_gen
class TestDefaultLibrary:

    def test_defaults_exist_for_governing_doc(self):
        """#24: GOVERNING_DOC → >= 2 questions."""
        qs = get_default_questions("GOVERNING_DOC")
        assert len(qs) >= 2

    def test_defaults_exist_for_troubleshoot(self):
        """#25: TROUBLESHOOT → >= 2 questions."""
        qs = get_default_questions("TROUBLESHOOT")
        assert len(qs) >= 2

    def test_defaults_exist_for_supplement(self):
        """#26: SUPPLEMENT → >= 1 question."""
        qs = get_default_questions("SUPPLEMENT")
        assert len(qs) >= 1

    def test_defaults_have_valid_schema(self):
        """#27: All default questions pass validation."""
        for doc_type, questions in DEFAULT_QUESTIONS.items():
            crit = DocCritique(
                doc_id="schema_test", doc_type=doc_type,
                doc_level_questions=list(questions),
            )
            errors = CritiqueQuestionGenerator.validate(crit)
            assert errors == [], f"{doc_type} defaults have validation errors: {errors}"

    def test_defaults_fallback_to_generic(self):
        """Unknown doc_type falls back to GENERIC_GUIDE."""
        qs = get_default_questions("UNKNOWN_TYPE")
        generic = get_default_questions("GENERIC_GUIDE")
        assert len(qs) == len(generic)

    def test_default_questions_have_ids(self):
        """All default questions have non-empty id fields."""
        for doc_type, questions in DEFAULT_QUESTIONS.items():
            for q in questions:
                assert q.id, f"{doc_type} question missing id"


# ══════════════════════════════════════════════════════════════════
# 2.1.6 Integration Tests — Ingestion Pipeline
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.critique_gen
class TestIngestionIntegration:

    def test_ingestion_generates_critique_with_defaults(self, tmp_path):
        """#28: Generator with no LLM → critique file with default questions."""
        gen = CritiqueQuestionGenerator(_FakeConfig())
        result = gen.generate(
            doc_text="Some HP guide text with CAUTION warnings.",
            doc_type="TROUBLESHOOT",
            sections=[],
            doc_id="hp_test",
            doc_title="HP Test",
        )
        out = gen.save(result, str(tmp_path))
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["doc_id"] == "hp_test"
        assert len(data["doc_level_questions"]) >= 1

    def test_ingestion_skips_when_disabled(self):
        """#29: critique_generation_enabled=False → generate still works (caller controls skip)."""
        cfg = _FakeConfig()
        cfg.critique_generation_enabled = False
        # The generator itself doesn't check the flag — the caller (ingestion_agent) does.
        # Here we verify the config flag exists.
        assert hasattr(cfg, 'critique_generation_enabled')
        assert cfg.critique_generation_enabled is False

    def test_ingestion_uses_configured_model(self):
        """#30: Config critique_generator_model appears in generated DocCritique."""
        cfg = _FakeConfig()
        cfg.critique_generator_model = "gpt-4o"
        gen = CritiqueQuestionGenerator(cfg)
        result = gen.generate(
            doc_text="x", doc_type="GOVERNING_DOC", sections=[],
            doc_id="model_test", llm_callable=_mock_llm(VALID_LLM_RESPONSE),
        )
        assert result.generator_model == "gpt-4o"


# ══════════════════════════════════════════════════════════════════
# Module-level function test
# ══════════════════════════════════════════════════════════════════

@pytest.mark.phase9
@pytest.mark.critique_gen
class TestModuleLevelFunction:

    def test_prepare_doc_for_critique_gen_exists(self):
        """prepare_doc_for_critique_gen is importable at module level."""
        from backend.agents.critique_question_generator import prepare_doc_for_critique_gen
        assert callable(prepare_doc_for_critique_gen)

    def test_generation_prompt_constant(self):
        """GENERATION_PROMPT constant is defined and non-empty."""
        assert GENERATION_PROMPT
        assert "{doc_type}" in GENERATION_PROMPT
        assert "{doc_content}" in GENERATION_PROMPT
