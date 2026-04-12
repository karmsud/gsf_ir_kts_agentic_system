"""
Phase 6 — Enhanced Graph Builder + Schema tests.

Tests hierarchical graph construction (Document → Section → Item),
typed edges, REFERENCES edges, and schema validation.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest
import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.graph.persistence import GraphStore
from backend.graph.enhanced_graph_builder import EnhancedGraphBuilder
from backend.graph import schema as graph_schema


# ── Schema tests ─────────────────────────────────────────────────

class TestSchemaV22:
    def test_item_node_type(self):
        assert "ITEM" in graph_schema.NODE_TYPES

    def test_phase6_edge_types(self):
        expected = {
            "CONTAINS", "NEXT", "HAS_ITEM", "HAS_RULE", "HAS_DEFINITION",
            "HAS_RIGHT", "HAS_CONDITION", "HAS_REQUIREMENT", "HAS_PROCEDURE",
            "HAS_CONFIGURATION", "HAS_WARNING", "HAS_THEOREM", "HAS_PROOF",
            "HAS_LEMMA", "HAS_ALGORITHM", "REFERENCES",
        }
        assert expected.issubset(graph_schema.EDGE_TYPES)

    def test_item_required_properties(self):
        assert "ITEM" in graph_schema.REQUIRED_PROPERTIES
        assert "item_type" in graph_schema.REQUIRED_PROPERTIES["ITEM"]
        assert "document_id" in graph_schema.REQUIRED_PROPERTIES["ITEM"]

    def test_validate_item_node(self):
        graph_schema.validate_node("ITEM", {"item_type": "Obligation", "document_id": "doc1"})

    def test_validate_item_missing_props(self):
        with pytest.raises(graph_schema.SchemaValidationError):
            graph_schema.validate_node("ITEM", {"item_type": "Obligation"})  # missing document_id

    def test_validate_phase6_edges(self):
        for edge in ["CONTAINS", "NEXT", "HAS_RULE", "REFERENCES"]:
            graph_schema.validate_edge(edge)

    def test_schema_version(self):
        assert graph_schema.SCHEMA_VERSION == "2.2"


# ── EnhancedGraphBuilder tests ───────────────────────────────────

class TestEnhancedGraphBuilder:
    @pytest.fixture
    def graph_path(self, tmp_path):
        return str(tmp_path / "test_graph.json")

    @pytest.fixture
    def builder(self, graph_path):
        store = GraphStore(graph_path)
        return EnhancedGraphBuilder(store)

    @pytest.fixture
    def sample_sections(self):
        return [
            {
                "section_number": "1.01",
                "section_heading": "Definitions",
                "section_text": '"Available Funds" means the sum of all amounts collected. '
                                '"Distribution Date" means the 25th of each month.',
            },
            {
                "section_number": "2.01",
                "section_heading": "Distributions",
                "section_text": "The Trustee shall distribute Available Funds to Certificateholders "
                                "on each Distribution Date as described in Section 1.01.",
            },
            {
                "section_number": "3.01",
                "section_heading": "Restrictions",
                "section_text": "The Servicer shall not commingle funds with its own assets.",
            },
        ]

    def test_build_creates_nodes(self, builder, sample_sections):
        stats = builder.build_hierarchical_graph(
            document_id="psa_2006he1",
            doc_type="GOVERNING_DOC_LEGAL",
            sections=sample_sections,
        )
        assert stats["sections_created"] == 3
        assert stats["items_created"] > 0
        assert stats["edges_created"] > 0

    def test_document_node_created(self, builder, sample_sections, graph_path):
        builder.build_hierarchical_graph("doc1", "GOVERNING_DOC_LEGAL", sample_sections)
        G = GraphStore(graph_path).load()
        assert "doc:doc1" in G
        assert G.nodes["doc:doc1"]["type"] == "DOCUMENT"

    def test_section_nodes_created(self, builder, sample_sections, graph_path):
        builder.build_hierarchical_graph("doc1", "GOVERNING_DOC_LEGAL", sample_sections)
        G = GraphStore(graph_path).load()
        section_nodes = [n for n, d in G.nodes(data=True) if d.get("type") == "SECTION"]
        assert len(section_nodes) == 3

    def test_contains_edges(self, builder, sample_sections, graph_path):
        builder.build_hierarchical_graph("doc1", "GOVERNING_DOC_LEGAL", sample_sections)
        G = GraphStore(graph_path).load()
        contains_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("type") == "CONTAINS"]
        assert len(contains_edges) == 3  # doc → each section

    def test_next_edges(self, builder, sample_sections, graph_path):
        builder.build_hierarchical_graph("doc1", "GOVERNING_DOC_LEGAL", sample_sections)
        G = GraphStore(graph_path).load()
        next_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("type") == "NEXT"]
        assert len(next_edges) == 2  # section1→section2, section2→section3

    def test_item_nodes_created(self, builder, sample_sections, graph_path):
        builder.build_hierarchical_graph("doc1", "GOVERNING_DOC_LEGAL", sample_sections)
        G = GraphStore(graph_path).load()
        item_nodes = [n for n, d in G.nodes(data=True) if d.get("type") == "ITEM"]
        assert len(item_nodes) > 0

    def test_typed_edges_for_items(self, builder, sample_sections, graph_path):
        builder.build_hierarchical_graph("doc1", "GOVERNING_DOC_LEGAL", sample_sections)
        G = GraphStore(graph_path).load()
        typed_edges = [
            d.get("type") for _, _, d in G.edges(data=True)
            if d.get("type") not in {"CONTAINS", "NEXT", "REFERENCES"}
        ]
        # Should have at least one HAS_RULE, HAS_DEFINITION, etc.
        assert len(typed_edges) > 0

    def test_references_edges(self, builder, sample_sections, graph_path):
        builder.build_hierarchical_graph("doc1", "GOVERNING_DOC_LEGAL", sample_sections)
        G = GraphStore(graph_path).load()
        ref_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("type") == "REFERENCES"]
        # The section 2.01 mentions "Available Funds" defined in 1.01
        # so at least one REFERENCES edge should exist
        assert len(ref_edges) >= 1

    def test_graph_persists(self, builder, sample_sections, graph_path):
        builder.build_hierarchical_graph("doc1", "GOVERNING_DOC_LEGAL", sample_sections)
        # Verify file exists and is valid JSON
        assert Path(graph_path).exists()
        data = json.loads(Path(graph_path).read_text())
        assert "nodes" in data
        assert "edges" in data

    def test_idempotent_upsert(self, builder, sample_sections, graph_path):
        builder.build_hierarchical_graph("doc1", "GOVERNING_DOC_LEGAL", sample_sections)
        G1 = GraphStore(graph_path).load()
        node_count_1 = len(G1)

        # Build again — should update, not duplicate
        builder.build_hierarchical_graph("doc1", "GOVERNING_DOC_LEGAL", sample_sections)
        G2 = GraphStore(graph_path).load()
        node_count_2 = len(G2)

        # Same doc → same nodes (idempotent)
        assert node_count_2 == node_count_1

    def test_technical_doc_type(self, graph_path):
        store = GraphStore(graph_path)
        builder = EnhancedGraphBuilder(store)
        sections = [
            {
                "section_number": "3.1",
                "section_heading": "Input Validation",
                "section_text": "The system MUST validate all input fields. WARNING: Invalid input may crash the server.",
            }
        ]
        stats = builder.build_hierarchical_graph("spec1", "SOP", sections)
        assert stats["items_created"] > 0
