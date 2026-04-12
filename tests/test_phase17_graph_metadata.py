"""Phase 17 — Dual Graph Metadata tests (Step 2).

Validates that ``doc_name_prefix`` is correctly stamped on every node and
edge produced by both the *EnhancedGraphBuilder* (hierarchical) and the
basic *GraphBuilder* (metadata-driven) pipelines.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.graph.persistence import GraphStore
from backend.graph.enhanced_graph_builder import EnhancedGraphBuilder
from backend.graph.builder import GraphBuilder
from backend.common.models import IngestedDocument
from backend.extraction.item_extractor_base import Item


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_sections(n: int = 2) -> List[Dict[str, Any]]:
    """Return *n* minimal section dicts suitable for EnhancedGraphBuilder."""
    sections = []
    for i in range(n):
        sections.append({
            "section_number": f"{i + 1}.01",
            "section_heading": f"Section {i + 1}",
            "section_text": f'"Alpha Term" means the first term. This is section {i + 1} body text with enough content.',
        })
    return sections


def _make_items(document_id: str, section_index: int, count: int = 1) -> List[Item]:
    """Create minimal Item objects that the enhanced builder would store."""
    items = []
    for j in range(count):
        items.append(Item(
            id=f"item:{document_id}:s{section_index}:i{j}",
            item_type="Obligation" if j % 2 == 0 else "Definition",
            text=f'"Test Term {j}" means something. Sample obligation number {j}.',
            document_id=document_id,
            section_number=f"{section_index + 1}.01",
            section_heading=f"Section {section_index + 1}",
            section_index=section_index,
            item_index=j,
        ))
    return items


@pytest.fixture()
def tmp_graph_store(tmp_path) -> GraphStore:
    """Return a GraphStore backed by a temp directory."""
    return GraphStore(str(tmp_path / "graph.json"))


@pytest.fixture()
def enhanced_builder(tmp_graph_store) -> EnhancedGraphBuilder:
    return EnhancedGraphBuilder(tmp_graph_store)


def _build_enhanced_graph(
    enhanced_builder: EnhancedGraphBuilder,
    *,
    doc_id: str = "test_doc",
    doc_type: str = "legal_contract",
    prefix: str = "PSA",
    sections: List[Dict[str, Any]] | None = None,
) -> nx.DiGraph:
    """Build a hierarchical graph and return the DiGraph from store."""
    if sections is None:
        sections = _make_sections(2)

    # Patch item extractor so we control output without real NLP
    fake_items_by_section: Dict[int, List[Item]] = {}
    for idx in range(len(sections)):
        fake_items_by_section[idx] = _make_items(doc_id, idx, count=2)

    def _fake_extract(section_text, section_number, section_heading, section_index, document_id):
        return fake_items_by_section.get(section_index, [])

    with patch("backend.graph.enhanced_graph_builder.get_item_extractor") as mock_get:
        mock_extractor = MagicMock()
        mock_extractor.extract_items.side_effect = _fake_extract
        mock_get.return_value = mock_extractor

        enhanced_builder.build_hierarchical_graph(
            document_id=doc_id,
            doc_type=doc_type,
            sections=sections,
            doc_metadata={"title": f"{prefix}_TestDoc"},
            doc_name_prefix=prefix,
        )

    return enhanced_builder.store.load()


# ---------------------------------------------------------------------------
# Test 1 — Document node carries doc_name_prefix
# ---------------------------------------------------------------------------

def test_enhanced_builder_stamps_doc_prefix_on_doc_node(enhanced_builder):
    """The DOCUMENT node must carry doc_name_prefix='PSA'."""
    G = _build_enhanced_graph(enhanced_builder, prefix="PSA")
    doc_nodes = [n for n, d in G.nodes(data=True) if d.get("type") == "DOCUMENT"]
    assert len(doc_nodes) >= 1, "Expected at least one DOCUMENT node"
    for nid in doc_nodes:
        assert G.nodes[nid]["doc_name_prefix"] == "PSA"


# ---------------------------------------------------------------------------
# Test 2 — All SECTION nodes carry the prefix
# ---------------------------------------------------------------------------

def test_enhanced_builder_stamps_doc_prefix_on_section_nodes(enhanced_builder):
    """Every SECTION node must have doc_name_prefix set to the build prefix."""
    G = _build_enhanced_graph(enhanced_builder, prefix="TRUST")
    section_nodes = [n for n, d in G.nodes(data=True) if d.get("type") == "SECTION"]
    assert len(section_nodes) >= 2, "Expected at least 2 SECTION nodes"
    for nid in section_nodes:
        assert G.nodes[nid]["doc_name_prefix"] == "TRUST", (
            f"SECTION node {nid} missing or wrong doc_name_prefix"
        )


# ---------------------------------------------------------------------------
# Test 3 — All ITEM nodes carry the prefix
# ---------------------------------------------------------------------------

def test_enhanced_builder_stamps_doc_prefix_on_item_nodes(enhanced_builder):
    """Every ITEM node must have doc_name_prefix set."""
    G = _build_enhanced_graph(enhanced_builder, prefix="INDENTURE")
    item_nodes = [n for n, d in G.nodes(data=True) if d.get("type") == "ITEM"]
    assert len(item_nodes) >= 1, "Expected at least one ITEM node"
    for nid in item_nodes:
        assert G.nodes[nid]["doc_name_prefix"] == "INDENTURE"


# ---------------------------------------------------------------------------
# Test 4 — All edges carry the prefix
# ---------------------------------------------------------------------------

def test_enhanced_builder_stamps_doc_prefix_on_edges(enhanced_builder):
    """Every edge produced by the enhanced builder must carry doc_name_prefix."""
    G = _build_enhanced_graph(enhanced_builder, prefix="PSA")
    assert G.number_of_edges() > 0, "Expected at least one edge"
    for src, tgt, data in G.edges(data=True):
        assert data.get("doc_name_prefix") == "PSA", (
            f"Edge ({src} -> {tgt}) missing doc_name_prefix"
        )


# ---------------------------------------------------------------------------
# Test 5 — Basic GraphBuilder stamps prefix from metadata
# ---------------------------------------------------------------------------

def test_basic_builder_stamps_doc_prefix(tmp_graph_store):
    """GraphBuilder.upsert_document should set doc_name_prefix via metadata."""
    builder = GraphBuilder(tmp_graph_store)
    doc = IngestedDocument(
        doc_id="basic_test",
        title="PSA_SomeDoc",
        source_path="/fake/PSA_SomeDoc.pdf",
        extension=".pdf",
        content_path="/fake/content",
        metadata_path="/fake/meta",
        images_dir="/fake/images",
        extracted_text='"Holder" means the registered holder of a Certificate.',
    )
    metadata = {
        "title": "PSA_SomeDoc",
        "doc_type": "legal_contract",
        "doc_regime": "TRUST",
        "doc_name_prefix": "PSA",
        "tools": [],
        "topics": [],
        "error_codes": [],
        "processes": [],
        "entities": [],
        "keyphrases": [],
    }
    G = builder.upsert_document(doc, metadata)

    doc_node = G.nodes.get("doc:basic_test", {})
    assert doc_node.get("doc_name_prefix") == "PSA"


# ---------------------------------------------------------------------------
# Test 6 — Ingestion agent passes doc_name_prefix to graph builder (mock)
# ---------------------------------------------------------------------------

def test_ingestion_passes_doc_prefix_to_graph():
    """Verify the ingestion agent's _extract_doc_name_prefix helper produces
    correct prefixes that are then forwarded to build_hierarchical_graph."""
    from backend.agents.ingestion_agent import _extract_doc_name_prefix

    # Known legal-doc prefixes
    assert _extract_doc_name_prefix("PSA_BearStearns_2006") == "PSA"
    assert _extract_doc_name_prefix("Trust_Agreement_2007") == "TRUST"
    assert _extract_doc_name_prefix("Indenture_v3") == "INDENTURE"

    # Generic fallback (first token uppercased)
    assert _extract_doc_name_prefix("quarterly_report") == "QUARTERLY"

    # Verify the call-site in ingestion_agent.py references the helper
    # (source-level check — ensures the wiring exists)
    import inspect, backend.agents.ingestion_agent as mod
    src = inspect.getsource(mod)
    assert "doc_name_prefix=_extract_doc_name_prefix(" in src, (
        "IngestionAgent must pass doc_name_prefix via _extract_doc_name_prefix"
    )


# ---------------------------------------------------------------------------
# Test 7 — Multi-doc graph preserves both prefixes after compose
# ---------------------------------------------------------------------------

def test_multi_doc_graph_has_both_prefixes(tmp_path):
    """Two graphs with different prefixes, composed, should retain both."""
    store1 = GraphStore(str(tmp_path / "g1.json"))
    store2 = GraphStore(str(tmp_path / "g2.json"))
    b1 = EnhancedGraphBuilder(store1)
    b2 = EnhancedGraphBuilder(store2)

    G1 = _build_enhanced_graph(b1, doc_id="doc_a", prefix="PSA")
    G2 = _build_enhanced_graph(b2, doc_id="doc_b", prefix="TRUST")

    composed = nx.compose(G1, G2)

    prefixes_found = {d.get("doc_name_prefix") for _, d in composed.nodes(data=True) if d.get("doc_name_prefix")}
    assert "PSA" in prefixes_found, "PSA prefix missing after compose"
    assert "TRUST" in prefixes_found, "TRUST prefix missing after compose"


# ---------------------------------------------------------------------------
# Test 8 — Backward compatibility: building without doc_name_prefix
# ---------------------------------------------------------------------------

def test_graph_without_prefix_backward_compatible(tmp_path):
    """Building without doc_name_prefix should not crash; attr defaults to ''."""
    store = GraphStore(str(tmp_path / "compat.json"))
    builder = EnhancedGraphBuilder(store)

    sections = _make_sections(1)

    with patch("backend.graph.enhanced_graph_builder.get_item_extractor") as mock_get:
        mock_extractor = MagicMock()
        mock_extractor.extract_items.return_value = _make_items("compat_doc", 0, 1)
        mock_get.return_value = mock_extractor

        # Explicit: do NOT pass doc_name_prefix (uses default "")
        stats = builder.build_hierarchical_graph(
            document_id="compat_doc",
            doc_type="legal_contract",
            sections=sections,
        )

    assert stats["sections_created"] >= 1
    G = store.load()
    doc_node = G.nodes.get("doc:compat_doc", {})
    assert doc_node.get("doc_name_prefix") == "", (
        "Default doc_name_prefix should be empty string"
    )


# ---------------------------------------------------------------------------
# Test 9 — DEFINED_TERM nodes from basic builder carry the prefix
# ---------------------------------------------------------------------------

def test_definition_nodes_have_prefix(tmp_graph_store):
    """DEFINED_TERM nodes produced by GraphBuilder must carry doc_name_prefix."""
    builder = GraphBuilder(tmp_graph_store)
    doc = IngestedDocument(
        doc_id="def_test",
        title="PSA_DefDoc",
        source_path="/fake/PSA_DefDoc.pdf",
        extension=".pdf",
        content_path="/fake/content",
        metadata_path="/fake/meta",
        images_dir="/fake/images",
        extracted_text='"Servicer" means the entity responsible for servicing.\n"Holder" means the registered holder.',
    )
    metadata = {
        "title": "PSA_DefDoc",
        "doc_type": "legal_contract",
        "doc_name_prefix": "PSA",
        "tools": [],
        "topics": [],
        "error_codes": [],
        "processes": [],
        "entities": [],
        "keyphrases": [],
    }
    G = builder.upsert_document(doc, metadata)

    defterm_nodes = [n for n, d in G.nodes(data=True) if d.get("type") == "DEFINED_TERM"]
    assert len(defterm_nodes) >= 1, "Expected at least one DEFINED_TERM node"
    for nid in defterm_nodes:
        assert G.nodes[nid].get("doc_name_prefix") == "PSA", (
            f"DEFINED_TERM node {nid} missing doc_name_prefix"
        )


# ---------------------------------------------------------------------------
# Test 10 — ENTITY nodes from basic builder carry the prefix
# ---------------------------------------------------------------------------

def test_entity_nodes_have_prefix(tmp_graph_store):
    """ENTITY nodes produced by GraphBuilder must carry doc_name_prefix."""
    builder = GraphBuilder(tmp_graph_store)
    doc = IngestedDocument(
        doc_id="ent_test",
        title="TRUST_EntDoc",
        source_path="/fake/TRUST_EntDoc.pdf",
        extension=".pdf",
        content_path="/fake/content",
        metadata_path="/fake/meta",
        images_dir="/fake/images",
        extracted_text="Some text about entities.",
    )
    metadata = {
        "title": "TRUST_EntDoc",
        "doc_type": "legal_contract",
        "doc_name_prefix": "TRUST",
        "tools": [],
        "topics": [],
        "error_codes": [],
        "processes": [],
        "entities": [
            {"text": "Bear Stearns", "label": "ORG"},
            {"text": "New York", "label": "GPE"},
        ],
        "keyphrases": [],
    }
    G = builder.upsert_document(doc, metadata)

    entity_nodes = [n for n, d in G.nodes(data=True) if d.get("type") == "ENTITY"]
    assert len(entity_nodes) >= 2, f"Expected at least 2 ENTITY nodes, got {len(entity_nodes)}"
    for nid in entity_nodes:
        assert G.nodes[nid].get("doc_name_prefix") == "TRUST", (
            f"ENTITY node {nid} missing doc_name_prefix"
        )
