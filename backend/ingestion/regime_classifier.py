"""Regime Classifier — 6-signal heuristic scoring (TD §2).

Classifies a document's text content into one of three regimes:
  * ``GOVERNING_DOC_LEGAL`` (legal_score ≥ 70)
  * ``MIXED``               (40 ≤ legal_score < 70)
  * ``GENERIC_GUIDE``        (legal_score < 40)

The scoring formula uses 6 binary signals with fixed weights.  Each
signal fires if its regex / heuristic test returns True.

Usage::

    from backend.ingestion.regime_classifier import RegimeClassifier
    regime, score, signals = RegimeClassifier.classify(text, filename="PSA.pdf")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ── Signal definitions (TD §2.1) ─────────────────────────────────
# Enhanced with financial document detection (PSA, mortgage-backed securities, etc.)
_SIGNAL_WEIGHTS: list[tuple[str, int]] = [
    ("definitions_section", 20),
    ("amendment_boilerplate", 15),
    ("named_party_structure", 12),
    ("section_article_headings", 10),
    ("legal_citation_density", 12),
    ("signature_notarization", 10),
    ("financial_terminology", 15),      # NEW: PSA/MBS/securitization terms
    ("table_of_contents", 10),          # NEW: Structured TOC presence
    ("regulatory_references", 10),      # NEW: SEC, Reg AB, compliance refs
]


@dataclass
class RegimeResult:
    regime: str
    score: int
    signals: dict[str, bool] = field(default_factory=dict)
    filename: str = ""


class RegimeClassifier:
    """Stateless document regime classifier."""

    # ── Signal detectors ──────────────────────────────────────────

    @staticmethod
    def _has_definitions_section(text: str) -> bool:
        """Signal 1: document contains capitalized defined terms laid out dictionary-style.

        A document is only considered "legal" if it has multiple capitalised terms
        explicitly defined in a glossary/dictionary pattern.  Simply having a
        heading called "Definitions" is NOT enough — the actual dictionary
        entries must be present.

        We look for patterns like:
            "Certificateholder" means ...
            "Distribution Date" shall mean ...
            "Servicer" has the meaning ...
            "Aggregate Principal Balance" is defined as ...

        Requires at least 5 such entries to fire.
        """
        # Pattern: "Capitalized Term(s)" means/shall mean/has the meaning/is defined as
        # Handles multi-word capitalized terms in quotes (straight or curly)
        defined_term_pattern = re.compile(
            r'["\u201c]'
            r'[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*'  # Capitalized Term Words
            r'["\u201d]'
            r'\s+(?:means?|shall\s+mean|has\s+the\s+meaning|is\s+defined\s+as|refers?\s+to)',
            re.IGNORECASE,
        )
        hits = len(defined_term_pattern.findall(text))
        if hits >= 5:
            return True

        # Alternative: bold/unquoted capitalized terms followed by definition marker
        # e.g., **Distribution Date** means ...
        # e.g., Capitalized Term. means ... (period after term name)
        alt_pattern = re.compile(
            r'(?:^|\n)\s*(?:\*{1,2})?'
            r'[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*'
            r'(?:\*{1,2})?'
            r'[.:]?\s+(?:means?|shall\s+mean|has\s+the\s+meaning|is\s+defined\s+as)',
            re.MULTILINE,
        )
        alt_hits = len(alt_pattern.findall(text))

        return (hits + alt_hits) >= 5

    @staticmethod
    def _has_amendment_boilerplate(text: str) -> bool:
        """Signal 2: amendment, supplement, or restated boilerplate."""
        return bool(re.search(
            r"\b(amendment|supplement|restated|as amended|amended and restated"
            r"|supplemental indenture|first amendment|second amendment)\b",
            text,
            re.IGNORECASE,
        ))

    @staticmethod
    def _has_named_party_structure(text: str) -> bool:
        """Signal 3: 'Party A' / 'the Trustee' / 'the Servicer' named-party patterns.
        
        Enhanced with financial document specific parties: servicer, depositor,
        certificateholder, master servicer, securities administrator, etc.
        """
        party_pattern = (
            r"\b(the\s+)?(trustee|servicer|master\s+servicer|sub[- ]?servicer|"
            r"depositor|issuer|seller|purchaser|underwriter|sponsor|originator|"
            r"indenture\s+trustee|owner\s+trustee|custodian|paying\s+agent|"
            r"certificate\s+registrar|certificateholder|certificate\s+holder|"
            r"securities\s+administrator|securities\s+intermediary|"
            r"borrower|lender|guarantor|obligor|mortgagor|"
            r"swap\s+counterparty|liquidity\s+provider|backup\s+servicer)\b"
        )
        hits = len(re.findall(party_pattern, text, re.IGNORECASE))
        # Lower threshold since financial docs repeat party names frequently
        return hits >= 5

    @staticmethod
    def _has_section_article_headings(text: str) -> bool:
        """Signal 4: numbered 'Section X.Y' or 'ARTICLE I' headings.
        
        Enhanced to handle PDF extraction variations and financial document
        section numbering (e.g., 'Section 2.01', 'Article III').
        """
        # Roman numeral articles (ARTICLE I, ARTICLE II, etc.)
        pattern1 = r"(?m)^\s*(ARTICLE|PART)\s+[IVXLC]+[.\s]"
        hits1 = len(re.findall(pattern1, text, re.IGNORECASE))
        
        # Decimal section numbers (Section 2.01, Section 3.05(a))
        pattern2 = r"(?m)^\s*SECTION\s+\d+\.\d+[.\s(]"
        hits2 = len(re.findall(pattern2, text, re.IGNORECASE))
        
        # Alternative patterns for broken extraction (Section 2.01 at line start)
        pattern3 = r"\bSection\s+\d+\.\d+[.\s:]"
        hits3 = len(re.findall(pattern3, text[:20000], re.IGNORECASE))
        
        # Clause/subsection patterns
        pattern4 = r"(?m)^\s*(CLAUSE|Subsection)\s+[0-9]+[.\s]"
        hits4 = len(re.findall(pattern4, text, re.IGNORECASE))
        
        total_hits = hits1 + hits2 + min(hits3, 5) + hits4
        return total_hits >= 3

    @staticmethod
    def _has_legal_citation_density(text: str) -> bool:
        """Signal 5: dense legal citation patterns (§ references, U.S.C., etc.)."""
        patterns = [
            r"§\s*\d",
            r"\bU\.?S\.?C\.?\b",
            r"\bpursuant to\b",
            r"\bhereinafter\b",
            r"\bherein\b",
            r"\bwhereas\b",
            r"\bnotwithstanding\b",
            r"\bshall mean\b",
            r"\bshall not\b",
            r'\b"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*"\s+(?:means|shall mean|has the meaning)\b',
        ]
        hits = sum(1 for p in patterns if re.search(p, text, re.IGNORECASE))
        return hits >= 3

    @staticmethod
    def _has_signature_notarization(text: str) -> bool:
        """Signal 6: signature block / notarization markers."""
        return bool(re.search(
            r"\b(IN WITNESS WHEREOF|NOTARIZED|ACKNOWLEDGED AND AGREED|"
            r"SIGNATURE PAGE|EXECUTED AND DELIVERED|BY:\s*_{3,}|"
            r"Authorized Signatory|Witness:)\b",
            text,
            re.IGNORECASE,
        ))

    @staticmethod
    def _has_financial_terminology(text: str) -> bool:
        """Signal 7: Financial/securitization terminology density.
        
        Detects PSA, MBS, ABS, CMBS, RMBS, and structured finance documents.
        Includes terms like: pool assets, mortgage loans, certificateholders,
        distribution date, remittance report, servicer advances, etc.
        """
        financial_terms = [
            # Securitization structure
            r"\b(mortgage\s+loan|pool\s+asset|underlying\s+asset|collateral\s+pool)\b",
            r"\b(certificate\s*holder|residual\s+certificate|pass[- ]?through\s+certificate)\b",
            r"\b(trust\s+fund|trust\s+estate|trust\s+property)\b",
            
            # Financial operations
            r"\b(distribution\s+date|record\s+date|determination\s+date|closing\s+date)\b",
            r"\b(remittance\s+report|monthly\s+statement|servicer\s+report)\b",
            r"\b(principal\s+balance|outstanding\s+balance|aggregate\s+principal)\b",
            r"\b(servicer\s+advance|interest\s+advance|P&I\s+advance)\b",
            r"\b(prepayment|curtailment|defeasance|modification)\b",
            
            # MBS/ABS specific
            r"\b(pooling\s+and\s+servicing|PSA\s+agreement|REMIC|real\s+estate\s+mortgage)\b",
            r"\b(asset[- ]backed|mortgage[- ]backed|securitization)\b",
            r"\b(credit\s+enhancement|reserve\s+account|spread\s+account)\b",
            r"\b(delinquency|default|foreclosure|REO\s+property)\b",
            
            # Regulatory/compliance
            r"\b(Regulation\s+AB|Reg\s+AB|Item\s+\d{4}\s+of\s+Regulation)\b",
            r"\b(securities\s+act|exchange\s+act|investment\s+company\s+act)\b",
        ]
        
        hits = sum(1 for pattern in financial_terms if re.search(pattern, text, re.IGNORECASE))
        # Require at least 4 different financial term categories
        return hits >= 4

    @staticmethod
    def _has_table_of_contents(text: str) -> bool:
        """Signal 8: Table of Contents presence.
        
        Strong indicator of formal legal documents. Looks for TOC markers
        and page number references.
        """
        # Common TOC headers
        toc_header = re.search(
            r"(?m)^\s*(TABLE\s+OF\s+CONTENTS?|CONTENTS?|INDEX)\s*$",
            text[:5000],  # Check first 5K chars
            re.IGNORECASE
        )
        
        # Page number patterns (Article I .... 5, Section 2.01 .... 12)
        page_refs = len(re.findall(
            r"(?m)^.{10,80}[.·]{3,}\s*\d+\s*$",
            text[:10000],  # TOC usually in first 10K
        ))
        
        return bool(toc_header) or page_refs >= 5

    @staticmethod
    def _has_regulatory_references(text: str) -> bool:
        """Signal 9: Regulatory and compliance references.
        
        Detects references to SEC regulations, federal statutes, compliance
        frameworks common in governed financial documents.
        """
        regulatory_patterns = [
            r"\bSEC\b",
            r"\bSecurities\s+and\s+Exchange\s+Commission\b",
            r"\bRegulation\s+[A-Z]{1,3}\b",
            r"\b(?:Item|Rule|Form)\s+\d+[A-Z]?(?:-\d+)?\b",
            r"\b\d+\s+U\.?S\.?C\.?\s+§?\s*\d+",  # Federal statute citations
            r"\bSarbanes[- ]Oxley\b",
            r"\bDodd[- ]Frank\b",
            r"\bGAAP\b",
            r"\bFASB\b",
            r"\bBasel\s+[III]+\b",
            r"\b(?:1933|1934|1940)\s+Act\b",
        ]
        
        hits = sum(1 for pattern in regulatory_patterns if re.search(pattern, text, re.IGNORECASE))
        return hits >= 2

    # ── Classification ────────────────────────────────────────────

    _SIGNAL_FUNCS = [
        ("definitions_section", _has_definitions_section.__func__),  # type: ignore[attr-defined]
        ("amendment_boilerplate", _has_amendment_boilerplate.__func__),
        ("named_party_structure", _has_named_party_structure.__func__),
        ("section_article_headings", _has_section_article_headings.__func__),
        ("legal_citation_density", _has_legal_citation_density.__func__),
        ("signature_notarization", _has_signature_notarization.__func__),
        ("financial_terminology", _has_financial_terminology.__func__),
        ("table_of_contents", _has_table_of_contents.__func__),
        ("regulatory_references", _has_regulatory_references.__func__),
    ]

    @classmethod
    def classify(cls, text: str, filename: str = "") -> RegimeResult:
        """Classify *text* and return a ``RegimeResult``."""
        signals: dict[str, bool] = {}
        score = 0

        for (signal_name, weight), (_, func) in zip(_SIGNAL_WEIGHTS, cls._SIGNAL_FUNCS):
            hit = func(text)
            signals[signal_name] = hit
            if hit:
                score += weight

        # Filename bonus — if filename strongly suggests legal doc
        # Enhanced with financial document patterns
        filename_lower = filename.lower()
        if re.search(
            r"(agreement|indenture|supplement|psa|pooling|servicing|"
            r"prospectus|offering|remic|trust|mortgage|"
            r"2\d{3}[- ]?[a-z]{2,4}\d|series\s*\d+)",  # Series identifiers like "2006-HE1"
            filename_lower,
            re.IGNORECASE,
        ):
            score = min(score + 15, 100)  # Increased bonus from 10 to 15
        
        # Additional boost for strong PSA/MBS indicators in filename
        if re.search(r"(psa|pooling.*servicing|mortgage.*backed|asset.*backed)", filename_lower):
            score = min(score + 10, 100)

        # Adjusted thresholds with more signals:
        # Total possible: 114 content + 25 filename = 139, but capped at 100
        if score >= 60:  # Lowered from 70 - more reliable signals now
            regime = "GOVERNING_DOC_LEGAL"
        elif score >= 35:  # Lowered from 40
            regime = "MIXED"
        else:
            regime = "GENERIC_GUIDE"

        return RegimeResult(regime=regime, score=score, signals=signals, filename=filename)

    @classmethod
    def corpus_regime(cls, regimes: list[RegimeResult] | list[str]) -> str:
        """Compute aggregate corpus regime via majority vote.

        Accepts either a list of ``RegimeResult`` objects or plain regime strings.
        """
        if not regimes:
            return "GENERIC_GUIDE"
        # Normalise to strings
        labels: list[str] = []
        for r in regimes:
            if isinstance(r, RegimeResult):
                labels.append(r.regime)
            else:
                labels.append(str(r))
        legal = sum(1 for r in labels if r == "GOVERNING_DOC_LEGAL")
        mixed = sum(1 for r in labels if r == "MIXED")
        generic = sum(1 for r in labels if r == "GENERIC_GUIDE")
        if legal >= mixed and legal >= generic:
            return "GOVERNING_DOC_LEGAL"
        if mixed >= generic:
            return "MIXED"
        return "GENERIC_GUIDE"
