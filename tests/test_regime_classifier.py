"""Tests for RegimeClassifier — TD §2."""

import pytest

from backend.ingestion.regime_classifier import RegimeClassifier, RegimeResult


class TestRegimeClassifier:
    def test_governing_doc_legal_with_all_signals(self):
        text = (
            "ARTICLE I - DEFINITIONS\n\n"
            "The following definitions shall apply to this Agreement:\n\n"
            "Certificateholder means any Person in whose name a Certificate is registered.\n"
            "Trustee shall mean the entity acting as trustee hereunder.\n\n"
            "ARTICLE II - REPRESENTATIONS AND WARRANTIES\n\n"
            "Each Seller hereby represents and warrants to the Depositor, "
            "as of the Closing Date:\n\n"
            "Section 2.01 Organization\n"
            "The Seller is duly organized, validly existing, and in good standing "
            "under the laws of the State of Delaware.\n\n"
            "This Agreement, as amended and restated, shall remain in full force.\n\n"
            "Pursuant to Section 3.01, notwithstanding any provision herein, "
            "the Trustee shall not be liable.\n\n"
            "IN WITNESS WHEREOF, the parties hereto have caused this Agreement "
            "to be duly executed by their respective officers.\n\n"
            "________________________\n"
            "By: [Name]\n"
            "Title: Authorized Signatory\n"
            "NOTARIZED on this ___ day of ________ 20__\n"
        )
        result = RegimeClassifier.classify(text, filename="Pooling_Agreement_v3.pdf")
        assert result.regime == "GOVERNING_DOC_LEGAL"
        assert result.score >= 70

    def test_generic_guide_with_no_signals(self):
        text = """
        # Getting Started with ToolX

        Welcome to ToolX! This guide will help you get started.

        ## Installation

        1. Download ToolX from the portal
        2. Run the installer
        3. Follow the on-screen prompts

        ## Usage

        Click the "Start" button to begin processing.
        """
        result = RegimeClassifier.classify(text, filename="ToolX_Getting_Started.md")
        assert result.regime == "GENERIC_GUIDE"
        assert result.score < 40

    def test_mixed_regime(self):
        text = (
            "DEFINITIONS\n\n"
            "Service Level Agreement means the performance targets defined herein.\n\n"
            "Section 3 - Procedures\n\n"
            "Follow these steps to configure the system:\n"
            "1. Open the admin panel\n"
            "2. Navigate to Settings\n"
            "3. Update the configuration\n\n"
            "This document hereby amends the prior agreement dated January 1, 2025.\n"
            "This first amendment supersedes all prior understandings.\n"
        )
        result = RegimeClassifier.classify(text, filename="ServiceAgreement_v2.docx")
        assert result.regime in {"MIXED", "GOVERNING_DOC_LEGAL"}

    def test_filename_bonus_applied(self):
        text = "Some generic text without strong legal indicators."
        result_with_legal_name = RegimeClassifier.classify(text, filename="Master_Agreement_v2.pdf")
        result_without = RegimeClassifier.classify(text, filename="readme.md")
        assert result_with_legal_name.score >= result_without.score

    def test_corpus_regime_majority_vote(self):
        results = [
            RegimeResult(regime="GOVERNING_DOC_LEGAL", score=90, signals={}, filename="a.pdf"),
            RegimeResult(regime="GOVERNING_DOC_LEGAL", score=85, signals={}, filename="b.pdf"),
            RegimeResult(regime="GENERIC_GUIDE", score=20, signals={}, filename="c.md"),
        ]
        assert RegimeClassifier.corpus_regime(results) == "GOVERNING_DOC_LEGAL"

    def test_corpus_regime_empty_list(self):
        assert RegimeClassifier.corpus_regime([]) == "GENERIC_GUIDE"

    def test_result_dataclass_fields(self):
        result = RegimeClassifier.classify("test text", filename="test.txt")
        assert hasattr(result, "regime")
        assert hasattr(result, "score")
        assert hasattr(result, "signals")
        assert hasattr(result, "filename")
