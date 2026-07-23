"""
ProjectionService — Layer A.5: scenario projections + stress testing.

Drives the deterministic cashflow engine across multiple CPR/CDR assumption
scenarios, storing class-level results per scenario. Results feed:
- The scenario comparison UI (class curves, waterfall per scenario)
- Stress testing (which scenarios breach triggers)
- Regression baseline capture (pin a "known good" output and alert on drift)

Also provides run_details (per-class waterfall trace) for the monthly run
results detail view. Stateless + async.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from backend.abs.services.base import ABSService, ProgressFn, ServiceContext, ServiceResult
from backend.abs.services.json_utils import parse_json_lenient
from backend.abs.services.model_run_service import _parse_amount, _parse_rate
from backend.abs.store import DealStore


_DEFAULT_MONTHS = 12


class ProjectionService(ABSService):
    """Run multi-scenario cashflow projections and capture regression baselines."""

    name = "projection"

    def __init__(self, deals_root: Path) -> None:
        self.deals_root = Path(deals_root)

    def context(self, deal_id: str) -> ServiceContext:
        return ServiceContext(deal_id=deal_id, deals_root=self.deals_root)

    # ------------------------------------------------------------------
    # Run projections (one or more scenarios)
    # ------------------------------------------------------------------
    async def run(
        self,
        deal_id: str,
        *,
        scenarios: Optional[list[str]] = None,
        months: int = _DEFAULT_MONTHS,
        actor: str = "system",
        progress: Optional[ProgressFn] = None,
    ) -> ServiceResult:
        return await self.guard(self._run(deal_id, scenarios, months, actor, progress))

    async def _run(
        self, deal_id: str, scenarios: Optional[list[str]], months: int, actor: str, progress: Optional[ProgressFn]
    ) -> dict[str, Any]:
        from backend.abs.services.assumptions_service import AssumptionsService
        assum_svc = AssumptionsService(self.deals_root)

        available_scenarios = (await assum_svc.list_scenarios(deal_id)).data or []
        if not available_scenarios:
            # Auto-seed default scenarios if none exist
            await assum_svc.seed_defaults(deal_id, actor=actor)
            available_scenarios = ["base", "stress_high_cdr", "stress_high_prepay"]
        scenarios_to_run = scenarios or available_scenarios

        if progress:
            progress({"stage": "projection", "status": "in-progress", "scenarios": len(scenarios_to_run)})

        all_results: dict[str, Any] = {}
        for scenario_name in scenarios_to_run:
            overrides = await assum_svc.get_scenario(deal_id, scenario_name)
            result = await self._to_thread(self._run_scenario, deal_id, scenario_name, months, overrides, actor)
            all_results[scenario_name] = result
            if progress:
                progress({"stage": "projection", "status": "running", "scenario": scenario_name})

        if progress:
            progress({"stage": "projection", "status": "done", "scenarios_run": len(all_results)})
        return {"scenarios": all_results, "months": months, "total": len(all_results)}

    def _run_scenario(
        self, deal_id: str, scenario_name: str, months: int, overrides: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        from backend.abs.skills.cashflow_engine import run_projections

        store = self.context(deal_id).store(init=False)
        classes = self._classes_from_store(store, deal_id)
        if not classes:
            return {"status": "error", "error": "No certificate classes found", "months": []}

        rules = self._waterfall_from_store(store, deal_id, classes)
        monthly_inputs = self._synthetic_monthly_inputs(classes, months, overrides)
        projection = run_projections(
            waterfall_rules=rules, classes_setup=classes,
            monthly_inputs=monthly_inputs, deal_id=deal_id, scenario=scenario_name,
            scenario_overrides=overrides,
        )
        monthly_summary = [m.to_dict() for m in projection.months]

        # Persist as agent_result so the WebView can retrieve it
        store.add_agent_result(deal_id, f"projection:{scenario_name}",
                               {"months": months, "scenario": scenario_name, "overrides": overrides},
                               {"months_summary": monthly_summary, "summary": projection.summary})
        store.audit("run_projection", actor=actor, object_type="projection",
                    object_id=f"{deal_id}:{scenario_name}",
                    after={"months": len(monthly_summary), "scenario": scenario_name})
        return {"scenario": scenario_name, "months": monthly_summary, "summary": projection.summary}

    # ------------------------------------------------------------------
    # Regression baseline
    # ------------------------------------------------------------------
    async def save_baseline(self, deal_id: str, scenario_name: str = "base", *, actor: str = "user") -> ServiceResult:
        def _work() -> dict[str, Any]:
            store = self.context(deal_id).store(init=False)
            existing = store.get_latest_agent_result(deal_id, f"projection:{scenario_name}")
            if not existing:
                raise ValueError(f"No projection result for scenario '{scenario_name}'. Run projections first.")
            store.add_agent_result(deal_id, f"baseline:{scenario_name}", {}, json.loads(existing["result_json"] or "{}"))
            store.audit("save_baseline", actor=actor, object_type="projection", object_id=f"{deal_id}:{scenario_name}")
            return {"saved": True, "scenario": scenario_name}
        return await self.guard(self._to_thread(_work))

    async def compare_baseline(self, deal_id: str, scenario_name: str = "base") -> ServiceResult:
        def _work() -> dict[str, Any]:
            store = self.context(deal_id).store(init=False)
            current = store.get_latest_agent_result(deal_id, f"projection:{scenario_name}")
            baseline = store.get_latest_agent_result(deal_id, f"baseline:{scenario_name}")
            if not current or not baseline:
                return {"comparison": None, "message": "Need both a baseline and a current projection."}
            curr_data = json.loads(current["result_json"] or "{}")
            base_data = json.loads(baseline["result_json"] or "{}")
            diffs: list[dict[str, Any]] = []
            curr_months = curr_data.get("months_summary") or curr_data.get("months") or []
            base_months = base_data.get("months_summary") or base_data.get("months") or []
            for i, (cm, bm) in enumerate(zip(curr_months, base_months)):
                curr_remaining = float(cm.get("remaining_funds", 0) or 0)
                base_remaining = float(bm.get("remaining_funds", 0) or 0)
                if abs(curr_remaining - base_remaining) > 0.01:
                    diffs.append({"month": i + 1, "field": "remaining_funds",
                                   "baseline": base_remaining, "current": curr_remaining,
                                   "delta": curr_remaining - base_remaining})
            return {"diffs": diffs, "months_compared": min(len(curr_months), len(base_months)),
                    "has_drift": bool(diffs), "scenario": scenario_name}
        return await self.guard(self._to_thread(_work))

    async def get_results(self, deal_id: str, scenario_name: Optional[str] = None) -> ServiceResult:
        def _work() -> list[dict[str, Any]]:
            store = self.context(deal_id).store(init=False)
            if scenario_name:
                r = store.get_latest_agent_result(deal_id, f"projection:{scenario_name}")
                if r:
                    try:
                        r["result_parsed"] = json.loads(r["result_json"] or "{}")
                    except Exception:
                        pass
                return [r] if r else []
            results = store.list_agent_results(deal_id)
            proj = [r for r in results if r.get("agent_name", "").startswith("projection:")]
            for r in proj:
                try:
                    r["result_parsed"] = json.loads(r["result_json"] or "{}")
                except Exception:
                    pass
            return proj
        return await self.guard(self._to_thread(_work))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _classes_from_store(self, store: DealStore, deal_id: str) -> list[dict[str, Any]]:
        classes = []
        for art in store.list_sep_artifacts(deal_id, "certificates"):
            v = parse_json_lenient(art.get("value") or "") or {}
            if not isinstance(v, dict):
                continue
            name = v.get("class_name") or v.get("class")
            if not name:
                continue
            classes.append({"class_name": str(name),
                             "original_balance": _parse_amount(v.get("original_balance")),
                             "coupon_rate": _parse_rate(v.get("accrual_formula", v.get("certificate_rate")))})
        return classes

    def _waterfall_from_store(self, store: DealStore, deal_id: str, classes: list[dict]) -> list[dict]:
        rules = []
        for c in classes:
            rules.append({"step": f"int_{c['class_name']}", "target": c["class_name"], "amount_type": "interest"})
        for c in classes:
            rules.append({"step": f"prin_{c['class_name']}", "target": c["class_name"], "amount_type": "principal"})
        return rules

    def _synthetic_monthly_inputs(
        self, classes: list[dict], months: int, overrides: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Generate synthetic monthly cashflows from the assumption overrides."""
        total_balance = sum(c.get("original_balance", 0) for c in classes)
        cpr_val = overrides.get("cpr", {})
        cdr_val = overrides.get("cdr", {})
        severity_val = overrides.get("severity", {})
        cpr = float(cpr_val.get("rate", 0.20) if isinstance(cpr_val, dict) else cpr_val)
        cdr = float(cdr_val.get("rate", 0.01) if isinstance(cdr_val, dict) else cdr_val)
        severity = float(severity_val.get("rate", 0.40) if isinstance(severity_val, dict) else severity_val)
        avg_coupon = sum(c.get("coupon_rate", 0.05) for c in classes) / max(1, len(classes))
        inputs = []
        balance = total_balance
        for m in range(1, months + 1):
            scheduled_prin = balance * (1 / max(1, 360 - m))
            prepayments = balance * cpr / 12
            defaults = balance * cdr / 12
            losses = defaults * severity
            interest = balance * avg_coupon / 12
            balance = max(0, balance - scheduled_prin - prepayments - defaults)
            inputs.append({
                "month": m, "beginning_pool_balance": balance + scheduled_prin + prepayments + defaults,
                "scheduled_principal": scheduled_prin, "prepayments": prepayments,
                "realized_losses": losses, "recoveries": 0.0,
                "interest_collected": interest, "principal_collections": scheduled_prin + prepayments,
                "interest_collections": interest,
            })
        return inputs
