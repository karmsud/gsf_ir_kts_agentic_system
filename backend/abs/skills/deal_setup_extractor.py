"""
Deal Setup Extractor — Extract deal_setup and classes_setup data
from document sections and governing documents.

Provides local extraction logic that does not depend on the
abs_waterfall_ai_v2 external module. Supports both CSV-based
loading (for already-parsed data) and text-based extraction
(for raw section content).

Ported from PayGen pipeline.skills.deal_setup_extractor → backend.abs.skills
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class DealSetup:
    """Top-level deal parameters."""
    deal_name: str = ""
    issuer: str = ""
    series: str = ""
    closing_date: str = ""
    cutoff_date: str = ""
    first_payment_date: str = ""
    original_pool_balance: float = 0.0
    day_count_convention: str = "30/360"
    payment_frequency: str = "monthly"
    servicer: str = ""
    trustee: str = ""
    custom_fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        result = {
            "deal_name": self.deal_name,
            "issuer": self.issuer,
            "series": self.series,
            "closing_date": self.closing_date,
            "cutoff_date": self.cutoff_date,
            "first_payment_date": self.first_payment_date,
            "original_pool_balance": self.original_pool_balance,
            "day_count_convention": self.day_count_convention,
            "payment_frequency": self.payment_frequency,
            "servicer": self.servicer,
            "trustee": self.trustee,
        }
        result.update(self.custom_fields)
        return result

    @classmethod
    def from_dict(cls, data: dict) -> DealSetup:
        known_fields = {f.name for f in cls.__dataclass_fields__.values()
                        if f.name != "custom_fields"}
        known = {k: v for k, v in data.items() if k in known_fields}
        custom = {k: v for k, v in data.items() if k not in known_fields}

        if "original_pool_balance" in known:
            known["original_pool_balance"] = _parse_amount(
                known["original_pool_balance"]
            )

        return cls(**known, custom_fields=custom)

    def to_csv_rows(self) -> list[dict]:
        """Convert to CSV-compatible rows (one row per field)."""
        rows = []
        for key, value in self.to_dict().items():
            rows.append({"field": key, "value": str(value)})
        return rows


@dataclass
class ClassSetup:
    """Single class/tranche parameters."""
    class_name: str = ""
    original_balance: float = 0.0
    coupon_rate: float = 0.0
    coupon_type: str = ""  # fixed, floating, etc.
    payment_priority: int = 0
    rating: str = ""
    credit_enhancement: float = 0.0
    subordination: float = 0.0
    custom_fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        result = {
            "class_name": self.class_name,
            "original_balance": self.original_balance,
            "coupon_rate": self.coupon_rate,
            "coupon_type": self.coupon_type,
            "payment_priority": self.payment_priority,
            "rating": self.rating,
            "credit_enhancement": self.credit_enhancement,
            "subordination": self.subordination,
        }
        result.update(self.custom_fields)
        return result

    @classmethod
    def from_dict(cls, data: dict) -> ClassSetup:
        known_fields = {f.name for f in cls.__dataclass_fields__.values()
                        if f.name != "custom_fields"}
        known = {}
        custom = {}
        for k, v in data.items():
            if k in known_fields:
                known[k] = v
            else:
                custom[k] = v

        # Parse numeric fields
        for num_field in ("original_balance",
                          "credit_enhancement", "subordination"):
            if num_field in known:
                known[num_field] = _parse_amount(known[num_field])
        # coupon_rate needs rate parsing (handles % → decimal)
        if "coupon_rate" in known:
            known["coupon_rate"] = _parse_rate(known["coupon_rate"])
        if "payment_priority" in known:
            try:
                known["payment_priority"] = int(known["payment_priority"])
            except (ValueError, TypeError):
                known["payment_priority"] = 0

        return cls(**known, custom_fields=custom)


# ── CSV Loaders ───────────────────────────────────────────────

def load_deal_setup_csv(path: Path) -> DealSetup:
    """
    Load deal_setup.csv into a DealSetup dataclass.

    CSV format: two columns — field, value (one row per field)
    """
    path = Path(path)
    if not path.exists():
        return DealSetup()

    data: dict[str, str] = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            field_name = row.get("field", "").strip().lower().replace(" ", "_")
            value = row.get("value", "").strip()
            if field_name:
                data[field_name] = value

    return DealSetup.from_dict(data)


def load_classes_setup_csv(path: Path) -> list[ClassSetup]:
    """
    Load classes_setup.csv into a list of ClassSetup dataclasses.

    CSV format: one row per class with columns matching ClassSetup fields.
    """
    path = Path(path)
    if not path.exists():
        return []

    classes: list[ClassSetup] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Normalize column names
            normalized = {
                k.strip().lower().replace(" ", "_"): v.strip()
                for k, v in row.items()
                if k is not None
            }
            classes.append(ClassSetup.from_dict(normalized))

    return classes


# ── Text Extractors ───────────────────────────────────────────

def extract_deal_setup_from_text(text: str) -> DealSetup:
    """
    Extract deal setup parameters from raw section text.

    Looks for patterns like:
        "Closing Date: March 30, 2006"
        "Original Pool Balance: $1,234,567,890"
    """
    setup = DealSetup()

    # Deal name patterns
    for pattern in [
        r"(?:series|deal)\s*(?:name)?[:\s]+([^\n]+)",
        r"(Bear\s+Stearns\s+\d{4}-\w+)",
        r"(WHFSC\s+\d{4}-\w+)",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            setup.deal_name = m.group(1).strip()
            break

    # Issuer
    m = re.search(r"(?:issuer|depositor)[:\s]+([^\n]+)", text, re.IGNORECASE)
    if m:
        setup.issuer = m.group(1).strip()

    # Series
    m = re.search(r"series\s*[:\s]+(\d{4}-\w+)", text, re.IGNORECASE)
    if m:
        setup.series = m.group(1).strip()

    # Dates
    date_fields = {
        "closing_date": r"closing\s+date[:\s]+([^\n]+)",
        "cutoff_date": r"(?:cut-?off|cutoff)\s+date[:\s]+([^\n]+)",
        "first_payment_date": r"(?:first|initial)\s+(?:payment|distribution)\s+date[:\s]+([^\n]+)",
    }
    for field_name, pattern in date_fields.items():
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            setattr(setup, field_name, m.group(1).strip())

    # Pool balance
    m = re.search(
        r"(?:original|initial)\s+(?:pool|aggregate)\s+balance\s*(?:is\s+)?[:\s]*\$?([\d,]+(?:\.\d+)?)",
        text, re.IGNORECASE,
    )
    if m:
        setup.original_pool_balance = _parse_amount(m.group(1))

    # Day count
    m = re.search(r"day\s+count\s+(?:convention|basis)[:\s]+([^\n]+)", text, re.IGNORECASE)
    if m:
        setup.day_count_convention = m.group(1).strip()

    # Servicer
    m = re.search(r"(?:master\s+)?servicer[:\s]+([^\n]+)", text, re.IGNORECASE)
    if m:
        setup.servicer = m.group(1).strip()

    # Trustee
    m = re.search(r"trustee[:\s]+([^\n]+)", text, re.IGNORECASE)
    if m:
        setup.trustee = m.group(1).strip()

    return setup


def extract_classes_from_text(text: str) -> list[ClassSetup]:
    """
    Extract class/tranche information from raw section text.

    Looks for table-like structures or repeated patterns describing
    certificate classes with balances, rates, and ratings.
    """
    classes: list[ClassSetup] = []

    # Pattern 1: Table rows like "Class A-1 | $100,000 | 5.25% | AAA"
    table_pattern = re.compile(
        r"(?:Class|Certificate)\s+([\w-]+)\s*[|\t]+\s*\$?([\d,]+(?:\.\d+)?)"
        r"\s*[|\t]+\s*([\d.]+)\s*%?"
        r"(?:\s*[|\t]+\s*(\w+))?",
        re.IGNORECASE,
    )
    for m in table_pattern.finditer(text):
        cls = ClassSetup(
            class_name=f"Class {m.group(1)}",
            original_balance=_parse_amount(m.group(2)),
            coupon_rate=_parse_rate(m.group(3)),
            rating=m.group(4).strip() if m.group(4) else "",
        )
        classes.append(cls)

    if classes:
        # Assign payment priority by order
        for i, cls in enumerate(classes, 1):
            cls.payment_priority = i
        return classes

    # Pattern 2: Paragraph-style
    para_pattern = re.compile(
        r"Class\s+([\w-]+)\s+(?:Certificate|Note)s?\s+.*?"
        r"(?:initial\s+)?(?:Certificate\s+)?Balance\s+of\s+\$?([\d,]+(?:\.\d+)?)"
        r".*?(?:Certificate\s+)?Rate\s+of\s+([\d.]+)\s*%?",
        re.IGNORECASE | re.DOTALL,
    )
    for m in para_pattern.finditer(text):
        cls = ClassSetup(
            class_name=f"Class {m.group(1)}",
            original_balance=_parse_amount(m.group(2)),
            coupon_rate=_parse_rate(m.group(3)),
        )
        classes.append(cls)

    # Assign priority
    for i, cls in enumerate(classes, 1):
        cls.payment_priority = i

    return classes


# ── Save Helpers ──────────────────────────────────────────────

def save_deal_setup_csv(setup: DealSetup, path: Path) -> Path:
    """Save deal setup to CSV."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["field", "value"])
        for key, value in setup.to_dict().items():
            writer.writerow([key, str(value)])

    return path


def save_classes_setup_csv(classes: list[ClassSetup], path: Path) -> Path:
    """Save classes setup to CSV."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not classes:
        path.write_text("class_name,original_balance,coupon_rate\n", encoding="utf-8")
        return path

    fieldnames = list(classes[0].to_dict().keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for cls in classes:
            writer.writerow(cls.to_dict())

    return path


# ── Private Helpers ───────────────────────────────────────────

def _parse_amount(val: Any) -> float:
    """Parse a monetary amount."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = re.sub(r'[$,\s]', '', val.strip())
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    return 0.0


def _parse_rate(val: Any) -> float:
    """Parse a rate/percentage value. Returns decimal (e.g., 0.0525)."""
    if isinstance(val, (int, float)):
        v = float(val)
        return v / 100.0 if v > 1.0 else v
    if isinstance(val, str):
        cleaned = re.sub(r'[%\s]', '', val.strip())
        try:
            v = float(cleaned)
            return v / 100.0 if v > 1.0 else v
        except ValueError:
            return 0.0
    return 0.0
