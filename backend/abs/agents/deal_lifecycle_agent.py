"""
DealLifecycleAgent — Monitor deal health, check triggers, and alert
on anomalies.

Loads the latest cashflow projections, evaluates trigger conditions
(overcollateralisation, delinquency thresholds), compares to deal
covenants from governing docs, and generates alerts for any breaches.

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
from backend.abs.deal_scope import DealScope
from config import KTSConfig

logger = logging.getLogger(__name__)


class DealLifecycleAgent(AgentBase):
    """
    Monitor deal health by checking trigger conditions and comparing
    performance to deal covenants.

    Workflow:
    1. Load the latest cashflow projections.
    2. Load trigger definitions and covenants from extractions.
    3. Evaluate each trigger against current data.
    4. Generate alerts for breaches or near-breaches.
    5. Compute an overall health score (0.0-1.0).
    """

    PROXIMITY_WARNING_PCT = 0.10

    agent_name = "deal_lifecycle"

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
            "Monitor deal health by checking trigger conditions, comparing "
            "performance to deal covenants, and generating alerts for any "
            "breaches or anomalies."
        )

    def _get_actions(self) -> list[str]:
        return [
            "Load the latest cashflow projections.",
            "Load trigger definitions from extractions.",
            "Load deal covenants from governing docs / extractions.",
            "Evaluate each trigger against current data.",
            "Generate alerts for breaches and near-breaches.",
            "Compute an overall deal health score.",
        ]

    def _get_output_spec(self) -> str:
        return (
            "dict with keys:\n"
            "  alerts: list[dict] — {type, trigger, message, severity}\n"
            "  trigger_status: dict[trigger_name, dict]\n"
            "  health_score: float (0.0 – 1.0)\n"
        )

    def _get_validation_rules(self) -> list[str]:
        return [
            "All known triggers must be evaluated.",
            "Alerts must have severity (critical/warning/info).",
            "Health score must reflect the number and severity of breaches.",
            "Report must be saved to deal_path/reports/.",
        ]

    # ------------------------------------------------------------------
    # Core execution
    # ------------------------------------------------------------------

    def _run(self, task: dict[str, Any]) -> dict[str, Any]:
        deal_path = self.deal_scope.deal_path

        # 1. Load latest projections
        projections = self._load_projections(deal_path)

        # 2. Load triggers and covenants
        triggers = self._load_json_list(deal_path / "extractions" / "triggers.json")
        covenants = self._load_covenants(deal_path)

        # 3. Get latest month data
        latest_month = projections[-1] if projections else {}

        # 4. Evaluate triggers
        trigger_status: dict[str, dict[str, Any]] = {}
        alerts: list[dict[str, Any]] = []

        for trig in triggers:
            name = trig.get("name", trig.get("id", ""))
            if not name:
                continue
            status = self._evaluate_trigger(trig, latest_month, covenants)
            trigger_status[name] = status
            if status.get("breached"):
                alerts.append({
                    "type": "trigger_breach",
                    "trigger": name,
                    "message": f"Trigger '{name}' has been breached: {status.get('detail', '')}",
                    "severity": "critical",
                })
            elif status.get("near_breach"):
                alerts.append({
                    "type": "trigger_warning",
                    "trigger": name,
                    "message": f"Trigger '{name}' is within {self.PROXIMITY_WARNING_PCT*100:.0f}% of breach threshold",
                    "severity": "warning",
                })

        # 5. Check for additional anomalies
        anomaly_alerts = self._check_anomalies(projections)
        alerts.extend(anomaly_alerts)

        # 6. Compute health score
        health_score = self._compute_health_score(trigger_status, alerts)

        # 7. Persist report
        report = {
            "deal_id": self.deal_scope.deal_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alerts": alerts,
            "trigger_status": trigger_status,
            "health_score": round(health_score, 4),
        }
        report_dir = deal_path / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "lifecycle_report.json"
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        logger.info("Lifecycle report saved to %s", report_path)

        return {
            "alerts": alerts,
            "trigger_status": trigger_status,
            "health_score": round(health_score, 4),
        }

    # ------------------------------------------------------------------
    # Trigger evaluation
    # ------------------------------------------------------------------

    def _evaluate_trigger(
        self,
        trigger: dict[str, Any],
        month_data: dict[str, Any],
        covenants: dict[str, Any],
    ) -> dict[str, Any]:
        name = trigger.get("name", trigger.get("id", ""))
        threshold = trigger.get("threshold")
        metric = trigger.get("metric", "")
        direction = trigger.get("direction", "below")

        status: dict[str, Any] = {
            "name": name,
            "breached": False,
            "near_breach": False,
            "current_value": None,
            "threshold": threshold,
            "detail": "",
        }

        if threshold is None:
            trigger_states = month_data.get("trigger_states", {})
            if trigger_states.get(name):
                status["breached"] = True
                status["detail"] = "Breached per projection engine"
            return status

        threshold_val = float(threshold)
        current_val = self._get_metric_value(metric, month_data, covenants)

        if current_val is None:
            status["detail"] = f"Metric '{metric}' not found in data"
            return status

        status["current_value"] = current_val

        if direction == "below":
            status["breached"] = current_val < threshold_val
            proximity = threshold_val * (1 + self.PROXIMITY_WARNING_PCT)
            status["near_breach"] = not status["breached"] and current_val < proximity
        else:
            status["breached"] = current_val > threshold_val
            proximity = threshold_val * (1 - self.PROXIMITY_WARNING_PCT)
            status["near_breach"] = not status["breached"] and current_val > proximity

        if status["breached"]:
            status["detail"] = (
                f"{metric}={current_val:.4f} vs threshold={threshold_val:.4f} "
                f"(direction={direction})"
            )

        return status

    @staticmethod
    def _get_metric_value(
        metric: str,
        month_data: dict[str, Any],
        covenants: dict[str, Any],
    ) -> float | None:
        if not metric:
            return None

        if metric in month_data:
            try:
                return float(month_data[metric])
            except (ValueError, TypeError):
                pass

        collections = month_data.get("collections", {})
        if metric in collections:
            try:
                return float(collections[metric])
            except (ValueError, TypeError):
                pass

        class_balances = month_data.get("class_balances", {})
        if isinstance(class_balances, dict):
            for cls_data in class_balances.values():
                if isinstance(cls_data, dict) and metric in cls_data:
                    try:
                        return float(cls_data[metric])
                    except (ValueError, TypeError):
                        pass

        return None

    # ------------------------------------------------------------------
    # Anomaly detection
    # ------------------------------------------------------------------

    @staticmethod
    def _check_anomalies(
        projections: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        if len(projections) < 2:
            return alerts

        for i in range(1, len(projections)):
            prev_balances = projections[i - 1].get("class_balances", {})
            curr_balances = projections[i].get("class_balances", {})
            month = projections[i].get("month", i + 1)

            for cls_name, prev_data in prev_balances.items():
                if not isinstance(prev_data, dict):
                    continue
                curr_data = curr_balances.get(cls_name, {})
                if not isinstance(curr_data, dict):
                    continue

                prev_bal = float(prev_data.get("ending_balance", prev_data.get("beginning_balance", 0)))
                curr_bal = float(curr_data.get("ending_balance", curr_data.get("beginning_balance", 0)))

                if prev_bal > 0 and curr_bal < prev_bal * 0.5:
                    alerts.append({
                        "type": "anomaly",
                        "trigger": f"{cls_name}_balance_drop",
                        "message": (
                            f"Class {cls_name} balance dropped >50% "
                            f"in month {month}: {prev_bal:.2f} -> {curr_bal:.2f}"
                        ),
                        "severity": "warning",
                    })

        return alerts

    # ------------------------------------------------------------------
    # Health score
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_health_score(
        trigger_status: dict[str, dict[str, Any]],
        alerts: list[dict[str, Any]],
    ) -> float:
        if not trigger_status and not alerts:
            return 1.0

        breached = sum(1 for s in trigger_status.values() if s.get("breached"))
        near_breach = sum(1 for s in trigger_status.values() if s.get("near_breach"))
        critical_alerts = sum(1 for a in alerts if a.get("severity") == "critical")
        warning_alerts = sum(1 for a in alerts if a.get("severity") == "warning")

        score = 1.0
        score -= 0.20 * breached
        score -= 0.05 * near_breach
        score -= 0.10 * critical_alerts
        score -= 0.02 * warning_alerts

        return max(0.0, min(1.0, score))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_projections(deal_path: Path) -> list[dict[str, Any]]:
        report_dir = deal_path / "reports"
        if report_dir.exists():
            for f in sorted(report_dir.glob("cashflow_*.json"), reverse=True):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    return data.get("projections", [])
                except (json.JSONDecodeError, OSError):
                    pass
            flat = report_dir / "cashflow_report.json"
            if flat.exists():
                try:
                    data = json.loads(flat.read_text(encoding="utf-8"))
                    return data.get("projections", [])
                except (json.JSONDecodeError, OSError):
                    pass
        return []

    def _load_covenants(self, deal_path: Path) -> dict[str, Any]:
        for candidate in (
            deal_path / "extractions" / "covenants.json",
            deal_path / "governing_docs" / "covenants.json",
        ):
            if candidate.exists():
                try:
                    return json.loads(candidate.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    pass
        return {}

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
        has_alerts = "alerts" in result
        has_triggers = bool(result.get("trigger_status"))
        has_health = "health_score" in result
        return 10.0 * sum([has_alerts, has_triggers, has_health]) / 3

    def _score_accuracy(self, result: Any, task: dict) -> float:
        trigger_status = result.get("trigger_status", {})
        if not trigger_status:
            return 8.0
        evaluated = sum(1 for s in trigger_status.values() if s.get("current_value") is not None or s.get("breached") is not None)
        return 10.0 * evaluated / max(len(trigger_status), 1)

    def _score_confidence(self, result: Any, task: dict) -> ConfidenceScore:
        health = result.get("health_score", 0.5)
        trigger_status = result.get("trigger_status", {})
        evaluated = sum(1 for s in trigger_status.values() if s.get("current_value") is not None)
        total = max(len(trigger_status), 1)
        value = evaluated / total
        tier = self._categorize_confidence(value)
        return ConfidenceScore(
            value=value, tier=tier,
            reasoning=f"{evaluated}/{total} triggers evaluated, health={health:.2f}",
        )

    def _get_artifacts(self, result: Any) -> list[str]:
        report_path = self.deal_scope.deal_path / "reports" / "lifecycle_report.json"
        return [str(report_path)] if report_path.exists() else []
