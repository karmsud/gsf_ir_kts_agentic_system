"""Phase 17 — Regression tests."""
from __future__ import annotations
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.common.scope_resolver import parse_command, resolve_scopes, ScopeExpr, ParsedCommand
from config.settings import KTSConfig
from backend.agents.diff_engine import DiffEngine
from backend.agents.aggregation_engine import AggregationEngine


# ── 1. No scope / no filter — plain text unchanged ──────────

class TestNoScopeNoFilterUnchanged:
    def test_no_scope_no_filter_unchanged(self):
        cmd = parse_command("What is Distribution Date?")
        assert cmd.mode == "search"
        assert cmd.scopes == []
        assert cmd.query == "What is Distribution Date?"


# ── 2. Single scope no filter — backward compatible ─────────

class TestSingleScopeNoFilterUnchanged:
    def test_single_scope_no_filter_unchanged(self):
        cmd = parse_command("/fin_deal1 What is Distribution Date?")
        assert cmd.mode == "search"
        assert len(cmd.scopes) == 1
        assert cmd.scopes[0].slug == "fin_deal1"
        assert cmd.scopes[0].doc_filter is None
        assert cmd.query == "What is Distribution Date?"


# ── 3. Compare mode backward compatible ─────────────────────

class TestCompareModeBackwardCompatible:
    def test_compare_mode_backward_compatible(self):
        cmd = parse_command("/compare /fin_deal1 /fin_deal2 What is Distribution Date?")
        assert cmd.mode == "compare"
        assert len(cmd.scopes) == 2
        slugs = [s.slug for s in cmd.scopes]
        assert "fin_deal1" in slugs
        assert "fin_deal2" in slugs
        assert cmd.query == "What is Distribution Date?"


# ── 4. Graph builder without prefix → attr is "" ────────────

class TestGraphWithoutPrefixDefaultEmpty:
    def test_graph_without_prefix_default_empty(self):
        """build_hierarchical_graph without prefix → doc_name_prefix attr is ''."""
        from backend.graph.enhanced_graph_builder import EnhancedGraphBuilder

        mock_store = MagicMock()
        import networkx as nx
        mock_store.load.return_value = nx.DiGraph()
        mock_store.save = MagicMock()

        builder = EnhancedGraphBuilder(mock_store)
        sections = [
            {
                "section_number": "1",
                "section_heading": "Test Section",
                "section_text": "Some text for testing purposes.",
            }
        ]
        # Call with default doc_name_prefix (should be "")
        stats = builder.build_hierarchical_graph(
            document_id="test_doc",
            doc_type="PSA",
            sections=sections,
            doc_name_prefix="",
        )
        # Verify the graph was loaded/saved and doc node has empty prefix
        G = mock_store.load.return_value
        doc_node = "doc:test_doc"
        assert doc_node in G.nodes
        assert G.nodes[doc_node].get("doc_name_prefix") == ""


# ── 5. Config phase17 flags default True ─────────────────────

class TestConfigPhase17FlagsDefaultTrue:
    def test_config_phase17_flags_default_true(self):
        """All phase17_* config flags default to True."""
        cfg = KTSConfig()
        assert cfg.phase17_doc_filter_enabled is True
        assert cfg.phase17_dual_graph_enabled is True
        assert cfg.phase17_rich_catalog_enabled is True
        assert cfg.phase17_scope_resolver_enabled is True
        assert cfg.phase17_graph_routing_enabled is True
        assert cfg.phase17_multi_deal_enabled is True
        assert cfg.phase17_diff_mode_enabled is True
        assert cfg.phase17_aggregate_mode_enabled is True


# ── 6. _merge_doc_filter noop when no prefix ────────────────

class TestMergeDocFilterNoopWhenNoPrefix:
    def test_merge_doc_filter_noop_when_no_prefix(self):
        """_merge_doc_filter returns None when no doc_name_prefix is set."""
        from backend.retrieval.human_like_retriever import HumanLikeRetriever

        # Create a minimal mock retriever without full init
        retriever = object.__new__(HumanLikeRetriever)
        # No _doc_name_prefix attribute → should return filters as-is
        result = retriever._merge_doc_filter(None)
        assert result is None

        # With an existing filter but no prefix
        result = retriever._merge_doc_filter({"doc_type": "PSA"})
        assert result == {"doc_type": "PSA"}

        # Now set a prefix and verify it merges
        retriever._doc_name_prefix = "PSA"
        result = retriever._merge_doc_filter(None)
        assert result == {"doc_name_prefix": "PSA"}

        result = retriever._merge_doc_filter({"doc_type": "legal"})
        assert result == {"doc_type": "legal", "doc_name_prefix": "PSA"}


# ── 7. Scope resolver handles empty input ────────────────────

class TestScopeResolverHandlesEmptyInput:
    def test_scope_resolver_handles_empty_input(self):
        """parse_command('') → no crash, sensible defaults."""
        cmd = parse_command("")
        assert cmd.mode == "search"
        assert cmd.scopes == []
        assert cmd.query == ""

    def test_scope_resolver_handles_whitespace(self):
        cmd = parse_command("   ")
        assert cmd.mode == "search"
        assert cmd.scopes == []


# ── 8. DiffEngine empty input ────────────────────────────────

class TestDiffEngineEmptyInput:
    def test_diff_engine_empty_input(self):
        """DiffEngine.diff with empty dict → graceful."""
        engine = DiffEngine()
        result = engine.diff({}, "test query")
        assert result["query"] == "test query"
        assert result["diffs"] == []
        assert result["common"] == []
        assert "Need at least 2" in result["summary"]
        assert result["scope_count"] == 0

    def test_diff_engine_single_scope(self):
        """DiffEngine.diff with 1 scope → graceful message."""
        engine = DiffEngine()
        result = engine.diff(
            {"fin_deal1/PSA": [{"text": "some text"}]},
            "test query",
        )
        assert result["scope_count"] == 1
        assert "Need at least 2" in result["summary"]


# ── 9. AggregationEngine empty input ─────────────────────────

class TestAggregationEngineEmptyInput:
    def test_aggregation_engine_empty_input(self):
        """AggregationEngine.aggregate with empty dict → graceful."""
        engine = AggregationEngine()
        result = engine.aggregate({}, "test query")
        assert result["query"] == "test query"
        assert result["pattern"] == ""
        assert result["outliers"] == []
        assert result["confidence"] == 0.0
        assert result["deal_count"] == 0
        assert "Need at least 2" in result["summary"]

    def test_aggregation_engine_single_scope(self):
        engine = AggregationEngine()
        result = engine.aggregate(
            {"fin_deal1": [{"text": "some text"}]},
            "test query",
        )
        assert result["deal_count"] == 1
        assert "Need at least 2" in result["summary"]


# ── 10. Deal catalog migration noop on fresh DB ─────────────

class TestDealCatalogMigrationNoopOnFreshDB:
    def test_deal_catalog_migration_noop_on_fresh_db(self):
        """Fresh catalog has Phase 17 columns after init."""
        import sqlite3
        from backend.vector.deal_catalog import DealCatalog

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_catalog.db")
            catalog = DealCatalog(db_path=db_path)

            # Check the table has Phase 17 columns
            conn = sqlite3.connect(db_path)
            try:
                cursor = conn.execute("PRAGMA table_info(deal_catalog)")
                columns = {row[1] for row in cursor.fetchall()}
                # Phase 17 columns that should exist
                assert "deal_name" in columns
                assert "vintage" in columns
                assert "series" in columns
                assert "chunk_count" in columns
                assert "status" in columns
                # Original columns should still be there
                assert "folder_name" in columns
                assert "slug" in columns
                assert "kts_path" in columns
                assert "doc_count" in columns
                assert "doc_types" in columns
            finally:
                conn.close()
