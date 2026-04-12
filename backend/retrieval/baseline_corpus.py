"""
Phase 15.3 — Baseline Corpus.

Curated collection of "standard" clause text for ~50 clause types, derived
from the most common language across ingested deals.

The baseline is constructed by KTS as a one-time setup per deal type, then
used by the anomaly scorer (Phase 15.4) to flag deviations.

Usage::

    corpus = BaselineCorpus(storage_dir="~/.kts/baseline_corpus")
    corpus.add_clause(BaselineClause(
        clause_type="servicer_advance_definition",
        deal_type="PSA_HELOC",
        standard_text="The Servicer shall make advances...",
    ))
    clause = corpus.get_baseline("servicer_advance_definition", "PSA_HELOC")
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Baseline Clause ───────────────────────────────────────────

@dataclass
class BaselineClause:
    """One baseline clause for a clause type + deal type combination."""

    clause_type: str                    # "servicer_advance_definition"
    deal_type: str                      # "PSA_HELOC"
    standard_text: str                  # modal text across N deals
    variant_texts: List[str] = field(default_factory=list)    # known acceptable variants
    deviation_signals: List[str] = field(default_factory=list) # patterns that signal non-standard
    source_deals: List[str] = field(default_factory=list)     # deals baseline derived from
    derived_date: str = ""              # ISO date when baseline was derived
    sample_size: int = 0               # number of deals used to derive baseline

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clause_type": self.clause_type,
            "deal_type": self.deal_type,
            "standard_text": self.standard_text,
            "variant_texts": self.variant_texts,
            "deviation_signals": self.deviation_signals,
            "source_deals": self.source_deals,
            "derived_date": self.derived_date,
            "sample_size": self.sample_size,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BaselineClause":
        return cls(
            clause_type=d["clause_type"],
            deal_type=d["deal_type"],
            standard_text=d["standard_text"],
            variant_texts=d.get("variant_texts", []),
            deviation_signals=d.get("deviation_signals", []),
            source_deals=d.get("source_deals", []),
            derived_date=d.get("derived_date", ""),
            sample_size=d.get("sample_size", 0),
        )


# ── Standard Clause Types ────────────────────────────────────

STANDARD_CLAUSE_TYPES = [
    # ── Core Definitions ──────────────────────────────────
    "servicer_advance_definition",
    "servicer_duties",
    "determination_date",
    "distribution_date",
    "record_date",
    "optional_termination",
    "cleanup_call",
    "events_of_default",
    "trustee_duties",
    "trustee_indemnification",
    "depositor_representations",
    "master_servicer_duties",
    "special_servicer_duties",
    "modification_standards",
    "replacement_of_servicer",
    "subordination_waterfall",
    "credit_enhancement",
    "overcollateralization",
    "excess_spread",
    "trigger_events",
    "early_amortization",
    "controlling_class",
    "majority_certificate_holder",
    "asset_representations",
    "repurchase_obligation",
    "assignment_conveyance",
    "tax_matters",
    "remic_election",
    "reporting_requirements",
    "amendment_provisions",
    # ── Additional Clause Types (~50 total) ───────────────
    "delinquency_advance",
    "principal_distribution_amount",
    "interest_distribution_amount",
    "certificate_balance",
    "realized_loss",
    "cumulative_loss",
    "step_down_date",
    "cross_collateralization",
    "available_funds",
    "servicing_fee",
    "collection_period",
    "substitution_provisions",
    "pool_factor",
    "prepayment_penalty",
    "draw_amount",
    "credit_line_reduction",
    "insurance_requirements",
    "force_placed_insurance",
    "seller_representations",
    "document_custody",
]


# ── Baseline Corpus ───────────────────────────────────────────

class BaselineCorpus:
    """
    Manages a collection of baseline clauses for anomaly detection.

    Each clause type + deal type pair is stored as a JSON file in the
    storage directory, organized as::

        {storage_dir}/{deal_type}/{clause_type}.json
    """

    def __init__(self, storage_dir: str = "") -> None:
        if not storage_dir:
            storage_dir = os.path.join(os.path.expanduser("~"), ".kts", "baseline_corpus")
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, BaselineClause] = {}

    def _key(self, clause_type: str, deal_type: str) -> str:
        return f"{deal_type}::{clause_type}"

    def _file_path(self, clause_type: str, deal_type: str) -> Path:
        return self.storage_dir / deal_type / f"{clause_type}.json"

    # ── CRUD ────────────────────────────────────────────────

    def add_clause(self, clause: BaselineClause) -> None:
        """Add or update a baseline clause."""
        key = self._key(clause.clause_type, clause.deal_type)
        self._cache[key] = clause

        fp = self._file_path(clause.clause_type, clause.deal_type)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(clause.to_dict(), indent=2), encoding="utf-8")

    def get_baseline(
        self, clause_type: str, deal_type: str
    ) -> Optional[BaselineClause]:
        """Get baseline for a clause type + deal type. Returns None if not found."""
        key = self._key(clause_type, deal_type)

        # Check in-memory cache first
        if key in self._cache:
            return self._cache[key]

        # Try loading from disk
        fp = self._file_path(clause_type, deal_type)
        if fp.exists():
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                clause = BaselineClause.from_dict(data)
                self._cache[key] = clause
                return clause
            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning("[BaselineCorpus] Failed to load %s: %s", fp, exc)

        return None

    def list_clause_types(self, deal_type: str) -> List[str]:
        """List all available clause types for a deal type."""
        dt_dir = self.storage_dir / deal_type
        if not dt_dir.is_dir():
            return []
        return [f.stem for f in dt_dir.glob("*.json")]

    def list_deal_types(self) -> List[str]:
        """List all deal types that have baselines."""
        if not self.storage_dir.is_dir():
            return []
        return [d.name for d in self.storage_dir.iterdir() if d.is_dir()]

    # ── Baseline Construction ───────────────────────────────

    def build_from_definitions(
        self,
        clause_type: str,
        deal_type: str,
        definitions: Dict[str, str],
        deviation_signals: Optional[List[str]] = None,
    ) -> BaselineClause:
        """
        Build a baseline clause from multiple deal definitions.

        Uses the most common (modal) text as the standard.
        Less common variants are stored as ``variant_texts``.

        Parameters
        ----------
        definitions : dict
            ``{scope_slug: definition_text}``
        """
        if not definitions:
            raise ValueError("Cannot build baseline from empty definitions")

        # Find modal text (most common)
        from collections import Counter

        # Normalize whitespace for comparison
        normalized = {
            slug: " ".join(text.split())
            for slug, text in definitions.items()
        }

        counts = Counter(normalized.values())
        modal_text, modal_count = counts.most_common(1)[0]

        # Everything else is a variant
        variant_set = {text for text, count in counts.items() if text != modal_text}

        clause = BaselineClause(
            clause_type=clause_type,
            deal_type=deal_type,
            standard_text=modal_text,
            variant_texts=list(variant_set),
            deviation_signals=deviation_signals or [],
            source_deals=list(definitions.keys()),
            derived_date=date.today().isoformat(),
            sample_size=len(definitions),
        )

        self.add_clause(clause)
        return clause
