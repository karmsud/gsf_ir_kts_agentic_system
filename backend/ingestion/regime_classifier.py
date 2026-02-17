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
_SIGNAL_WEIGHTS: list[tuple[str, int]] = [
    ("definitions_section", 25),
    ("amendment_boilerplate", 20),
    ("named_party_structure", 15),
    ("section_article_headings", 10),
    ("legal_citation_density", 15),
    ("signature_notarization", 15),
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
        """Signal 1: document has a section titled 'Definitions' or similar."""
        return bool(re.search(
            r"^#{0,4}\s*(?:ARTICLE|SECTION)?\s*[IVXLC0-9.]*\s*[-–—:.]?\s*DEFINITIONS?\s*$"
            r"|^DEFINITIONS?\s*$"
            r"|^\*{0,2}Definitions?\*{0,2}\s*$",
            text,
            re.IGNORECASE | re.MULTILINE,
        ))

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
        """Signal 3: 'Party A' / 'the Trustee' / 'the Servicer' named-party patterns."""
        party_pattern = (
            r"\b(the\s+)?(trustee|servicer|master servicer|depositor|issuer|"
            r"seller|purchaser|underwriter|indenture trustee|custodian|"
            r"paying agent|certificate registrar|certificateholder|"
            r"borrower|lender|guarantor|obligor)\b"
        )
        hits = len(re.findall(party_pattern, text, re.IGNORECASE))
        return hits >= 3

    @staticmethod
    def _has_section_article_headings(text: str) -> bool:
        """Signal 4: numbered 'Section X.Y' or 'ARTICLE I' headings."""
        pattern = r"(?m)^\s*(SECTION|ARTICLE|CLAUSE)\s+[IVXLC0-9]+[.\s]"
        hits = len(re.findall(pattern, text, re.IGNORECASE))
        return hits >= 2

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

    # ── Classification ────────────────────────────────────────────

    _SIGNAL_FUNCS = [
        ("definitions_section", _has_definitions_section.__func__),  # type: ignore[attr-defined]
        ("amendment_boilerplate", _has_amendment_boilerplate.__func__),
        ("named_party_structure", _has_named_party_structure.__func__),
        ("section_article_headings", _has_section_article_headings.__func__),
        ("legal_citation_density", _has_legal_citation_density.__func__),
        ("signature_notarization", _has_signature_notarization.__func__),
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
        if re.search(
            r"(agreement|indenture|supplement|psa|remic|prospectus|servicing)",
            filename,
            re.IGNORECASE,
        ):
            score = min(score + 10, 100)

        if score >= 70:
            regime = "GOVERNING_DOC_LEGAL"
        elif score >= 40:
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
