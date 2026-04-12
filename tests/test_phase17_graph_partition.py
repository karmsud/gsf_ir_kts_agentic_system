"""Phase 17 — Graph Partitioning tests (Step 3)."""
from __future__ import annotations

import json
import sys
import tempfile
import shutil
from pathlib import Path

import pytest
import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.graph.graph_partitioner import (
    partition_graph_by_document,
    add_cross_document_edges,
)


@pytest.fixture
def two_doc_graph() -> nx.DiGraph:
    """Build a realistic deal graph with PSA and PROSUPP documents."""
    G = nx.DiGraph()

    # --- DOCUMENT nodes ---
    G.add_node("DOC_PSA", type="DOCUMENT", doc_name_prefix="PSA", label="PSA")
    G.add_node("DOC_PROSUPP", type="DOCUMENT", doc_name_prefix="PROSUPP", label="PROSUPP")

    # --- SECTION nodes for PSA ---
    G.add_node("SEC_PSA_1", type="SECTION", doc_name_prefix="PSA", label="Article I")
    G.add_node("SEC_PSA_2", type="SECTION", doc_name_prefix="PSA", label="Article II")
    G.add_node("SEC_PSA_3", type="SECTION", doc_name_prefix="PSA", label="Article III")

    # --- SECTION nodes for PROSUPP ---
    G.add_node("SEC_PRO_1", type="SECTION", doc_name_prefix="PROSUPP", label="Section 1")
    G.add_node("SEC_PRO_2", type="SECTION", doc_name_prefix="PROSUPP", label="Section 2")

    # --- DEFINED_TERM nodes ---
    # "Distribution Date" appears in BOTH documents (cross-doc candidate)
    G.add_node(
        "TERM_PSA_DistDate",
        type="DEFINED_TERM",
        doc_name_prefix="PSA",
        surface_form="Distribution Date",
        label="Distribution Date",
    )
    G.add_node(
        "TERM_PRO_DistDate",
        type="DEFINED_TERM",
        doc_name_prefix="PROSUPP",
        surface_form="Distribution Date",
        label="Distribution Date",
    )
    # A term unique to PSA
    G.add_node(
        "TERM_PSA_Trustee",
        type="DEFINED_TERM",
        doc_name_prefix="PSA",
        surface_form="Trustee",
        label="Trustee",
    )

    # --- ENTITY nodes ---
    # Entity appearing in both docs (cross-doc candidate)
    G.add_node(
        "ENT_PSA_WellsFargo",
        type="ENTITY",
        doc_name_prefix="PSA",
        surface_form="Wells Fargo",
        label="Wells Fargo",
    )
    G.add_node(
        "ENT_PRO_WellsFargo",
        type="ENTITY",
        doc_name_prefix="PROSUPP",
        surface_form="Wells Fargo",
        label="Wells Fargo",
    )
    # Entity unique to PROSUPP
    G.add_node(
        "ENT_PRO_DBRS",
        type="ENTITY",
        doc_name_prefix="PROSUPP",
        surface_form="DBRS Morningstar",
        label="DBRS Morningstar",
    )

    # --- CONTAINS edges (doc → section) ---
    G.add_edge("DOC_PSA", "SEC_PSA_1", type="CONTAINS")
    G.add_edge("DOC_PSA", "SEC_PSA_2", type="CONTAINS")
    G.add_edge("DOC_PSA", "SEC_PSA_3", type="CONTAINS")
    G.add_edge("DOC_PROSUPP", "SEC_PRO_1", type="CONTAINS")
    G.add_edge("DOC_PROSUPP", "SEC_PRO_2", type="CONTAINS")

    # --- DEFINES edges (section → term) ---
    G.add_edge("SEC_PSA_1", "TERM_PSA_DistDate", type="DEFINES")
    G.add_edge("SEC_PRO_1", "TERM_PRO_DistDate", type="DEFINES")
    G.add_edge("SEC_PSA_2", "TERM_PSA_Trustee", type="DEFINES")

    # --- MENTIONS edges (section → entity) ---
    G.add_edge("SEC_PSA_3", "ENT_PSA_WellsFargo", type="MENTIONS")
    G.add_edge("SEC_PRO_2", "ENT_PRO_WellsFargo", type="MENTIONS")
    G.add_edge("SEC_PRO_2", "ENT_PRO_DBRS", type="MENTIONS")

    return G


@pytest.fixture
def output_dir():
    """Provide a temporary directory, cleaned up after the test."""
    d = tempfile.mkdtemp(prefix="kts_partition_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


class TestGraphPartition:
    """15 comprehensive tests for the graph partitioner."""

    # ------------------------------------------------------------------
    # 1. partition creates doc_graphs/ directory
    # ------------------------------------------------------------------
    def test_partition_creates_doc_graphs_dir(self, two_doc_graph, output_dir):
        partition_graph_by_document(two_doc_graph, output_dir)
        assert (Path(output_dir) / "doc_graphs").is_dir()

    # ------------------------------------------------------------------
    # 2. partition creates per-doc JSON files
    # ------------------------------------------------------------------
    def test_partition_creates_per_doc_files(self, two_doc_graph, output_dir):
        partition_graph_by_document(two_doc_graph, output_dir)
        doc_dir = Path(output_dir) / "doc_graphs"
        assert (doc_dir / "PSA.json").exists()
        assert (doc_dir / "PROSUPP.json").exists()

    # ------------------------------------------------------------------
    # 3. PSA graph contains only PSA-prefixed nodes
    # ------------------------------------------------------------------
    def test_psa_graph_contains_only_psa_nodes(self, two_doc_graph, output_dir):
        partition_graph_by_document(two_doc_graph, output_dir)
        psa_json = Path(output_dir) / "doc_graphs" / "PSA.json"
        data = json.loads(psa_json.read_text(encoding="utf-8"))
        for node_id, node_attrs in data["nodes"].items():
            assert node_attrs.get("doc_name_prefix") == "PSA", (
                f"Node {node_id} has unexpected prefix {node_attrs.get('doc_name_prefix')}"
            )

    # ------------------------------------------------------------------
    # 4. PROSUPP graph contains only PROSUPP-prefixed nodes
    # ------------------------------------------------------------------
    def test_prosupp_graph_contains_only_prosupp_nodes(self, two_doc_graph, output_dir):
        partition_graph_by_document(two_doc_graph, output_dir)
        pro_json = Path(output_dir) / "doc_graphs" / "PROSUPP.json"
        data = json.loads(pro_json.read_text(encoding="utf-8"))
        for node_id, node_attrs in data["nodes"].items():
            assert node_attrs.get("doc_name_prefix") == "PROSUPP", (
                f"Node {node_id} has unexpected prefix {node_attrs.get('doc_name_prefix')}"
            )

    # ------------------------------------------------------------------
    # 5. Edges in PSA sub-graph don't reference PROSUPP-only nodes
    # ------------------------------------------------------------------
    def test_doc_graph_edges_are_intra_doc_only(self, two_doc_graph, output_dir):
        partition_graph_by_document(two_doc_graph, output_dir)
        psa_json = Path(output_dir) / "doc_graphs" / "PSA.json"
        data = json.loads(psa_json.read_text(encoding="utf-8"))
        psa_node_ids = set(data["nodes"].keys())
        for edge in data["edges"]:
            assert edge["source"] in psa_node_ids, (
                f"Edge source {edge['source']} not in PSA nodes"
            )
            assert edge["target"] in psa_node_ids, (
                f"Edge target {edge['target']} not in PSA nodes"
            )

    # ------------------------------------------------------------------
    # 6. Node counts across sub-graphs sum to deal graph total
    #    (nodes with prefix only)
    # ------------------------------------------------------------------
    def test_doc_graph_node_count_sums_to_deal_graph(self, two_doc_graph, output_dir):
        stats = partition_graph_by_document(two_doc_graph, output_dir)
        total_partitioned = sum(stats.values())
        # Count nodes in deal graph that have a doc_name_prefix
        prefixed_nodes = sum(
            1 for _, a in two_doc_graph.nodes(data=True) if a.get("doc_name_prefix")
        )
        assert total_partitioned == prefixed_nodes

    # ------------------------------------------------------------------
    # 7. CROSS_DOC_TERM edges are added for shared defined terms
    # ------------------------------------------------------------------
    def test_cross_doc_term_edges_added(self, two_doc_graph):
        count = add_cross_document_edges(two_doc_graph)
        cross_term_edges = [
            (u, v) for u, v, d in two_doc_graph.edges(data=True)
            if d.get("type") == "CROSS_DOC_TERM"
        ]
        assert len(cross_term_edges) >= 1, "Expected at least one CROSS_DOC_TERM edge"

    # ------------------------------------------------------------------
    # 8. CROSS_DOC_ENTITY edges are added for shared entities
    # ------------------------------------------------------------------
    def test_cross_doc_entity_edges_added(self, two_doc_graph):
        add_cross_document_edges(two_doc_graph)
        cross_entity_edges = [
            (u, v) for u, v, d in two_doc_graph.edges(data=True)
            if d.get("type") == "CROSS_DOC_ENTITY"
        ]
        assert len(cross_entity_edges) >= 1, "Expected at least one CROSS_DOC_ENTITY edge"

    # ------------------------------------------------------------------
    # 9. Cross-doc edges carry source_doc and target_doc attributes
    # ------------------------------------------------------------------
    def test_cross_doc_edges_have_attributes(self, two_doc_graph):
        add_cross_document_edges(two_doc_graph)
        cross_edges = [
            d for _, _, d in two_doc_graph.edges(data=True)
            if d.get("type", "").startswith("CROSS_DOC_")
        ]
        assert len(cross_edges) > 0, "No cross-doc edges found"
        for edge_data in cross_edges:
            assert "source_doc" in edge_data, f"Missing source_doc: {edge_data}"
            assert "target_doc" in edge_data, f"Missing target_doc: {edge_data}"
            assert edge_data["source_doc"] != edge_data["target_doc"]

    # ------------------------------------------------------------------
    # 10. Partitioning is idempotent (same results on second run)
    # ------------------------------------------------------------------
    def test_partition_idempotent(self, two_doc_graph, output_dir):
        stats1 = partition_graph_by_document(two_doc_graph, output_dir)
        stats2 = partition_graph_by_document(two_doc_graph, output_dir)
        assert stats1 == stats2
        # Also verify file contents are identical
        doc_dir = Path(output_dir) / "doc_graphs"
        for prefix in stats1:
            p = doc_dir / f"{prefix}.json"
            data = json.loads(p.read_text(encoding="utf-8"))
            assert len(data["nodes"]) == stats1[prefix]

    # ------------------------------------------------------------------
    # 11. Single-document deal produces exactly one sub-graph file
    # ------------------------------------------------------------------
    def test_partition_single_doc_deal(self, output_dir):
        G = nx.DiGraph()
        G.add_node("DOC_PSA", type="DOCUMENT", doc_name_prefix="PSA")
        G.add_node("SEC_1", type="SECTION", doc_name_prefix="PSA")
        G.add_edge("DOC_PSA", "SEC_1", type="CONTAINS")

        stats = partition_graph_by_document(G, output_dir)
        assert len(stats) == 1
        assert "PSA" in stats
        doc_dir = Path(output_dir) / "doc_graphs"
        json_files = list(doc_dir.glob("*.json"))
        assert len(json_files) == 1
        assert json_files[0].name == "PSA.json"

    # ------------------------------------------------------------------
    # 12. Nodes without doc_name_prefix are excluded gracefully
    # ------------------------------------------------------------------
    def test_partition_handles_nodes_without_prefix(self, output_dir):
        G = nx.DiGraph()
        G.add_node("DOC_PSA", type="DOCUMENT", doc_name_prefix="PSA")
        G.add_node("ORPHAN_NODE", type="MISC")  # no doc_name_prefix
        G.add_node("SEC_1", type="SECTION", doc_name_prefix="PSA")
        G.add_edge("DOC_PSA", "SEC_1", type="CONTAINS")

        stats = partition_graph_by_document(G, output_dir)
        # Only "PSA" prefix should exist; orphan is silently excluded
        assert "PSA" in stats
        assert stats["PSA"] == 2  # DOC_PSA + SEC_1
        # ORPHAN_NODE should not appear in any sub-graph
        psa_data = json.loads(
            (Path(output_dir) / "doc_graphs" / "PSA.json").read_text(encoding="utf-8")
        )
        assert "ORPHAN_NODE" not in psa_data["nodes"]

    # ------------------------------------------------------------------
    # 13. add_cross_document_edges returns an int >= 0
    # ------------------------------------------------------------------
    def test_add_cross_doc_edges_returns_count(self, two_doc_graph):
        result = add_cross_document_edges(two_doc_graph)
        assert isinstance(result, int)
        assert result >= 0
        # With our fixture we expect at least 2 cross-doc edges
        # (1 CROSS_DOC_TERM for "Distribution Date", 1 CROSS_DOC_ENTITY for "Wells Fargo")
        assert result >= 2

    # ------------------------------------------------------------------
    # 14. Saved JSON has the expected structure (nodes dict, edges list)
    # ------------------------------------------------------------------
    def test_doc_graph_json_format(self, two_doc_graph, output_dir):
        partition_graph_by_document(two_doc_graph, output_dir)
        psa_json = Path(output_dir) / "doc_graphs" / "PSA.json"
        data = json.loads(psa_json.read_text(encoding="utf-8"))
        # Top-level keys
        assert "nodes" in data
        assert "edges" in data
        # nodes is a dict of dicts, each with an "id" key
        assert isinstance(data["nodes"], dict)
        for node_id, node_attrs in data["nodes"].items():
            assert "id" in node_attrs
            assert node_attrs["id"] == node_id
        # edges is a list of dicts with source/target
        assert isinstance(data["edges"], list)
        for edge in data["edges"]:
            assert "source" in edge
            assert "target" in edge

    # ------------------------------------------------------------------
    # 15. Empty graph → no files, no crash
    # ------------------------------------------------------------------
    def test_partition_with_empty_graph(self, output_dir):
        G = nx.DiGraph()
        stats = partition_graph_by_document(G, output_dir)
        assert stats == {}
        doc_dir = Path(output_dir) / "doc_graphs"
        assert doc_dir.is_dir()
        json_files = list(doc_dir.glob("*.json"))
        assert len(json_files) == 0
