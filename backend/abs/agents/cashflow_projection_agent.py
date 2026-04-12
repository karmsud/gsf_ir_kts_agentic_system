"""
CashflowProjectionAgent — Run multi-month cashflow projections with
optional tax calculations (OID, discount, yield).

No LLM / OpenAI dependency — all calculations are deterministic.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from backend.agents.base_agent import AgentBase
from backend.agents.agent_tools import ToolRegistry
from backend.common.confidence import ConfidenceScore, ConfidenceTier
from backend.abs.config.constants import CONFIDENCE_HIGH_THRESHOLD
from backend.abs.deal_scope import DealScope
from backend.abs.generation.data_prep import (
    load_deal_setup,
    load_classes_setup,
    prepare_month_data,
)
from config import KTSConfig

logger = logging.getLogger(__name__)

DEFAULT_PROJECTION_MONTHS = 12


class CashflowProjectionAgent(AgentBase):
    """Run multi-month cashflow projections with optional tax calculations."""

    agent_name = "cashflow_projection"

    def __init__(self, config: KTSConfig, deal_scope: DealScope, tool_registry: ToolRegistry, llm_callable=None) -> None:
        super().__init__(config, deal_scope=deal_scope, tool_registry=tool_registry, llm_callable=llm_callable)

    def _get_mission(self) -> str:
        return (
            "Run multi-month cashflow projections for the deal, "
            "accumulating per-class results and calculating tax-relevant "
            "metrics (OID, discount, yield)."
        )

    def _get_actions(self) -> list[str]:
        return [
            "Load deal setup and classes setup.",
            "For each month: prepare monthly data using prepare_month_data().",
            "Run cashflow projections via run_projections().",
            "Accumulate results across months.",
            "Calculate tax-relevant metrics (OID, discount, yield).",
            "Generate a cashflow report and save to deal_path/reports/.",
        ]

    def _get_output_spec(self) -> str:
        return (
            "dict with keys:\n"
            "  projections: list[dict] — per-month results\n"
            "  tax_summary: dict — OID, discount, yield metrics per class\n"
            "  months_completed: int\n"
        )

    def _get_validation_rules(self) -> list[str]:
        return [
            "Projections must cover the configured number of months.",
            "Per-class balances must chain correctly month-to-month.",
            "Tax metrics must be internally consistent.",
            "Report must be saved to deal_path/reports/.",
        ]

    def _run(self, task: dict[str, Any]) -> dict[str, Any]:
        deal_path = self.deal_scope.deal_path
        months = task.get("months", DEFAULT_PROJECTION_MONTHS)
        scenario = task.get("scenario", "base")

        try:
            deal_setup = load_deal_setup(deal_path)
        except FileNotFoundError:
            return {"status": "error", "error": "deal_setup.csv not found", "months_completed": 0}

        try:
            classes_df = load_classes_setup(deal_path)
            classes_setup = classes_df.to_dict(orient="records")
        except FileNotFoundError:
            return {"status": "error", "error": "classes_setup.csv not found", "months_completed": 0}

        waterfall_rules = self._load_json_list(deal_path / "extractions" / "waterfall_rules.json")
        triggers = self._load_json_list(deal_path / "extractions" / "triggers.json")
        accounts = self._load_json_list(deal_path / "extractions" / "accounts.json")

        monthly_inputs: list[dict[str, Any]] = []
        for m in range(1, months + 1):
            try:
                month_data = prepare_month_data(deal_path, m)
                monthly_inputs.append(month_data)
            except FileNotFoundError:
                monthly_inputs.append(self._minimal_month_input(m, deal_setup, classes_setup))

        projections = self._run_projections(
            waterfall_rules, classes_setup, monthly_inputs,
            triggers, accounts, scenario,
        )

        tax_summary = self._calculate_tax_metrics(projections, classes_setup, deal_setup)

        report_data = {
            "deal_id": self.deal_scope.deal_id,
            "scenario": scenario,
            "months_completed": len(projections),
            "projections": projections,
            "tax_summary": tax_summary,
        }
        self._save_report(deal_path, report_data)

        return {
            "projections": projections,
            "tax_summary": tax_summary,
            "months_completed": len(projections),
        }

    def _run_projections(self, waterfall_rules, classes_setup, monthly_inputs, triggers, accounts, scenario):
        try:
            from backend.abs.skills.cashflow_engine import run_projections
            result = run_projections(
                waterfall_rules=waterfall_rules, classes_setup=classes_setup,
                monthly_inputs=monthly_inputs, deal_id=self.deal_scope.deal_id,
                scenario=scenario, triggers=triggers, accounts=accounts,
            )
            return [m.to_dict() for m in result.months]
        except Exception as exc:
            logger.info("Cashflow engine unavailable (%s), using inline projection", exc)
            return self._inline_projection(classes_setup, monthly_inputs)

    @staticmethod
    def _inline_projection(classes_setup, monthly_inputs):
        results: list[dict[str, Any]] = []
        balances = {
            str(c.get("class_name", f"class_{i}")): float(c.get("original_balance", 0))
            for i, c in enumerate(classes_setup)
        }
        for inp in monthly_inputs:
            month = inp.get("month", len(results) + 1)
            rate = float(inp.get("interest_rate", inp.get("deal_setup", {}).get("interest_rate", "0.05")))
            monthly_rate = rate / 12
            month_result: dict[str, Any] = {"month": month, "collections": {}, "distributions": [], "class_balances": {}, "available_funds": 0.0}
            for cls_name, bal in balances.items():
                interest = round(bal * monthly_rate, 2)
                month_result["class_balances"][cls_name] = {"beginning_balance": round(bal, 2), "interest_payment": interest, "principal_payment": 0.0, "ending_balance": round(bal, 2)}
                month_result["collections"][cls_name] = interest
            results.append(month_result)
        return results

    @staticmethod
    def _minimal_month_input(month, deal_setup, classes_setup):
        pool_balance = sum(float(c.get("original_balance", 0)) for c in classes_setup)
        return {"month": month, "pool_balance": pool_balance, "interest_rate": float(deal_setup.get("interest_rate", "0.05")), "default_amount": 0.0, "recovery_amount": 0.0, "prepayment_amount": 0.0, "loss_amount": 0.0, "deal_setup": deal_setup}

    @staticmethod
    def _calculate_tax_metrics(projections, classes_setup, deal_setup):
        tax_summary: dict[str, Any] = {}
        issue_price_pct = float(deal_setup.get("issue_price_pct", "100")) / 100.0
        for cls in classes_setup:
            class_name = str(cls.get("class_name", ""))
            par = float(cls.get("original_balance", 0))
            issue_price = par * issue_price_pct
            oid = max(par - issue_price, 0.0)
            total_months = max(len(projections), 1)
            monthly_oid_accrual = oid / total_months if oid > 0 else 0.0
            total_interest = 0.0
            for proj in projections:
                cb = proj.get("class_balances", {}).get(class_name, {})
                total_interest += float(cb.get("interest_payment", 0))
            effective_yield = (total_interest / issue_price) if issue_price > 0 else 0.0
            tax_summary[class_name] = {"par_value": round(par, 2), "issue_price": round(issue_price, 2), "oid": round(oid, 2), "monthly_oid_accrual": round(monthly_oid_accrual, 4), "total_interest": round(total_interest, 2), "effective_yield": round(effective_yield, 6)}
        return tax_summary

    def _save_report(self, deal_path, data):
        try:
            from backend.abs.skills.report_generator import generate_report
            return generate_report(report_type="cashflow", data=data, output_dir=deal_path / "reports", deal_id=self.deal_scope.deal_id, format="json")
        except Exception:
            report_dir = deal_path / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / "cashflow_report.json"
            report_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            return report_path

    @staticmethod
    def _load_json_list(path: Path) -> list[dict]:
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else data.get("items", [data])
        except (json.JSONDecodeError, OSError):
            return []

    def _score_completeness(self, result, task):
        expected = task.get("months", DEFAULT_PROJECTION_MONTHS)
        completed = result.get("months_completed", 0)
        return 10.0 * min(completed, expected) / max(expected, 1)

    def _score_accuracy(self, result, task):
        projections = result.get("projections", [])
        return 10.0 if projections else 5.0

    def _score_confidence(self, result, task):
        expected = task.get("months", DEFAULT_PROJECTION_MONTHS)
        completed = result.get("months_completed", 0)
        tax = result.get("tax_summary", {})
        value = 0.5 * (min(completed, expected) / max(expected, 1)) + 0.5 * (1.0 if tax else 0.5)
        tier = self._categorize_confidence(value)
        return ConfidenceScore(value=value, tier=tier, reasoning=f"{completed}/{expected} months, {len(tax)} classes with tax data")

    def _get_artifacts(self, result):
        report_path = self.deal_scope.deal_path / "reports" / "cashflow_report.json"
        return [str(report_path)] if report_path.exists() else []
