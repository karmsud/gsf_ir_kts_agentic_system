"""
Phase 13.5 — Regime-Aware Retrieval Routing Tests.

Verifies:
 - _resolve_corpus_regime() picks config > graph > default
 - _should_use_guide_strategy() correctly branches by regime + intent
 - GuideRetriever pipeline runs without error on trivial inputs
 - HumanLikeRetriever is still selected for legal corpora
"""

from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

import networkx as nx


# ---------------------------------------------------------------------------
# Helpers — minimal mock config and service
# ---------------------------------------------------------------------------

def _make_config(**overrides):
    """Return a namespace-like config with sane defaults."""
    defaults = {
        "chroma_persist_dir": "/tmp/kts_test_chroma",
        "graph_path": "/tmp/kts_test_graph.json",
        "knowledge_base_path": "/tmp/kts_test_kb",
        "phase6_chroma_dir": "/tmp/kts_test_chroma/phase6",
        "human_like_retrieval": True,
        "regime_aware_retrieval": True,
        "corpus_regime_override": "",
        # Optional guide-specific knobs
        "guide_items_top_k": 60,
        "guide_sections_top_k": 20,
        "guide_graph_expansion": True,
        "guide_bfs_depth": 4,
        "guide_error_code_boost": 0.35,
        "guide_step_ordering": True,
        # Standard knobs
        "cross_encoder_enabled": True,
        "query_decomposition": True,
        "self_query_filters": True,
        "graph_first_lookup": True,
        "section_scoped_search": True,
        "definition_enrichment": True,
        "items_per_section": 10,
    }
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def _make_graph(corpus_regime: str = "MIXED") -> nx.DiGraph:
    """Return a tiny graph with corpus_regime set."""
    g = nx.DiGraph()
    g.graph["corpus_regime"] = corpus_regime
    # Add one section, one item, one error_code node for BFS tests
    g.add_node("sec:1.01", type="SECTION", section_number="1.01", heading="Overview")
    g.add_node("item:1", type="ITEM", text="Step 1: restart", chunk_index=0,
               document_id="doc1", item_type="STEP")
    g.add_node("err:AUTH401", type="ERROR_CODE", name="AUTH401")
    g.add_edge("sec:1.01", "item:1", type="CONTAINS")
    g.add_edge("item:1", "err:AUTH401", type="REFERENCES")
    return g


# ---------------------------------------------------------------------------
# _resolve_corpus_regime
# ---------------------------------------------------------------------------

class TestResolveCorpusRegime:
    """Unit tests for regime resolution priority."""

    def test_config_override_wins(self):
        from backend.agents.retrieval_service import RetrievalService

        cfg = _make_config(corpus_regime_override="GOVERNING_DOC_LEGAL")
        svc = object.__new__(RetrievalService)
        svc.config = cfg
        svc.graph_store = MagicMock()
        svc.graph_store.load.return_value = _make_graph("GENERIC_GUIDE")

        assert svc._resolve_corpus_regime() == "GOVERNING_DOC_LEGAL"

    def test_graph_metadata_used_when_no_override(self):
        from backend.agents.retrieval_service import RetrievalService

        cfg = _make_config(corpus_regime_override="")
        svc = object.__new__(RetrievalService)
        svc.config = cfg
        svc.graph_store = MagicMock()
        svc.graph_store.load.return_value = _make_graph("GENERIC_GUIDE")

        assert svc._resolve_corpus_regime() == "GENERIC_GUIDE"

    def test_defaults_to_mixed(self):
        from backend.agents.retrieval_service import RetrievalService

        cfg = _make_config(corpus_regime_override="")
        svc = object.__new__(RetrievalService)
        svc.config = cfg
        svc.graph_store = MagicMock()
        svc.graph_store.load.return_value = _make_graph("")

        assert svc._resolve_corpus_regime() == "MIXED"


# ---------------------------------------------------------------------------
# _should_use_guide_strategy
# ---------------------------------------------------------------------------

class TestShouldUseGuideStrategy:
    """Unit tests for the regime + intent routing decision."""

    def _make_svc(self, **cfg_overrides):
        from backend.agents.retrieval_service import RetrievalService

        svc = object.__new__(RetrievalService)
        svc.config = _make_config(**cfg_overrides)
        return svc

    def test_legal_regime_always_graph_first(self):
        svc = self._make_svc()
        assert svc._should_use_guide_strategy("how do I fix error X", "GOVERNING_DOC_LEGAL") is False

    def test_guide_regime_always_vector_first(self):
        svc = self._make_svc()
        assert svc._should_use_guide_strategy("what does PSA mean?", "GENERIC_GUIDE") is True

    def test_mixed_regime_legal_intent_goes_graph_first(self):
        svc = self._make_svc()
        # "pooling and servicing agreement" triggers governing_doc intent
        assert svc._should_use_guide_strategy(
            "what are the servicer obligations under the PSA", "MIXED"
        ) is False

    def test_mixed_regime_troubleshoot_intent_goes_vector_first(self):
        svc = self._make_svc()
        assert svc._should_use_guide_strategy(
            "how do I fix error AUTH401 in the upload module", "MIXED"
        ) is True

    def test_mixed_regime_general_intent_goes_vector_first(self):
        svc = self._make_svc()
        assert svc._should_use_guide_strategy("what is a good practice for logging", "MIXED") is True

    def test_feature_flag_disabled_always_graph_first(self):
        svc = self._make_svc(regime_aware_retrieval=False)
        # Even GENERIC_GUIDE regime should not trigger guide path when flag is off
        assert svc._should_use_guide_strategy("error AUTH401", "GENERIC_GUIDE") is False


# ---------------------------------------------------------------------------
# GuideRetriever — basic smoke test
# ---------------------------------------------------------------------------

class TestGuideRetriever:
    """Smoke tests for the GuideRetriever pipeline."""

    def test_empty_store_returns_zero_confidence(self):
        from backend.retrieval.guide_retriever import GuideRetriever, GuideRetrievalConfig

        dual = MagicMock()
        dual.search_items.return_value = []
        dual.search_sections.return_value = []

        graph = _make_graph("GENERIC_GUIDE")
        cfg = GuideRetrievalConfig(use_cross_encoder=False)
        retriever = GuideRetriever(dual, graph, cfg)
        result = retriever.retrieve("fix AUTH401 error")

        assert result.confidence == 0.0
        assert result.results == []
        assert result.strategy == "vector_first_guide"

    def test_error_code_boost_applied(self):
        from backend.retrieval.guide_retriever import GuideRetriever, GuideRetrievalConfig

        dual = MagicMock()
        dual.search_items.return_value = [
            {"id": "c1", "text": "If you see AUTH401, restart the service.", "similarity": 0.6,
             "metadata": {"document_id": "doc1", "chunk_index": 0}},
            {"id": "c2", "text": "Configure logging for performance.", "similarity": 0.65,
             "metadata": {"document_id": "doc2", "chunk_index": 0}},
        ]
        dual.search_sections.return_value = []

        graph = _make_graph("GENERIC_GUIDE")
        cfg = GuideRetrievalConfig(
            use_cross_encoder=False,
            graph_expansion_enabled=False,
            error_code_boost=0.35,
        )
        retriever = GuideRetriever(dual, graph, cfg)
        result = retriever.retrieve("AUTH401 error fix")

        # c1 mentions AUTH401, so it should get boosted above c2
        assert len(result.results) >= 2
        top_id = result.results[0].get("id")
        assert top_id == "c1", f"Expected c1 at top after error-code boost, got {top_id}"

    def test_step_sequence_ordering(self):
        from backend.retrieval.guide_retriever import GuideRetriever, GuideRetrievalConfig

        dual = MagicMock()
        # Two chunks from same doc, chunk_index 2 ranked higher by similarity
        dual.search_items.return_value = [
            {"id": "c2", "text": "Step 2: verify.", "similarity": 0.8,
             "metadata": {"document_id": "doc1", "chunk_index": 2}},
            {"id": "c1", "text": "Step 1: restart.", "similarity": 0.75,
             "metadata": {"document_id": "doc1", "chunk_index": 1}},
        ]
        dual.search_sections.return_value = []

        graph = _make_graph()
        cfg = GuideRetrievalConfig(
            use_cross_encoder=False,
            graph_expansion_enabled=False,
            step_sequence_ordering=True,
        )
        retriever = GuideRetriever(dual, graph, cfg)
        result = retriever.retrieve("restart procedure")

        # After step-sequence ordering, chunk_index 1 should come before 2
        assert result.results[0]["id"] == "c1"
        assert result.results[1]["id"] == "c2"


# ---------------------------------------------------------------------------
# Integration: _phase6_retrieve routes correctly
# ---------------------------------------------------------------------------

class TestPhase6RegimeRouting:
    """Verify _phase6_retrieve calls the right strategy based on regime."""

    def _make_svc(self, corpus_regime: str, **cfg_overrides):
        from backend.agents.retrieval_service import RetrievalService

        svc = object.__new__(RetrievalService)
        svc.config = _make_config(**cfg_overrides)
        svc.graph_store = MagicMock()
        svc.graph_store.load.return_value = _make_graph(corpus_regime)
        svc._embedding_provider = MagicMock()
        svc.vector_store = MagicMock()
        svc._hyde_processor = None  # Phase 13.4: HyDE off by default in test
        return svc

    @patch("backend.agents.retrieval_service.RetrievalService._human_like_retrieve")
    @patch("backend.agents.retrieval_service.RetrievalService._guide_retrieve")
    def test_legal_corpus_routes_to_human_like(self, mock_guide, mock_human):
        mock_human.return_value = {"results": [], "confidence": 0.0, "iterations": 1, "trace": []}
        svc = self._make_svc("GOVERNING_DOC_LEGAL")

        svc._phase6_retrieve("what is the Determination Date")

        mock_human.assert_called_once()
        mock_guide.assert_not_called()

    @patch("backend.agents.retrieval_service.RetrievalService._human_like_retrieve")
    @patch("backend.agents.retrieval_service.RetrievalService._guide_retrieve")
    def test_guide_corpus_routes_to_guide(self, mock_guide, mock_human):
        mock_guide.return_value = {"results": [], "confidence": 0.0, "iterations": 1, "trace": []}
        svc = self._make_svc("GENERIC_GUIDE")

        svc._phase6_retrieve("how to fix AUTH401")

        mock_guide.assert_called_once()
        mock_human.assert_not_called()

    @patch("backend.agents.retrieval_service.RetrievalService._human_like_retrieve")
    @patch("backend.agents.retrieval_service.RetrievalService._guide_retrieve")
    def test_mixed_corpus_troubleshoot_routes_to_guide(self, mock_guide, mock_human):
        mock_guide.return_value = {"results": [], "confidence": 0.0, "iterations": 1, "trace": []}
        svc = self._make_svc("MIXED")

        svc._phase6_retrieve("error AUTH401 in upload module")

        mock_guide.assert_called_once()
        mock_human.assert_not_called()

    @patch("backend.agents.retrieval_service.RetrievalService._human_like_retrieve")
    @patch("backend.agents.retrieval_service.RetrievalService._guide_retrieve")
    def test_mixed_corpus_legal_query_routes_to_human_like(self, mock_guide, mock_human):
        mock_human.return_value = {"results": [], "confidence": 0.0, "iterations": 1, "trace": []}
        svc = self._make_svc("MIXED")

        svc._phase6_retrieve("what are the servicer obligations under the PSA")

        mock_human.assert_called_once()
        mock_guide.assert_not_called()

    @patch("backend.agents.retrieval_service.RetrievalService._human_like_retrieve")
    @patch("backend.agents.retrieval_service.RetrievalService._guide_retrieve")
    def test_feature_flag_disabled_always_human_like(self, mock_guide, mock_human):
        mock_human.return_value = {"results": [], "confidence": 0.0, "iterations": 1, "trace": []}
        svc = self._make_svc("GENERIC_GUIDE", regime_aware_retrieval=False)

        svc._phase6_retrieve("error AUTH401")

        mock_human.assert_called_once()
        mock_guide.assert_not_called()
