"""
Output Comparator — Compare model outputs against reference/teaching data.
Supports CSV comparison with configurable tolerance ($0.01 default).

Ported from PayGen pipeline.skills.output_comparator → backend.abs.skills
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from backend.abs.config.constants import OUTPUT_TOLERANCE


@dataclass
class CellDifference:
    """Single cell-level difference."""
    row: int
    column: str
    expected: Any
    actual: Any
    difference: float = 0.0
    is_within_tolerance: bool = True


@dataclass
class ComparisonResult:
    """Full comparison result."""
    match: bool
    match_percentage: float  # 0.0 to 100.0
    total_cells: int = 0
    matching_cells: int = 0
    differences: list[CellDifference] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    extra_columns: list[str] = field(default_factory=list)
    row_count_expected: int = 0
    row_count_actual: int = 0
    summary: str = ""


def compare_outputs(
    expected_path: Path,
    actual_path: Path,
    tolerance: float = OUTPUT_TOLERANCE,
    key_columns: Optional[list[str]] = None,
) -> ComparisonResult:
    """
    Compare expected vs. actual CSV outputs.

    Args:
        expected_path: Path to reference/teaching CSV
        actual_path: Path to generated output CSV
        tolerance: Acceptable numeric difference (default: $0.01)
        key_columns: Columns to use for row matching (default: match by position)

    Returns:
        ComparisonResult with detailed differences
    """
    expected_path = Path(expected_path)
    actual_path = Path(actual_path)

    if not expected_path.exists():
        return ComparisonResult(
            match=False, match_percentage=0.0,
            summary=f"Expected file not found: {expected_path}",
        )
    if not actual_path.exists():
        return ComparisonResult(
            match=False, match_percentage=0.0,
            summary=f"Actual file not found: {actual_path}",
        )

    expected_rows = _read_csv(expected_path)
    actual_rows = _read_csv(actual_path)

    if not expected_rows:
        return ComparisonResult(
            match=len(actual_rows) == 0,
            match_percentage=100.0 if len(actual_rows) == 0 else 0.0,
            summary="Expected file is empty",
        )

    # Column comparison
    expected_cols = set(expected_rows[0].keys())
    actual_cols = set(actual_rows[0].keys()) if actual_rows else set()
    missing_cols = sorted(expected_cols - actual_cols)
    extra_cols = sorted(actual_cols - expected_cols)
    common_cols = sorted(expected_cols & actual_cols)

    differences: list[CellDifference] = []
    total_cells = 0
    matching_cells = 0

    # Row-by-row comparison
    max_rows = max(len(expected_rows), len(actual_rows))
    for i in range(max_rows):
        if i >= len(expected_rows):
            # Extra actual rows
            for col in common_cols:
                total_cells += 1
                differences.append(CellDifference(
                    row=i, column=col,
                    expected="<missing>", actual=actual_rows[i].get(col, ""),
                    is_within_tolerance=False,
                ))
            continue

        if i >= len(actual_rows):
            # Missing actual rows
            for col in common_cols:
                total_cells += 1
                differences.append(CellDifference(
                    row=i, column=col,
                    expected=expected_rows[i].get(col, ""),
                    actual="<missing>",
                    is_within_tolerance=False,
                ))
            continue

        for col in common_cols:
            total_cells += 1
            exp_val = expected_rows[i].get(col, "")
            act_val = actual_rows[i].get(col, "")

            exp_num = _parse_number(exp_val)
            act_num = _parse_number(act_val)

            if exp_num is not None and act_num is not None:
                diff = abs(exp_num - act_num)
                within_tol = diff <= tolerance
                if within_tol:
                    matching_cells += 1
                else:
                    differences.append(CellDifference(
                        row=i, column=col,
                        expected=exp_val, actual=act_val,
                        difference=diff, is_within_tolerance=False,
                    ))
            else:
                # String comparison
                if str(exp_val).strip() == str(act_val).strip():
                    matching_cells += 1
                else:
                    differences.append(CellDifference(
                        row=i, column=col,
                        expected=exp_val, actual=act_val,
                        is_within_tolerance=False,
                    ))

    match_pct = (matching_cells / total_cells * 100.0) if total_cells > 0 else 100.0
    is_match = len(differences) == 0 and not missing_cols

    summary_parts = []
    if is_match:
        summary_parts.append(f"PASS: {matching_cells}/{total_cells} cells match within ${tolerance:.2f} tolerance")
    else:
        summary_parts.append(f"FAIL: {len(differences)} differences found, {match_pct:.1f}% match")
        if missing_cols:
            summary_parts.append(f"Missing columns: {', '.join(missing_cols)}")
        if extra_cols:
            summary_parts.append(f"Extra columns: {', '.join(extra_cols)}")

    return ComparisonResult(
        match=is_match,
        match_percentage=round(match_pct, 2),
        total_cells=total_cells,
        matching_cells=matching_cells,
        differences=differences,
        missing_columns=missing_cols,
        extra_columns=extra_cols,
        row_count_expected=len(expected_rows),
        row_count_actual=len(actual_rows),
        summary="; ".join(summary_parts),
    )


def compare_extractions(
    expected: dict[str, list[dict]],
    actual: dict[str, list[dict]],
    id_field: str = "id",
) -> dict[str, Any]:
    """
    Compare extraction dictionaries (JSON-level comparison).

    Args:
        expected: Reference extractions (section → items)
        actual: Generated extractions
        id_field: Field to use for item matching

    Returns:
        Dict with per-section accuracy metrics
    """
    results: dict[str, Any] = {}

    all_sections = set(expected.keys()) | set(actual.keys())

    for section in sorted(all_sections):
        exp_items = expected.get(section, [])
        act_items = actual.get(section, [])

        exp_ids = {item.get(id_field, f"idx_{i}"): item for i, item in enumerate(exp_items)}
        act_ids = {item.get(id_field, f"idx_{i}"): item for i, item in enumerate(act_items)}

        matched = 0
        missing = []
        extra = []
        mismatched = []

        for eid, eitem in exp_ids.items():
            if eid in act_ids:
                # Compare fields
                aitem = act_ids[eid]
                if _items_match(eitem, aitem):
                    matched += 1
                else:
                    mismatched.append(eid)
            else:
                missing.append(eid)

        for aid in act_ids:
            if aid not in exp_ids:
                extra.append(aid)

        total = len(exp_ids)
        accuracy = (matched / total * 100.0) if total > 0 else 100.0

        results[section] = {
            "expected_count": len(exp_ids),
            "actual_count": len(act_ids),
            "matched": matched,
            "missing": missing,
            "extra": extra,
            "mismatched": mismatched,
            "accuracy_pct": round(accuracy, 2),
        }

    return results


# ── Helpers ───────────────────────────────────────────────────

def _read_csv(path: Path) -> list[dict]:
    """Read CSV into list of dicts."""
    rows = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))
    return rows


def _parse_number(val: Any) -> Optional[float]:
    """Try to parse a value as a number, stripping currency symbols."""
    if isinstance(val, (int, float)):
        return float(val)
    if not isinstance(val, str):
        return None
    cleaned = re.sub(r'[$,\s%]', '', val.strip())
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _items_match(expected: dict, actual: dict) -> bool:
    """Check if two extraction items match on key fields."""
    for key, exp_val in expected.items():
        if key == "id":
            continue
        act_val = actual.get(key)
        if act_val is None:
            continue  # Optional field
        exp_num = _parse_number(exp_val)
        act_num = _parse_number(act_val)
        if exp_num is not None and act_num is not None:
            if abs(exp_num - act_num) > OUTPUT_TOLERANCE:
                return False
        elif str(exp_val).strip().lower() != str(act_val).strip().lower():
            return False
    return True
