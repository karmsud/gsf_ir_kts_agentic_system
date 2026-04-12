"""
Pre-Build Validation Suite — comprehensive gate test run before packaging.

This file aggregates all Phase 17 features plus core pipeline checks into a
single pytest module.  Run it via:

    pytest tests/test_prebuild_suite.py -v

Or through the F5 "Test: Pre-Build Validation Suite" launch config.

Structure:
  1. Module import checks   — every new Phase 17 module loads without error
  2. Config flag checks     — all feature flags exist and default correctly
  3. Core subsystem smoke   — scope resolver, partitioner, catalog, diff/agg
  4. CLI surface checks     — new options parse correctly
  5. Extension JS parity    — JS test runner invoked (optional, skip if node missing)
  6. Regression guard       — non-Phase-17 modules still import cleanly
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ═══════════════════════════════════════════════════════════════
#  1. Module Import Checks
# ═══════════════════════════════════════════════════════════════

class TestModuleImports:
    """Every Phase 17 module must import without errors."""

    @pytest.mark.prebuild
    @pytest.mark.parametrize("mod", [
        # ── Phase 17 modules ──────────────────────────────────────
        "backend.common.scope_resolver",
        "backend.graph.graph_partitioner",
        "backend.agents.diff_engine",
        "backend.agents.aggregation_engine",
        "backend.vector.deal_catalog",
        "backend.agents.retrieval_service",
        "backend.retrieval.human_like_retriever",
        "backend.graph.enhanced_graph_builder",
        "backend.graph.builder",
        "backend.agents.ingestion_agent",
        "config.settings",
        "cli.main",
        # ── ABS modules (Phases 21–23) ────────────────────────────
        "backend.abs.orchestrator",
        "backend.abs.deal_scope",
        "backend.abs.deal_manifest",
        "backend.abs.llm_bridge",
        "backend.abs.ipc_protocol",
        "backend.abs.streaming",
        "backend.abs.agents.ingestion_pipeline_agent",
        "backend.abs.agents.model_creation_agent",
        "backend.abs.agents.model_auditor_agent",
        "backend.abs.agents.qa_agent",
        "backend.abs.agents.cashflow_projection_agent",
        "backend.abs.agents.stress_testing_agent",
        "cli.abs",
    ])
    def test_import(self, mod):
        m = importlib.import_module(mod)
        assert m is not None


# ═══════════════════════════════════════════════════════════════
#  2. Config Flag Checks
# ═══════════════════════════════════════════════════════════════

class TestConfigFlags:
    """All Phase 17 feature flags must exist and default to their expected values."""

    @pytest.fixture(autouse=True)
    def cfg(self):
        from config.settings import load_config
        self.config = load_config(ROOT)

    BOOL_FLAGS = [
        "phase17_doc_filter_enabled",
        "phase17_dual_graph_enabled",
        "phase17_rich_catalog_enabled",
        "phase17_scope_resolver_enabled",
        "phase17_graph_routing_enabled",
        "phase17_multi_deal_enabled",
        "phase17_diff_mode_enabled",
        "phase17_aggregate_mode_enabled",
    ]

    @pytest.mark.prebuild
    @pytest.mark.parametrize("flag", BOOL_FLAGS)
    def test_bool_flag_exists_and_defaults_true(self, flag):
        val = getattr(self.config, flag, "MISSING")
        assert val is not "MISSING", f"Config missing {flag}"
        assert val is True, f"{flag} should default to True, got {val}"

    INT_FLAGS = {
        "phase17_max_parallel_scopes": 5,
        "phase17_wildcard_max_matches": 20,
        "phase17_multi_scope_timeout_ms": 30000,
    }

    @pytest.mark.prebuild
    @pytest.mark.parametrize("flag,expected", list(INT_FLAGS.items()), ids=list(INT_FLAGS.keys()))
    def test_int_flag_defaults(self, flag, expected):
        val = getattr(self.config, flag, "MISSING")
        assert val == expected

    FLOAT_FLAGS = {
        "phase17_diff_similarity_threshold": 0.85,
        "phase17_aggregate_outlier_threshold": 0.70,
    }

    @pytest.mark.prebuild
    @pytest.mark.parametrize("flag,expected", list(FLOAT_FLAGS.items()), ids=list(FLOAT_FLAGS.keys()))
    def test_float_flag_defaults(self, flag, expected):
        val = getattr(self.config, flag, "MISSING")
        assert abs(val - expected) < 1e-6


# ═══════════════════════════════════════════════════════════════
#  2b. ABS Config Flag Checks (Phases 21–22)
# ═══════════════════════════════════════════════════════════════

class TestABSConfigFlags:
    """All ABS feature flags must exist and have correct defaults."""

    @pytest.fixture(autouse=True)
    def cfg(self):
        from config.settings import load_config
        self.config = load_config(ROOT)

    ABS_BOOL_FLAGS = [
        "abs_enabled",
        "abs_vectorstore_enabled",
        "abs_graph_enabled",
        "abs_normalize_embeddings",
        "abs_definition_resolution_enabled",
        "abs_use_dual_store",
        "abs_use_enhanced_graph",
        "abs_use_full_retrieval",
        "abs_graph_pagerank_enabled",
        "abs_crag_enabled",
        "abs_critique_enabled",
        "abs_multi_query_enabled",
        "abs_hyde_enabled",
    ]

    @pytest.mark.prebuild
    @pytest.mark.abs_smoke
    @pytest.mark.parametrize("flag", ABS_BOOL_FLAGS)
    def test_abs_bool_flag_exists(self, flag):
        val = getattr(self.config, flag, "MISSING")
        assert val != "MISSING", f"ABS config missing: {flag}"
        assert isinstance(val, bool), f"{flag} should be bool, got {type(val)}"

    ABS_STR_FLAGS = {
        "abs_llm_mode": "vscode",
        "abs_extraction_mode": str,   # any string
    }

    @pytest.mark.prebuild
    @pytest.mark.abs_smoke
    def test_abs_llm_mode_default(self):
        val = getattr(self.config, "abs_llm_mode", "MISSING")
        assert val != "MISSING", "Config missing abs_llm_mode"
        assert val in ("vscode", "mock", "none"), f"abs_llm_mode invalid: {val}"
        assert val == "vscode", f"abs_llm_mode should default to vscode, got {val}"

    @pytest.mark.prebuild
    @pytest.mark.abs_smoke
    def test_abs_deals_root_exists(self):
        val = getattr(self.config, "abs_deals_root", "MISSING")
        assert val != "MISSING", "Config missing abs_deals_root"
        assert isinstance(val, str), "abs_deals_root should be a string"

    @pytest.mark.prebuild
    @pytest.mark.abs_smoke
    def test_abs_no_data_dir_alias(self):
        """abs_data_dir was a naming bug — must not exist on the config."""
        val = getattr(self.config, "abs_data_dir", "NOT_PRESENT")
        assert val == "NOT_PRESENT", (
            "abs_data_dir is a stale alias — use abs_deals_root instead"
        )


# ═══════════════════════════════════════════════════════════════
#  3. Core Subsystem Smoke Tests
# ═══════════════════════════════════════════════════════════════

class TestScopeResolver:
    """Scope resolver parse + resolve pipeline."""

    @pytest.mark.prebuild
    def test_parse_simple_query(self):
        from backend.common.scope_resolver import parse_command
        parsed = parse_command("What is the waterfall?")
        assert parsed.mode == "search"  # default mode is 'search'
        assert len(parsed.scopes) == 0
        assert "waterfall" in parsed.query

    @pytest.mark.prebuild
    def test_parse_mode_with_scope(self):
        from backend.common.scope_resolver import parse_command
        parsed = parse_command("/diff /deal1 /deal2 Compare rates")
        assert parsed.mode == "diff"
        assert len(parsed.scopes) >= 2
        assert "Compare rates" in parsed.query

    @pytest.mark.prebuild
    def test_parse_scope_with_doc_filter(self):
        from backend.common.scope_resolver import parse_command
        parsed = parse_command("/deal1/PSA What is the waterfall?")
        scope = parsed.scopes[0]
        assert scope.slug == "deal1"
        assert scope.doc_filter == "PSA"

    @pytest.mark.prebuild
    def test_parse_global_doc_filter(self):
        from backend.common.scope_resolver import parse_command
        parsed = parse_command("//PSA /deal1 /deal2 Compare clauses")
        # global doc filter should be captured (implementation specific)
        # At minimum the scopes should be correct
        assert len(parsed.scopes) >= 2

    @pytest.mark.prebuild
    def test_wildcard_scope(self):
        from backend.common.scope_resolver import parse_command
        parsed = parse_command("/deal* What is the interest rate?")
        assert any(s.is_wildcard for s in parsed.scopes)

    @pytest.mark.prebuild
    def test_all_modes_recognized(self):
        from backend.common.scope_resolver import parse_command
        for mode in ["compare", "diff", "aggregate", "audit", "define", "list"]:
            parsed = parse_command(f"/{mode} test")
            assert parsed.mode == mode, f"Mode {mode!r} not detected"

    @pytest.mark.prebuild
    def test_resolve_scopes_with_mock_catalog(self):
        from backend.common.scope_resolver import parse_command, resolve_scopes
        parsed = parse_command("/deal* What?")
        cat = MagicMock()
        cat.search_deals.return_value = [
            {"slug": "deal1", "kts_path": "/a"},
            {"slug": "deal2", "kts_path": "/b"},
        ]
        resolved = resolve_scopes(parsed, cat)  # returns list[ScopeExpr]
        assert len(resolved) >= 2


class TestGraphPartitioner:
    """Graph partitioning into doc-level subgraphs."""

    @pytest.fixture
    def deal_graph(self):
        G = nx.DiGraph()
        G.add_node("DOC:psa", type="DOCUMENT", doc_name_prefix="PSA")
        G.add_node("DOC:sa", type="DOCUMENT", doc_name_prefix="SA")
        G.add_node("SEC:psa:1", type="SECTION", doc_name_prefix="PSA")
        G.add_node("SEC:sa:1", type="SECTION", doc_name_prefix="SA")
        G.add_node("TERM:rate", type="DEFINED_TERM", doc_name_prefix="PSA", surface_form="Interest Rate")
        G.add_node("TERM:rate2", type="DEFINED_TERM", doc_name_prefix="SA", surface_form="Interest Rate")
        G.add_edge("DOC:psa", "SEC:psa:1", relation="CONTAINS")
        G.add_edge("DOC:sa", "SEC:sa:1", relation="CONTAINS")
        return G

    @pytest.mark.prebuild
    def test_partition_creates_subgraphs(self, deal_graph, tmp_path):
        from backend.graph.graph_partitioner import partition_graph_by_document
        result = partition_graph_by_document(deal_graph, str(tmp_path))
        assert len(result) >= 2
        # result is Dict[str, int] mapping doc_name_prefix → node count
        for doc_prefix, node_count in result.items():
            assert isinstance(node_count, int) and node_count >= 1
            # Verify sub-graph JSON was written
            assert (tmp_path / "doc_graphs" / f"{doc_prefix}.json").exists()

    @pytest.mark.prebuild
    def test_cross_doc_edges(self, deal_graph):
        from backend.graph.graph_partitioner import add_cross_document_edges
        add_cross_document_edges(deal_graph)
        cross_edges = [
            (u, v) for u, v, d in deal_graph.edges(data=True)
            if d.get("type", "").startswith("CROSS_DOC")
        ]
        assert len(cross_edges) > 0


class TestDealCatalog:
    """Deal catalog Phase 17 schema and methods."""

    @pytest.fixture
    def catalog(self):
        from backend.vector.deal_catalog import DealCatalog
        tmp = tempfile.mkdtemp(prefix="kts_prebuild_cat_")
        db_file = os.path.join(tmp, "deal_catalog.db")
        cat = DealCatalog(db_file)
        yield cat
        shutil.rmtree(tmp, ignore_errors=True)

    @pytest.mark.prebuild
    def test_upsert_and_get(self, catalog):
        catalog.upsert_deal(
            scope_slug="test_deal",
            folder_path="/fake/path",
            deal_name="Test Deal",
            vintage=2024,
            series="HE",
            chunk_count=100,
            status="ready",
        )
        entry = catalog.get_by_slug("test_deal")
        assert entry is not None
        assert entry.slug == "test_deal"

    @pytest.mark.prebuild
    def test_search_deals_wildcard(self, catalog):
        catalog.upsert_deal(scope_slug="deal_alpha", folder_path="/a")
        catalog.upsert_deal(scope_slug="deal_beta", folder_path="/b")
        catalog.upsert_deal(scope_slug="other", folder_path="/c")
        results = catalog.search_deals(pattern="deal*")
        slugs = {r["slug"] for r in results}
        assert "deal_alpha" in slugs
        assert "deal_beta" in slugs
        assert "other" not in slugs

    @pytest.mark.prebuild
    def test_list_all_deals(self, catalog):
        catalog.upsert_deal(scope_slug="a", folder_path="/a")
        catalog.upsert_deal(scope_slug="b", folder_path="/b")
        all_deals = catalog.list_all_deals()
        assert len(all_deals) >= 2

    @pytest.mark.prebuild
    def test_get_doc_types(self, catalog):
        # get_doc_types requires doc_graphs on disk. Test it returns list.
        result = catalog.get_doc_types("nonexistent")
        assert isinstance(result, list)


class TestDiffEngine:
    """Diff engine pairwise comparison."""

    @pytest.mark.prebuild
    def test_diff_produces_pairwise(self):
        from backend.agents.diff_engine import DiffEngine
        results = {
            "scope_a": [{"text": "The interest rate is 3.5% per annum, paid monthly on the 25th day", "doc_type": "PSA"}],
            "scope_b": [{"text": "The applicable margin equals 7.0% compounded quarterly on the last business day", "doc_type": "PSA"}],
        }
        output = DiffEngine().diff(results, "interest rate")
        assert "diffs" in output
        assert len(output["diffs"]) >= 1

    @pytest.mark.prebuild
    def test_diff_empty_input(self):
        from backend.agents.diff_engine import DiffEngine
        output = DiffEngine().diff({}, "test")
        assert "diffs" in output
        assert len(output["diffs"]) == 0

    @pytest.mark.prebuild
    def test_diff_single_scope(self):
        from backend.agents.diff_engine import DiffEngine
        results = {"only_scope": [{"text": "Hello"}]}
        output = DiffEngine().diff(results, "test")
        assert len(output["diffs"]) == 0


class TestAggregationEngine:
    """Aggregation engine consensus + outlier detection."""

    @pytest.mark.prebuild
    def test_aggregate_produces_consensus(self):
        from backend.agents.aggregation_engine import AggregationEngine
        results = {
            "scope_a": [{"text": "Interest rate is 3.5%. Term is 30 years."}],
            "scope_b": [{"text": "Interest rate is 3.5%. Term is 30 years."}],
            "scope_c": [{"text": "Interest rate is 8.0%. Term is 5 years."}],
        }
        output = AggregationEngine().aggregate(results, "interest rate")
        assert "pattern" in output
        assert "outliers" in output
        assert "deal_count" in output
        assert output["deal_count"] == 3

    @pytest.mark.prebuild
    def test_aggregate_empty(self):
        from backend.agents.aggregation_engine import AggregationEngine
        output = AggregationEngine().aggregate({}, "test")
        assert output["deal_count"] == 0


# ═══════════════════════════════════════════════════════════════
#  4. CLI Surface Checks
# ═══════════════════════════════════════════════════════════════

class TestCLISurface:
    """CLI options parse without error."""

    @pytest.mark.prebuild
    def test_search_command_accepts_doc_filter(self):
        from click.testing import CliRunner
        from cli.main import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "--help"])
        assert result.exit_code == 0
        assert "--doc-filter" in result.output

    @pytest.mark.prebuild
    def test_search_command_accepts_mode(self):
        from click.testing import CliRunner
        from cli.main import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "--help"])
        assert "--mode" in result.output

    @pytest.mark.prebuild
    def test_search_command_accepts_scopes(self):
        from click.testing import CliRunner
        from cli.main import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "--help"])
        assert "--scopes" in result.output

    @pytest.mark.prebuild
    def test_list_deals_command_exists(self):
        from click.testing import CliRunner
        from cli.main import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["list-deals", "--help"])
        assert result.exit_code == 0
        assert "--scope" in result.output or "--format" in result.output

    @pytest.mark.prebuild
    def test_list_deals_format_option(self):
        from click.testing import CliRunner
        from cli.main import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["list-deals", "--help"])
        assert "--format" in result.output


# ═══════════════════════════════════════════════════════════════
#  5. Extension JS Parity Tests
# ═══════════════════════════════════════════════════════════════

class TestExtensionJS:
    """Run extension JS tests via Node.js."""

    @pytest.mark.prebuild
    def test_js_tests_pass(self):
        """Run all three JS test files via `node --test`."""
        test_files = [
            str(ROOT / "extension" / "tests" / "scope_discovery.test.js"),
            str(ROOT / "extension" / "tests" / "participant_phase17.test.js"),
            str(ROOT / "extension" / "tests" / "kts_tool_forwarding.test.js"),
        ]
        # Check that test files exist
        for f in test_files:
            assert Path(f).exists(), f"JS test file missing: {f}"

        try:
            result = subprocess.run(
                ["node", "--test"] + test_files,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(ROOT),
            )
        except FileNotFoundError:
            pytest.skip("Node.js not installed — skipping JS tests")
        except subprocess.TimeoutExpired:
            pytest.fail("JS tests timed out after 60s")

        if result.returncode != 0:
            # Show test output for debugging
            output = result.stdout + "\n" + result.stderr
            pytest.fail(f"JS tests failed (exit code {result.returncode}):\n{output[-3000:]}")


# ═══════════════════════════════════════════════════════════════
#  6. Regression Guard
# ═══════════════════════════════════════════════════════════════

class TestRegressionGuard:
    """Non-Phase-17 modules still import cleanly."""

    @pytest.mark.prebuild
    @pytest.mark.parametrize("mod", [
        "backend.agents.ingestion_agent",
        "backend.agents.retrieval_service",
        "backend.retrieval.human_like_retriever",
        "backend.graph.builder",
        "backend.graph.enhanced_graph_builder",
        "backend.vector.deal_catalog",
        "config.settings",
        "cli.main",
    ])
    def test_core_modules_import(self, mod):
        m = importlib.import_module(mod)
        assert m is not None

    @pytest.mark.prebuild
    def test_config_load(self):
        from config.settings import load_config
        cfg = load_config(ROOT)
        assert cfg is not None
        assert hasattr(cfg, "knowledge_base_path")

    @pytest.mark.prebuild
    def test_doc_filter_merge_backward_compat(self):
        """With no doc_name_prefix, _merge_doc_filter should return original filters."""
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        stub = MagicMock(spec=HumanLikeRetriever)
        stub._merge_doc_filter = HumanLikeRetriever._merge_doc_filter.__get__(stub)
        stub._doc_name_prefix = None

        original = {"doc_type": "PSA"}
        result = stub._merge_doc_filter(original)
        assert result == original

    @pytest.mark.prebuild
    def test_doc_filter_merge_with_prefix(self):
        """With doc_name_prefix set, it should be merged into filters."""
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        stub = MagicMock(spec=HumanLikeRetriever)
        stub._merge_doc_filter = HumanLikeRetriever._merge_doc_filter.__get__(stub)
        stub._doc_name_prefix = "PSA"

        result = stub._merge_doc_filter(None)
        assert result == {"doc_name_prefix": "PSA"}

        result2 = stub._merge_doc_filter({"doc_type": "SA"})
        assert result2["doc_name_prefix"] == "PSA"
        assert result2["doc_type"] == "SA"

    @pytest.mark.prebuild
    def test_retrieval_service_has_phase17_modes(self):
        """RetrievalService.execute should handle Phase 17 mode dispatch."""
        from backend.agents.retrieval_service import RetrievalService
        # Just verify the class is importable and has execute method
        assert hasattr(RetrievalService, "execute")


# ═══════════════════════════════════════════════════════════════
#  7. Feature-flag gating
# ═══════════════════════════════════════════════════════════════

class TestFeatureFlagGating:
    """Feature flags are respected — disabled flags skip Phase 17 logic."""

    @pytest.mark.prebuild
    def test_env_override_disables_doc_filter(self):
        """Setting KTS_PHASE17_DOC_FILTER_ENABLED=0 should disable the flag."""
        from config.settings import load_config
        with patch.dict(os.environ, {"KTS_PHASE17_DOC_FILTER_ENABLED": "0"}):
            cfg = load_config(ROOT)
            assert cfg.phase17_doc_filter_enabled is False

    @pytest.mark.prebuild
    def test_env_override_parallel_scopes(self):
        from config.settings import load_config
        with patch.dict(os.environ, {"KTS_PHASE17_MAX_PARALLEL_SCOPES": "10"}):
            cfg = load_config(ROOT)
            assert cfg.phase17_max_parallel_scopes == 10

    @pytest.mark.prebuild
    def test_env_override_timeout(self):
        from config.settings import load_config
        with patch.dict(os.environ, {"KTS_PHASE17_MULTI_SCOPE_TIMEOUT_MS": "60000"}):
            cfg = load_config(ROOT)
            assert cfg.phase17_multi_scope_timeout_ms == 60000
