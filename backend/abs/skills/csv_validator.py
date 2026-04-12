"""
CSV Validator — Validates CSV files against named schemas.

Ported from PayGen pipeline.skills.csv_validator → backend.abs.skills
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from backend.abs.config.schemas import SCHEMA_REGISTRY


def validate_csv(
    csv_path: Path,
    schema_name: str,
) -> tuple[bool, list[str]]:
    """
    Validate a CSV against a named schema.

    Args:
        csv_path: Path to CSV file
        schema_name: One of "deal_setup", "classes_setup", "monthly_input",
                     "class_balances", "output_teaching"

    Returns:
        (is_valid, list_of_errors)
    """
    errors: list[str] = []

    # Schema lookup
    if schema_name not in SCHEMA_REGISTRY:
        return False, [f"Unknown schema: '{schema_name}'"]

    schema = SCHEMA_REGISTRY[schema_name]

    # File existence
    if not csv_path.exists():
        return False, [f"File not found: {csv_path}"]

    # Read CSV
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                return False, ["CSV has no header row"]

            headers = [h.strip().lower() for h in reader.fieldnames]
            rows = list(reader)
    except Exception as e:
        return False, [f"Cannot read CSV: {e}"]

    # Check required columns
    required = schema.get("required_columns", [])
    for col in required:
        if col.lower() not in headers:
            errors.append(f"Missing required column: '{col}'")

    # Check for empty file
    if not rows:
        errors.append("CSV has no data rows")

    # Type validation
    type_map = schema.get("types", {})
    for row_idx, row in enumerate(rows):
        for col, expected_type in type_map.items():
            if col.lower() not in headers:
                continue
            value = row.get(col, "").strip()
            if not value:
                continue  # Empty is OK for optional fields

            try:
                if expected_type == "float":
                    # Remove currency symbols and commas
                    cleaned = value.replace("$", "").replace(",", "").strip()
                    float(cleaned)
                elif expected_type == "int":
                    int(value)
            except ValueError:
                errors.append(
                    f"Row {row_idx + 1}, column '{col}': "
                    f"'{value}' is not a valid {expected_type}"
                )

    return len(errors) == 0, errors


def validate_extraction_json(
    data: list[dict],
    schema_name: str,
) -> tuple[bool, list[str]]:
    """
    Validate extraction JSON output against schema.

    Args:
        data: List of extraction dicts
        schema_name: One of "definitions", "waterfall_rules", etc.

    Returns:
        (is_valid, list_of_errors)
    """
    from backend.abs.config.schemas import EXTRACTION_SCHEMA_REGISTRY

    errors: list[str] = []

    if schema_name not in EXTRACTION_SCHEMA_REGISTRY:
        return False, [f"Unknown extraction schema: '{schema_name}'"]

    schema = EXTRACTION_SCHEMA_REGISTRY[schema_name]
    required_fields = schema.get("required_fields", [])

    if not data:
        return False, ["Extraction data is empty"]

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            errors.append(f"Item {i}: not a dict")
            continue

        for field in required_fields:
            if field not in item or item[field] is None or item[field] == "":
                errors.append(f"Item {i}: missing required field '{field}'")

    return len(errors) == 0, errors
