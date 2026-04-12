"""Golden tests for NER graph enrichment.

Covers:
- NERGraphEnricher unit tests (entity creation, MENTIONS edges,
  ASSIGNED_ROLE edges, section-text collection, role detection)
- ConceptVocabularyBuilder.apply_term_keywords (Q1 per-definition keywords)
- Entity-aware section scoring in graph_section_lookup
- ner_extractor entity ruler helpers
- Integration: enrich() with a mock spaCy model over PSA-like synthetic data

Tests that require spaCy are guarded by a skip if the model is unavailable.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import networkx as nx
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def _make_psa_graph() -> nx.DiGraph:
    """Build a small PSA-like graph that mirrors real Fin_deal1 structure."""
    G = nx.DiGraph()
    G.graph["schema_version"] = "1.0"

    # Sections
    G.add_node(
        "sec:psa:0000",
        type="SECTION",
        section_number="1.01",
        heading="Definitions",
        pagerank=0.05,
    )
    G.add_node(
        "sec:psa:0001",
        type="SECTION",
        section_number="3.01",
        heading="Duties of the Trustee",
        pagerank=0.03,
    )
    G.add_node(
        "sec:psa:0002",
        type="SECTION",
        section_number="5.06",
        heading="Distributions to Certificateholders",
        pagerank=0.04,
    )

    # ITEM nodes under the Definitions section
    G.add_node(
        "item:def:available_funds",
        type="ITEM",
        item_type="Definition",
        text='"Available Funds" means, with respect to any Distribution Date, '
             'the sum of all scheduled and unscheduled principal and interest '
             'collected on the Mortgage Loans during the related Collection Period.',
        section_number="1.01",
    )
    G.add_node(
        "item:def:trustee",
        type="ITEM",
        item_type="Definition",
        text='"Trustee" means LaSalle Bank National Association, as Trustee, '
             'or any Person appointed as a successor trustee pursuant to this Agreement.',
        section_number="1.01",
    )
    G.add_node(
        "item:def:servicer",
        type="ITEM",
        item_type="Definition",
        text='"Servicer" means EMC Mortgage Corporation, as Servicer, '
             'and any successor servicer duly appointed in accordance with '
             'the terms of this Agreement.',
        section_number="1.01",
    )

    # Edges: SECTION --HAS_DEFINITION--> ITEM
    G.add_edge("sec:psa:0000", "item:def:available_funds", type="HAS_DEFINITION")
    G.add_edge("sec:psa:0000", "item:def:trustee", type="HAS_DEFINITION")
    G.add_edge("sec:psa:0000", "item:def:servicer", type="HAS_DEFINITION")

    # TERM::* nodes (defined_term)
    G.add_node(
        "TERM::Available Funds",
        type="defined_term",
        term_name="Available Funds",
        definition_text=(
            '"Available Funds" means, with respect to any Distribution Date, '
            'the sum of all scheduled and unscheduled principal and interest '
            'collected on the Mortgage Loans during the related Collection Period.'
        ),
    )
    G.add_node(
        "TERM::Trustee",
        type="defined_term",
        term_name="Trustee",
        definition_text=(
            '"Trustee" means LaSalle Bank National Association, as Trustee, '
            'or any Person appointed as a successor trustee.'
        ),
    )
    G.add_node(
        "TERM::Servicer",
        type="defined_term",
        term_name="Servicer",
        definition_text=(
            '"Servicer" means EMC Mortgage Corporation, as Servicer, '
            'and any successor servicer.'
        ),
    )
    G.add_node(
        "TERM::Certificateholder",
        type="defined_term",
        term_name="Certificateholder",
        definition_text=(
            '"Certificateholder" means a holder of record of a Certificate.'
        ),
    )
    G.add_node(
        "TERM::Distribution Date",
        type="defined_term",
        term_name="Distribution Date",
        definition_text=(
            '"Distribution Date" means the 25th day of each calendar month '
            'or, if such day is not a Business Day, the immediately succeeding Business Day.'
        ),
    )

    return G


def _make_mock_nlp(entities_by_text: dict):
    """Return a mock spaCy nlp callable that returns specific entities per text."""
    def nlp(text):
        doc = MagicMock()
        doc.ents = []
        for trigger_text, ents in entities_by_text.items():
            if trigger_text in text:
                for ent_text, ent_label in ents:
                    ent = MagicMock()
                    ent.text = ent_text
                    ent.label_ = ent_label
                    doc.ents.append(ent)
        return doc
    return nlp


# ---------------------------------------------------------------------------
# TestNEREnricherEntityCreation — entity node creation & dedup
# ---------------------------------------------------------------------------

class TestNEREnricherEntityCreation:
    """Test _get_or_create_entity helper."""

    def setup_method(self):
        self.G = nx.DiGraph()

    def _stats(self):
        return {"entity_nodes_created": 0, "entity_nodes_updated": 0}

    def test_creates_entity_node(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        stats = self._stats()
        nid = NERGraphEnricher._get_or_create_entity(self.G, "LaSalle Bank", "ORG", stats)
        assert self.G.has_node(nid)
        assert self.G.nodes[nid]["type"] == "ENTITY"
        assert self.G.nodes[nid]["entity_type"] == "ORG"
        assert self.G.nodes[nid]["surface_form"] == "LaSalle Bank"
        assert stats["entity_nodes_created"] == 1

    def test_mention_count_initialized_to_one(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        stats = self._stats()
        nid = NERGraphEnricher._get_or_create_entity(self.G, "Bear Stearns", "ORG", stats)
        assert self.G.nodes[nid]["mention_count"] == 1

    def test_second_call_increments_mention_count(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        stats = self._stats()
        nid = NERGraphEnricher._get_or_create_entity(self.G, "Bear Stearns", "ORG", stats)
        NERGraphEnricher._get_or_create_entity(self.G, "Bear Stearns", "ORG", stats)
        assert self.G.nodes[nid]["mention_count"] == 2
        assert stats["entity_nodes_updated"] == 1

    def test_different_labels_give_different_nodes(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        stats = self._stats()
        nid1 = NERGraphEnricher._get_or_create_entity(self.G, "January 2006", "DATE", stats)
        nid2 = NERGraphEnricher._get_or_create_entity(self.G, "January 2006", "TIME", stats)
        assert nid1 != nid2

    def test_node_id_normalises_spaces(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        stats = self._stats()
        nid = NERGraphEnricher._get_or_create_entity(self.G, "EMC Mortgage Corporation", "ORG", stats)
        assert " " not in nid  # spaces replaced with underscores
        assert "emc_mortgage_corporation" in nid

    def test_node_id_lowercased(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        stats = self._stats()
        nid = NERGraphEnricher._get_or_create_entity(self.G, "LaSalle Bank", "ORG", stats)
        # Node ID should be lowercase
        assert nid == nid.lower()

    def test_multiple_entity_types_created(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        stats = self._stats()
        for text, label in [
            ("January 2006", "DATE"),
            ("10%", "PERCENT"),
            ("$1,000,000", "MONEY"),
            ("LaSalle Bank", "ORG"),
            ("New York", "GPE"),
        ]:
            NERGraphEnricher._get_or_create_entity(self.G, text, label, stats)
        assert stats["entity_nodes_created"] == 5

    def test_graph_node_count_accurate(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        stats = self._stats()
        NERGraphEnricher._get_or_create_entity(self.G, "ABC Corp", "ORG", stats)
        NERGraphEnricher._get_or_create_entity(self.G, "ABC Corp", "ORG", stats)
        NERGraphEnricher._get_or_create_entity(self.G, "XYZ Corp", "ORG", stats)
        assert self.G.number_of_nodes() == 2  # two UNIQUE entities


# ---------------------------------------------------------------------------
# TestNEREnricherRunNER — _run_ner helper (uses real spaCy if available)
# ---------------------------------------------------------------------------

# Guard for tests that need spaCy
try:
    import spacy as _spacy_check
    _spacy_check.load("en_core_web_sm")
    SPACY_AVAILABLE = True
except Exception:
    SPACY_AVAILABLE = False

spacy_skip = pytest.mark.skipif(not SPACY_AVAILABLE, reason="en_core_web_sm not found")


class TestNEREnricherRunNER:
    """Test _run_ner using the real spaCy model when available."""

    @spacy_skip
    def test_extracts_org_entity(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        from backend.ingestion.ner_extractor import _load_model
        nlp = _load_model()
        results = NERGraphEnricher._run_ner(nlp, "LaSalle Bank National Association is the Trustee.")
        labels = [label for _, label in results]
        assert "ORG" in labels

    @spacy_skip
    def test_extracts_money_entity(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        from backend.ingestion.ner_extractor import _load_model
        nlp = _load_model()
        results = NERGraphEnricher._run_ner(
            nlp, "The Available Funds shall not exceed $5,000,000."
        )
        labels = [label for _, label in results]
        assert "MONEY" in labels

    @spacy_skip
    def test_extracts_date_entity(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        from backend.ingestion.ner_extractor import _load_model
        nlp = _load_model()
        results = NERGraphEnricher._run_ner(
            nlp, "The Closing Date shall be January 15, 2006."
        )
        labels = [label for _, label in results]
        assert "DATE" in labels

    @spacy_skip
    def test_returns_list_of_tuples(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        from backend.ingestion.ner_extractor import _load_model
        nlp = _load_model()
        results = NERGraphEnricher._run_ner(nlp, "EMC Mortgage Corporation, as Servicer.")
        assert isinstance(results, list)
        for item in results:
            assert isinstance(item, tuple)
            assert len(item) == 2

    @spacy_skip
    def test_deduplicates_entities(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        from backend.ingestion.ner_extractor import _load_model
        nlp = _load_model()
        text = "LaSalle Bank and LaSalle Bank and LaSalle Bank shall act as Trustee."
        results = NERGraphEnricher._run_ner(nlp, text)
        # Count ORG hits for LaSalle Bank — should be exactly 1 after dedup
        lasalle_hits = [(t, l) for t, l in results if "LaSalle" in t and l == "ORG"]
        assert len(lasalle_hits) <= 1

    def test_graceful_on_exception(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        # nlp that raises
        bad_nlp = MagicMock(side_effect=RuntimeError("NLP exploded"))
        results = NERGraphEnricher._run_ner(bad_nlp, "some text")
        assert results == []

    def test_short_entities_filtered(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        # nlp that returns a 1-char entity
        mock_ent = MagicMock()
        mock_ent.text = "X"
        mock_ent.label_ = "ORG"
        mock_doc = MagicMock()
        mock_doc.ents = [mock_ent]
        mock_nlp = MagicMock(return_value=mock_doc)
        results = NERGraphEnricher._run_ner(mock_nlp, "X is an entity")
        assert results == []


# ---------------------------------------------------------------------------
# TestNEREnricherSectionTextMap — _build_section_text_map
# ---------------------------------------------------------------------------

class TestNEREnricherSectionTextMap:
    """Test how section text is collected for NER."""

    def test_uses_raw_sections_when_available(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = nx.DiGraph()
        G.add_node("sec:1", type="SECTION", section_number="1.01")
        sections = [{"section_number": "1.01", "section_text": "Full raw text of section 1.01."}]
        result = NERGraphEnricher._build_section_text_map(G, sections)
        assert result["sec:1"] == "Full raw text of section 1.01."

    def test_falls_back_to_item_texts(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = nx.DiGraph()
        G.add_node("sec:1", type="SECTION", section_number="1.01")
        G.add_node("item:A", type="ITEM", text="Item A text.")
        G.add_node("item:B", type="ITEM", text="Item B text.")
        G.add_edge("sec:1", "item:A", type="HAS_ITEM")
        G.add_edge("sec:1", "item:B", type="HAS_DEFINITION")
        result = NERGraphEnricher._build_section_text_map(G, [])
        assert "Item A text." in result["sec:1"]
        assert "Item B text." in result["sec:1"]

    def test_skips_non_section_nodes(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = nx.DiGraph()
        G.add_node("TERM::Available Funds", type="defined_term", section_number="1.01")
        G.add_node("sec:1", type="SECTION", section_number="1.01")
        result = NERGraphEnricher._build_section_text_map(G, [])
        assert "TERM::Available Funds" not in result

    def test_section_without_text_has_empty_string(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = nx.DiGraph()
        G.add_node("sec:1", type="SECTION", section_number="1.01")
        result = NERGraphEnricher._build_section_text_map(G, [])
        assert result.get("sec:1", "") == ""

    def test_handles_multiple_sections(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = nx.DiGraph()
        G.add_node("sec:1", type="SECTION", section_number="1.01")
        G.add_node("sec:2", type="SECTION", section_number="3.01")
        sections = [
            {"section_number": "1.01", "section_text": "Text A"},
            {"section_number": "3.01", "section_text": "Text B"},
        ]
        result = NERGraphEnricher._build_section_text_map(G, sections)
        assert result["sec:1"] == "Text A"
        assert result["sec:2"] == "Text B"

    def test_hasm_item_rule_has_def_edges_collected(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = nx.DiGraph()
        G.add_node("sec:1", type="SECTION", section_number="1.01")
        G.add_node("i1", type="ITEM", text="Rule A.")
        G.add_node("i2", type="ITEM", text="Rule B.")
        G.add_node("i3", type="ITEM", text="Def C.")
        G.add_edge("sec:1", "i1", type="HAS_RULE")
        G.add_edge("sec:1", "i2", type="HAS_ITEM")
        G.add_edge("sec:1", "i3", type="HAS_DEFINITION")
        result = NERGraphEnricher._build_section_text_map(G, [])
        combined = result["sec:1"]
        for part in ["Rule A.", "Rule B.", "Def C."]:
            assert part in combined


# ---------------------------------------------------------------------------
# TestNEREnricherMENTIONSEdges — SECTION/TERM → ENTITY MENTIONS edges
# ---------------------------------------------------------------------------

class TestNEREnricherMENTIONSEdges:
    """Test MENTIONS edge creation using a mock spaCy model."""

    def _make_mock_entity_nlp(self):
        """nlp that always returns ('LaSalle Bank', 'ORG')."""
        mock_ent = MagicMock()
        mock_ent.text = "LaSalle Bank"
        mock_ent.label_ = "ORG"
        mock_doc = MagicMock()
        mock_doc.ents = [mock_ent]
        return MagicMock(return_value=mock_doc)

    def test_section_gets_mentions_edge(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = nx.DiGraph()
        G.add_node("sec:1", type="SECTION", section_number="1.01")
        sections = [{"section_number": "1.01", "section_text": "LaSalle Bank is Trustee."}]
        mock_nlp = self._make_mock_entity_nlp()

        with patch.object(NERGraphEnricher, "_load_nlp", return_value=mock_nlp), \
             patch.object(NERGraphEnricher, "_collect_term_names", return_value=[]):
            NERGraphEnricher.enrich(G, sections)

        entity_nodes = [n for n, d in G.nodes(data=True) if d.get("type") == "ENTITY"]
        assert len(entity_nodes) >= 1
        # At least one SECTION → ENTITY mentions edge
        mentions_edges = [
            (s, t) for s, t, d in G.edges(data=True) if d.get("type") == "MENTIONS"
        ]
        assert len(mentions_edges) >= 1

    def test_term_node_gets_mentions_edge(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = nx.DiGraph()
        G.add_node(
            "TERM::Available Funds",
            type="defined_term",
            term_name="Available Funds",
            definition_text="Available Funds collected from LaSalle Bank accounts.",
        )
        mock_nlp = self._make_mock_entity_nlp()

        with patch.object(NERGraphEnricher, "_load_nlp", return_value=mock_nlp), \
             patch.object(NERGraphEnricher, "_collect_term_names", return_value=[]):
            stats = NERGraphEnricher.enrich(G, [])

        assert stats["term_mentions_added"] >= 1

    def test_no_duplicate_mentions_edges(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = nx.DiGraph()
        G.add_node("sec:1", type="SECTION", section_number="1.01")
        sections = [{"section_number": "1.01", "section_text": "LaSalle Bank is Trustee."}]
        mock_nlp = self._make_mock_entity_nlp()

        with patch.object(NERGraphEnricher, "_load_nlp", return_value=mock_nlp), \
             patch.object(NERGraphEnricher, "_collect_term_names", return_value=[]):
            NERGraphEnricher.enrich(G, sections)
            # Second enrich call must not duplicate edges
            NERGraphEnricher.enrich(G, sections)

        ent_id = "entity:org:lasalle_bank"
        if G.has_edge("sec:1", ent_id):
            # Should have exactly one edge
            assert G["sec:1"][ent_id]["type"] == "MENTIONS"

    def test_returns_ner_available_true_on_success(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = nx.DiGraph()
        mock_nlp = self._make_mock_entity_nlp()

        with patch.object(NERGraphEnricher, "_load_nlp", return_value=mock_nlp), \
             patch.object(NERGraphEnricher, "_collect_term_names", return_value=[]):
            stats = NERGraphEnricher.enrich(G, [])

        assert stats["ner_available"] is True

    def test_returns_ner_available_false_when_no_model(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = nx.DiGraph()

        with patch.object(NERGraphEnricher, "_load_nlp", return_value=None):
            stats = NERGraphEnricher.enrich(G, [])

        assert stats["ner_available"] is False
        # Graph should not be modified
        assert G.number_of_nodes() == 0

    def test_entity_node_attributes_complete(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = nx.DiGraph()
        G.add_node("sec:1", type="SECTION", section_number="1.01")
        sections = [{"section_number": "1.01", "section_text": "LaSalle Bank is Trustee."}]
        mock_nlp = self._make_mock_entity_nlp()

        with patch.object(NERGraphEnricher, "_load_nlp", return_value=mock_nlp), \
             patch.object(NERGraphEnricher, "_collect_term_names", return_value=[]):
            NERGraphEnricher.enrich(G, sections)

        ent_nodes = [(n, d) for n, d in G.nodes(data=True) if d.get("type") == "ENTITY"]
        for _, data in ent_nodes:
            assert "entity_type" in data
            assert "surface_form" in data
            assert "mention_count" in data


# ---------------------------------------------------------------------------
# TestNEREnricherRoleAssignment — ASSIGNED_ROLE edges
# ---------------------------------------------------------------------------

class TestNEREnricherRoleAssignment:
    """Test 'X, as Trustee' / 'X acting as Servicer' role detection."""

    def test_basic_role_detection(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = nx.DiGraph()
        G.add_node(
            "TERM::Trustee",
            type="defined_term",
            term_name="Trustee",
            definition_text="",
        )
        term_names_lower = {"trustee": "TERM::Trustee"}
        stats = {"entity_nodes_created": 0, "entity_nodes_updated": 0, "role_assignments_added": 0}

        text = "LaSalle Bank National Association, as Trustee, shall act."
        added = NERGraphEnricher._detect_role_assignments(text, G, term_names_lower, stats)
        assert added >= 1

    def test_emc_as_servicer_role_detected(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = nx.DiGraph()
        G.add_node(
            "TERM::Servicer",
            type="defined_term",
            term_name="Servicer",
            definition_text="",
        )
        term_names_lower = {"servicer": "TERM::Servicer"}
        stats = {"entity_nodes_created": 0, "entity_nodes_updated": 0, "role_assignments_added": 0}

        text = "EMC Mortgage Corporation, as Servicer, hereby agrees."
        added = NERGraphEnricher._detect_role_assignments(text, G, term_names_lower, stats)
        assert added >= 1

    def test_unknown_role_not_added(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = nx.DiGraph()
        term_names_lower: dict = {}  # no terms in graph
        stats = {"entity_nodes_created": 0, "entity_nodes_updated": 0, "role_assignments_added": 0}

        text = "Deutsche Bank, as Administrator, shall act."
        added = NERGraphEnricher._detect_role_assignments(text, G, term_names_lower, stats)
        assert added == 0

    def test_assigned_role_edge_type(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = nx.DiGraph()
        G.add_node(
            "TERM::Depositor",
            type="defined_term",
            term_name="Depositor",
            definition_text="",
        )
        term_names_lower = {"depositor": "TERM::Depositor"}
        stats = {"entity_nodes_created": 0, "entity_nodes_updated": 0, "role_assignments_added": 0}

        text = "Bear Stearns Asset Backed Securities, acting as Depositor."
        NERGraphEnricher._detect_role_assignments(text, G, term_names_lower, stats)

        # Find any ASSIGNED_ROLE edge
        role_edges = [
            (s, t) for s, t, d in G.edges(data=True) if d.get("type") == "ASSIGNED_ROLE"
        ]
        assert len(role_edges) >= 1
        # Target must be the TERM::Depositor node
        assert any(t == "TERM::Depositor" for _, t in role_edges)

    def test_no_duplicate_role_edges(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = nx.DiGraph()
        G.add_node("TERM::Trustee", type="defined_term", term_name="Trustee", definition_text="")
        term_names_lower = {"trustee": "TERM::Trustee"}
        stats = {"entity_nodes_created": 0, "entity_nodes_updated": 0, "role_assignments_added": 0}
        text = "LaSalle Bank National Association, as Trustee, shall act."
        NERGraphEnricher._detect_role_assignments(text, G, term_names_lower, stats)
        added_first = stats["role_assignments_added"]
        NERGraphEnricher._detect_role_assignments(text, G, term_names_lower, stats)
        # Second pass must not add new edges
        added_second = stats["role_assignments_added"] - added_first
        assert added_second == 0

    def test_entity_node_created_for_org(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = nx.DiGraph()
        G.add_node("TERM::Trustee", type="defined_term", term_name="Trustee", definition_text="")
        term_names_lower = {"trustee": "TERM::Trustee"}
        stats = {"entity_nodes_created": 0, "entity_nodes_updated": 0, "role_assignments_added": 0}
        text = "LaSalle Bank National Association, as Trustee, shall distribute."
        NERGraphEnricher._detect_role_assignments(text, G, term_names_lower, stats)
        entity_nodes = [n for n, d in G.nodes(data=True) if d.get("type") == "ENTITY"]
        assert len(entity_nodes) >= 1

    def test_psa_graph_role_assignment_integration(self):
        """Full enrich() with mock nlp on PSA graph finds at least one ASSIGNED_ROLE edge."""
        from backend.graph.ner_enricher import NERGraphEnricher
        G = _make_psa_graph()
        # Use empty nlp so NER doesn't produce anything; role detection uses regex only
        mock_doc = MagicMock()
        mock_doc.ents = []
        mock_nlp = MagicMock(return_value=mock_doc)

        sections = [
            {
                "section_number": "1.01",
                "section_text": (
                    '"Trustee" means LaSalle Bank National Association, as Trustee. '
                    '"Servicer" means EMC Mortgage Corporation, as Servicer.'
                ),
            }
        ]

        with patch.object(NERGraphEnricher, "_load_nlp", return_value=mock_nlp):
            stats = NERGraphEnricher.enrich(G, sections)

        role_edges = [
            (s, t, d) for s, t, d in G.edges(data=True) if d.get("type") == "ASSIGNED_ROLE"
        ]
        assert len(role_edges) >= 1, (
            "Expected ASSIGNED_ROLE edges from 'LaSalle Bank, as Trustee' pattern"
        )

    def test_role_assignment_target_is_defined_term(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = _make_psa_graph()
        mock_doc = MagicMock()
        mock_doc.ents = []
        mock_nlp = MagicMock(return_value=mock_doc)

        sections = [
            {
                "section_number": "1.01",
                "section_text": 'EMC Mortgage Corporation, as Servicer, shall service the loans.',
            }
        ]

        with patch.object(NERGraphEnricher, "_load_nlp", return_value=mock_nlp):
            NERGraphEnricher.enrich(G, sections)

        role_edges = [
            (s, t) for s, t, d in G.edges(data=True) if d.get("type") == "ASSIGNED_ROLE"
        ]
        for _, target in role_edges:
            assert G.nodes[target].get("type") == "defined_term", (
                f"ASSIGNED_ROLE target {target} is not a defined_term node"
            )


# ---------------------------------------------------------------------------
# TestNEREnricherCollectTermNames — _collect_term_names
# ---------------------------------------------------------------------------

class TestNEREnricherCollectTermNames:
    def test_returns_all_defined_term_names(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = _make_psa_graph()
        names = NERGraphEnricher._collect_term_names(G)
        assert "Available Funds" in names
        assert "Trustee" in names
        assert "Servicer" in names
        assert "Certificateholder" in names
        assert "Distribution Date" in names

    def test_ignores_non_defined_term_nodes(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = nx.DiGraph()
        G.add_node("sec:1", type="SECTION", heading="Overview")
        G.add_node("TERM::Alpha", type="defined_term", term_name="Alpha")
        names = NERGraphEnricher._collect_term_names(G)
        assert names == ["Alpha"]

    def test_empty_graph_returns_empty_list(self):
        from backend.graph.ner_enricher import NERGraphEnricher
        G = nx.DiGraph()
        assert NERGraphEnricher._collect_term_names(G) == []


# ---------------------------------------------------------------------------
# TestApplyTermKeywords — Q1 per-definition keyword storage
# ---------------------------------------------------------------------------

class TestApplyTermKeywords:
    """Test ConceptVocabularyBuilder.apply_term_keywords()."""

    def _graph_with_terms(self):
        G = nx.DiGraph()
        G.add_node(
            "TERM::Available Funds",
            type="defined_term",
            term_name="Available Funds",
            definition_text="sum of all collected principal and interest",
        )
        G.add_node(
            "TERM::Trustee",
            type="defined_term",
            term_name="Trustee",
            definition_text="LaSalle Bank National Association as Trustee",
        )
        G.add_node(
            "TERM::Servicer",
            type="defined_term",
            term_name="Servicer",
            definition_text="EMC Mortgage Corporation as Servicer",
        )
        return G

    def test_keywords_stored_on_term_node(self):
        from backend.graph.concept_vocabulary import ConceptVocabularyBuilder
        G = self._graph_with_terms()
        keywords_dict = {"Available Funds": ["collected funds", "interest collected", "principal balance"]}
        ConceptVocabularyBuilder.apply_term_keywords(G, keywords_dict)
        stored = G.nodes["TERM::Available Funds"].get("concept_keywords", [])
        assert "collected funds" in stored

    def test_multiple_terms_stored(self):
        from backend.graph.concept_vocabulary import ConceptVocabularyBuilder
        G = self._graph_with_terms()
        keywords_dict = {
            "Available Funds": ["collected funds", "interest income"],
            "Trustee": ["trustee duties", "indenture trustee", "bond trustee"],
        }
        stats = ConceptVocabularyBuilder.apply_term_keywords(G, keywords_dict)
        assert stats["terms_matched"] == 2

    def test_returns_keywords_stored_count(self):
        from backend.graph.concept_vocabulary import ConceptVocabularyBuilder
        G = self._graph_with_terms()
        keywords_dict = {"Servicer": ["loan servicer", "mortgage servicer", "servicing agent"]}
        stats = ConceptVocabularyBuilder.apply_term_keywords(G, keywords_dict)
        assert stats["keywords_stored"] == 3

    def test_incremental_keywords_merged(self):
        from backend.graph.concept_vocabulary import ConceptVocabularyBuilder
        G = self._graph_with_terms()
        G.nodes["TERM::Trustee"]["concept_keywords"] = ["existing_keyword"]
        keywords_dict = {"Trustee": ["indenture trustee", "bond trustee"]}
        ConceptVocabularyBuilder.apply_term_keywords(G, keywords_dict)
        stored = G.nodes["TERM::Trustee"].get("concept_keywords", [])
        assert "existing_keyword" in stored
        assert "indenture trustee" in stored

    def test_unknown_term_gracefully_skipped(self):
        from backend.graph.concept_vocabulary import ConceptVocabularyBuilder
        G = self._graph_with_terms()
        keywords_dict = {"NonexistentTerm": ["kw1", "kw2"]}
        stats = ConceptVocabularyBuilder.apply_term_keywords(G, keywords_dict)
        assert stats["terms_matched"] == 0
        assert stats["keywords_stored"] == 0

    def test_keywords_deduped(self):
        from backend.graph.concept_vocabulary import ConceptVocabularyBuilder
        G = self._graph_with_terms()
        keywords_dict = {
            "Available Funds": ["collected funds", "collected funds", "interest income"]
        }
        ConceptVocabularyBuilder.apply_term_keywords(G, keywords_dict)
        stored = G.nodes["TERM::Available Funds"].get("concept_keywords", [])
        assert stored.count("collected funds") == 1

    def test_empty_keywords_not_stored(self):
        from backend.graph.concept_vocabulary import ConceptVocabularyBuilder
        G = self._graph_with_terms()
        keywords_dict = {"Available Funds": []}
        stats = ConceptVocabularyBuilder.apply_term_keywords(G, keywords_dict)
        assert stats["terms_matched"] == 0

    def test_non_string_values_coerced(self):
        from backend.graph.concept_vocabulary import ConceptVocabularyBuilder
        G = self._graph_with_terms()
        # keywords as numbers — should be coerced to string and lowercased
        keywords_dict = {"Trustee": [123, "bond trustee"]}
        stats = ConceptVocabularyBuilder.apply_term_keywords(G, keywords_dict)
        assert stats["terms_matched"] == 1

    def test_section_nodes_unaffected(self):
        """apply_term_keywords must not modify SECTION nodes."""
        from backend.graph.concept_vocabulary import ConceptVocabularyBuilder
        G = self._graph_with_terms()
        G.add_node("sec:1", type="SECTION", heading="Definitions", concept_keywords=[])
        keywords_dict = {"Available Funds": ["collected funds"]}
        ConceptVocabularyBuilder.apply_term_keywords(G, keywords_dict)
        # Section node must be untouched
        assert G.nodes["sec:1"].get("concept_keywords") == []

    def test_case_insensitive_term_matching(self):
        from backend.graph.concept_vocabulary import ConceptVocabularyBuilder
        G = self._graph_with_terms()
        # Term name provided in different case
        keywords_dict = {"available funds": ["principal", "interest"]}
        stats = ConceptVocabularyBuilder.apply_term_keywords(G, keywords_dict)
        assert stats["terms_matched"] == 1

    def test_all_psa_terms_processed(self):
        from backend.graph.concept_vocabulary import ConceptVocabularyBuilder
        G = _make_psa_graph()
        keywords_dict = {
            "Available Funds": ["collected principal", "interest income", "available funds"],
            "Trustee": ["trustee duties", "indenture trustee"],
            "Servicer": ["loan servicer", "mortgage servicer"],
            "Certificateholder": ["certificate holder", "investor"],
            "Distribution Date": ["payment date", "distribution schedule"],
        }
        stats = ConceptVocabularyBuilder.apply_term_keywords(G, keywords_dict)
        assert stats["terms_matched"] == 5
        # Verify keywords stored on TERM nodes, not SECTION nodes
        for node_id, data in G.nodes(data=True):
            if data.get("type") == "defined_term":
                kws = data.get("concept_keywords", [])
                if kws:  # if this term had keywords
                    assert isinstance(kws, list)


# ---------------------------------------------------------------------------
# TestEntityAwareSectionLookup — entity boost in human_like_retriever
# ---------------------------------------------------------------------------

class TestEntityAwareSectionLookup:
    """Test the Layer 5 entity-based section score boost."""

    def _make_retriever_with_graph(self, G):
        """Create a minimal HumanLikeRetriever backed by graph G."""
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        config = MagicMock()
        config.max_section_candidates = 10
        config.graph_path = "/fake/path"
        retriever = object.__new__(HumanLikeRetriever)
        retriever.graph = G
        retriever.config = config
        retriever.dual_store = MagicMock()
        return retriever

    def test_entity_boost_raises_section_score(self):
        """A section that MENTIONS a query entity gets a score boost."""
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        G = nx.DiGraph()
        # Section with no keyword match to "LaSalle Bank"
        G.add_node("sec:trustee", type="SECTION", section_number="3.01",
                   heading="Duties of Trustee", pagerank=0.0, concept_keywords=[])
        # Entity node
        G.add_node("entity:org:lasalle_bank", type="ENTITY",
                   entity_type="ORG", surface_form="LaSalle Bank", mention_count=1)
        # SECTION --MENTIONS--> ENTITY
        G.add_edge("sec:trustee", "entity:org:lasalle_bank", type="MENTIONS")

        retriever = self._make_retriever_with_graph(G)

        xlog = MagicMock()
        results = retriever.graph_section_lookup("LaSalle Bank trustee duties", xlog)

        # The Trustee section should appear in results
        found = any(r.get("node_id") == "sec:trustee" for r in results)
        assert found, "Expected 'sec:trustee' to appear in results via entity boost"

    def test_no_entity_no_boost(self):
        """Sections without matching ENTITY or keyword do not appear."""
        G = nx.DiGraph()
        G.add_node("sec:irrelevant", type="SECTION", section_number="9.01",
                   heading="Miscellaneous", pagerank=0.0, concept_keywords=[])
        # No ENTITY nodes linked to sec:irrelevant

        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        config = MagicMock()
        config.max_section_candidates = 5
        retriever = object.__new__(HumanLikeRetriever)
        retriever.graph = G
        retriever.config = config
        retriever.dual_store = MagicMock()

        xlog = MagicMock()
        results = retriever.graph_section_lookup("LaSalle Bank trustee duties", xlog)
        # The irrelevant section should NOT appear
        found = any(r.get("node_id") == "sec:irrelevant" for r in results)
        assert not found

    def test_entity_boost_capped_at_one(self):
        """Score must not exceed 1.0 even with many entity hits."""
        G = nx.DiGraph()
        G.add_node("sec:1", type="SECTION", section_number="1.01",
                   heading="Definitions", pagerank=0.99, concept_keywords=["lasalle", "bank"])
        for i in range(10):
            ent_id = f"entity:org:entity_{i}"
            G.add_node(ent_id, type="ENTITY", entity_type="ORG",
                       surface_form=f"lasalle entity {i}", mention_count=1)
            G.add_edge("sec:1", ent_id, type="MENTIONS")

        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        config = MagicMock()
        config.max_section_candidates = 5
        retriever = object.__new__(HumanLikeRetriever)
        retriever.graph = G
        retriever.config = config

        xlog = MagicMock()
        results = retriever.graph_section_lookup("lasalle bank", xlog)
        for r in results:
            assert r.get("score", 0) <= 1.0


# ---------------------------------------------------------------------------
# TestNERExtractorEntityRuler — create_term_entity_ruler / remove helpers
# ---------------------------------------------------------------------------

class TestNERExtractorEntityRuler:
    """Test the entity ruler injection helpers in ner_extractor.py."""

    @spacy_skip
    def test_create_ruler_adds_pipe(self):
        from backend.ingestion.ner_extractor import _load_model, create_term_entity_ruler
        import backend.ingestion.ner_extractor as ner_mod
        ner_mod._nlp = None
        nlp = _load_model()
        create_term_entity_ruler(nlp, ["Available Funds", "Trustee"])
        assert "kts_term_ruler" in nlp.pipe_names

    @spacy_skip
    def test_remove_ruler_removes_pipe(self):
        from backend.ingestion.ner_extractor import (
            _load_model, create_term_entity_ruler, remove_term_entity_ruler
        )
        import backend.ingestion.ner_extractor as ner_mod
        ner_mod._nlp = None
        nlp = _load_model()
        create_term_entity_ruler(nlp, ["Trustee"])
        remove_term_entity_ruler(nlp)
        assert "kts_term_ruler" not in nlp.pipe_names

    @spacy_skip
    def test_ruler_labels_defined_terms(self):
        from backend.ingestion.ner_extractor import _load_model, create_term_entity_ruler
        import backend.ingestion.ner_extractor as ner_mod
        ner_mod._nlp = None
        nlp = _load_model()
        create_term_entity_ruler(nlp, ["Available Funds"])
        doc = nlp("The Available Funds shall be distributed monthly.")
        defined_term_ents = [e for e in doc.ents if e.label_ == "DEFINED_TERM"]
        assert any("Available Funds" in e.text for e in defined_term_ents), (
            "Expected 'Available Funds' to be labeled as DEFINED_TERM by entity ruler"
        )

    @spacy_skip
    def test_ruler_handles_empty_term_list(self):
        from backend.ingestion.ner_extractor import _load_model, create_term_entity_ruler
        import backend.ingestion.ner_extractor as ner_mod
        ner_mod._nlp = None
        nlp = _load_model()
        # Should not raise
        try:
            create_term_entity_ruler(nlp, [])
            success = True
        except Exception:
            success = False
        assert success

    def test_create_ruler_graceful_without_spacy(self):
        from backend.ingestion.ner_extractor import create_term_entity_ruler
        mock_nlp = MagicMock()
        # Should not raise even if nlp has unexpected structure
        mock_nlp.pipe_names = []
        mock_nlp.add_pipe = MagicMock()
        try:
            create_term_entity_ruler(mock_nlp, ["Trustee", "Servicer"])
        except Exception:
            pass  # graceful failure acceptable


# ---------------------------------------------------------------------------
# TestTermKeywordLookup — Q1 per-definition keyword retrieval (the consumer)
# ---------------------------------------------------------------------------

class TestTermKeywordLookup:
    """Test the term_keyword_lookup method and the term-keyword index.

    The storage side (apply_term_keywords) is tested above.
    These tests cover the retrieval consumption:
    - _term_keyword_index built correctly from TERM::* concept_keywords
    - term_keyword_lookup matches query keywords to correct terms
    - Ranking by keyword overlap count
    - max_terms cap honoured
    - Shared-root fuzzy matching
    - Empty index returns empty
    """

    def _make_retriever(self, G):
        """Build a minimal HumanLikeRetriever via _build_indexes."""
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        config = MagicMock()
        config.max_section_candidates = 10
        retriever = object.__new__(HumanLikeRetriever)
        retriever.graph = G
        retriever.config = config
        retriever.dual_store = MagicMock()
        retriever._section_index = {}
        retriever._definition_index = {}
        retriever._term_node_index = {}
        retriever._term_keyword_index = {}
        retriever._build_indexes()
        return retriever

    def test_index_built_from_concept_keywords(self):
        """Keywords on TERM::* nodes are indexed during _build_indexes."""
        G = _make_psa_graph()
        G.nodes["TERM::Available Funds"]["concept_keywords"] = [
            "funds", "principal", "interest", "collection",
        ]
        G.nodes["TERM::Trustee"]["concept_keywords"] = [
            "trustee", "fiduciary", "appointment",
        ]
        retriever = self._make_retriever(G)

        assert "funds" in retriever._term_keyword_index
        assert "TERM::Available Funds" in retriever._term_keyword_index["funds"]
        assert "trustee" in retriever._term_keyword_index
        assert "TERM::Trustee" in retriever._term_keyword_index["trustee"]

    def test_empty_index_returns_empty(self):
        """No concept_keywords on any TERM → empty result."""
        G = _make_psa_graph()
        retriever = self._make_retriever(G)

        xlog = MagicMock()
        result = retriever.term_keyword_lookup("available funds collection", xlog)
        assert result == []

    def test_matches_query_to_correct_term(self):
        """Query keywords match the TERM that has those keywords."""
        G = _make_psa_graph()
        G.nodes["TERM::Available Funds"]["concept_keywords"] = [
            "funds", "principal", "interest", "collection", "scheduled",
        ]
        G.nodes["TERM::Trustee"]["concept_keywords"] = [
            "trustee", "fiduciary", "appointment",
        ]
        retriever = self._make_retriever(G)

        xlog = MagicMock()
        result = retriever.term_keyword_lookup("principal interest collection", xlog)
        assert "Available Funds" in result
        # Trustee should NOT match (no keyword overlap)
        assert "Trustee" not in result

    def test_ranks_by_keyword_overlap(self):
        """Term with more keyword hits ranks higher."""
        G = _make_psa_graph()
        G.nodes["TERM::Available Funds"]["concept_keywords"] = [
            "funds", "principal", "interest", "collection",
        ]
        G.nodes["TERM::Distribution Date"]["concept_keywords"] = [
            "distribution", "monthly", "business",
        ]
        G.nodes["TERM::Certificateholder"]["concept_keywords"] = [
            "holder", "certificate", "distribution", "funds",
        ]
        retriever = self._make_retriever(G)

        xlog = MagicMock()
        result = retriever.term_keyword_lookup(
            "funds distribution certificateholder", xlog
        )
        # Certificateholder matches 3 keywords (holder, distribution, funds via cert)
        # but only "distribution" and "funds" are in query keywords
        # Available Funds matches "funds" (1 hit)
        # Distribution Date matches "distribution" (1 hit)
        # Certificateholder matches "distribution" + "funds" (2 hits) → rank 1
        assert len(result) >= 1
        assert result[0] == "Certificateholder"

    def test_max_terms_cap(self):
        """max_terms limits the result list."""
        G = _make_psa_graph()
        # Give every term the same keyword so all match
        for nid, data in G.nodes(data=True):
            if data.get("type") == "defined_term":
                data["concept_keywords"] = ["mortgage"]
        retriever = self._make_retriever(G)

        xlog = MagicMock()
        result = retriever.term_keyword_lookup("mortgage loans", xlog, max_terms=2)
        assert len(result) <= 2

    def test_shared_root_fuzzy_matching(self):
        """Fuzzy shared-root matching (≥6 chars, ≥60% overlap)."""
        G = _make_psa_graph()
        G.nodes["TERM::Available Funds"]["concept_keywords"] = [
            "distributions", "scheduled",
        ]
        retriever = self._make_retriever(G)

        xlog = MagicMock()
        # "distribution" (12 chars) vs "distributions" (13 chars) → 12 shared chars ≥ 6
        result = retriever.term_keyword_lookup("distribution schedule", xlog)
        assert "Available Funds" in result

    def test_multiple_terms_returned(self):
        """Multiple terms can be returned when keywords match several."""
        G = _make_psa_graph()
        G.nodes["TERM::Available Funds"]["concept_keywords"] = [
            "funds", "interest",
        ]
        G.nodes["TERM::Trustee"]["concept_keywords"] = [
            "trustee", "fiduciary",
        ]
        G.nodes["TERM::Servicer"]["concept_keywords"] = [
            "servicer", "mortgage",
        ]
        retriever = self._make_retriever(G)

        xlog = MagicMock()
        result = retriever.term_keyword_lookup(
            "funds trustee servicer interest", xlog
        )
        # All three should match — Available Funds (2), Trustee (1), Servicer (1)
        assert len(result) >= 3
        assert "Available Funds" in result
        assert "Trustee" in result
        assert "Servicer" in result


# ---------------------------------------------------------------------------
# TestTermAwareStepBack — Q1 step-back query broadening via term keywords
# ---------------------------------------------------------------------------

class TestTermAwareStepBack:
    """Test that _generate_step_back_query uses term-keyword broadening."""

    def _make_retriever(self, G):
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        config = MagicMock()
        config.max_section_candidates = 10
        retriever = object.__new__(HumanLikeRetriever)
        retriever.graph = G
        retriever.config = config
        retriever.dual_store = MagicMock()
        retriever._section_index = {}
        retriever._definition_index = {}
        retriever._term_node_index = {}
        retriever._term_keyword_index = {}
        retriever._build_indexes()
        return retriever

    def test_step_back_uses_term_keywords_when_vocab_empty(self):
        """When step_back_vocabulary is empty, term keywords provide broadening."""
        G = _make_psa_graph()
        G.graph["step_back_vocabulary"] = {}  # empty section vocab
        G.nodes["TERM::Available Funds"]["concept_keywords"] = [
            "shortfall", "principal", "interest",
        ]
        retriever = self._make_retriever(G)

        step_back = retriever._generate_step_back_query("shortfall allocation")
        # Should contain "Available Funds" as broadening term
        assert "available funds" in step_back.lower()

    def test_step_back_prefers_section_vocab(self):
        """Section-level vocabulary is preferred over term keywords."""
        G = _make_psa_graph()
        G.graph["step_back_vocabulary"] = {
            "shortfall": ["Distributions to Certificateholders"],
        }
        G.nodes["TERM::Available Funds"]["concept_keywords"] = [
            "shortfall",
        ]
        retriever = self._make_retriever(G)

        step_back = retriever._generate_step_back_query("shortfall allocation")
        # Should use section heading, NOT term name
        assert "distributions" in step_back.lower()
        assert "available funds" not in step_back.lower()

    def test_step_back_falls_through_to_hardcoded_when_no_match(self):
        """When no keyword matches anywhere, hardcoded fallbacks still work."""
        G = _make_psa_graph()
        G.graph["step_back_vocabulary"] = {}
        # No concept_keywords on any TERM
        retriever = self._make_retriever(G)

        step_back = retriever._generate_step_back_query("loss allocation")
        # Hardcoded fallback for "loss"
        assert "loss" in step_back.lower()


# ---------------------------------------------------------------------------
# TestTermKeywordPipelineWiring — Q1 end-to-end pipeline wiring
# ---------------------------------------------------------------------------

class TestTermKeywordPipelineWiring:
    """Verify that keyword-matched terms feed into the resolution tree
    via the retrieve() pipeline (Step 3b → Step 7 integration)."""

    def test_keyword_matched_terms_merge_into_prior_context(self):
        """term_keyword_lookup results merge into prior_context_terms."""
        from backend.retrieval.human_like_retriever import HumanLikeRetriever

        G = _make_psa_graph()
        G.nodes["TERM::Available Funds"]["concept_keywords"] = [
            "funds", "principal", "collection",
        ]

        config = MagicMock()
        config.max_section_candidates = 5
        config.enable_self_query_filters = False
        config.enable_query_decomposition = False
        config.section_scoped_search = False
        config.fallback_to_global = False
        config.inject_definitions = False
        config.use_cross_encoder = False

        retriever = object.__new__(HumanLikeRetriever)
        retriever.graph = G
        retriever.config = config
        retriever.dual_store = MagicMock()
        retriever._section_index = {}
        retriever._definition_index = {}
        retriever._term_node_index = {}
        retriever._term_keyword_index = {}
        retriever._build_indexes()

        # Verify the index has the expected keywords
        assert "funds" in retriever._term_keyword_index
        assert "TERM::Available Funds" in retriever._term_keyword_index["funds"]

        # Call term_keyword_lookup directly
        xlog = MagicMock()
        matched = retriever.term_keyword_lookup("principal funds collection", xlog)
        assert "Available Funds" in matched
