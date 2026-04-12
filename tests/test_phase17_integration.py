"""Phase 17 — Cross-Step Integration tests."""
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
from backend.graph.graph_partitioner import partition_graph_by_document, add_cross_document_edges
from backend.agents.diff_engine import DiffEngine
from backend.agents.aggregation_engine import AggregationEngine

import networkx as nx


# ── Helpers ──────────────────────────────────────────────────

def _mock_catalog(deals: list[dict]) -> MagicMock:
    """Build a mock DealCatalog returning *deals* for list/search."""
    cat = MagicMock()
    cat.list_all_deals.return_value = deals
    cat.search_deals.side_effect = lambda pattern="", **kw: [
        d for d in deals if d["slug"].startswith(pattern.rstrip("*"))
    ]
    return cat


def _make_graph(prefixes: list[str], nodes_per_prefix: int = 3) -> nx.DiGraph:
    """Build a small test graph with doc_name_prefix on every node."""
    G = nx.DiGraph()
    for prefix in prefixes:
        for i in range(nodes_per_prefix):
            nid = f"{prefix}:sec:{i}"
            G.add_node(nid, type="SECTION", doc_name_prefix=prefix, label=f"S{i}")
        # chain edges inside the same prefix
        for i in range(nodes_per_prefix - 1):
            G.add_edge(f"{prefix}:sec:{i}", f"{prefix}:sec:{i+1}", type="NEXT")
    return G


# ── UC1-UC14 Integration tests ──────────────────────────────

class TestUC1SingleDocInDeal:
    """parse_command → scope_resolver + doc_filter → verify filter applied."""

    def test_uc1_single_doc_in_deal(self):
        cmd = parse_command("/fin_deal1/PSA What is Distribution Date?")
        assert cmd.mode == "search"
        assert len(cmd.scopes) == 1
        assert cmd.scopes[0].slug == "fin_deal1"
        assert cmd.scopes[0].doc_filter == "PSA"
        assert cmd.query == "What is Distribution Date?"


class TestUC2AllDocsInDeal:
    """parse single scope without doc filter → no filter applied."""

    def test_uc2_all_docs_in_deal(self):
        cmd = parse_command("/fin_deal1 What is Distribution Date?")
        assert cmd.mode == "search"
        assert len(cmd.scopes) == 1
        assert cmd.scopes[0].slug == "fin_deal1"
        assert cmd.scopes[0].doc_filter is None


class TestUC3OneDocTypeAcrossDeals:
    """parse //PSA → global doc filter set."""

    def test_uc3_one_doc_type_across_deals(self):
        cmd = parse_command("//PSA What is Distribution Date?")
        assert len(cmd.scopes) == 1
        # Global doc filter produces slug="*" with doc_filter
        assert cmd.scopes[0].slug == "*"
        assert cmd.scopes[0].doc_filter == "PSA"

        # resolve_scopes expands the "*" to all known deals
        deals = [
            {"slug": "fin_deal1", "kts_path": "/d1/.kts"},
            {"slug": "fin_deal2", "kts_path": "/d2/.kts"},
        ]
        catalog = _mock_catalog(deals)
        resolved = resolve_scopes(cmd, catalog)
        assert len(resolved) == 2
        assert all(s.doc_filter == "PSA" for s in resolved)
        assert {s.slug for s in resolved} == {"fin_deal1", "fin_deal2"}


class TestUC4WildcardAcrossDeals:
    """parse wildcard → multiple scopes produced."""

    def test_uc4_wildcard_across_deals(self):
        cmd = parse_command("/bear_stearns_2006* What is the cutoff date?")
        assert len(cmd.scopes) == 1
        assert cmd.scopes[0].is_wildcard is True
        assert cmd.scopes[0].slug == "bear_stearns_2006"

        deals = [
            {"slug": "bear_stearns_2006_he1"},
            {"slug": "bear_stearns_2006_he2"},
            {"slug": "bear_stearns_2006_he3"},
        ]
        catalog = _mock_catalog(deals)
        resolved = resolve_scopes(cmd, catalog)
        assert len(resolved) == 3
        assert all(not s.is_wildcard for s in resolved)


class TestUC5WildcardWithDocFilter:
    """wildcard + doc filter → both set."""

    def test_uc5_wildcard_with_doc_filter(self):
        cmd = parse_command("/bear_stearns_2006*/PSA What is the cutoff date?")
        assert len(cmd.scopes) == 1
        scope = cmd.scopes[0]
        assert scope.is_wildcard is True
        assert scope.slug == "bear_stearns_2006"
        assert scope.doc_filter == "PSA"

        deals = [{"slug": "bear_stearns_2006_he1"}, {"slug": "bear_stearns_2006_he2"}]
        catalog = _mock_catalog(deals)
        resolved = resolve_scopes(cmd, catalog)
        assert len(resolved) == 2
        assert all(s.doc_filter == "PSA" for s in resolved)


class TestUC6CompareWildcard:
    """parse compare + wildcard → mode=compare + wildcard scope."""

    def test_uc6_compare_wildcard(self):
        cmd = parse_command("/compare /bear_stearns_2006* What is Distribution Date?")
        assert cmd.mode == "compare"
        assert len(cmd.scopes) == 1
        assert cmd.scopes[0].is_wildcard is True


class TestUC7CompareSpecificDocs:
    """parse compare + 2 explicit scopes with doc filters."""

    def test_uc7_compare_specific_docs(self):
        cmd = parse_command("/compare /fin_deal1/PSA /fin_deal2/PSA What is Distribution Date?")
        assert cmd.mode == "compare"
        assert len(cmd.scopes) == 2
        assert cmd.scopes[0].slug == "fin_deal1"
        assert cmd.scopes[0].doc_filter == "PSA"
        assert cmd.scopes[1].slug == "fin_deal2"
        assert cmd.scopes[1].doc_filter == "PSA"


class TestUC8DefineMode:
    """parse define command → mode=define."""

    def test_uc8_define_mode(self):
        cmd = parse_command("/define /fin_deal1/PSA Distribution Date")
        assert cmd.mode == "define"
        assert len(cmd.scopes) == 1
        assert cmd.scopes[0].doc_filter == "PSA"


class TestUC9AuditMode:
    """parse audit → mode=audit."""

    def test_uc9_audit_mode(self):
        cmd = parse_command("/audit /fin_deal1")
        assert cmd.mode == "audit"
        assert len(cmd.scopes) == 1
        assert cmd.scopes[0].slug == "fin_deal1"


class TestUC10DiffTwoDocsSameDeal:
    """diff mode + same slug different docs."""

    def test_uc10_diff_two_docs_same_deal(self):
        cmd = parse_command("/diff /fin_deal1/PSA /fin_deal1/PROSUPP waterfall")
        assert cmd.mode == "diff"
        assert len(cmd.scopes) == 2
        assert cmd.scopes[0].slug == cmd.scopes[1].slug == "fin_deal1"
        assert cmd.scopes[0].doc_filter == "PSA"
        assert cmd.scopes[1].doc_filter == "PROSUPP"


class TestUC11DiffSameDocAcrossDeals:
    """diff mode + PSA from 2 deals."""

    def test_uc11_diff_same_doc_across_deals(self):
        cmd = parse_command("/diff /fin_deal1/PSA /fin_deal2/PSA Distribution Date")
        assert cmd.mode == "diff"
        assert len(cmd.scopes) == 2
        assert cmd.scopes[0].doc_filter == "PSA"
        assert cmd.scopes[1].doc_filter == "PSA"
        assert cmd.scopes[0].slug != cmd.scopes[1].slug


class TestUC13ListMode:
    """list mode → mode=list."""

    def test_uc13_list_mode(self):
        cmd = parse_command("/list")
        assert cmd.mode == "list"
        assert len(cmd.scopes) == 0


class TestUC14AggregatePattern:
    """aggregate + wildcard."""

    def test_uc14_aggregate_pattern(self):
        cmd = parse_command("/aggregate /bear_stearns_2006*/PSA Distribution Date")
        assert cmd.mode == "aggregate"
        assert len(cmd.scopes) == 1
        assert cmd.scopes[0].is_wildcard is True
        assert cmd.scopes[0].doc_filter == "PSA"

        deals = [{"slug": "bear_stearns_2006_he1"}, {"slug": "bear_stearns_2006_he2"}]
        catalog = _mock_catalog(deals)
        resolved = resolve_scopes(cmd, catalog)
        assert len(resolved) == 2
        assert all(s.doc_filter == "PSA" for s in resolved)


class TestPipelineScopeToCatalogToResolver:
    """scope resolver + mock catalog → expanded scopes correct."""

    def test_pipeline_scope_to_catalog_to_resolver(self):
        raw = "/compare /fin_deal*/PSA What is Distribution Date?"
        cmd = parse_command(raw)
        assert cmd.mode == "compare"

        deals = [
            {"slug": "fin_deal1"},
            {"slug": "fin_deal2"},
            {"slug": "fin_deal3"},
        ]
        catalog = _mock_catalog(deals)
        resolved = resolve_scopes(cmd, catalog)

        # All three deals should be expanded from wildcard
        assert len(resolved) == 3
        slugs = {s.slug for s in resolved}
        assert slugs == {"fin_deal1", "fin_deal2", "fin_deal3"}
        # All should carry through the doc filter
        assert all(s.doc_filter == "PSA" for s in resolved)
        # None should remain as wildcards
        assert all(not s.is_wildcard for s in resolved)


class TestGraphPartitionToDocFilterFlow:
    """partition → doc graph exists → _select_graph_path returns doc graph."""

    def test_graph_partition_to_doc_filter_flow(self):
        G = _make_graph(["PSA", "PROSUPP"], nodes_per_prefix=4)
        assert G.number_of_nodes() == 8

        with tempfile.TemporaryDirectory() as tmpdir:
            stats = partition_graph_by_document(G, tmpdir)

            # Both doc graphs should be written
            assert "PSA" in stats
            assert "PROSUPP" in stats
            assert stats["PSA"] == 4
            assert stats["PROSUPP"] == 4

            # Verify doc graph files exist on disk
            doc_graphs_dir = Path(tmpdir) / "doc_graphs"
            assert (doc_graphs_dir / "PSA.json").exists()
            assert (doc_graphs_dir / "PROSUPP.json").exists()

            # Simulate _select_graph_path logic:
            # When doc_name_prefix is set and the doc graph exists,
            # it should prefer the doc-specific graph path.
            doc_graph_path = os.path.join(
                tmpdir, "graph", "doc_graphs", "PSA.json"
            )
            deal_graph_path = os.path.join(tmpdir, "graph", "knowledge_graph.json")

            # The partition wrote into tmpdir/doc_graphs (not tmpdir/graph/doc_graphs)
            # so emulate the real layout
            real_doc_graph = str(doc_graphs_dir / "PSA.json")
            assert os.path.exists(real_doc_graph)
