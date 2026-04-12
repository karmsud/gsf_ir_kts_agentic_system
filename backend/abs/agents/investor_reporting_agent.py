"""
InvestorReportingAgent — Generate investor reports from model outputs.

Loads the latest model run, deal manifest, and cashflow projections,
then generates a formatted report covering deal summary, per-class
performance, payment waterfall summary, and trigger status.

No LLM / OpenAI dependency.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.agents.base_agent import AgentBase
from backend.agents.agent_tools import ToolRegistry
from backend.common.confidence import ConfidenceScore, ConfidenceTier
from backend.abs.deal_manifest import DealManifest
from backend.abs.deal_scope import DealScope
from config import KTSConfig

logger = logging.getLogger(__name__)


class InvestorReportingAgent(AgentBase):
    """
    Generate investor reports from model outputs and deal metadata.

    Report sections:
    1. **Deal Summary** — deal ID, closing date, pool balance, class count.
    2. **Per-Class Performance** — interest/principal payments, balances.
    3. **Payment Waterfall Summary** — flow of funds through the waterfall.
    4. **Trigger Status** — current status of all OC/IC and other triggers.
    """

    agent_name = "investor_reporting"

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
            "Generate investor reports from model outputs, including "
            "deal summary, per-class performance, payment waterfall summary, "
            "and trigger status."
        )

    def _get_actions(self) -> list[str]:
        return [
            "Load model output from the latest run.",
            "Load deal manifest for deal metadata.",
            "Build deal summary section.",
            "Build per-class performance section.",
            "Build payment waterfall summary section.",
            "Build trigger status section.",
            "Generate report.",
            "Save report to deal_path/reports/.",
        ]

    def _get_output_spec(self) -> str:
        return (
            "dict with keys:\n"
            "  report_path: str — path to generated report\n"
            "  sections_included: list[str]\n"
            "  coverage: dict — metrics on report completeness\n"
        )

    def _get_validation_rules(self) -> list[str]:
        return [
            "Report must include all four sections.",
            "Per-class data must cover all classes from classes_setup.",
            "Trigger section must reflect the latest projection state.",
            "Report must be saved to deal_path/reports/.",
        ]

    # ------------------------------------------------------------------
    # Core execution
    # ------------------------------------------------------------------

    def _run(self, task: dict[str, Any]) -> dict[str, Any]:
        deal_path = self.deal_scope.deal_path
        sections_included: list[str] = []

        model_outputs = self._load_latest_run(deal_path)
        manifest_data = self._load_manifest(deal_path)
        projections = self._load_projections(deal_path)

        report_data: dict[str, Any] = {
            "deal_id": self.deal_scope.deal_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        deal_summary = self._build_deal_summary(manifest_data, model_outputs)
        report_data["deal_summary"] = deal_summary
        sections_included.append("deal_summary")

        class_performance = self._build_class_performance(model_outputs, projections)
        report_data["class_performance"] = class_performance
        sections_included.append("class_performance")

        waterfall_summary = self._build_waterfall_summary(projections)
        report_data["waterfall_summary"] = waterfall_summary
        sections_included.append("waterfall_summary")

        trigger_status = self._build_trigger_status(projections)
        report_data["trigger_status"] = trigger_status
        sections_included.append("trigger_status")

        report_path = self._generate_report(deal_path, report_data)

        coverage = self._compute_coverage(
            class_performance, waterfall_summary, trigger_status,
        )

        return {
            "report_path": str(report_path),
            "sections_included": sections_included,
            "coverage": coverage,
        }

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    @staticmethod
    def _load_latest_run(deal_path: Path) -> dict[str, Any]:
        runs_dir = deal_path / "runs"
        if not runs_dir.exists():
            return {}
        month_dirs = sorted(
            [d for d in runs_dir.iterdir() if d.is_dir() and d.name.startswith("month_")],
            key=lambda d: int(d.name.split("_")[-1]) if d.name.split("_")[-1].isdigit() else 0,
        )
        if not month_dirs:
            return {}
        latest = month_dirs[-1]
        output_csv = latest / "output.csv"
        if not output_csv.exists():
            return {}
        import csv
        with open(output_csv, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        return {"month": latest.name, "rows": rows}

    @staticmethod
    def _load_manifest(deal_path: Path) -> dict[str, Any]:
        try:
            manifest = DealManifest.load(deal_path)
            return {
                "deal_id": getattr(manifest, "deal_id", ""),
                "issuer": getattr(manifest, "issuer", ""),
                "closing_date": getattr(manifest, "closing_date", ""),
                "documents": [
                    getattr(d, "filename", str(d))
                    for d in getattr(manifest, "documents", [])
                ],
            }
        except Exception:
            manifest_path = deal_path / "deal_manifest.json"
            if manifest_path.exists():
                return json.loads(manifest_path.read_text(encoding="utf-8"))
            return {}

    @staticmethod
    def _load_projections(deal_path: Path) -> list[dict[str, Any]]:
        report_dir = deal_path / "reports"
        for name in ("cashflow_report.json",):
            candidate = report_dir / name
            if candidate.exists():
                try:
                    data = json.loads(candidate.read_text(encoding="utf-8"))
                    return data.get("projections", [])
                except (json.JSONDecodeError, OSError):
                    pass
        if report_dir.exists():
            for f in sorted(report_dir.glob("cashflow_*.json")):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    return data.get("projections", [])
                except (json.JSONDecodeError, OSError):
                    pass
        return []

    # ------------------------------------------------------------------
    # Report section builders
    # ------------------------------------------------------------------

    def _build_deal_summary(
        self,
        manifest: dict[str, Any],
        model_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "deal_id": self.deal_scope.deal_id,
            "issuer": manifest.get("issuer", ""),
            "closing_date": manifest.get("closing_date", ""),
            "documents_count": len(manifest.get("documents", [])),
            "latest_run": model_outputs.get("month", ""),
            "rows_in_latest": len(model_outputs.get("rows", [])),
        }

    @staticmethod
    def _build_class_performance(
        model_outputs: dict[str, Any],
        projections: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        performance: dict[str, dict[str, Any]] = {}

        for row in model_outputs.get("rows", []):
            class_name = row.get("class_name", "")
            if class_name:
                performance[class_name] = {
                    "class_name": class_name,
                    "latest_payment": float(row.get("payment", row.get("total_payment", 0))),
                    "ending_balance": float(row.get("ending_balance", 0)),
                }

        if projections:
            latest_proj = projections[-1]
            class_balances = latest_proj.get("class_balances", {})
            for cls_name, data in class_balances.items():
                if cls_name not in performance:
                    performance[cls_name] = {"class_name": cls_name}
                if isinstance(data, dict):
                    performance[cls_name].update({
                        "interest_payment": data.get("interest_payment", 0),
                        "principal_payment": data.get("principal_payment", 0),
                        "ending_balance": data.get("ending_balance", 0),
                    })

        return list(performance.values())

    @staticmethod
    def _build_waterfall_summary(
        projections: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not projections:
            return {"months": 0, "total_distributions": 0.0}

        total_distributions = 0.0
        for proj in projections:
            distributions = proj.get("distributions", [])
            for dist in distributions:
                total_distributions += float(dist.get("amount", 0))

        return {
            "months": len(projections),
            "total_distributions": round(total_distributions, 2),
            "first_month": projections[0].get("month", 1),
            "last_month": projections[-1].get("month", len(projections)),
        }

    @staticmethod
    def _build_trigger_status(
        projections: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not projections:
            return {"triggers": {}, "any_breached": False}

        latest = projections[-1]
        trigger_states = latest.get("trigger_states", {})
        any_breached = any(trigger_states.values()) if trigger_states else False

        return {
            "triggers": trigger_states,
            "any_breached": any_breached,
            "as_of_month": latest.get("month", len(projections)),
        }

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    def _generate_report(
        self,
        deal_path: Path,
        data: dict[str, Any],
    ) -> Path:
        try:
            from backend.abs.skills.report_generator import generate_report
            return generate_report(
                report_type="cashflow",
                data=data,
                output_dir=deal_path / "reports",
                deal_id=self.deal_scope.deal_id,
            )
        except Exception as exc:
            logger.info("report_generator unavailable (%s), saving directly", exc)
            report_dir = deal_path / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / "investor_report.json"
            report_path.write_text(
                json.dumps(data, indent=2, default=str), encoding="utf-8",
            )
            return report_path

    @staticmethod
    def _compute_coverage(
        class_performance: list[dict],
        waterfall_summary: dict,
        trigger_status: dict,
    ) -> dict[str, Any]:
        return {
            "classes_covered": len(class_performance),
            "waterfall_months": waterfall_summary.get("months", 0),
            "triggers_tracked": len(trigger_status.get("triggers", {})),
            "sections_complete": sum([
                len(class_performance) > 0,
                waterfall_summary.get("months", 0) > 0,
                len(trigger_status.get("triggers", {})) > 0,
            ]),
        }

    # ------------------------------------------------------------------
    # Quality scoring overrides
    # ------------------------------------------------------------------

    def _score_completeness(self, result: Any, task: dict) -> float:
        sections = result.get("sections_included", [])
        required = {"deal_summary", "class_performance", "waterfall_summary", "trigger_status"}
        present = required & set(sections)
        return 10.0 * len(present) / len(required)

    def _score_accuracy(self, result: Any, task: dict) -> float:
        coverage = result.get("coverage", {})
        return 10.0 if coverage.get("classes_covered", 0) > 0 else 6.0

    def _score_confidence(self, result: Any, task: dict) -> ConfidenceScore:
        coverage = result.get("coverage", {})
        complete = coverage.get("sections_complete", 0)
        value = complete / 3
        tier = self._categorize_confidence(value)
        return ConfidenceScore(
            value=value, tier=tier,
            reasoning=f"{complete}/3 data sections populated",
        )

    def _get_artifacts(self, result: Any) -> list[str]:
        report_path = result.get("report_path", "")
        return [report_path] if report_path else []
