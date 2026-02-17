"""Tests for DefinedTermExtractor — TD §5.4-§5.6."""

import pytest

from backend.graph.defined_term_extractor import DefinedTerm, DefinedTermExtractor


class TestStrategy1MeansPattern:
    def test_quoted_means(self):
        text = '"Certificateholder" means any Person in whose name a Certificate is registered.'
        extractor = DefinedTermExtractor()
        terms = extractor.extract(text)
        assert len(terms) >= 1
        match = next(t for t in terms if t.surface_form == "Certificateholder")
        assert match.confidence == 0.95
        assert match.extraction_strategy == "regex_means"
        assert "Person" in match.definition_text

    def test_shall_mean(self):
        text = '"Trustee" shall mean the entity appointed pursuant to this Agreement.'
        extractor = DefinedTermExtractor()
        terms = extractor.extract(text)
        assert any(t.surface_form == "Trustee" for t in terms)

    def test_is_defined_as(self):
        text = '"Closing Date" is defined as the date on which the transaction closes.'
        extractor = DefinedTermExtractor()
        terms = extractor.extract(text)
        assert any(t.surface_form == "Closing Date" for t in terms)

    def test_smart_quotes(self):
        text = '\u201cBorrower\u201d means any individual who has entered into a loan agreement.'
        extractor = DefinedTermExtractor()
        terms = extractor.extract(text)
        assert any(t.surface_form == "Borrower" for t in terms)


class TestStrategy2DefinitionsSection:
    def test_definitions_heading_extraction(self):
        text = """
ARTICLE I
DEFINITIONS

Certificateholder: Any person in whose name a Certificate is registered on the books of the Trust.
Servicer: The entity responsible for managing and collecting payments on the underlying mortgage pool.
Trustee: The institution serving as trustee under this agreement.
"""
        extractor = DefinedTermExtractor()
        terms = extractor.extract(text)
        section_terms = [t for t in terms if t.extraction_strategy == "definitions_section"]
        assert len(section_terms) >= 2
        assert any(t.surface_form == "Certificateholder" for t in section_terms)

    def test_no_definitions_section(self):
        text = "Just a regular paragraph with no definitions section."
        extractor = DefinedTermExtractor()
        terms = extractor._strategy2_definitions_section(text)
        assert terms == []


class TestStrategy3BoldItalic:
    def test_markdown_bold_extraction(self):
        text = "**Payment Date** - The 25th day of each calendar month."
        extractor = DefinedTermExtractor()
        terms = extractor._strategy3_bold_italic(text)
        assert len(terms) >= 1
        assert terms[0].surface_form == "Payment Date"
        assert terms[0].confidence == 0.85

    def test_underscore_bold_extraction(self):
        text = "__Settlement Date__ - The date on which final settlement occurs."
        extractor = DefinedTermExtractor()
        terms = extractor._strategy3_bold_italic(text)
        assert len(terms) >= 1
        assert terms[0].surface_form == "Settlement Date"


class TestStrategy4InlineReference:
    def test_as_defined_in_extraction(self):
        text = 'The "Collateral Agent" (as defined in Section 4.2) shall hold the assets.'
        extractor = DefinedTermExtractor()
        terms = extractor._strategy4_inline_reference(text)
        assert len(terms) >= 1
        assert terms[0].surface_form == "Collateral Agent"
        assert terms[0].confidence == 0.80
        assert terms[0].extraction_strategy == "inline_reference"

    def test_as_defined_herein(self):
        text = 'The "Master Servicer" (as defined herein) is responsible for oversight.'
        extractor = DefinedTermExtractor()
        terms = extractor._strategy4_inline_reference(text)
        assert len(terms) >= 1
        assert terms[0].surface_form == "Master Servicer"


class TestDeduplication:
    def test_keeps_highest_confidence(self):
        extractor = DefinedTermExtractor()
        text = (
            '"Servicer" means the entity servicing the loans.\n\n'
            "## DEFINITIONS\n\n"
            "Servicer: The entity responsible for servicing.\n"
        )
        terms = extractor.extract(text)
        servicer_terms = [t for t in terms if t.surface_form.lower() == "servicer"]
        assert len(servicer_terms) == 1
        assert servicer_terms[0].confidence == 0.95  # regex_means beats definitions_section

    def test_sorted_by_confidence_descending(self):
        extractor = DefinedTermExtractor()
        text = (
            '"Alpha" means the first letter.\n'
            '**Beta** - The second letter.\n'
            'The "Gamma" (as defined herein) is the third.\n'
        )
        terms = extractor.extract(text)
        for i in range(len(terms) - 1):
            assert terms[i].confidence >= terms[i + 1].confidence


class TestExtractorIntegration:
    def test_multi_strategy_extraction(self):
        text = """
        ARTICLE I - DEFINITIONS

        "Certificateholder" means any Person registered as holder of a Certificate.

        Servicer: The entity responsible for mortgage pool servicing.

        **Payment Date** - The 25th day of each calendar month.

        The "Master Servicer" (as defined in Section 2.1) shall oversee operations.
        """
        extractor = DefinedTermExtractor()
        terms = extractor.extract(text)
        strategies = {t.extraction_strategy for t in terms}
        # Should find terms from multiple strategies
        assert "regex_means" in strategies
        assert len(terms) >= 3
