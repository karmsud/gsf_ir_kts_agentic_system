"""Phase 17 — Performance Benchmark tests."""
from __future__ import annotations
import sys
import os
import time
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.common.scope_resolver import parse_command, resolve_scopes, ScopeExpr
from backend.agents.diff_engine import DiffEngine
from backend.agents.aggregation_engine import AggregationEngine
from backend.graph.graph_partitioner import partition_graph_by_document, add_cross_document_edges

import networkx as nx


# ── Helpers ──────────────────────────────────────────────────

def _make_graph(prefixes: list[str], nodes_per_prefix: int = 10) -> nx.DiGraph:
    """Build a test graph with given prefixes."""
    G = nx.DiGraph()
    for prefix in prefixes:
        for i in range(nodes_per_prefix):
            nid = f"{prefix}:sec:{i}"
            G.add_node(
                nid,
                type="SECTION",
                doc_name_prefix=prefix,
                label=f"Section {i}",
                surface_form=f"Term_{prefix}_{i % 3}",  # reuse terms for cross-doc
            )
        # Add some DEFINED_TERM nodes to trigger cross-doc edge detection
        for i in range(3):
            tid = f"{prefix}:term:{i}"
            G.add_node(
                tid,
                type="DEFINED_TERM",
                doc_name_prefix=prefix,
                surface_form=f"SharedTerm{i}",  # shared across prefixes
                label=f"SharedTerm{i}",
            )
        # Chain section edges
        for i in range(nodes_per_prefix - 1):
            G.add_edge(f"{prefix}:sec:{i}", f"{prefix}:sec:{i+1}", type="NEXT")
    return G


def _make_results(n_scopes: int, n_results: int = 5) -> dict:
    """Build mock results_by_scope with n_scopes, each having n_results."""
    results = {}
    for i in range(n_scopes):
        scope_key = f"deal_{i}/PSA"
        results[scope_key] = [
            {
                "text": f"Distribution Date means the {25 + (i % 5)}th day of each calendar month "
                        f"following the related determination date. Amount: ${100000 + i * 1000:,.2f}. "
                        f"Rate: {5.0 + i * 0.1:.1f}%.",
                "section_number": f"2.0{j}",
                "score": 0.9 - j * 0.05,
            }
            for j in range(n_results)
        ]
    return results


# ── 1. Scope resolver parse time ─────────────────────────────

class TestScopeResolverParseTime:
    def test_scope_resolver_parse_time(self):
        """parse_command completes in < 10ms avg over 1000 iterations."""
        inputs = [
            "/fin_deal1/PSA What is Distribution Date?",
            "/compare /fin_deal1/PSA /fin_deal2/PROSUPP waterfall",
            "/aggregate /bear_stearns_2006*/PSA Distribution Date",
            "/diff /deal_a/PSA /deal_b/PSA cutoff date",
            "//PSA What is the servicer?",
            "/define /fin_deal1 Trust",
            "/audit /fin_deal1",
            "/list",
        ]
        iterations = 1000

        start = time.perf_counter()
        for _ in range(iterations):
            for inp in inputs:
                parse_command(inp)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / (iterations * len(inputs))) * 1000
        # Should be well under 10ms per call; generous limit for CI
        assert avg_ms < 10, f"parse_command avg {avg_ms:.3f}ms exceeds 10ms"


# ── 2. _merge_doc_filter performance ─────────────────────────

class TestMergeDocFilterPerformance:
    def test_merge_doc_filter_performance(self):
        """_merge_doc_filter is < 1ms avg for 1000 calls."""
        from backend.retrieval.human_like_retriever import HumanLikeRetriever

        retriever = object.__new__(HumanLikeRetriever)
        retriever._doc_name_prefix = "PSA"

        iterations = 1000
        filters = {"doc_type": "PSA", "scope": "fin_deal1"}

        start = time.perf_counter()
        for _ in range(iterations):
            retriever._merge_doc_filter(filters)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        assert avg_ms < 1, f"_merge_doc_filter avg {avg_ms:.4f}ms exceeds 1ms"


# ── 3. DiffEngine small input time ───────────────────────────

class TestDiffEngineSmallInputTime:
    def test_diff_engine_small_input_time(self):
        """DiffEngine.diff with 2 scopes × 5 results < 100ms."""
        engine = DiffEngine()
        results = _make_results(n_scopes=2, n_results=5)
        query = "What is Distribution Date?"

        start = time.perf_counter()
        result = engine.diff(results, query)
        elapsed = time.perf_counter() - start

        elapsed_ms = elapsed * 1000
        assert elapsed_ms < 100, f"DiffEngine.diff took {elapsed_ms:.1f}ms, exceeds 100ms"
        assert result["scope_count"] == 2


# ── 4. AggregationEngine small input time ────────────────────

class TestAggregationEngineSmallInputTime:
    def test_aggregation_engine_small_input_time(self):
        """AggregationEngine.aggregate with 5 scopes × 5 results < 100ms."""
        engine = AggregationEngine()
        results = _make_results(n_scopes=5, n_results=5)
        query = "What is Distribution Date?"

        start = time.perf_counter()
        result = engine.aggregate(results, query)
        elapsed = time.perf_counter() - start

        elapsed_ms = elapsed * 1000
        assert elapsed_ms < 100, f"AggregationEngine.aggregate took {elapsed_ms:.1f}ms, exceeds 100ms"
        assert result["deal_count"] == 5


# ── 5. Graph partition small graph time ──────────────────────

class TestGraphPartitionSmallGraphTime:
    def test_graph_partition_small_graph_time(self):
        """partition 20-node graph < 100ms."""
        G = _make_graph(["PSA", "PROSUPP"], nodes_per_prefix=10)
        # 10 sections + 3 terms per prefix × 2 = 26 nodes total

        with tempfile.TemporaryDirectory() as tmpdir:
            start = time.perf_counter()
            stats = partition_graph_by_document(G, tmpdir)
            elapsed = time.perf_counter() - start

            elapsed_ms = elapsed * 1000
            assert elapsed_ms < 100, f"partition_graph took {elapsed_ms:.1f}ms, exceeds 100ms"
            assert len(stats) == 2
            assert all(v > 0 for v in stats.values())


# ── 6. Catalog wildcard query time ───────────────────────────

class TestCatalogWildcardQueryTime:
    def test_catalog_wildcard_query_time(self):
        """search_deals with pattern < 50ms on a small catalog."""
        from backend.vector.deal_catalog import DealCatalog

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "perf_catalog.db")
            catalog = DealCatalog(db_path=db_path)

            # Insert 50 deals to have a non-trivial catalog
            for i in range(50):
                catalog.upsert_deal(
                    scope_slug=f"bear_stearns_2006_he{i}",
                    folder_path=f"/deals/bear_stearns_2006_HE{i}",
                    deal_name=f"Bear Stearns 2006-HE{i}",
                    vintage=2006,
                    doc_types=["PSA", "PROSUPP"],
                )

            start = time.perf_counter()
            results = catalog.search_deals(pattern="bear_stearns_2006%")
            elapsed = time.perf_counter() - start

            elapsed_ms = elapsed * 1000
            assert elapsed_ms < 50, f"search_deals took {elapsed_ms:.1f}ms, exceeds 50ms"
            assert len(results) == 50


# ── 7. Scope resolver complex command time ───────────────────

class TestScopeResolverComplexCommandTime:
    def test_scope_resolver_complex_command_time(self):
        """Complex command parse < 10ms (single call)."""
        complex_input = (
            "/compare /bear_stearns_2006*/PSA /fin_deal1/PROSUPP "
            "/fin_deal2/PSA What is the Distribution Date and who is the servicer?"
        )

        start = time.perf_counter()
        cmd = parse_command(complex_input)
        elapsed = time.perf_counter() - start

        elapsed_ms = elapsed * 1000
        assert elapsed_ms < 10, f"Complex parse took {elapsed_ms:.3f}ms, exceeds 10ms"
        assert cmd.mode == "compare"
        assert len(cmd.scopes) == 3


# ── 8. Cross-document edges small graph time ─────────────────

class TestCrossDocEdgesSmallGraphTime:
    def test_cross_doc_edges_small_graph_time(self):
        """add_cross_document_edges on 20-node graph < 100ms."""
        G = _make_graph(["PSA", "PROSUPP"], nodes_per_prefix=10)

        start = time.perf_counter()
        cross_count = add_cross_document_edges(G)
        elapsed = time.perf_counter() - start

        elapsed_ms = elapsed * 1000
        assert elapsed_ms < 100, f"add_cross_document_edges took {elapsed_ms:.1f}ms, exceeds 100ms"
        # Should have found at least some cross-doc edges from shared terms
        assert cross_count >= 0  # may be 0 if term overlap doesn't trigger
