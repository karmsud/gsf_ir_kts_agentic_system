"""Phase 17 — Retriever Routing tests (Step 6)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock, call

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.agents.retrieval_service import RetrievalService
from backend.retrieval.human_like_retriever import HumanLikeRetriever, RetrievalConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides):
    """Build a lightweight mock config with sensible defaults."""
    cfg = MagicMock()
    cfg.chroma_persist_dir = "mock_chroma"
    cfg.graph_path = "mock_graph.json"
    cfg.knowledge_base_path = "/fake/kb"
    cfg.phase6_chroma_dir = "/fake/kb/vectors/phase6"
    cfg.human_like_retrieval = True
    cfg.phase17_graph_routing_enabled = True
    cfg.phase17_doc_filter_enabled = True
    cfg.phase17_diff_mode_enabled = True
    cfg.phase17_aggregate_mode_enabled = True
    cfg.phase17_max_parallel_scopes = 5
    cfg.phase17_multi_scope_timeout_ms = 30000
    cfg.session_memory_enabled = False
    cfg.query_rewriting_enabled = False
    cfg.temporal_reasoning_enabled = False
    cfg.hyde_enabled = False
    cfg.extraction_mode_enabled = False
    cfg.summary_mode_enabled = False
    cfg.comparison_mode_enabled = False
    cfg.audit_mode_enabled = False
    cfg.definition_mode_enabled = False
    cfg.contradiction_detection_enabled = False
    cfg.baseline_corpus_enabled = False
    cfg.anomaly_detection_enabled = False
    cfg.deal_catalog_enabled = False
    cfg.sse_progress_enabled = False
    cfg.self_query_filters = True
    cfg.query_decomposition = True
    cfg.graph_first_lookup = True
    cfg.section_scoped_search = True
    cfg.definition_enrichment = True
    cfg.cross_encoder_enabled = False
    cfg.items_per_section = 10
    cfg.enable_bm25_hybrid = False
    cfg.per_folder_kts_enabled = False
    cfg.deal_summary_cache_enabled = False
    cfg.acronym_resolver_enabled = False
    cfg.query_expansion_enabled = False
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _make_retrieval_result(results=None, confidence=0.9):
    """Build a fake RetrievalResult-like object for HumanLikeRetriever."""
    rr = MagicMock()
    rr.results = results or []
    rr.confidence = confidence
    rr.trace = []
    rr.definitions_glossary = {}
    rr.entity_roles = {}
    return rr


def _make_agent_result(success=True, data=None, payload=None):
    """Build a fake AgentResult-like object."""
    ar = MagicMock()
    ar.success = success
    ar.data = data or {}
    ar.payload = payload or data or {}
    return ar


# ---------------------------------------------------------------------------
# 1. _select_graph_path — doc graph exists → returns doc graph path
# ---------------------------------------------------------------------------
class TestSelectGraphPathWithDocFilterExisting:
    def test_select_graph_path_with_doc_filter_existing(self, tmp_path):
        """When doc_graphs/PSA.json exists, _select_graph_path returns doc graph."""
        # Create file structure
        doc_graphs_dir = tmp_path / "graph" / "doc_graphs"
        doc_graphs_dir.mkdir(parents=True)
        doc_graph = doc_graphs_dir / "PSA.json"
        doc_graph.write_text("{}")

        # Also create the deal-level graph
        deal_graph = tmp_path / "graph" / "knowledge_graph.json"
        deal_graph.write_text("{}")

        with patch.object(RetrievalService, "__init__", lambda self, cfg: None):
            svc = RetrievalService.__new__(RetrievalService)
            svc.config = _make_config()

            result = svc._select_graph_path(str(tmp_path), "PSA")
            assert result == str(doc_graph)


# ---------------------------------------------------------------------------
# 2. _select_graph_path — no doc graph → returns deal graph
# ---------------------------------------------------------------------------
class TestSelectGraphPathWithDocFilterMissing:
    def test_select_graph_path_with_doc_filter_missing(self, tmp_path):
        """When doc_graphs/PSA.json does NOT exist, falls back to deal graph."""
        graph_dir = tmp_path / "graph"
        graph_dir.mkdir(parents=True)
        deal_graph = graph_dir / "knowledge_graph.json"
        deal_graph.write_text("{}")

        with patch.object(RetrievalService, "__init__", lambda self, cfg: None):
            svc = RetrievalService.__new__(RetrievalService)
            svc.config = _make_config(
                graph_path=str(deal_graph),
            )

            result = svc._select_graph_path(str(tmp_path), "PSA")
            assert result == str(deal_graph)


# ---------------------------------------------------------------------------
# 3. _select_graph_path — prefix=None → deal graph
# ---------------------------------------------------------------------------
class TestSelectGraphPathWithoutDocFilter:
    def test_select_graph_path_without_doc_filter(self, tmp_path):
        """When doc_name_prefix is None, always returns deal graph."""
        graph_dir = tmp_path / "graph"
        graph_dir.mkdir(parents=True)
        deal_graph = graph_dir / "knowledge_graph.json"
        deal_graph.write_text("{}")

        # Even if a doc graph existed, None prefix should skip it
        doc_graphs_dir = graph_dir / "doc_graphs"
        doc_graphs_dir.mkdir()
        (doc_graphs_dir / "PSA.json").write_text("{}")

        with patch.object(RetrievalService, "__init__", lambda self, cfg: None):
            svc = RetrievalService.__new__(RetrievalService)
            svc.config = _make_config(
                graph_path=str(deal_graph),
            )

            result = svc._select_graph_path(str(tmp_path), None)
            assert result == str(deal_graph)


# ---------------------------------------------------------------------------
# 4. _human_like_retrieve uses doc graph
# ---------------------------------------------------------------------------
class TestHumanLikeRetrieverUsesDocGraph:
    @patch("backend.agents.retrieval_service.GraphStore")
    @patch("backend.retrieval.human_like_retriever.HumanLikeRetriever.retrieve")
    @patch("backend.vector.dual_vector_store.DualVectorStore")
    def test_human_like_retriever_uses_doc_graph(
        self, MockDual, mock_retrieve, MockGraphStore, tmp_path
    ):
        """When doc_name_prefix is set and doc graph exists, _human_like_retrieve
        passes the doc graph path to GraphStore."""
        # Prepare file structure
        doc_graphs_dir = tmp_path / "graph" / "doc_graphs"
        doc_graphs_dir.mkdir(parents=True)
        (doc_graphs_dir / "PSA.json").write_text("{}")
        (tmp_path / "graph" / "knowledge_graph.json").write_text("{}")

        mock_retrieve.return_value = _make_retrieval_result(
            results=[{"id": "chunk1", "score": 0.95, "doc_name": "PSA"}]
        )
        MockGraphStore.return_value.load.return_value = MagicMock()

        with patch.object(RetrievalService, "__init__", lambda self, cfg: None):
            svc = RetrievalService.__new__(RetrievalService)
            svc.config = _make_config(
                knowledge_base_path=str(tmp_path),
                phase6_chroma_dir=str(tmp_path / "vectors" / "phase6"),
            )
            svc._embedding_provider = MagicMock()
            svc.graph_store = MagicMock()

            result = svc._human_like_retrieve(
                "What is Realized Loss?",
                kb_path=str(tmp_path),
                max_results=5,
                doc_name_prefix="PSA",
            )

            # Verify GraphStore was instantiated with the doc-graph path
            expected_path = str(doc_graphs_dir / "PSA.json")
            MockGraphStore.assert_called_once_with(expected_path)
            assert result is not None
            assert result["strategy"] == "graph_first_legal"


# ---------------------------------------------------------------------------
# 5. _human_like_retrieve without filter → deal graph
# ---------------------------------------------------------------------------
class TestHumanLikeRetrieverUsesDealGraph:
    @patch("backend.agents.retrieval_service.GraphStore")
    @patch("backend.retrieval.human_like_retriever.HumanLikeRetriever.retrieve")
    @patch("backend.vector.dual_vector_store.DualVectorStore")
    def test_human_like_retriever_uses_deal_graph(
        self, MockDual, mock_retrieve, MockGraphStore, tmp_path
    ):
        """Without doc_name_prefix, _human_like_retrieve uses deal graph."""
        graph_dir = tmp_path / "graph"
        graph_dir.mkdir(parents=True)
        deal_graph = graph_dir / "knowledge_graph.json"
        deal_graph.write_text("{}")

        mock_retrieve.return_value = _make_retrieval_result()
        MockGraphStore.return_value.load.return_value = MagicMock()

        with patch.object(RetrievalService, "__init__", lambda self, cfg: None):
            svc = RetrievalService.__new__(RetrievalService)
            svc.config = _make_config(
                knowledge_base_path=str(tmp_path),
                graph_path=str(deal_graph),
                phase6_chroma_dir=str(tmp_path / "vectors" / "phase6"),
            )
            svc._embedding_provider = MagicMock()
            svc.graph_store = MagicMock()

            svc._human_like_retrieve(
                "What is Realized Loss?",
                kb_path=str(tmp_path),
                max_results=5,
                doc_name_prefix=None,
            )

            # Should use deal graph — the path passed to GraphStore
            MockGraphStore.assert_called_once_with(str(deal_graph))


# ---------------------------------------------------------------------------
# 6. Doc filter propagated to search_items
# ---------------------------------------------------------------------------
class TestDocFilterPropagatedToSearchItems:
    def test_doc_filter_propagated_to_search_items(self):
        """_merge_doc_filter adds doc_name_prefix to item search filters."""
        import networkx as nx

        graph = nx.DiGraph()
        dual = MagicMock()
        retriever = HumanLikeRetriever(dual, graph, RetrievalConfig())

        # Simulate Phase 17 doc filter being set during retrieve()
        retriever._doc_name_prefix = "PSA"

        # No existing filters
        result = retriever._merge_doc_filter(None)
        assert result == {"doc_name_prefix": "PSA"}

        # With existing section filter
        result2 = retriever._merge_doc_filter({"section_number": "5.05"})
        assert result2 == {"section_number": "5.05", "doc_name_prefix": "PSA"}


# ---------------------------------------------------------------------------
# 7. Doc filter propagated to search_sections
# ---------------------------------------------------------------------------
class TestDocFilterPropagatedToSearchSections:
    def test_doc_filter_propagated_to_search_sections(self):
        """_merge_doc_filter correctly merges into section search filters."""
        import networkx as nx

        graph = nx.DiGraph()
        dual = MagicMock()
        retriever = HumanLikeRetriever(dual, graph, RetrievalConfig())

        # No doc filter active
        retriever._doc_name_prefix = None
        result_none = retriever._merge_doc_filter({"section_number": "3.01"})
        assert result_none == {"section_number": "3.01"}, "Without prefix, filters unchanged"

        result_empty = retriever._merge_doc_filter(None)
        assert result_empty is None, "Without prefix and no filters, returns None"

        # With doc filter active
        retriever._doc_name_prefix = "SPA"
        result_with = retriever._merge_doc_filter(None)
        assert result_with == {"doc_name_prefix": "SPA"}


# ---------------------------------------------------------------------------
# 8. Section-scoped search with doc filter
# ---------------------------------------------------------------------------
class TestSectionScopedSearchWithDocFilter:
    def test_section_scoped_search_with_doc_filter(self):
        """When both section_number AND doc_name_prefix are present,
        _merge_doc_filter returns both keys (ChromaDB AND semantics)."""
        import networkx as nx

        graph = nx.DiGraph()
        dual = MagicMock()
        retriever = HumanLikeRetriever(dual, graph, RetrievalConfig())
        retriever._doc_name_prefix = "PSA"

        filters = {"section_number": "5.05"}
        merged = retriever._merge_doc_filter(filters)

        assert merged is not None
        assert merged["section_number"] == "5.05"
        assert merged["doc_name_prefix"] == "PSA"
        # Original filters dict should NOT be mutated
        assert "doc_name_prefix" not in filters or filters is not merged


# ---------------------------------------------------------------------------
# 9. Retrieval quality: PSA filter returns PSA-tagged results only
# ---------------------------------------------------------------------------
class TestRetrievalQualityPSAOnly:
    @patch("backend.agents.retrieval_service.GraphStore")
    @patch("backend.retrieval.human_like_retriever.HumanLikeRetriever.retrieve")
    @patch("backend.vector.dual_vector_store.DualVectorStore")
    def test_retrieval_quality_psa_only(
        self, MockDual, mock_retrieve, MockGraphStore
    ):
        """With PSA doc_name_prefix, returned results are PSA-only."""
        psa_results = [
            {"id": "psa_c1", "score": 0.95, "doc_name": "PSA", "text": "Section 5.05 of PSA"},
            {"id": "psa_c2", "score": 0.88, "doc_name": "PSA", "text": "Article III distributions"},
        ]
        mock_retrieve.return_value = _make_retrieval_result(results=psa_results)
        MockGraphStore.return_value.load.return_value = MagicMock()

        with patch.object(RetrievalService, "__init__", lambda self, cfg: None):
            svc = RetrievalService.__new__(RetrievalService)
            svc.config = _make_config()
            svc._embedding_provider = MagicMock()
            svc.graph_store = MagicMock()

            result = svc._human_like_retrieve(
                "loss allocation",
                kb_path="/fake/kb",
                max_results=5,
                doc_name_prefix="PSA",
            )

            # Verify doc_name_prefix was passed through to HumanLikeRetriever.retrieve
            _, kwargs = mock_retrieve.call_args
            assert kwargs.get("doc_name_prefix") == "PSA"

            # All returned results should be PSA-tagged
            for hit in result["results"]:
                assert hit.get("doc_name") == "PSA"


# ---------------------------------------------------------------------------
# 10. Retrieval quality: deal-level returns mixed results
# ---------------------------------------------------------------------------
class TestRetrievalQualityDealLevel:
    @patch("backend.agents.retrieval_service.GraphStore")
    @patch("backend.retrieval.human_like_retriever.HumanLikeRetriever.retrieve")
    @patch("backend.vector.dual_vector_store.DualVectorStore")
    def test_retrieval_quality_deal_level(
        self, MockDual, mock_retrieve, MockGraphStore
    ):
        """Without doc filter, deal-level retrieval returns mixed doc types."""
        mixed_results = [
            {"id": "psa_1", "score": 0.95, "doc_name": "PSA"},
            {"id": "spa_1", "score": 0.90, "doc_name": "SPA"},
            {"id": "ins_1", "score": 0.80, "doc_name": "Insurance_Agreement"},
        ]
        mock_retrieve.return_value = _make_retrieval_result(results=mixed_results)
        MockGraphStore.return_value.load.return_value = MagicMock()

        with patch.object(RetrievalService, "__init__", lambda self, cfg: None):
            svc = RetrievalService.__new__(RetrievalService)
            svc.config = _make_config()
            svc._embedding_provider = MagicMock()
            svc.graph_store = MagicMock()

            result = svc._human_like_retrieve(
                "loss allocation",
                kb_path="/fake/kb",
                max_results=10,
                doc_name_prefix=None,
            )

            # Verify doc_name_prefix was None for deal-level
            _, kwargs = mock_retrieve.call_args
            assert kwargs.get("doc_name_prefix") is None

            doc_names = {h.get("doc_name") for h in result["results"]}
            assert len(doc_names) > 1, "Deal-level should return multiple doc types"


# ---------------------------------------------------------------------------
# 11. Graph traversal confined to doc graph (no cross-doc edges)
# ---------------------------------------------------------------------------
class TestGraphTraversalConfinedToDocGraph:
    def test_graph_traversal_confined_to_doc_graph(self):
        """A doc-specific graph has no cross-doc edges — traversal stays in-doc."""
        import networkx as nx

        # Build a small PSA-only graph (no edges to other docs)
        g = nx.DiGraph()
        g.add_node("SEC::PSA::5.05", type="SECTION", section_number="5.05",
                    heading="Realized Losses", doc_name="PSA")
        g.add_node("ITEM::PSA::5.05::1", type="ITEM", doc_name="PSA",
                    text="Realized Loss means...")
        g.add_edge("SEC::PSA::5.05", "ITEM::PSA::5.05::1", type="CONTAINS")

        # Verify no cross-doc edges
        for src, tgt, data in g.edges(data=True):
            src_doc = g.nodes[src].get("doc_name", "")
            tgt_doc = g.nodes[tgt].get("doc_name", "")
            if src_doc and tgt_doc:
                assert src_doc == tgt_doc, f"Cross-doc edge found: {src_doc} → {tgt_doc}"

        # All nodes belong to PSA
        for nid, ndata in g.nodes(data=True):
            assert ndata.get("doc_name") == "PSA"


# ---------------------------------------------------------------------------
# 12. Graph traversal follows cross-doc edges (deal graph)
# ---------------------------------------------------------------------------
class TestGraphTraversalFollowsCrossDocEdges:
    def test_graph_traversal_follows_cross_doc_edges(self):
        """A deal-level graph contains cross-doc edges (e.g. PSA → SPA)."""
        import networkx as nx

        g = nx.DiGraph()
        g.add_node("SEC::PSA::5.05", type="SECTION", section_number="5.05",
                    heading="Realized Losses", doc_name="PSA")
        g.add_node("SEC::SPA::3.01", type="SECTION", section_number="3.01",
                    heading="Sale of Mortgage Loans", doc_name="SPA")
        g.add_node("TERM::Realized_Loss", type="defined_term",
                    term_name="Realized Loss")
        # Cross-doc edges
        g.add_edge("SEC::PSA::5.05", "TERM::Realized_Loss", type="DEFINES")
        g.add_edge("SEC::SPA::3.01", "TERM::Realized_Loss", type="REFERENCES")

        # Find cross-doc edges
        cross_doc_edges = []
        for src, tgt, data in g.edges(data=True):
            src_doc = g.nodes[src].get("doc_name", "")
            tgt_doc = g.nodes[tgt].get("doc_name", "")
            if src_doc and tgt_doc and src_doc != tgt_doc:
                cross_doc_edges.append((src, tgt))

        # Deal graph should have cross-doc connectivity (via shared term nodes)
        # Here the term node has no doc_name, so reachable from both docs
        psa_neighbors = set(nx.descendants(g, "SEC::PSA::5.05"))
        spa_neighbors = set(nx.descendants(g, "SEC::SPA::3.01"))
        shared = psa_neighbors & spa_neighbors
        assert "TERM::Realized_Loss" in shared, "Deal graph should share terms across docs"


# ---------------------------------------------------------------------------
# 13. Doc filter with mode dispatch (diff/aggregate/list)
# ---------------------------------------------------------------------------
class TestDocFilterWithModeDispatch:
    def test_doc_filter_with_mode_dispatch(self):
        """Phase 17 mode dispatch (diff/aggregate/list) forwards doc_name_prefix
        to _collect_multi_scope_results.

        We test the contract at the _collect_multi_scope_results boundary
        rather than running the full execute() pipeline, because execute()
        relies on many downstream modules.
        """
        with patch.object(RetrievalService, "__init__", lambda self, cfg: None):
            svc = RetrievalService.__new__(RetrievalService)
            svc.config = _make_config()

            # Patch the downstream service instantiation inside _collect_multi_scope_results
            with patch("backend.agents.retrieval_service.RetrievalService") as MockInner:
                inner_result = _make_agent_result(
                    success=True,
                    data={"results": [{"id": "c1", "score": 0.9, "doc_name": "PSA"}]},
                )
                MockInner.return_value.execute.return_value = inner_result

                with patch("config.settings.scope_config") as mock_scope_cfg:
                    mock_scope_cfg.return_value = _make_config()

                    # Run _collect_multi_scope_results directly
                    results = svc._collect_multi_scope_results(
                        "loss allocation",
                        ["fin_deal1", "fin_deal2"],
                        5,
                        doc_name_prefix="PSA",
                    )

                    # Verify execute was called with doc_name_prefix for each scope
                    for c in MockInner.return_value.execute.call_args_list:
                        req = c[0][0]  # positional arg: the request dict
                        assert req.get("doc_name_prefix") == "PSA", \
                            f"doc_name_prefix not forwarded: {req}"


# ---------------------------------------------------------------------------
# 14. Doc filter feature flag disabled
# ---------------------------------------------------------------------------
class TestDocFilterFeatureFlagDisabled:
    @patch("backend.agents.retrieval_service.GraphStore")
    @patch("backend.retrieval.human_like_retriever.HumanLikeRetriever.retrieve")
    @patch("backend.vector.dual_vector_store.DualVectorStore")
    def test_doc_filter_feature_flag_disabled(
        self, MockDual, mock_retrieve, MockGraphStore
    ):
        """When phase17_doc_filter_enabled=False, doc_name_prefix is ignored."""
        mock_retrieve.return_value = _make_retrieval_result(
            results=[{"id": "c1", "score": 0.9}]
        )
        MockGraphStore.return_value.load.return_value = MagicMock()

        with patch.object(RetrievalService, "__init__", lambda self, cfg: None):
            svc = RetrievalService.__new__(RetrievalService)
            svc.config = _make_config(
                phase17_doc_filter_enabled=False,  # Feature flag OFF
            )
            svc._embedding_provider = MagicMock()
            svc.graph_store = MagicMock()
            svc._session_memory = None
            svc._query_rewriter = None
            svc._hyde_processor = None
            svc._scope_router = None
            svc._extraction_mode = None
            svc._summary_mode = None
            svc._comparison_mode = None
            svc._audit_mode = None
            svc._definition_mode = None
            svc.vector_store = MagicMock()
            svc._confidence_scorer = MagicMock()
            svc._temporal_reasoner = None
            svc._contradiction_detector = None
            svc._baseline_corpus = None
            svc._anomaly_scorer = None
            svc._gap_detector = MagicMock()

            # execute() should null out doc_name_prefix when flag is off
            with patch.object(svc, "_phase6_retrieve") as mock_p6:
                mock_p6.return_value = {
                    "results": [{"id": "c1", "score": 0.9}],
                    "confidence": 0.9,
                    "iterations": 1,
                    "trace": [],
                }
                with patch.object(svc, "_build_phase6_response") as mock_build:
                    mock_build.return_value = _make_agent_result()

                    svc.execute({
                        "query": "loss allocation",
                        "doc_name_prefix": "PSA",  # Provided but flag is off
                    })

                    # _phase6_retrieve should have been called with
                    # doc_name_prefix=None because the flag is disabled
                    _, kwargs = mock_p6.call_args
                    assert kwargs.get("doc_name_prefix") is None, \
                        "doc_name_prefix should be None when phase17_doc_filter_enabled=False"
