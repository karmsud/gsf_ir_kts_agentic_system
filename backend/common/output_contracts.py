"""
OutputContractValidator — Validates standardized ID prefixes (Decision D8).

Prefixes:
  DEF-xxx  for definitions
  RULE-xxx for waterfall rules
  ACC-xxx  for accounts
  LOSS-xxx for loss allocations
  TRIG-xxx for triggers
  SEC-xxx  for sections
  RPT-xxx  for reporting requirements
"""

from __future__ import annotations

from typing import Any

from backend.abs.config.constants import OUTPUT_PREFIXES


class OutputContractValidator:
    """
    Validates that all artifacts have correct standardized ID prefixes.

    Each extraction type has an assigned prefix (see OUTPUT_PREFIXES).
    This validator checks that external_id or rule_id fields conform.
    """

    VALID_PREFIXES = OUTPUT_PREFIXES

    # Map artifact types to the field that should have the prefix
    ID_FIELD_MAP = {
        "definition": "external_id",
        "rule": "rule_id",
        "account": "external_id",
        "loss": "rule_id",
        "trigger": "external_id",
        "section": "external_id",
        "report": "external_id",
    }

    def validate(
        self,
        artifacts: list[dict],
        artifact_type: str,
    ) -> tuple[bool, list[str]]:
        """
        Validate all artifacts have correct ID prefixes.

        Args:
            artifacts: List of extraction dicts
            artifact_type: One of "definition", "rule", "account",
                          "loss", "trigger", "section", "report"

        Returns:
            (is_valid, list_of_errors)
        """
        if artifact_type not in self.VALID_PREFIXES:
            return False, [f"Unknown artifact type: '{artifact_type}'"]

        expected_prefix = self.VALID_PREFIXES[artifact_type]
        id_field = self.ID_FIELD_MAP.get(artifact_type, "external_id")
        errors: list[str] = []

        for i, item in enumerate(artifacts):
            if not isinstance(item, dict):
                errors.append(f"Item {i}: not a dict")
                continue

            item_id = item.get(id_field)
            if item_id is None:
                errors.append(f"Item {i}: missing '{id_field}' field")
                continue

            if not isinstance(item_id, str):
                errors.append(f"Item {i}: '{id_field}' is not a string")
                continue

            if not item_id.startswith(expected_prefix):
                errors.append(
                    f"Item {i}: '{id_field}'='{item_id}' does not start with "
                    f"'{expected_prefix}'"
                )

        return len(errors) == 0, errors

    def validate_all(
        self,
        extractions: dict[str, list[dict]],
    ) -> dict[str, tuple[bool, list[str]]]:
        """
        Validate all extraction types at once.

        Args:
            extractions: Dict mapping artifact_type to list of items
                        e.g., {"definition": [...], "rule": [...]}

        Returns:
            Dict mapping artifact_type to (is_valid, errors)
        """
        results = {}
        for artifact_type, items in extractions.items():
            results[artifact_type] = self.validate(items, artifact_type)
        return results

    @staticmethod
    def assign_ids(
        artifacts: list[dict],
        artifact_type: str,
        id_field: str = "external_id",
        start: int = 1,
    ) -> list[dict]:
        """
        Assign standardized IDs to artifacts that don't have them.

        Args:
            artifacts: List of extraction dicts
            artifact_type: Type key for prefix lookup
            id_field: Field name for the ID
            start: Starting number

        Returns:
            Updated list with IDs assigned
        """
        prefix = OUTPUT_PREFIXES.get(artifact_type, "UNK-")
        for i, item in enumerate(artifacts):
            if isinstance(item, dict) and not item.get(id_field):
                item[id_field] = f"{prefix}{str(start + i).zfill(3)}"
        return artifacts
