"""
Phase 6 — Item Extractor unit tests.

Tests all four domain extractors (legal, technical, research, generic)
and the factory routing function.
"""

from __future__ import annotations

import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.extraction.item_extractor_base import (
    Item,
    ItemExtractor,
    get_item_extractor,
)
from backend.extraction.legal_item_extractor import LegalItemExtractor
from backend.extraction.technical_item_extractor import TechnicalItemExtractor
from backend.extraction.research_item_extractor import ResearchItemExtractor
from backend.extraction.generic_item_extractor import GenericItemExtractor


# ── Factory routing ───────────────────────────────────────────────

class TestGetItemExtractor:
    def test_legal_doc_types(self):
        for dt in ["GOVERNING_DOC_LEGAL", "PSA", "INDENTURE", "CONTRACT", "AGREEMENT"]:
            ext = get_item_extractor(dt)
            assert isinstance(ext, LegalItemExtractor), f"Expected LegalItemExtractor for {dt}"

    def test_technical_doc_types(self):
        for dt in ["SOP", "API_DOC", "SPEC", "TECHNICAL_SPEC"]:
            ext = get_item_extractor(dt)
            assert isinstance(ext, TechnicalItemExtractor), f"Expected TechnicalItemExtractor for {dt}"

    def test_research_doc_types(self):
        for dt in ["RESEARCH", "THESIS", "PAPER", "RESEARCH_PAPER"]:
            ext = get_item_extractor(dt)
            assert isinstance(ext, ResearchItemExtractor), f"Expected ResearchItemExtractor for {dt}"

    def test_generic_fallback(self):
        ext = get_item_extractor("UNKNOWN_TYPE_XYZ")
        assert isinstance(ext, GenericItemExtractor)

    def test_keyword_routing(self):
        ext = get_item_extractor("my_pooling_trust_doc")
        assert isinstance(ext, LegalItemExtractor)


# ── Legal Extractor ──────────────────────────────────────────────

class TestLegalItemExtractor:
    @pytest.fixture
    def extractor(self):
        return LegalItemExtractor()

    def test_obligation_detection(self, extractor):
        text = "The Trustee shall distribute the Available Funds to the Certificateholders."
        items = extractor.extract_items(text, "2.01", "Distributions", 0, "test_doc")
        assert any(i.item_type == "Obligation" for i in items)

    def test_prohibition_detection(self, extractor):
        text = "The Servicer shall not commingle funds with its own assets."
        items = extractor.extract_items(text, "3.01", "Restrictions", 0, "test_doc")
        assert any(i.item_type == "Prohibition" for i in items)

    def test_definition_detection(self, extractor):
        text = '"Available Funds" means the sum of all amounts received during the Collection Period.'
        items = extractor.extract_items(text, "1.01", "Definitions", 0, "test_doc")
        assert any(i.item_type == "Definition" for i in items)

    def test_right_detection(self, extractor):
        text = "The Certificateholders may request additional reports from the Trustee."
        items = extractor.extract_items(text, "4.01", "Rights", 0, "test_doc")
        assert any(i.item_type == "Right" for i in items)

    def test_condition_detection(self, extractor):
        text = "Unless the Required Amount is satisfied, no additional distributions are permitted."
        items = extractor.extract_items(text, "5.01", "Triggers", 0, "test_doc")
        assert any(i.item_type == "Condition" for i in items)

    def test_item_id_format(self, extractor):
        text = "The Trustee shall file reports quarterly."
        items = extractor.extract_items(text, "2.01", "Reporting", 0, "test_doc")
        assert items
        # ID should follow pattern: doc-secXXX-type-N-hash
        assert items[0].id.startswith("test_doc-sec000-")

    def test_section_references_extracted(self, extractor):
        text = "As described in Section 3.05(a), the Servicer shall comply."
        items = extractor.extract_items(text, "2.01", "Cross Ref", 0, "test_doc")
        assert items
        refs = items[0].metadata.get("section_refs", [])
        assert any("3.05" in r for r in refs)

    def test_empty_text(self, extractor):
        items = extractor.extract_items("", "1.01", "Empty", 0, "doc")
        assert items == []

    def test_supported_types(self, extractor):
        types = extractor.get_supported_types()
        assert "Obligation" in types
        assert "Prohibition" in types
        assert "Definition" in types


# ── Technical Extractor ──────────────────────────────────────────

class TestTechnicalItemExtractor:
    @pytest.fixture
    def extractor(self):
        return TechnicalItemExtractor()

    def test_requirement_detection(self, extractor):
        text = "The system MUST validate all input fields before processing."
        items = extractor.extract_items(text, "3.1", "Input Validation", 0, "spec_doc")
        assert any(i.item_type == "Requirement" for i in items)

    def test_procedure_detection(self, extractor):
        text = "Step 1: Open the configuration panel. Step 2: Enter the API key."
        items = extractor.extract_items(text, "4.1", "Setup", 0, "spec_doc")
        assert any(i.item_type == "Procedure" for i in items)

    def test_warning_detection(self, extractor):
        text = "WARNING: Do not restart the service during migration."
        items = extractor.extract_items(text, "5.1", "Migration", 0, "spec_doc")
        assert any(i.item_type == "Warning" for i in items)

    def test_rfc2119_shall(self, extractor):
        text = "The client SHALL authenticate before accessing protected resources."
        items = extractor.extract_items(text, "2.1", "Auth", 0, "spec_doc")
        assert any(i.item_type == "Requirement" for i in items)


# ── Research Extractor ───────────────────────────────────────────

class TestResearchItemExtractor:
    @pytest.fixture
    def extractor(self):
        return ResearchItemExtractor()

    def test_theorem_detection(self, extractor):
        text = "Theorem 1: For all x in R, f(x) is continuous."
        items = extractor.extract_items(text, "3", "Results", 0, "paper")
        assert any(i.item_type == "Theorem" for i in items)

    def test_proof_detection(self, extractor):
        text = "Proof: By induction on n, we show that the statement holds."
        items = extractor.extract_items(text, "3", "Results", 0, "paper")
        assert any(i.item_type == "Proof" for i in items)

    def test_algorithm_detection(self, extractor):
        text = "Algorithm 2: Binary search over the sorted array."
        items = extractor.extract_items(text, "4", "Methods", 0, "paper")
        assert any(i.item_type == "Algorithm" for i in items)


# ── Generic Extractor ────────────────────────────────────────────

class TestGenericItemExtractor:
    @pytest.fixture
    def extractor(self):
        return GenericItemExtractor()

    def test_paragraph_splitting(self, extractor):
        text = "First paragraph here.\n\nSecond paragraph here."
        items = extractor.extract_items(text, "1", "Content", 0, "doc")
        assert len(items) == 2
        assert all(i.item_type == "Paragraph" for i in items)

    def test_single_paragraph(self, extractor):
        text = "Just one paragraph with no breaks."
        items = extractor.extract_items(text, "1", "Content", 0, "doc")
        assert len(items) == 1

    def test_empty_text(self, extractor):
        items = extractor.extract_items("", "1", "Content", 0, "doc")
        assert items == []


# ── Item dataclass ───────────────────────────────────────────────

class TestItem:
    def test_item_fields(self):
        item = Item(
            id="doc-sec001-Obligation-0-abc123",
            text="Shall distribute funds",
            item_type="Obligation",
            document_id="doc",
            section_number="2.01",
            section_heading="Distributions",
            section_index=1,
            item_index=0,
        )
        assert item.id == "doc-sec001-Obligation-0-abc123"
        assert item.item_type == "Obligation"
        assert item.metadata == {}

    def test_item_metadata(self):
        item = Item(
            id="test", text="", item_type="Obligation",
            document_id="d", section_number="1", section_heading="h",
            section_index=0, item_index=0,
            metadata={"actors": ["Trustee"]},
        )
        assert item.metadata["actors"] == ["Trustee"]
