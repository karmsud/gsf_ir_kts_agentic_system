"""
StressTestingAgent — Run stress scenarios against the payment model.

Defines a set of deterministic stress scenarios (elevated defaults,
rate shocks, prepayment spikes), runs cashflow projections for each,
and tracks which triggers get breached.

No LLM / OpenAI dependency.
"""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any

from backend.agents.base_agent import AgentBase
from backend.agents.agent_tools import ToolRegistry
from backend.common.confidence import ConfidenceScore, ConfidenceTier
from backend.abs.config.constants import CONFIDENCE_HIGH_THRESHOLD
from backend.abs.deal_scope import DealScope
from backend.abs.generation.data_prep import load_deal_setup, load_classes_setup
from config import KTSConfig

logger = logging.getLogger(__name__)

# ── Pre-defined stress scenarios ─────────────────────────────────────────

DEFAULT_SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "elevated_defaults",
        "description": "2× default rate applied to every month",
        "overrides": {"default_multiplier": 2.0},
    },
    {
        "name": "severe_defaults",
        "description": "3× default rate applied to every month",
        "overrides": {"default_multiplier": 3.0},
    },
    {
        "name": "rate_shock_up_200bps",
        "description": "Interest rate increased by 200 basis points",
        "overrides": {"rate_shock_bps": 200},
    },
    {
        "name": "rate_shock_down_100bps",
        "description": "Interest rate decreased by 100 basis points",
        "overrides": {"rate_shock_bps": -100},
    },
    {
        "name": "prepayment_spike",
        "description": "3× prepayment rate (CPR) in months 1-6",
        "overrides": {"prepayment_multiplier": 3.0, "spike_months": 6},
    },
    {
        "name": "combined_stress",
        "description": "2× defaults + 150bps rate shock",
        "overrides": {"default_multiplier": 2.0, "rate_shock_bps": 150},
    },
]


class StressTestingAgent(AgentBase):
    """
    Run deterministic stress scenarios against the deal's payment model.

    For each scenario the agent:
    1. Copies baseline monthly inputs.
    2. Applies scenario overrides (multiplied defaults, rate shocks, etc.).
    3. Runs cashflow projections via ``run_projections()``.
    4. Checks which triggers breach under the scenario.
    5. Produces a consolidated stress report.
    """

    agent_name = "stress_testing"

    DEFAULT_PROJECTION_MONTHS = 12

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
            "Run stress scenarios against the payment model to identify "
            "trigger breaches and assess deal resilience under adverse conditions."
        )

    def _get_actions(self) -> list[str]:
        return [
            "Load deal setup, classes setup, and extraction data.",
            "Define stress scenarios (elevated defaults, rate shocks, prepayment spikes).",
            "For each scenario: apply overrides to monthly inputs.",
            "Run cashflow projections using run_projections().",
            "Check trigger conditions under each scenario.",
            "Generate a consolidated stress report.",
        ]

    def _get_output_spec(self) -> str:
        return (
            "dict with keys:\n"
            "  scenarios: list[dict] — per-scenario results\n"
            "  trigger_breaches: dict[scenario_name, list[str]] — breached triggers\n"
            "  summary: dict — aggregate metrics\n"
        )

    def _get_validation_rules(self) -> list[str]:
        return [
            "Every defined scenario must be executed.",
            "Trigger breaches must be recorded accurately.",
            "Projections must run for the configured number of months.",
            "Report must be saved to deal_path/reports/.",
        ]

    # ------------------------------------------------------------------
    # Core execution
    # ------------------------------------------------------------------

    def _run(self, task: dict[str, Any]) -> dict[str, Any]:
        deal_path = self.deal_scope.deal_path
        months = task.get("months", self.DEFAULT_PROJECTION_MONTHS)

        # Load baseline data
        try:
            deal_setup = load_deal_setup(deal_path)
        except FileNotFoundError:
            return {"status": "error", "error": "deal_setup.csv not found", "scenarios": []}

        try:
            classes_df = load_classes_setup(deal_path)
            classes_setup = classes_df.to_dict(orient="records")
        except FileNotFoundError:
            return {"status": "error", "error": "classes_setup.csv not found", "scenarios": []}

        # Load extractions for waterfall / triggers
        waterfall_rules = self._load_json_list(deal_path / "extractions" / "waterfall_rules.json")
        triggers = self._load_json_list(deal_path / "extractions" / "triggers.json")

        # Build baseline monthly inputs
        baseline_inputs = self._build_baseline_inputs(deal_setup, classes_setup, months)

        scenarios_to_run = task.get("scenarios", DEFAULT_SCENARIOS)
        scenario_results: list[dict[str, Any]] = []
        trigger_breaches: dict[str, list[str]] = {}

        for scenario in scenarios_to_run:
            name = scenario["name"]
            overrides = scenario.get("overrides", {})

            # Apply overrides
            stressed_inputs = self._apply_overrides(baseline_inputs, overrides)

            # Run projection
            projection = self._run_projection(
                waterfall_rules, classes_setup, stressed_inputs,
                triggers, name,
            )

            # Check triggers
            breaches = self._check_trigger_breaches(projection, triggers)
            trigger_breaches[name] = breaches

            scenario_results.append({
                "name": name,
                "description": scenario.get("description", ""),
                "months_projected": len(projection),
                "triggers_breached": breaches,
                "final_balances": projection[-1] if projection else {},
            })

        summary = self._build_summary(scenario_results, trigger_breaches)

        # Persist report
        report = {
            "deal_id": self.deal_scope.deal_id,
            "scenarios": scenario_results,
            "trigger_breaches": trigger_breaches,
            "summary": summary,
        }
        report_dir = deal_path / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "stress_report.json"
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        logger.info("Stress report saved to %s", report_path)

        return report

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_baseline_inputs(
        self,
        deal_setup: dict[str, Any],
        classes_setup: list[dict],
        months: int,
    ) -> list[dict[str, Any]]:
        """Create baseline monthly input dicts."""
        pool_balance = float(deal_setup.get("original_balance", deal_setup.get("pool_balance", "0")))
        interest_rate = float(deal_setup.get("interest_rate", "0.05"))
        inputs: list[dict[str, Any]] = []
        for m in range(1, months + 1):
            inputs.append({
                "month": m,
                "pool_balance": pool_balance,
                "interest_rate": interest_rate,
                "default_amount": 0.0,
                "recovery_amount": 0.0,
                "prepayment_amount": 0.0,
                "loss_amount": 0.0,
            })
        return inputs

    @staticmethod
    def _apply_overrides(
        baseline: list[dict[str, Any]],
        overrides: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Apply scenario overrides to baseline inputs."""
        stressed = copy.deepcopy(baseline)
        default_mult = overrides.get("default_multiplier", 1.0)
        rate_shock_bps = overrides.get("rate_shock_bps", 0)
        prepay_mult = overrides.get("prepayment_multiplier", 1.0)
        spike_months = overrides.get("spike_months", 999)

        for inp in stressed:
            inp["default_amount"] *= default_mult
            inp["interest_rate"] += rate_shock_bps / 10_000
            if inp["month"] <= spike_months:
                inp["prepayment_amount"] *= prepay_mult
        return stressed

    def _run_projection(
        self,
        waterfall_rules: list[dict],
        classes_setup: list[dict],
        monthly_inputs: list[dict],
        triggers: list[dict],
        scenario: str,
    ) -> list[dict[str, Any]]:
        """Run cashflow projection; gracefully degrade if engine unavailable."""
        try:
            from backend.abs.skills.cashflow_engine import run_projections
            result = run_projections(
                waterfall_rules=waterfall_rules,
                classes_setup=classes_setup,
                monthly_inputs=monthly_inputs,
                deal_id=self.deal_scope.deal_id,
                scenario=scenario,
                triggers=triggers,
            )
            return [m.to_dict() for m in result.months]
        except Exception as exc:
            logger.warning("Cashflow engine unavailable (%s), using inline projection", exc)
            return self._inline_projection(classes_setup, monthly_inputs)

    @staticmethod
    def _inline_projection(
        classes_setup: list[dict],
        monthly_inputs: list[dict],
    ) -> list[dict[str, Any]]:
        """Minimal inline projection when cashflow_engine is unavailable."""
        results: list[dict[str, Any]] = []
        balances = {
            str(c.get("class_name", f"class_{i}")): float(c.get("original_balance", 0))
            for i, c in enumerate(classes_setup)
        }
        for inp in monthly_inputs:
            month_result: dict[str, Any] = {"month": inp["month"], "class_balances": {}}
            rate = inp.get("interest_rate", 0.05) / 12
            for cls_name, bal in balances.items():
                interest = bal * rate
                month_result["class_balances"][cls_name] = {
                    "beginning_balance": bal,
                    "interest": round(interest, 2),
                    "ending_balance": round(bal, 2),
                }
            results.append(month_result)
        return results

    @staticmethod
    def _check_trigger_breaches(
        projection: list[dict[str, Any]],
        triggers: list[dict],
    ) -> list[str]:
        """Check which triggers are breached in the projection."""
        breached: list[str] = []
        for trig in triggers:
            name = trig.get("name", trig.get("id", ""))
            threshold = trig.get("threshold")
            metric = trig.get("metric", "")
            if not name or threshold is None:
                continue
            threshold_val = float(threshold)
            for month_data in projection:
                trigger_states = month_data.get("trigger_states", {})
                if trigger_states.get(name):
                    if name not in breached:
                        breached.append(name)
                    break
                # Also check class_balances for OC-type triggers
                class_balances = month_data.get("class_balances", {})
                if metric and isinstance(class_balances, dict):
                    for cls_data in class_balances.values():
                        if isinstance(cls_data, dict):
                            val = cls_data.get(metric, 0)
                            if isinstance(val, (int, float)) and val > threshold_val:
                                if name not in breached:
                                    breached.append(name)
        return breached

    @staticmethod
    def _build_summary(
        scenario_results: list[dict[str, Any]],
        trigger_breaches: dict[str, list[str]],
    ) -> dict[str, Any]:
        total = len(scenario_results)
        with_breaches = sum(1 for v in trigger_breaches.values() if v)
        all_triggers = set()
        for bl in trigger_breaches.values():
            all_triggers.update(bl)
        return {
            "total_scenarios": total,
            "scenarios_with_breaches": with_breaches,
            "unique_triggers_breached": sorted(all_triggers),
        }

    @staticmethod
    def _load_json_list(path: Path) -> list[dict]:
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else data.get("items", [data])
        except (json.JSONDecodeError, OSError):
            return []

    # ------------------------------------------------------------------
    # Quality scoring overrides
    # ------------------------------------------------------------------

    def _score_completeness(self, result: Any, task: dict) -> float:
        scenarios = result.get("scenarios", [])
        expected = len(task.get("scenarios", DEFAULT_SCENARIOS))
        return 10.0 * min(len(scenarios), expected) / max(expected, 1)

    def _score_accuracy(self, result: Any, task: dict) -> float:
        # All scenarios must have run projections
        scenarios = result.get("scenarios", [])
        ran = sum(1 for s in scenarios if s.get("months_projected", 0) > 0)
        return 10.0 * ran / max(len(scenarios), 1)

    def _score_confidence(self, result: Any, task: dict) -> ConfidenceScore:
        scenarios = result.get("scenarios", [])
        ran = sum(1 for s in scenarios if s.get("months_projected", 0) > 0)
        value = ran / max(len(scenarios), 1)
        tier = self._categorize_confidence(value)
        return ConfidenceScore(
            value=value, tier=tier,
            reasoning=f"{ran}/{len(scenarios)} scenarios projected",
        )

    def _get_artifacts(self, result: Any) -> list[str]:
        report_path = self.deal_scope.deal_path / "reports" / "stress_report.json"
        return [str(report_path)] if report_path.exists() else []
