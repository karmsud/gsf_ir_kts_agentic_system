"""
Data preparation utilities for monthly payment model runs.

Loads deal setup, classes setup, and assembles per-month input
dictionaries from either initial balances or prior-month outputs.

Ported from PayGen pipeline.generation.data_prep → backend.abs.generation
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Fields that every monthly input dict MUST contain.
REQUIRED_MONTHLY_FIELDS: list[str] = [
    "pool_balance",
    "interest_rate",
    "default_amount",
    "recovery_amount",
    "prepayment_amount",
    "loss_amount",
]


# ── Deal / Classes Setup ────────────────────────────────────────────────

def load_deal_setup(deal_path: Path) -> dict[str, Any]:
    """Read deal_setup.csv as key-value pairs.

    The CSV is expected to have two columns: ``field`` and ``value``.
    Returns a plain dict mapping field names to their string values.
    """
    setup_file = Path(deal_path) / "deal_setup.csv"
    if not setup_file.exists():
        raise FileNotFoundError(f"deal_setup.csv not found at {setup_file}")

    result: dict[str, Any] = {}
    with open(setup_file, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            # Support both capitalized and lowercase column names
            key = (row.get("Field") or row.get("field", "")).strip()
            value = (row.get("Value") or row.get("value", "")).strip()
            if key:
                result[key] = value
    logger.info("Loaded %d deal-setup fields from %s", len(result), setup_file)
    return result


def load_classes_setup(deal_path: Path) -> pd.DataFrame:
    """Read classes_setup.csv into a DataFrame.

    Expected columns include at minimum: class_name, original_balance.
    """
    setup_file = Path(deal_path) / "classes_setup.csv"
    if not setup_file.exists():
        raise FileNotFoundError(f"classes_setup.csv not found at {setup_file}")

    df = pd.read_csv(setup_file)
    logger.info("Loaded classes_setup with %d rows from %s", len(df), setup_file)
    return df


# ── Monthly Data Assembly ────────────────────────────────────────────────

def prepare_month_data(
    deal_path: Path,
    month_number: int,
    classes_setup_path: Path | None = None,
) -> dict[str, Any]:
    """Build the input dictionary for a specific month.

    * **Month 1** — class balances are auto-filled from the
      ``original_balance`` column in ``classes_setup.csv``.
    * **Month N > 1** — balances are read from the previous month's
      output located at ``runs/month_{N-1}/output.csv``.

    Returns a dict ready to feed into the payment model.
    """
    deal_path = Path(deal_path)
    data: dict[str, Any] = {
        "month": month_number,
        "deal_setup": load_deal_setup(deal_path),
    }

    if month_number == 1:
        # Use classes_setup for starting balances.
        cs_path = Path(classes_setup_path) if classes_setup_path else deal_path
        classes_df = load_classes_setup(cs_path)
        class_balances: dict[str, float] = {}
        for _, row in classes_df.iterrows():
            class_balances[str(row["class_name"])] = float(row["original_balance"])
        data["class_balances"] = class_balances
        logger.info("Month 1: seeded %d class balances from classes_setup", len(class_balances))
    else:
        prev_output = deal_path / f"runs/month_{month_number - 1}/output.csv"
        if not prev_output.exists():
            raise FileNotFoundError(
                f"Previous month output not found: {prev_output}"
            )
        prev_df = pd.read_csv(prev_output)
        class_balances = {}
        for _, row in prev_df.iterrows():
            class_balances[str(row["class_name"])] = float(row["ending_balance"])
        data["class_balances"] = class_balances
        data["previous_month_output"] = str(prev_output)
        logger.info("Month %d: loaded balances from %s", month_number, prev_output)

    return data


# ── Validation ───────────────────────────────────────────────────────────

def validate_monthly_inputs(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Check that *data* contains all required monthly fields.

    Returns ``(True, [])`` when valid, or ``(False, [<missing>, ...])``
    when one or more fields are absent.
    """
    missing: list[str] = [
        field for field in REQUIRED_MONTHLY_FIELDS if field not in data
    ]
    if missing:
        logger.warning("Monthly input validation failed — missing: %s", missing)
        return False, missing
    return True, []
