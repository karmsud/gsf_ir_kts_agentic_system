"""
Model output validator for the ABS Waterfall AI pipeline.

Compares generated payment model output against a teaching-model
baseline and produces per-class diff reports.

Ported from PayGen pipeline.generation.model_validator → backend.abs.generation
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.abs.skills.document_hasher import compute_text_hash

logger = logging.getLogger(__name__)

# Fields compared on every class row.
COMPARISON_FIELDS: list[str] = [
    "interest_payment",
    "principal_payment",
    "ending_balance",
    "total_payment",
    "loss_allocation",
    "shortfall",
]


# ── Data Classes ─────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    """Outcome of comparing generated output to teaching-model output."""

    passed: bool
    max_diff: float
    per_class_diffs: dict[str, float] = field(default_factory=dict)
    report: str = ""
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "max_diff": self.max_diff,
            "per_class_diffs": self.per_class_diffs,
            "report": self.report,
            "issues": list(self.issues),
        }


# ── Core Validation ──────────────────────────────────────────────────────

def _diff_value(generated: float, expected: float) -> float:
    """Absolute difference between two monetary values."""
    return abs(generated - expected)


def _compare_class_row(
    gen_row: dict[str, Any],
    teach_row: dict[str, Any],
    tolerance: float,
) -> tuple[float, list[str]]:
    """Compare a single class row across all comparison fields.

    Returns the maximum difference found and a list of issue strings
    for any field that exceeds the tolerance.
    """
    max_diff = 0.0
    issues: list[str] = []
    class_name = gen_row.get("class_name", "unknown")

    for col in COMPARISON_FIELDS:
        gen_val = float(gen_row.get(col, 0.0))
        teach_val = float(teach_row.get(col, 0.0))
        diff = _diff_value(gen_val, teach_val)
        if diff > max_diff:
            max_diff = diff
        if diff > tolerance:
            issues.append(
                f"{class_name}.{col}: generated={gen_val:.4f}, "
                f"expected={teach_val:.4f}, diff={diff:.4f}"
            )
    return max_diff, issues


def validate_model_output(
    generated_output: dict[str, Any],
    teaching_output: dict[str, Any],
    tolerance: float = 0.01,
) -> ValidationResult:
    """Compare *generated_output* against *teaching_output* per class.

    Both inputs are dicts keyed by class name, each value being a dict
    of payment fields (interest_payment, principal_payment, etc.).

    Passes when **every** field difference is <= *tolerance* ($0.01).
    """
    overall_max = 0.0
    per_class_diffs: dict[str, float] = {}
    all_issues: list[str] = []

    all_classes = set(generated_output.keys()) | set(teaching_output.keys())

    for cls in sorted(all_classes):
        gen_row = generated_output.get(cls)
        teach_row = teaching_output.get(cls)

        if gen_row is None:
            all_issues.append(f"Class '{cls}' missing from generated output")
            per_class_diffs[cls] = float("inf")
            continue
        if teach_row is None:
            all_issues.append(f"Class '{cls}' missing from teaching output")
            per_class_diffs[cls] = float("inf")
            continue

        cls_max, cls_issues = _compare_class_row(gen_row, teach_row, tolerance)
        per_class_diffs[cls] = cls_max
        all_issues.extend(cls_issues)
        if cls_max > overall_max:
            overall_max = cls_max

    passed = overall_max <= tolerance and not all_issues
    report_lines = [
        f"Validation {'PASSED' if passed else 'FAILED'}",
        f"Tolerance: ${tolerance:.4f}",
        f"Max diff:  ${overall_max:.4f}",
        f"Classes:   {len(all_classes)}",
        f"Issues:    {len(all_issues)}",
    ]
    report = "\n".join(report_lines)
    logger.info(report_lines[0])

    return ValidationResult(
        passed=passed,
        max_diff=overall_max,
        per_class_diffs=per_class_diffs,
        report=report,
        issues=all_issues,
    )


# ── CSV-Level Comparison ─────────────────────────────────────────────────

def compare_csv_outputs(
    generated_csv: Path,
    teaching_csv: Path,
    tolerance: float = 0.01,
) -> ValidationResult:
    """Load two CSV files and compare them row-by-row as class data.

    Each CSV must have a ``class_name`` column used as the join key.
    """
    generated_csv = Path(generated_csv)
    teaching_csv = Path(teaching_csv)

    def _csv_to_dict(csv_path: Path) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        with open(csv_path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                class_name = row.get("class_name", "").strip()
                if class_name:
                    result[class_name] = row
        return result

    gen_data = _csv_to_dict(generated_csv)
    teach_data = _csv_to_dict(teaching_csv)
    return validate_model_output(gen_data, teach_data, tolerance)


# ── Report Generation ────────────────────────────────────────────────────

def generate_validation_notes(
    result: ValidationResult,
    output_path: Path,
) -> Path:
    """Write a ``VALIDATION_NOTES.md`` file summarising *result*.

    Returns the path to the written file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    content_hash = compute_text_hash(result.report)

    lines = [
        "# Validation Notes",
        "",
        f"**Generated:** {now}",
        f"**Status:** {'PASSED' if result.passed else 'FAILED'}",
        f"**Max Diff:** ${result.max_diff:.4f}",
        f"**Report Hash:** {content_hash}",
        "",
        "## Per-Class Differences",
        "",
        "| Class | Max Diff |",
        "|-------|----------|",
    ]
    for cls, diff in sorted(result.per_class_diffs.items()):
        diff_str = "missing" if diff == float("inf") else f"${diff:.4f}"
        lines.append(f"| {cls} | {diff_str} |")

    if result.issues:
        lines.extend(["", "## Issues", ""])
        for issue in result.issues:
            lines.append(f"- {issue}")

    lines.append("")  # trailing newline
    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote validation notes to %s", output_path)
    return output_path
