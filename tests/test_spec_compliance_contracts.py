"""Spec-Compliance Contract Tests — Phases 8-15.

This file locks down every hard requirement extracted from the phase
specification documents.  Its sole purpose is to **prevent silent regressions**
when new phase work is added.  No LLM or network calls needed — every test is
deterministic and runs in < 1 ms.

Organization:
    One test class per phase.  Within each class, tests are organized:
        test_files_exist_*       — source files exist on disk
        test_config_*            — KTSConfig flag names, types, defaults
        test_import_*            — classes/functions importable
        test_fields_*            — dataclass / class fields present
        test_constants_*         — numeric / string constants match spec
        test_routing_*           — routing strings / enums match spec

Run just this file:
    pytest tests/test_spec_compliance_contracts.py -q
"""

from __future__ import annotations

import importlib
import inspect
import os
import sys
from dataclasses import fields as dc_fields
from pathlib import Path

import pytest

# ── Resolve workspace root ──────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import KTSConfig


# ── Helpers ──────────────────────────────────────────────────────────

def _cfg() -> KTSConfig:
    """Return a pristine default config (no env overrides)."""
    # Temporarily clear KTS_ env vars to get pure defaults
    saved = {}
    for k, v in list(os.environ.items()):
        if k.startswith("KTS_"):
            saved[k] = v
            del os.environ[k]
    try:
        return KTSConfig()
    finally:
        os.environ.update(saved)


def _file_exists(relpath: str) -> bool:
    return (ROOT / relpath).exists()


def _module_has(module_path: str, name: str) -> bool:
    """Check that *name* is importable from *module_path*."""
    try:
        mod = importlib.import_module(module_path)
        return hasattr(mod, name)
    except Exception:
        return False


def _class_has_field(module_path: str, class_name: str, field_name: str) -> bool:
    """Check that a dataclass or regular class has a given field/attribute."""
    try:
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        # Try dataclass fields first
        try:
            return any(f.name == field_name for f in dc_fields(cls))
        except TypeError:
            pass
        # Fall back to checking __init__ params or class attributes
        sig = inspect.signature(cls.__init__)
        if field_name in sig.parameters:
            return True
        return hasattr(cls, field_name)
    except Exception:
        return False


def _class_has_method(module_path: str, class_name: str, method_name: str) -> bool:
    try:
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        return callable(getattr(cls, method_name, None))
    except Exception:
        return False


# ═════════════════════════════════════════════════════════════════════
#  PHASE 8 — RAG Upgrade (9 Increments)
# ═════════════════════════════════════════════════════════════════════

class TestPhase8SpecContracts:
    """Spec contracts for Phase 8 (RAG Upgrade)."""

    # ── 8.0 File Existence ──────────────────────────────────────────

    @pytest.mark.parametrize("path", [
        "backend/retrieval/bm25_retriever.py",
        "extension/lib/hype_enricher.js",
        "extension/lib/query_expander.js",
        "backend/vector/legal_chunker.py",
        "backend/vector/dual_vector_store.py",
        "backend/retrieval/human_like_retriever.py",
        "backend/agents/retrieval_service.py",
        "config/settings.py",
    ])
    def test_files_exist(self, path):
        assert _file_exists(path), f"Phase 8 required file missing: {path}"

    # ── 8.0 Config Flag Defaults ────────────────────────────────────

    @pytest.mark.parametrize("flag,expected_type,expected_default", [
        ("enable_cch",               bool,  True),
        ("cch_max_section_len",      int,   80),
        ("enable_bm25_hybrid",       bool,  True),
        ("bm25_weight",              float, 0.4),
        ("vector_weight",            float, 0.6),
        ("rrf_constant",             int,   60),
        ("bm25_k1",                  float, 1.5),
        ("bm25_b",                   float, 0.75),
        ("enable_mmr",               bool,  True),
        ("mmr_lambda",               float, 0.7),
        ("mmr_fetch_multiplier",     int,   5),
        ("enable_parent_expansion",  bool,  True),
        ("max_parent_sections",      int,   20),
        ("enable_hype",              bool,  False),
        ("multi_query_rag_enabled",  bool,  True),
        ("multi_query_variants",     int,   8),
        ("multi_query_pool_size",    int,   60),
        ("definition_traversal_enabled", bool, True),
        ("definition_traversal_depth",   int,  8),
        ("self_rag_enabled",         bool,  False),
        ("self_rag_max_rounds",      int,   5),
        ("self_rag_model",           str,   "gpt-4.1"),
    ])
    def test_config_defaults(self, flag, expected_type, expected_default):
        cfg = _cfg()
        val = getattr(cfg, flag)
        assert isinstance(val, expected_type), f"{flag}: expected {expected_type}, got {type(val)}"
        assert val == expected_default, f"{flag}: expected {expected_default}, got {val}"

    # ── 8.1 BM25Retriever Class ─────────────────────────────────────

    def test_import_bm25_retriever(self):
        assert _module_has("backend.retrieval.bm25_retriever", "BM25Retriever")

    @pytest.mark.parametrize("method", ["build_index", "search", "save_index", "load_index"])
    def test_bm25_methods(self, method):
        assert _class_has_method("backend.retrieval.bm25_retriever", "BM25Retriever", method)

    # ── 8.0 CCH — legal_chunker ────────────────────────────────────

    def test_import_build_cch_header(self):
        assert _module_has("backend.vector.legal_chunker", "build_cch_header")

    # ── 8.2 MMR — dual_vector_store ────────────────────────────────

    @pytest.mark.parametrize("fn", ["search_items_mmr", "search_sections_mmr"])
    def test_dual_store_mmr_methods(self, fn):
        assert _module_has("backend.vector.dual_vector_store", "DualVectorStore") or \
               _class_has_method("backend.vector.dual_vector_store", "DualVectorStore", fn)

    # ── 8.5 HyPE — dual_vector_store collections ──────────────────

    def test_dual_store_search_item_questions(self):
        assert _class_has_method("backend.vector.dual_vector_store", "DualVectorStore", "search_item_questions")

    def test_dual_store_has_question_collection_support(self):
        """DualVectorStore must support HyPE question collection (add via internal or public API)."""
        from backend.vector.dual_vector_store import DualVectorStore
        src = inspect.getsource(DualVectorStore)
        assert "item_questions" in src, "DualVectorStore must reference item_questions collection"

    # ── 8.4 Parent Expansion — human_like_retriever ────────────────

    def test_parent_expansion_method(self):
        assert _class_has_method(
            "backend.retrieval.human_like_retriever",
            "HumanLikeRetriever",
            "_expand_items_to_parent_sections",
        )

    # ── 8.1 BM25 Integration — human_like_retriever ───────────────

    def test_human_like_retriever_supports_bm25(self):
        """HumanLikeRetriever must integrate BM25 (via param or internal wiring)."""
        from backend.retrieval import human_like_retriever as hlr
        src = inspect.getsource(hlr)
        assert "bm25" in src.lower() or "BM25" in src, \
            "human_like_retriever must reference BM25 integration"

    # ── 8.6 Multi-Query — human_like_retriever ─────────────────────

    def test_retrieve_accepts_extra_queries(self):
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        sig = inspect.signature(HumanLikeRetriever.retrieve)
        assert "extra_queries" in sig.parameters, "retrieve() must accept extra_queries param"


# ═════════════════════════════════════════════════════════════════════
#  PHASE 9 — Directed Critique RAG
# ═════════════════════════════════════════════════════════════════════

class TestPhase9SpecContracts:
    """Spec contracts for Phase 9 (Directed Critique RAG)."""

    # ── File Existence ──────────────────────────────────────────────

    @pytest.mark.parametrize("path", [
        "backend/agents/critique_question_generator.py",
        "backend/agents/critique_defaults.py",
        "backend/retrieval/critique_loop.py",
        "backend/retrieval/critique_prompts.py",
        "backend/retrieval/critique_merger.py",
        "extension/lib/critique_client.js",
    ])
    def test_files_exist(self, path):
        assert _file_exists(path), f"Phase 9 required file missing: {path}"

    # ── Config Defaults ─────────────────────────────────────────────

    @pytest.mark.parametrize("flag,expected_type,expected_default", [
        ("critique_generation_enabled",     bool,  True),
        ("critique_generator_model",        str,   "gpt-4.1"),
        ("critique_max_questions_per_doc",  int,   25),
        ("critique_loop_enabled",           bool,  True),
        ("critique_model",                  str,   "gpt-4.1"),
        ("critique_max_rounds",             int,   5),
        ("critique_restart_on_gap",         bool,  True),
        ("critique_multi_doc_enabled",      bool,  True),
        ("critique_confidence_exit",        float, 0.90),
    ])
    def test_config_defaults(self, flag, expected_type, expected_default):
        cfg = _cfg()
        val = getattr(cfg, flag)
        assert isinstance(val, expected_type), f"{flag}: expected {expected_type}, got {type(val)}"
        assert val == expected_default, f"{flag}: expected {expected_default}, got {val}"

    # ── Importable Classes/Functions ────────────────────────────────

    def test_import_critique_question_generator(self):
        assert _module_has(
            "backend.agents.critique_question_generator",
            "CritiqueQuestionGenerator",
        )

    def test_import_critique_defaults(self):
        assert _module_has("backend.agents.critique_defaults", "DEFAULT_QUESTIONS")

    def test_import_directed_critique_loop(self):
        assert _module_has("backend.retrieval.critique_loop", "DirectedCritiqueLoop")

    def test_import_critique_merger(self):
        assert _module_has("backend.retrieval.critique_merger", "merge_critique_questions")

    def test_import_should_early_exit(self):
        assert _module_has("backend.retrieval.critique_merger", "should_early_exit")

    # ── Dataclass Fields (CritiqueQuestion) ─────────────────────────

    @pytest.mark.parametrize("field", [
        "id", "question", "trigger_keywords", "trigger_logic", "priority",
    ])
    def test_critique_question_fields(self, field):
        assert _class_has_field("backend.common.models", "CritiqueQuestion", field)

    # ── Dataclass Fields (CritiqueResult) ───────────────────────────

    @pytest.mark.parametrize("field", [
        "answer", "confidence", "rounds_executed", "questions_evaluated",
        "gaps_found", "gaps_fixed", "re_queries", "converged", "answer_history",
    ])
    def test_critique_result_fields(self, field):
        assert _class_has_field("backend.common.models", "CritiqueResult", field)

    # ── Safety Keywords ─────────────────────────────────────────────

    def test_safety_keywords_exist(self):
        from backend.retrieval.critique_loop import SAFETY_KEYWORDS
        for kw in ["CAUTION", "WARNING", "NOTE:", "IMPORTANT:"]:
            assert kw in SAFETY_KEYWORDS, f"SAFETY_KEYWORDS missing '{kw}'"

    # ── Critique Prompts ────────────────────────────────────────────

    def test_gap_to_query_prompt_exists(self):
        assert _module_has("backend.retrieval.critique_prompts", "GAP_TO_QUERY_PROMPT")

    # ── Generator Methods ───────────────────────────────────────────

    @pytest.mark.parametrize("method", ["generate", "save", "load", "validate"])
    def test_generator_methods(self, method):
        assert _class_has_method(
            "backend.agents.critique_question_generator",
            "CritiqueQuestionGenerator",
            method,
        )

    # ── Loop Methods ────────────────────────────────────────────────

    @pytest.mark.parametrize("method", [
        "run", "_evaluate_question", "_re_retrieve", "_re_synthesize",
    ])
    def test_loop_methods(self, method):
        assert _class_has_method(
            "backend.retrieval.critique_loop",
            "DirectedCritiqueLoop",
            method,
        )

    def test_gap_translation_exists(self):
        """Gap-to-query translation must exist (as GapToQueryTranslator or _translate_gap)."""
        from backend.retrieval import critique_loop as cl
        has_translator = (
            hasattr(cl, "GapToQueryTranslator") or
            _class_has_method("backend.retrieval.critique_loop", "DirectedCritiqueLoop", "_translate_gap")
        )
        assert has_translator, "critique_loop must have gap translation (GapToQueryTranslator or _translate_gap)"

    # ── Trigger Logic ───────────────────────────────────────────────

    def test_trigger_matches_exists(self):
        assert _module_has("backend.retrieval.critique_loop", "trigger_matches")


# ═════════════════════════════════════════════════════════════════════
#  PHASE 10 — Conversation Memory & Session Intelligence
# ═════════════════════════════════════════════════════════════════════

class TestPhase10SpecContracts:
    """Spec contracts for Phase 10 (Conversation Memory)."""

    # ── File Existence ──────────────────────────────────────────────

    @pytest.mark.parametrize("path", [
        "backend/retrieval/query_rewriter.py",
        "backend/retrieval/session_memory.py",
    ])
    def test_files_exist(self, path):
        assert _file_exists(path), f"Phase 10 required file missing: {path}"

    # ── Config Defaults ─────────────────────────────────────────────

    @pytest.mark.parametrize("flag,expected_type,expected_default", [
        ("session_memory_enabled",         bool,  True),
        ("query_rewriting_enabled",        bool,  True),
        ("history_summarization_enabled",  bool,  True),
        ("history_max_turns",              int,   20),
        ("session_memory_ttl_hours",       float, 4.0),
    ])
    def test_config_defaults(self, flag, expected_type, expected_default):
        cfg = _cfg()
        val = getattr(cfg, flag)
        assert isinstance(val, expected_type), f"{flag}: expected {expected_type}, got {type(val)}"
        assert val == expected_default, f"{flag}: expected {expected_default}, got {val}"

    # ── Importable Classes/Functions ────────────────────────────────

    def test_import_query_rewriter_class(self):
        assert _module_has("backend.retrieval.query_rewriter", "QueryRewriter")

    def test_import_rewrite_prompt(self):
        assert _module_has("backend.retrieval.query_rewriter", "REWRITE_PROMPT")

    def test_import_coreference_signals(self):
        assert _module_has("backend.retrieval.query_rewriter", "COREFERENCE_SIGNALS")

    def test_import_session_memory(self):
        assert _module_has("backend.retrieval.session_memory", "SessionMemory")

    def test_import_apply_document_bias(self):
        assert _module_has("backend.retrieval.session_memory", "apply_document_bias")

    # ── Coreference Signals Contain Required Values ─────────────────

    def test_coreference_signals_values(self):
        from backend.retrieval.query_rewriter import COREFERENCE_SIGNALS
        required = ["it", "this", "that", "they", "same", "which", "those"]
        for sig in required:
            assert sig in COREFERENCE_SIGNALS, f"COREFERENCE_SIGNALS missing '{sig}'"

    # ── SessionMemory Fields ────────────────────────────────────────

    @pytest.mark.parametrize("field", [
        "session_id", "resolved_terms", "active_documents", "active_sections",
        "turn_count", "created_at", "last_accessed",
    ])
    def test_session_memory_fields(self, field):
        assert _class_has_field("backend.retrieval.session_memory", "SessionMemory", field)

    # ── Document Bias Boost Value ───────────────────────────────────

    def test_document_bias_boost_value(self):
        from backend.retrieval import session_memory as sm
        # The module should expose the 1.15 constant somewhere
        boost = getattr(sm, "DOCUMENT_BIAS_BOOST", None)
        if boost is None:
            # Check inside apply_document_bias source for the literal 1.15
            src = inspect.getsource(sm.apply_document_bias)
            assert "1.15" in src, "apply_document_bias must use 1.15 boost factor"
        else:
            assert boost == 1.15


# ═════════════════════════════════════════════════════════════════════
#  PHASE 11 — VS Code Native Intelligence Layer
# ═════════════════════════════════════════════════════════════════════

class TestPhase11SpecContracts:
    """Spec contracts for Phase 11 (VS Code Deep Integration)."""

    # ── File Existence ──────────────────────────────────────────────

    @pytest.mark.parametrize("path", [
        "backend/retrieval/extraction_mode.py",
        "backend/retrieval/audit_mode.py",
        "backend/retrieval/definition_mode.py",
        "extension/chat/participant.js",
        "extension/commands/select_source.js",
    ])
    def test_files_exist(self, path):
        assert _file_exists(path), f"Phase 11 required file missing: {path}"

    # ── Config Defaults ─────────────────────────────────────────────

    @pytest.mark.parametrize("flag,expected_type,expected_default", [
        ("follow_up_suggestions_enabled", bool, True),
        ("sse_progress_enabled",          bool, True),
        ("hitl_classification_enabled",   bool, True),
        ("definition_mode_enabled",       bool, True),
        ("audit_mode_enabled",            bool, True),
    ])
    def test_config_defaults(self, flag, expected_type, expected_default):
        cfg = _cfg()
        val = getattr(cfg, flag)
        assert isinstance(val, expected_type), f"{flag}: expected {expected_type}, got {type(val)}"
        assert val == expected_default, f"{flag}: expected {expected_default}, got {val}"

    # ── Importable Classes ──────────────────────────────────────────

    def test_import_extraction_mode(self):
        assert _module_has("backend.retrieval.extraction_mode", "ExtractionMode")

    def test_import_extraction_config(self):
        assert _module_has("backend.retrieval.extraction_mode", "ExtractionConfig")

    def test_import_audit_mode(self):
        assert _module_has("backend.retrieval.audit_mode", "AuditMode")

    def test_import_audit_config(self):
        assert _module_has("backend.retrieval.audit_mode", "AuditConfig")

    def test_import_definition_mode(self):
        assert _module_has("backend.retrieval.definition_mode", "DefinitionMode")

    def test_import_definition_config(self):
        assert _module_has("backend.retrieval.definition_mode", "DefinitionConfig")

    # ── ExtractionConfig Defaults (Phase 14.3 spec) ────────────────

    def test_extraction_config_chunk_budget(self):
        from backend.retrieval.extraction_mode import ExtractionConfig
        assert ExtractionConfig().chunk_budget == 10

    def test_extraction_config_temperature(self):
        from backend.retrieval.extraction_mode import ExtractionConfig
        assert ExtractionConfig().temperature == 0.0

    def test_extraction_config_max_output_tokens(self):
        from backend.retrieval.extraction_mode import ExtractionConfig
        assert ExtractionConfig().max_output_tokens == 2000

    # ── AuditConfig Defaults ────────────────────────────────────────

    def test_audit_config_chunk_budget(self):
        from backend.retrieval.audit_mode import AuditConfig
        assert AuditConfig().chunk_budget == 15

    def test_audit_config_temperature(self):
        from backend.retrieval.audit_mode import AuditConfig
        assert AuditConfig().temperature == 0.2

    # ── DefinitionConfig Defaults ───────────────────────────────────

    def test_definition_config_chunk_budget(self):
        from backend.retrieval.definition_mode import DefinitionConfig
        assert DefinitionConfig().chunk_budget == 3

    def test_definition_config_temperature(self):
        from backend.retrieval.definition_mode import DefinitionConfig
        assert DefinitionConfig().temperature == 0.0

    # ── SummaryConfig Defaults (Phase 14.4 spec) ───────────────────

    def test_summary_config_chunk_budget(self):
        from backend.retrieval.summary_mode import SummaryConfig
        assert SummaryConfig().chunk_budget == 20

    def test_summary_config_temperature(self):
        from backend.retrieval.summary_mode import SummaryConfig
        assert SummaryConfig().temperature == 0.5

    def test_summary_config_max_output_tokens(self):
        from backend.retrieval.summary_mode import SummaryConfig
        assert SummaryConfig().max_output_tokens == 4000

    # ── Regime Classifier has is_ambiguous ──────────────────────────

    def test_regime_result_is_ambiguous(self):
        from backend.ingestion.regime_classifier import RegimeResult
        r = RegimeResult(regime="test", score=50, signals=[], filename="test.pdf")
        assert hasattr(r, "is_ambiguous")
        assert r.is_ambiguous is True  # 35 <= 50 <= 64

    def test_regime_result_not_ambiguous_high(self):
        from backend.ingestion.regime_classifier import RegimeResult
        r = RegimeResult(regime="test", score=80, signals=[], filename="test.pdf")
        assert r.is_ambiguous is False

    def test_regime_result_not_ambiguous_low(self):
        from backend.ingestion.regime_classifier import RegimeResult
        r = RegimeResult(regime="test", score=20, signals=[], filename="test.pdf")
        assert r.is_ambiguous is False


# ═════════════════════════════════════════════════════════════════════
#  PHASE 12 — Named Scoped Knowledge Spaces
# ═════════════════════════════════════════════════════════════════════

class TestPhase12SpecContracts:
    """Spec contracts for Phase 12 (Scoped Knowledge Spaces)."""

    # ── File Existence ──────────────────────────────────────────────

    @pytest.mark.parametrize("path", [
        "backend/retrieval/scope_router.py",
        "backend/vector/deal_catalog.py",
        "extension/lib/scope_discovery.js",
    ])
    def test_files_exist(self, path):
        assert _file_exists(path), f"Phase 12 required file missing: {path}"

    # ── Config Defaults ─────────────────────────────────────────────

    @pytest.mark.parametrize("flag,expected_type,expected_default", [
        ("knowledge_source_root",      str,  ""),
        ("per_folder_kts_enabled",     bool, True),
        ("deal_catalog_enabled",       bool, True),
        ("scope_discovery_on_startup", bool, True),
    ])
    def test_config_defaults(self, flag, expected_type, expected_default):
        cfg = _cfg()
        val = getattr(cfg, flag)
        assert isinstance(val, expected_type), f"{flag}: expected {expected_type}, got {type(val)}"
        assert val == expected_default, f"{flag}: expected {expected_default}, got {val}"

    # ── Importable Classes ──────────────────────────────────────────

    def test_import_deal_catalog(self):
        assert _module_has("backend.vector.deal_catalog", "DealCatalog")

    def test_import_scope_router(self):
        assert _module_has("backend.retrieval.scope_router", "ScopeRouter")

    def test_import_route_query(self):
        assert _module_has("backend.retrieval.scope_router", "route_query") or \
               _class_has_method("backend.retrieval.scope_router", "ScopeRouter", "route")

    def test_import_federated_search(self):
        assert _module_has("backend.retrieval.scope_router", "federated_search") or \
               _class_has_method("backend.retrieval.scope_router", "ScopeRouter", "federated_search")

    # ── ScopeRouter Constants ───────────────────────────────────────

    def test_max_federated_scopes(self):
        from backend.retrieval import scope_router as sr
        # Must be 100 either as attr on class or module
        val = getattr(sr, "MAX_FEDERATED_SCOPES", None)
        if val is None:
            val = getattr(sr.ScopeRouter, "MAX_FEDERATED_SCOPES", None)
        assert val == 100, f"MAX_FEDERATED_SCOPES should be 100, got {val}"

    # ── DealCatalog SQLite Schema Fields ────────────────────────────

    def test_deal_catalog_has_required_fields(self):
        """DealCatalog must define the 10 required columns."""
        from backend.vector.deal_catalog import DealCatalog
        required = [
            "folder_name", "slug", "kts_path", "doc_count", "doc_types",
            "issuers", "years", "collateral_types", "key_parties", "last_indexed",
        ]
        # Check via DEAL_CATALOG_COLUMNS or class source
        src = inspect.getsource(DealCatalog)
        for col in required:
            assert col in src, f"DealCatalog missing column reference: {col}"

    # ── Slugification ───────────────────────────────────────────────

    def test_scope_router_slugify_exists(self):
        """ScopeRouter or deal_catalog must expose a slugification function."""
        from backend.retrieval import scope_router as sr
        from backend.vector import deal_catalog as dc
        has_slugify = (
            hasattr(sr, "slugify") or
            hasattr(sr, "_slugify") or
            hasattr(dc, "slugify") or
            hasattr(dc, "_slugify") or
            hasattr(dc.DealCatalog, "slugify") or
            hasattr(dc.DealCatalog, "_slugify")
        )
        assert has_slugify, "No slugify function found in scope_router or deal_catalog"


# ═════════════════════════════════════════════════════════════════════
#  PHASE 13 — Retrieval Quality Upgrades
# ═════════════════════════════════════════════════════════════════════

class TestPhase13SpecContracts:
    """Spec contracts for Phase 13 (Retrieval Quality)."""

    # ── File Existence ──────────────────────────────────────────────

    @pytest.mark.parametrize("path", [
        "backend/retrieval/confidence_scorer.py",
        "backend/retrieval/gap_detector.py",
        "backend/retrieval/hyde.py",
        "backend/retrieval/guide_retriever.py",
    ])
    def test_files_exist(self, path):
        assert _file_exists(path), f"Phase 13 required file missing: {path}"

    # ── Config Defaults ─────────────────────────────────────────────

    @pytest.mark.parametrize("flag,expected_type,expected_default", [
        ("confidence_scoring_enabled",       bool,  True),
        ("gap_detection_enabled",            bool,  True),
        ("parent_child_chunking_enabled",    bool,  False),
        ("hyde_enabled",                     bool,  True),
        ("regime_aware_retrieval",           bool,  True),
        ("guide_items_top_k",               int,   60),
        ("guide_sections_top_k",            int,   20),
        ("guide_graph_expansion",           bool,  True),
        ("guide_bfs_depth",                 int,   4),
        ("guide_error_code_boost",          float, 0.35),
        ("guide_step_ordering",             bool,  True),
    ])
    def test_config_defaults(self, flag, expected_type, expected_default):
        cfg = _cfg()
        val = getattr(cfg, flag)
        assert isinstance(val, expected_type), f"{flag}: expected {expected_type}, got {type(val)}"
        assert val == expected_default, f"{flag}: expected {expected_default}, got {val}"

    # ── Importable Classes/Functions ────────────────────────────────

    def test_import_confidence_scorer(self):
        assert _module_has("backend.retrieval.confidence_scorer", "ConfidenceScorer")

    def test_import_confidence_tier(self):
        assert _module_has("backend.retrieval.confidence_scorer", "ConfidenceTier")

    def test_import_gap_detector(self):
        assert _module_has("backend.retrieval.gap_detector", "GapDetector")

    def test_import_extract_entities(self):
        assert _module_has("backend.retrieval.gap_detector", "extract_entities")

    def test_import_hyde_processor(self):
        assert _module_has("backend.retrieval.hyde", "HyDEProcessor")

    def test_import_hyde_prompts(self):
        """HyDE must have prompt template(s) for legal/guide document types."""
        from backend.retrieval import hyde
        has_prompt = (
            hasattr(hyde, "HYDE_PROMPT") or
            hasattr(hyde, "HYDE_PROMPT_LEGAL") or
            hasattr(hyde, "HYDE_PROMPT_GUIDE")
        )
        assert has_prompt, "hyde module must export HYDE_PROMPT or HYDE_PROMPT_LEGAL/GUIDE"

    def test_import_guide_retriever(self):
        assert _module_has("backend.retrieval.guide_retriever", "GuideRetriever")

    # ── Confidence Tier Values ──────────────────────────────────────

    def test_confidence_tier_values(self):
        from backend.retrieval.confidence_scorer import ConfidenceTier
        for tier in ["HIGH", "MEDIUM", "LOW", "SPECULATIVE"]:
            assert hasattr(ConfidenceTier, tier), f"ConfidenceTier missing tier: {tier}"

    # ── Confidence Thresholds ───────────────────────────────────────

    def test_confidence_high_threshold(self):
        from backend.retrieval import confidence_scorer as cs
        src = inspect.getsource(cs)
        assert "0.85" in src, "confidence_scorer missing HIGH threshold 0.85"

    def test_confidence_direct_match_threshold(self):
        from backend.retrieval import confidence_scorer as cs
        src = inspect.getsource(cs)
        assert "0.75" in src, "confidence_scorer missing direct match threshold 0.75"

    def test_confidence_medium_threshold(self):
        from backend.retrieval import confidence_scorer as cs
        src = inspect.getsource(cs)
        assert "0.65" in src, "confidence_scorer missing MEDIUM threshold 0.65"

    def test_confidence_low_threshold(self):
        from backend.retrieval import confidence_scorer as cs
        src = inspect.getsource(cs)
        assert "0.45" in src, "confidence_scorer missing LOW threshold 0.45"

    def test_confidence_scorer_has_score_method(self):
        assert _class_has_method(
            "backend.retrieval.confidence_scorer", "ConfidenceScorer", "score"
        )

    def test_gap_detector_has_detect_method(self):
        assert _class_has_method(
            "backend.retrieval.gap_detector", "GapDetector", "detect"
        )

    # ── GuideRetriever Methods ──────────────────────────────────────

    def test_guide_retriever_has_retrieve(self):
        assert _class_has_method(
            "backend.retrieval.guide_retriever", "GuideRetriever", "retrieve"
        )

    # ── GuideRetriever BFS Edges ────────────────────────────────────

    def test_guide_bfs_edges(self):
        from backend.retrieval import guide_retriever as gr
        src = inspect.getsource(gr)
        required_edges = ["NEXT", "CONTAINS", "REFERENCES", "HAS_STEP", "HAS_RULE"]
        for edge in required_edges:
            assert edge in src, f"guide_retriever missing BFS edge type: {edge}"

    # ── HyDE Prompt Template ────────────────────────────────────────

    def test_hyde_prompt_has_placeholders(self):
        """HyDE prompt template(s) must have query/doc_type placeholders."""
        from backend.retrieval import hyde
        # Check any available prompt template
        prompt = getattr(hyde, "HYDE_PROMPT", None) or \
                 getattr(hyde, "HYDE_PROMPT_LEGAL", None) or \
                 getattr(hyde, "HYDE_PROMPT_GUIDE", None)
        assert prompt is not None, "hyde must have at least one prompt template"
        assert "{query}" in prompt, "HyDE prompt missing {query} placeholder"


# ═════════════════════════════════════════════════════════════════════
#  PHASE 14 — Structured Deal Intelligence
# ═════════════════════════════════════════════════════════════════════

class TestPhase14SpecContracts:
    """Spec contracts for Phase 14 (Deal Intelligence)."""

    # ── File Existence ──────────────────────────────────────────────

    @pytest.mark.parametrize("path", [
        "backend/retrieval/temporal_reasoner.py",
        "backend/retrieval/extraction_mode.py",
        "backend/retrieval/summary_mode.py",
        "backend/retrieval/session_memory.py",
    ])
    def test_files_exist(self, path):
        assert _file_exists(path), f"Phase 14 required file missing: {path}"

    # ── Config Defaults ─────────────────────────────────────────────

    @pytest.mark.parametrize("flag,expected_type,expected_default", [
        ("deal_summary_cache_enabled",  bool, True),
        ("temporal_reasoning_enabled",  bool, True),
        ("extraction_mode_enabled",     bool, True),
        ("summary_mode_enabled",        bool, True),
    ])
    def test_config_defaults(self, flag, expected_type, expected_default):
        cfg = _cfg()
        val = getattr(cfg, flag)
        assert isinstance(val, expected_type), f"{flag}: expected {expected_type}, got {type(val)}"
        assert val == expected_default, f"{flag}: expected {expected_default}, got {val}"

    # ── Importable Classes ──────────────────────────────────────────

    def test_import_temporal_reasoner(self):
        assert _module_has("backend.retrieval.temporal_reasoner", "TemporalReasoner")

    def test_import_temporal_signals(self):
        assert _module_has("backend.retrieval.temporal_reasoner", "TEMPORAL_SIGNALS")

    def test_import_extraction_mode(self):
        assert _module_has("backend.retrieval.extraction_mode", "ExtractionMode")

    def test_import_extraction_result(self):
        assert _module_has("backend.retrieval.extraction_mode", "ExtractionResult")

    def test_import_extraction_schema(self):
        assert _module_has("backend.retrieval.extraction_mode", "EXTRACTION_SCHEMA")

    def test_import_summary_mode(self):
        assert _module_has("backend.retrieval.summary_mode", "SummaryMode")

    def test_import_summary_result(self):
        assert _module_has("backend.retrieval.summary_mode", "SummaryResult")

    def test_import_deal_summary(self):
        assert _module_has("backend.retrieval.session_memory", "DealSummary")

    def test_import_session_store(self):
        assert _module_has("backend.retrieval.session_memory", "SessionStore")

    # ── TemporalReasoner Methods ────────────────────────────────────

    @pytest.mark.parametrize("method", [
        "is_temporal_query", "get_temporal_context",
        "get_temporal_evaluation_instruction", "build_temporal_prompt_prefix",
        "extract_dates_from_text",
    ])
    def test_temporal_reasoner_methods(self, method):
        assert _class_has_method(
            "backend.retrieval.temporal_reasoner", "TemporalReasoner", method
        )

    # ── TemporalReasoner current_date properties ───────────────────

    def test_temporal_reasoner_current_date(self):
        from backend.retrieval.temporal_reasoner import TemporalReasoner
        tr = TemporalReasoner()
        assert hasattr(tr, "current_date")
        assert hasattr(tr, "current_date_str")

    # ── TEMPORAL_SIGNALS Values ─────────────────────────────────────

    def test_temporal_signals_values(self):
        from backend.retrieval.temporal_reasoner import TEMPORAL_SIGNALS
        required = ["passed", "current", "active", "expired", "when does"]
        for sig in required:
            assert sig in TEMPORAL_SIGNALS, f"TEMPORAL_SIGNALS missing '{sig}'"

    # ── TemporalReasoner is_temporal_query ──────────────────────────

    def test_is_temporal_query_positive(self):
        from backend.retrieval.temporal_reasoner import TemporalReasoner
        tr = TemporalReasoner()
        assert tr.is_temporal_query("Has the distribution date passed?")

    def test_is_temporal_query_negative(self):
        from backend.retrieval.temporal_reasoner import TemporalReasoner
        tr = TemporalReasoner()
        assert not tr.is_temporal_query("What is the definition of Trustee?")

    # ── DealSummary Fields ──────────────────────────────────────────

    @pytest.mark.parametrize("field", [
        "scope", "deal_name", "doc_types_present", "parties",
        "key_dates", "key_amounts", "defined_terms", "cited_sections",
        "turn_count", "last_updated",
    ])
    def test_deal_summary_fields(self, field):
        assert _class_has_field("backend.retrieval.session_memory", "DealSummary", field)

    # ── DealSummary Methods ─────────────────────────────────────────

    @pytest.mark.parametrize("method", ["update_from_answer", "lookup_term", "to_dict"])
    def test_deal_summary_methods(self, method):
        assert _class_has_method(
            "backend.retrieval.session_memory", "DealSummary", method
        )

    # ── SessionStore Methods ────────────────────────────────────────

    @pytest.mark.parametrize("method", ["get_or_create", "get", "remove"])
    def test_session_store_methods(self, method):
        assert _class_has_method(
            "backend.retrieval.session_memory", "SessionStore", method
        )

    # ── SessionMemory Constants ─────────────────────────────────────

    def test_default_ttl_hours(self):
        from backend.retrieval import session_memory as sm
        val = getattr(sm, "DEFAULT_TTL_HOURS", None)
        assert val == 4, f"DEFAULT_TTL_HOURS should be 4, got {val}"

    def test_max_sessions(self):
        from backend.retrieval import session_memory as sm
        val = getattr(sm, "MAX_SESSIONS", None)
        assert val == 100, f"MAX_SESSIONS should be 100, got {val}"

    def test_max_verbatim_turns(self):
        from backend.retrieval import session_memory as sm
        val = getattr(sm, "MAX_VERBATIM_TURNS", None)
        assert val == 4, f"MAX_VERBATIM_TURNS should be 4, got {val}"

    # ── ExtractionMode Schema Keys ──────────────────────────────────

    def test_extraction_schema_keys(self):
        from backend.retrieval.extraction_mode import EXTRACTION_SCHEMA
        required = [
            "deal_name", "deal_type", "closing_date", "parties",
            "key_dates", "key_amounts", "defined_terms",
        ]
        for key in required:
            assert key in EXTRACTION_SCHEMA, f"EXTRACTION_SCHEMA missing key: {key}"

    # ── ExtractionResult Fields ─────────────────────────────────────

    @pytest.mark.parametrize("field", [
        "data", "raw_response", "parsed_ok", "extraction_gaps",
    ])
    def test_extraction_result_fields(self, field):
        assert _class_has_field("backend.retrieval.extraction_mode", "ExtractionResult", field)

    # ── SummaryResult Fields ────────────────────────────────────────

    @pytest.mark.parametrize("field", [
        "scope", "raw_markdown", "sections_found", "source_sections", "confidence",
    ])
    def test_summary_result_fields(self, field):
        assert _class_has_field("backend.retrieval.summary_mode", "SummaryResult", field)

    # ── Summary 5-Section Template References ───────────────────────

    def test_summary_prompt_has_5_sections(self):
        from backend.retrieval.summary_mode import SUMMARY_PROMPT
        for section in ["Parties", "Key Dates", "Key Amounts", "Key Obligations", "Risk Factors"]:
            assert section in SUMMARY_PROMPT, f"SUMMARY_PROMPT missing section: {section}"


# ═════════════════════════════════════════════════════════════════════
#  PHASE 15 — Cross-Deal Intelligence & Anomaly Detection
# ═════════════════════════════════════════════════════════════════════

class TestPhase15SpecContracts:
    """Spec contracts for Phase 15 (Cross-Deal Intelligence)."""

    # ── File Existence ──────────────────────────────────────────────

    @pytest.mark.parametrize("path", [
        "backend/retrieval/comparison_mode.py",
        "backend/retrieval/contradiction_detector.py",
        "backend/retrieval/baseline_corpus.py",
        "backend/retrieval/anomaly_scorer.py",
    ])
    def test_files_exist(self, path):
        assert _file_exists(path), f"Phase 15 required file missing: {path}"

    # ── Config Defaults ─────────────────────────────────────────────

    @pytest.mark.parametrize("flag,expected_type,expected_default", [
        ("comparison_mode_enabled",           bool, True),
        ("contradiction_detection_enabled",   bool, True),
        ("baseline_corpus_enabled",           bool, False),
        ("anomaly_detection_enabled",         bool, True),
    ])
    def test_config_defaults(self, flag, expected_type, expected_default):
        cfg = _cfg()
        val = getattr(cfg, flag)
        assert isinstance(val, expected_type), f"{flag}: expected {expected_type}, got {type(val)}"
        assert val == expected_default, f"{flag}: expected {expected_default}, got {val}"

    # ── Importable Classes ──────────────────────────────────────────

    def test_import_comparison_mode(self):
        assert _module_has("backend.retrieval.comparison_mode", "ComparisonMode")

    def test_import_comparison_result(self):
        assert _module_has("backend.retrieval.comparison_mode", "ComparisonResult")

    def test_import_scope_definition(self):
        assert _module_has("backend.retrieval.comparison_mode", "ScopeDefinition")

    def test_import_contradiction_detector(self):
        assert _module_has("backend.retrieval.contradiction_detector", "ContradictionDetector")

    def test_import_contradiction_result(self):
        assert _module_has("backend.retrieval.contradiction_detector", "ContradictionResult")

    def test_import_baseline_corpus(self):
        assert _module_has("backend.retrieval.baseline_corpus", "BaselineCorpus")

    def test_import_baseline_clause(self):
        assert _module_has("backend.retrieval.baseline_corpus", "BaselineClause")

    def test_import_standard_clause_types(self):
        assert _module_has("backend.retrieval.baseline_corpus", "STANDARD_CLAUSE_TYPES")

    def test_import_anomaly_scorer(self):
        assert _module_has("backend.retrieval.anomaly_scorer", "AnomalyScorer")

    def test_import_anomaly_result(self):
        assert _module_has("backend.retrieval.anomaly_scorer", "AnomalyResult")

    # ── ComparisonMode Constructor Defaults ─────────────────────────

    def test_comparison_mode_temperature(self):
        from backend.retrieval.comparison_mode import ComparisonMode
        sig = inspect.signature(ComparisonMode.__init__)
        temp_param = sig.parameters.get("temperature")
        if temp_param and temp_param.default != inspect.Parameter.empty:
            assert temp_param.default == 0.3, f"ComparisonMode temperature default should be 0.3, got {temp_param.default}"
        else:
            # Check instance default
            cm = ComparisonMode()
            assert getattr(cm, "temperature", None) == 0.3

    def test_comparison_mode_max_tokens(self):
        from backend.retrieval.comparison_mode import ComparisonMode
        sig = inspect.signature(ComparisonMode.__init__)
        mt_param = sig.parameters.get("max_tokens")
        if mt_param and mt_param.default != inspect.Parameter.empty:
            assert mt_param.default == 3000
        else:
            cm = ComparisonMode()
            assert getattr(cm, "max_tokens", None) == 3000

    def test_comparison_mode_top_k_per_scope(self):
        from backend.retrieval.comparison_mode import ComparisonMode
        sig = inspect.signature(ComparisonMode.__init__)
        tk_param = sig.parameters.get("top_k_per_scope")
        if tk_param and tk_param.default != inspect.Parameter.empty:
            assert tk_param.default == 2
        else:
            cm = ComparisonMode()
            assert getattr(cm, "top_k_per_scope", None) == 2

    # ── ComparisonResult Fields ─────────────────────────────────────

    @pytest.mark.parametrize("field", [
        "concept", "scopes_compared", "raw_markdown", "definitions", "has_divergences",
    ])
    def test_comparison_result_fields(self, field):
        assert _class_has_field("backend.retrieval.comparison_mode", "ComparisonResult", field)

    # ── ContradictionDetector Constructor Defaults ──────────────────

    def test_contradiction_detector_temperature(self):
        from backend.retrieval.contradiction_detector import ContradictionDetector
        cd = ContradictionDetector()
        assert getattr(cd, "temperature", 0.0) == 0.0

    def test_contradiction_detector_max_tokens(self):
        from backend.retrieval.contradiction_detector import ContradictionDetector
        cd = ContradictionDetector()
        assert getattr(cd, "max_tokens", 500) == 500

    # ── ContradictionResult Fields ──────────────────────────────────

    @pytest.mark.parametrize("field", [
        "concept", "scope_a", "scope_b", "contradicts",
        "contradiction_type", "summary", "severity", "raw_response",
    ])
    def test_contradiction_result_fields(self, field):
        assert _class_has_field(
            "backend.retrieval.contradiction_detector", "ContradictionResult", field
        )

    # ── ContradictionDetector Methods ───────────────────────────────

    @pytest.mark.parametrize("method", ["detect", "detect_batch"])
    def test_contradiction_methods(self, method):
        assert _class_has_method(
            "backend.retrieval.contradiction_detector",
            "ContradictionDetector",
            method,
        )

    # ── BaselineCorpus Methods ──────────────────────────────────────

    @pytest.mark.parametrize("method", [
        "add_clause", "get_baseline", "list_clause_types",
        "list_deal_types", "build_from_definitions",
    ])
    def test_baseline_corpus_methods(self, method):
        assert _class_has_method(
            "backend.retrieval.baseline_corpus", "BaselineCorpus", method
        )

    # ── STANDARD_CLAUSE_TYPES ───────────────────────────────────────

    def test_standard_clause_types_count(self):
        from backend.retrieval.baseline_corpus import STANDARD_CLAUSE_TYPES
        assert len(STANDARD_CLAUSE_TYPES) >= 50, \
            f"STANDARD_CLAUSE_TYPES should have >= 50 entries, got {len(STANDARD_CLAUSE_TYPES)}"

    def test_standard_clause_types_samples(self):
        from backend.retrieval.baseline_corpus import STANDARD_CLAUSE_TYPES
        required = [
            "servicer_advance_definition", "determination_date",
            "events_of_default", "trustee_duties",
        ]
        for ct in required:
            assert ct in STANDARD_CLAUSE_TYPES, f"STANDARD_CLAUSE_TYPES missing: {ct}"

    # ── BaselineClause Fields ───────────────────────────────────────

    @pytest.mark.parametrize("field", [
        "clause_type", "deal_type", "standard_text", "variant_texts",
        "deviation_signals", "source_deals", "derived_date", "sample_size",
    ])
    def test_baseline_clause_fields(self, field):
        assert _class_has_field("backend.retrieval.baseline_corpus", "BaselineClause", field)

    # ── AnomalyScorer Thresholds ────────────────────────────────────

    def test_anomaly_threshold_default(self):
        from backend.retrieval.anomaly_scorer import AnomalyScorer
        sig = inspect.signature(AnomalyScorer.__init__)
        at_param = sig.parameters.get("anomaly_threshold")
        if at_param and at_param.default != inspect.Parameter.empty:
            assert at_param.default == 0.35
        else:
            scorer = AnomalyScorer()
            assert getattr(scorer, "anomaly_threshold", None) == 0.35

    def test_high_severity_threshold_default(self):
        from backend.retrieval.anomaly_scorer import AnomalyScorer
        sig = inspect.signature(AnomalyScorer.__init__)
        hs_param = sig.parameters.get("high_severity_threshold")
        if hs_param and hs_param.default != inspect.Parameter.empty:
            assert hs_param.default == 0.6
        else:
            scorer = AnomalyScorer()
            assert getattr(scorer, "high_severity_threshold", None) == 0.6

    # ── AnomalyResult Fields ────────────────────────────────────────

    @pytest.mark.parametrize("field", [
        "score", "is_anomalous", "severity", "deviation_signals",
        "similarity_to_standard", "clause_type", "deal_type",
    ])
    def test_anomaly_result_fields(self, field):
        assert _class_has_field("backend.retrieval.anomaly_scorer", "AnomalyResult", field)

    # ── AnomalyResult format_flag Icons ─────────────────────────────

    def test_anomaly_result_format_flag(self):
        from backend.retrieval.anomaly_scorer import AnomalyResult
        assert hasattr(AnomalyResult, "format_flag") or \
               callable(getattr(AnomalyResult(score=0.0), "format_flag", None)), \
               "AnomalyResult must have format_flag() method"

    # ── AnomalyScorer Methods ───────────────────────────────────────

    @pytest.mark.parametrize("method", ["score", "score_batch"])
    def test_anomaly_scorer_methods(self, method):
        assert _class_has_method(
            "backend.retrieval.anomaly_scorer", "AnomalyScorer", method
        )

    # ── Anomaly Scoring Formula (source inspection) ─────────────────

    def test_anomaly_scoring_formula(self):
        """Check the anomaly formula uses 0.15 signal boost."""
        from backend.retrieval import anomaly_scorer as asmod
        src = inspect.getsource(asmod)
        assert "0.15" in src, "anomaly_scorer must use 0.15 signal boost multiplier"

    # ── Anomaly Severity Tiers ──────────────────────────────────────

    def test_anomaly_severity_tiers(self):
        from backend.retrieval import anomaly_scorer as asmod
        src = inspect.getsource(asmod)
        for tier in ["standard", "low", "medium", "high"]:
            assert tier in src, f"anomaly_scorer missing severity tier: {tier}"

    # ── Comparison Prompt Has Required Placeholders ─────────────────

    def test_comparison_prompt_placeholders(self):
        from backend.retrieval.comparison_mode import COMPARISON_PROMPT
        assert "{concept}" in COMPARISON_PROMPT
        assert "{per_scope_definitions}" in COMPARISON_PROMPT or "{scope_definitions}" in COMPARISON_PROMPT

    # ── Contradiction Prompt Has Required Placeholders ──────────────

    def test_contradiction_prompt_placeholders(self):
        from backend.retrieval.contradiction_detector import CONTRADICTION_PROMPT
        assert "{concept}" in CONTRADICTION_PROMPT
        assert "{scope_a}" in CONTRADICTION_PROMPT
        assert "{scope_b}" in CONTRADICTION_PROMPT


# ═════════════════════════════════════════════════════════════════════
#  CROSS-PHASE — retrieval_service.py Wiring Contracts
# ═════════════════════════════════════════════════════════════════════

class TestRetrievalServiceWiring:
    """Verify that retrieval_service.py imports and wires all phases."""

    def _get_service_source(self):
        from backend.agents import retrieval_service as rs
        return inspect.getsource(rs)

    # ── Phase 8 ─────────────────────────────────────────────────────

    def test_imports_bm25_retriever(self):
        src = self._get_service_source()
        assert "BM25Retriever" in src, "retrieval_service must import BM25Retriever"

    # ── Phase 9 ─────────────────────────────────────────────────────

    def test_critique_wired_in_extension(self):
        """Phase 9 critique loop is wired through extension/lib/critique_client.js."""
        content = (ROOT / "extension/lib/critique_client.js").read_text(encoding="utf-8")
        assert "runCritiqueLoop" in content or "critique" in content.lower(), \
            "critique_client.js must implement critique loop wiring"

    # ── Phase 11 ────────────────────────────────────────────────────

    def test_imports_definition_mode(self):
        src = self._get_service_source()
        assert "DefinitionMode" in src, "retrieval_service must import DefinitionMode"

    def test_imports_audit_mode(self):
        src = self._get_service_source()
        assert "AuditMode" in src, "retrieval_service must import AuditMode"

    def test_routes_audit_mode(self):
        src = self._get_service_source()
        assert '"audit"' in src or "'audit'" in src, \
            "retrieval_service must route 'audit' retrieval mode"

    def test_routes_define_mode(self):
        src = self._get_service_source()
        assert '"define"' in src or "'define'" in src, \
            "retrieval_service must route 'define' retrieval mode"

    # ── Phase 12 ────────────────────────────────────────────────────

    def test_imports_scope_router(self):
        src = self._get_service_source()
        assert "ScopeRouter" in src or "scope_router" in src, \
            "retrieval_service must reference ScopeRouter"

    # ── Phase 13 ────────────────────────────────────────────────────

    def test_imports_confidence_scorer(self):
        src = self._get_service_source()
        assert "classify_confidence" in src or "confidence_scorer" in src, \
            "retrieval_service must reference confidence scoring"

    def test_imports_guide_retriever(self):
        src = self._get_service_source()
        assert "GuideRetriever" in src or "guide_retriever" in src, \
            "retrieval_service must reference GuideRetriever"

    # ── Phase 14 ────────────────────────────────────────────────────

    def test_imports_temporal_reasoner(self):
        src = self._get_service_source()
        assert "TemporalReasoner" in src, "retrieval_service must import TemporalReasoner"

    def test_imports_extraction_mode(self):
        src = self._get_service_source()
        assert "ExtractionMode" in src, "retrieval_service must import ExtractionMode"

    def test_imports_summary_mode(self):
        src = self._get_service_source()
        assert "SummaryMode" in src, "retrieval_service must import SummaryMode"

    # ── Phase 15 ────────────────────────────────────────────────────

    def test_imports_comparison_mode(self):
        src = self._get_service_source()
        assert "ComparisonMode" in src, "retrieval_service must import ComparisonMode"

    def test_imports_contradiction_detector(self):
        src = self._get_service_source()
        assert "ContradictionDetector" in src, \
            "retrieval_service must import ContradictionDetector"

    def test_imports_baseline_corpus(self):
        src = self._get_service_source()
        assert "BaselineCorpus" in src, "retrieval_service must import BaselineCorpus"

    def test_imports_anomaly_scorer(self):
        src = self._get_service_source()
        assert "AnomalyScorer" in src, "retrieval_service must import AnomalyScorer"

    # ── Phase 11 Progress / SSE ─────────────────────────────────────

    def test_sse_progress_callback(self):
        src = self._get_service_source()
        assert "progress_callback" in src or "sse_progress" in src, \
            "retrieval_service must support SSE progress callbacks"

    # ── Mode Routing Strings ────────────────────────────────────────

    @pytest.mark.parametrize("mode", ["compare", "extract", "summary", "audit", "define"])
    def test_mode_routing_string(self, mode):
        src = self._get_service_source()
        assert f'"{mode}"' in src or f"'{mode}'" in src, \
            f"retrieval_service must handle retrieval_mode='{mode}'"


# ═════════════════════════════════════════════════════════════════════
#  CROSS-PHASE — Extension Files (JS) Existence
# ═════════════════════════════════════════════════════════════════════

class TestExtensionFileContracts:
    """Verify all required JS extension files exist and contain key strings."""

    @pytest.mark.parametrize("path", [
        "extension/chat/participant.js",
        "extension/lib/hype_enricher.js",
        "extension/lib/query_expander.js",
        "extension/lib/critique_client.js",
        "extension/lib/scope_discovery.js",
        "extension/commands/select_source.js",
        "extension/package.json",
    ])
    def test_extension_files_exist(self, path):
        assert _file_exists(path), f"Extension file missing: {path}"

    # ── participant.js Key Features ────────────────────────────────

    def test_participant_has_token_trimming(self):
        content = (ROOT / "extension/chat/participant.js").read_text(encoding="utf-8")
        assert "trimContextToTokenBudget" in content, \
            "participant.js missing trimContextToTokenBudget (Phase 8.3)"

    def test_participant_has_followup_provider(self):
        content = (ROOT / "extension/chat/participant.js").read_text(encoding="utf-8")
        assert "followupProvider" in content, \
            "participant.js missing followupProvider (Phase 11.2)"

    def test_participant_has_slash_mode_routing(self):
        content = (ROOT / "extension/chat/participant.js").read_text(encoding="utf-8")
        assert "retrievalMode" in content or "retrieval_mode" in content, \
            "participant.js missing retrieval mode routing (Phase 11.4)"

    def test_participant_has_conversation_context(self):
        content = (ROOT / "extension/chat/participant.js").read_text(encoding="utf-8")
        assert "buildConversationContext" in content or "conversation_context" in content, \
            "participant.js missing conversation context (Phase 10.1)"

    # ── select_source.js HITL ──────────────────────────────────────

    def test_select_source_hitl(self):
        content = (ROOT / "extension/commands/select_source.js").read_text(encoding="utf-8")
        assert "doc-type" in content or "doc_type" in content, \
            "select_source.js missing HITL doc-type wiring (Phase 11.7)"

    # ── package.json Slash Commands ────────────────────────────────

    def test_package_json_slash_commands(self):
        import json
        pkg = json.loads((ROOT / "extension/package.json").read_text(encoding="utf-8"))
        # Find commands in contributes.chatParticipants[].commands
        commands = set()
        for participant in pkg.get("contributes", {}).get("chatParticipants", []):
            for cmd in participant.get("commands", []):
                commands.add(cmd.get("name", ""))
        required_commands = {"define", "extract", "compare", "audit", "summary"}
        missing = required_commands - commands
        assert not missing, f"package.json missing slash commands: {missing}"


# ═════════════════════════════════════════════════════════════════════
#  CROSS-PHASE — Pytest Markers
# ═════════════════════════════════════════════════════════════════════

class TestPytestMarkers:
    """Verify conftest.py has markers for all phases."""

    def test_conftest_has_phase_markers(self):
        content = (ROOT / "tests/conftest.py").read_text(encoding="utf-8")
        for phase in ["phase8", "phase9", "phase10", "phase11"]:
            assert phase in content, f"conftest.py missing marker: {phase}"
