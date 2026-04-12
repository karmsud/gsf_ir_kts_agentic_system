"""
RegressionTestingAgent — Detect model drift by comparing current outputs
to a persisted baseline.

Compares per-class payment fields using $0.01 tolerance and flags any
classes whose outputs have drifted beyond the threshold.

No LLM / OpenAI dependency.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from backend.agents.base_agent import AgentBase
from backend.agents.agent_tools import ToolRegistry
from backend.common.confidence import ConfidenceScore, ConfidenceTier
from backend.abs.config.constants import OUTPUT_TOLERANCE
from backend.abs.deal_scope import DealScope
from config import KTSConfig

logger = logging.getLogger(__name__)


class RegressionTestingAgent(AgentBase):
    """
    Detect model drift by comparing current model outputs to a baseline.

    Workflow:
    1. Load baseline outputs from ``deal_path/baseline/``.
    2. Run the current model to produce fresh outputs.
    3. Compare using ``compare_outputs()`` with $0.01 tolerance.
    4. Flag any class where ``|diff| > tolerance``.
    5. Generate a regression report.
    """

    agent_name = "regression_testing"

    def __init__(
        self,
        config: KTSConfig,
        deal_scope: DealScope,
        tool_registry: ToolRegistry,
        llm_callable=None,
    ) -> None:
        super().__init__(config, deal_scope=deal_scope, tool_registry=tool_registry, llm_callable=llm_callable)

    # ------------------------------------------------------------------
    # Prompt structure
    # ------------------------------------------------------------------

    def _get_mission(self) -> str:
        return (
            "Detect model drift by comparing the current model's outputs "
            "to a persisted baseline with $0.01 tolerance."
        )

    def _get_actions(self) -> list[str]:
        return [
            "Load baseline outputs from deal_path/baseline/.",
            "Run the current model to produce fresh outputs.",
            "Compare baseline vs. current using compare_outputs().",
            "Detect drift: flag any class with |diff| > tolerance.",
            "Generate a regression report.",
        ]

    def _get_output_spec(self) -> str:
        return (
            "dict with keys:\n"
            "  drift_detected: bool\n"
            "  drifted_classes: list[str]\n"
            "  max_drift: float\n"
            "  comparison_details: dict\n"
        )

    def _get_validation_rules(self) -> list[str]:
        return [
            "Baseline outputs must exist for comparison.",
            "Current model must produce outputs for the same months.",
            "Tolerance is $0.01 per field per class.",
            "Drift flag must be set if any class exceeds tolerance.",
        ]

    # ------------------------------------------------------------------
    # Core execution
    # ------------------------------------------------------------------

    def _run(self, task: dict[str, Any]) -> dict[str, Any]:
        deal_path = self.deal_scope.deal_path
        tolerance = task.get("tolerance", OUTPUT_TOLERANCE)
        month = task.get("month", 1)

        # 1. Locate baseline
        baseline_dir = deal_path / "baseline"
        baseline_csv = baseline_dir / f"month_{month}" / "output.csv"

        if not baseline_csv.exists():
            # Try flat layout
            baseline_csv = baseline_dir / "output.csv"

        if not baseline_csv.exists():
            logger.warning("No baseline found at %s", baseline_dir)
            return {
                "drift_detected": False,
                "drifted_classes": [],
                "max_drift": 0.0,
                "comparison_details": {"error": "No baseline found"},
            }

        # 2. Locate current outputs
        current_csv = deal_path / "runs" / f"month_{month}" / "output.csv"
        if not current_csv.exists():
            # Attempt to run model
            current_csv = self._run_current_model(deal_path, month)

        if current_csv is None or not current_csv.exists():
            logger.warning("No current output for month %d", month)
            return {
                "drift_detected": False,
                "drifted_classes": [],
                "max_drift": 0.0,
                "comparison_details": {"error": "No current output available"},
            }

        # 3. Compare
        comparison = self._compare(baseline_csv, current_csv, tolerance)

        # 4. Persist report
        report = {
            "deal_id": self.deal_scope.deal_id,
            "month": month,
            "tolerance": tolerance,
            **comparison,
        }
        report_dir = deal_path / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "regression_report.json"
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        logger.info("Regression report saved to %s", report_path)

        return comparison

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _run_current_model(self, deal_path: Path, month: int) -> Path | None:
        """Attempt to run the model for the given month."""
        model_path = deal_path / "model" / "payment_model.py"
        if not model_path.exists():
            return None
        try:
            from backend.abs.generation.model_runner import run_model_for_month
            result = run_model_for_month(
                model_path=model_path,
                data_path=deal_path,
                month=month,
                output_dir=deal_path,
            )
            if result.success:
                return result.output_path
        except Exception as exc:
            logger.warning("Model run failed: %s", exc)
        return None

    def _compare(
        self,
        baseline_csv: Path,
        current_csv: Path,
        tolerance: float,
    ) -> dict[str, Any]:
        """Compare baseline vs current CSV outputs."""
        # Try using the output_comparator skill
        try:
            from backend.abs.skills.output_comparator import compare_outputs
            comp = compare_outputs(
                expected_path=baseline_csv,
                actual_path=current_csv,
                tolerance=tolerance,
            )
            drifted = self._extract_drifted_classes(comp)
            max_drift = max(
                (abs(d.difference) for d in comp.differences),
                default=0.0,
            )
            return {
                "drift_detected": not comp.match,
                "drifted_classes": drifted,
                "max_drift": round(max_drift, 4),
                "comparison_details": {
                    "match_percentage": comp.match_percentage,
                    "total_cells": comp.total_cells,
                    "differences_count": len(comp.differences),
                    "missing_columns": comp.missing_columns,
                },
            }
        except Exception as exc:
            logger.info("output_comparator unavailable (%s), using inline compare", exc)
            return self._inline_compare(baseline_csv, current_csv, tolerance)

    @staticmethod
    def _extract_drifted_classes(comp: Any) -> list[str]:
        """Extract unique class names from comparison differences."""
        classes: set[str] = set()
        for diff in comp.differences:
            if not diff.is_within_tolerance:
                # Try to determine class from row context
                classes.add(f"row_{diff.row}")
        return sorted(classes)

    def _inline_compare(
        self,
        baseline_csv: Path,
        current_csv: Path,
        tolerance: float,
    ) -> dict[str, Any]:
        """Inline CSV comparison when output_comparator is unavailable."""
        import csv as csv_mod

        def _read(path: Path) -> list[dict[str, str]]:
            with open(path, newline="", encoding="utf-8") as fh:
                return list(csv_mod.DictReader(fh))

        baseline_rows = _read(baseline_csv)
        current_rows = _read(current_csv)

        drifted_classes: list[str] = []
        max_drift = 0.0
        numeric_fields = {
            "interest_payment", "principal_payment", "ending_balance",
            "total_payment", "loss_allocation", "shortfall", "payment",
        }

        for i, (b_row, c_row) in enumerate(zip(baseline_rows, current_rows)):
            class_name = b_row.get("class_name", f"row_{i}")
            for col in numeric_fields & set(b_row.keys()):
                try:
                    b_val = float(b_row.get(col, "0"))
                    c_val = float(c_row.get(col, "0"))
                    diff = abs(b_val - c_val)
                    if diff > tolerance:
                        if class_name not in drifted_classes:
                            drifted_classes.append(class_name)
                    max_drift = max(max_drift, diff)
                except (ValueError, TypeError):
                    pass

        return {
            "drift_detected": len(drifted_classes) > 0,
            "drifted_classes": drifted_classes,
            "max_drift": round(max_drift, 4),
            "comparison_details": {
                "baseline_rows": len(baseline_rows),
                "current_rows": len(current_rows),
            },
        }

    # ------------------------------------------------------------------
    # Quality scoring overrides
    # ------------------------------------------------------------------

    def _score_completeness(self, result: Any, task: dict) -> float:
        details = result.get("comparison_details", {})
        if "error" in details:
            return 5.0
        return 10.0

    def _score_accuracy(self, result: Any, task: dict) -> float:
        details = result.get("comparison_details", {})
        if "error" in details:
            return 5.0
        return 10.0

    def _score_confidence(self, result: Any, task: dict) -> ConfidenceScore:
        details = result.get("comparison_details", {})
        if "error" in details:
            value = 0.5
        elif result.get("drift_detected"):
            value = 0.75  # Drift found — confident in result but deal needs attention
        else:
            value = 0.95
        tier = self._categorize_confidence(value)
        return ConfidenceScore(
            value=value, tier=tier,
            reasoning=f"drift={'yes' if result.get('drift_detected') else 'no'}, "
                      f"max_drift={result.get('max_drift', 0):.4f}",
        )

    def _get_artifacts(self, result: Any) -> list[str]:
        report_path = self.deal_scope.deal_path / "reports" / "regression_report.json"
        return [str(report_path)] if report_path.exists() else []
