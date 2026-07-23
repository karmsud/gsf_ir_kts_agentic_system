"""
ModelRunService — execute the deal's cashflow model to produce real numbers.

Rather than executing LLM-generated Python (an unsafe arbitrary-code path), this
service drives the deterministic, tested ``run_projections`` engine using the
deal's approved structured artifacts (certificates → classes, waterfall rules,
accounts) plus monthly collateral inputs. The result is stored as a
``monthly_run`` whose class-level numbers feed the distribution-statement
report. Stateless + async.
"""

from __future__ import annotations

import csv as _csv
import re
from pathlib import Path
from typing import Any, Optional

from backend.abs.services.base import ABSService, ProgressFn, ServiceContext, ServiceResult
from backend.abs.services.json_utils import parse_json_lenient
from backend.abs.store import DealStore

_PCT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _parse_rate(value: Any) -> float:
    """Parse a coupon rate from text like '5.02956%' → 0.0502956."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    m = _PCT_RE.search(str(value))
    if m:
        return float(m.group(1)) / 100.0
    m = _NUM_RE.search(str(value))
    return float(m.group(0)) if m else 0.0


def _parse_amount(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace(",", "").replace("$", "")
    m = _NUM_RE.search(cleaned)
    return float(m.group(0)) if m else 0.0


class ProductionReadinessGate:
    """Check that monthly inputs meet quality standards before execution."""

    REQUIRED_FIELDS = {"interest_collections", "principal_collections"}

    def check(self, monthly_inputs: list[dict[str, Any]]) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        if not monthly_inputs:
            issues.append({"field": "*", "severity": "error", "message": "No monthly input rows provided"})
            return {"ready": False, "issues": issues}
        for i, row in enumerate(monthly_inputs):
            for field in self.REQUIRED_FIELDS:
                if row.get(field) is None:
                    issues.append({"row": i, "field": field, "severity": "warning",
                                   "message": f"Missing {field} in row {i}"})
            for field in ("interest_collections", "principal_collections", "realized_losses"):
                val = row.get(field)
                if val is not None:
                    try:
                        float(val)
                    except (TypeError, ValueError):
                        issues.append({"row": i, "field": field, "severity": "error",
                                       "message": f"Non-numeric value '{val}' in {field}"})
        errors = [x for x in issues if x["severity"] == "error"]
        return {"ready": len(errors) == 0, "issues": issues,
                "rows": len(monthly_inputs), "errors": len(errors), "warnings": len(issues) - len(errors)}


class ModelRunService(ABSService):
    """Run the cashflow model and persist class-level results."""

    name = "model_run"

    def __init__(self, deals_root: Path) -> None:
        self.deals_root = Path(deals_root)

    def context(self, deal_id: str) -> ServiceContext:
        return ServiceContext(deal_id=deal_id, deals_root=self.deals_root)

    async def check_readiness(
        self, monthly_inputs: list[dict[str, Any]] | None = None, csv_path: str | None = None
    ) -> ServiceResult:
        def _work():
            inputs = monthly_inputs
            if inputs is None and csv_path:
                inputs = self._load_monthly_csv(Path(csv_path))
            return ProductionReadinessGate().check(inputs or [])
        return await self.guard(self._to_thread(_work))

    async def run(
        self,
        deal_id: str,
        *,
        monthly_inputs: Optional[list[dict[str, Any]]] = None,
        csv_path: Optional[str] = None,
        classes_setup: Optional[list[dict[str, Any]]] = None,
        waterfall_rules: Optional[list[dict[str, Any]]] = None,
        run_date: str = "",
        scenario: str = "base",
        actor: str = "system",
        progress: Optional[ProgressFn] = None,
    ) -> ServiceResult:
        return await self.guard(
            self._run(deal_id, monthly_inputs, csv_path, classes_setup, waterfall_rules,
                      run_date, scenario, actor, progress)
        )

    async def _run(
        self,
        deal_id: str,
        monthly_inputs: Optional[list[dict[str, Any]]],
        csv_path: Optional[str],
        classes_setup: Optional[list[dict[str, Any]]],
        waterfall_rules: Optional[list[dict[str, Any]]],
        run_date: str,
        scenario: str,
        actor: str,
        progress: Optional[ProgressFn],
    ) -> dict[str, Any]:
        if progress:
            progress({"stage": "model_run", "status": "in-progress"})
        result = await self._to_thread(
            self._execute, deal_id, monthly_inputs, csv_path, classes_setup,
            waterfall_rules, run_date, scenario, actor,
        )
        if progress:
            progress({"stage": "model_run", "status": "done", "classes": len(result["results"])})
        return result

    # ------------------------------------------------------------------
    # Sync execution (off-thread)
    # ------------------------------------------------------------------
    def _execute(
        self,
        deal_id: str,
        monthly_inputs: Optional[list[dict[str, Any]]],
        csv_path: Optional[str],
        classes_setup: Optional[list[dict[str, Any]]],
        waterfall_rules: Optional[list[dict[str, Any]]],
        run_date: str,
        scenario: str,
        actor: str,
    ) -> dict[str, Any]:
        from backend.abs.skills.cashflow_engine import run_projections

        store = self.context(deal_id).store(init=False)

        if not monthly_inputs:
            if csv_path:
                monthly_inputs = self._load_monthly_csv(Path(csv_path))
            else:
                raise ValueError("Provide monthly_inputs or csv_path.")
        if not monthly_inputs:
            raise ValueError("No monthly inputs to run.")
        # Production readiness check
        gate = ProductionReadinessGate().check(monthly_inputs)
        if not gate["ready"]:
            raise ValueError(f"Production readiness failed: {gate['issues']}")

        classes = classes_setup or self._classes_from_artifacts(store, deal_id)
        if not classes:
            raise ValueError("No classes available (extract & approve Certificates SEP first).")
        rules = waterfall_rules or self._waterfall_from_artifacts(store, deal_id, classes)

        projection = run_projections(
            waterfall_rules=rules,
            classes_setup=classes,
            monthly_inputs=monthly_inputs,
            deal_id=deal_id,
            scenario=scenario,
        )

        # Attribute interest vs principal for the final month.
        results = self._extract_class_results(projection, rules)

        run_id = store.add_monthly_run({
            "deal_id": deal_id,
            "run_date": run_date or "",
            "results": results,
            "exceptions": projection.summary.get("errors", []) if isinstance(projection.summary, dict) else [],
        })
        # Persist per-class per-step waterfall trace for the detail view
        last_month = projection.months[-1] if projection.months else None
        if last_month:
            detail_rows = []
            for step_ord, dist in enumerate(last_month.distributions):
                target = dist.get("target") or ""
                amount = float(dist.get("amount", 0) or 0)
                bal_data = last_month.class_balances.get(target, {})
                detail_rows.append({
                    "class_name": target, "step_name": dist.get("step", ""),
                    "step_order": step_ord,
                    "interest": amount if "int_" in dist.get("step", "") else 0.0,
                    "principal": amount if "prin_" in dist.get("step", "") else 0.0,
                    "beginning_bal": float(bal_data.get("original_balance", 0) or 0),
                    "ending_bal": float(bal_data.get("current_balance", 0) or 0),
                })
            store.add_run_details(run_id, deal_id, detail_rows)
        store.audit("run_model", actor=actor, object_type="monthly_run", object_id=run_id,
                    after={"classes": len(results), "months": len(projection.months)})

        return {
            "run_id": run_id,
            "results": results,
            "total_months": len(projection.months),
            "summary": projection.summary,
        }

    def _extract_class_results(self, projection: Any, rules: list[dict[str, Any]]) -> dict[str, Any]:
        if not projection.months:
            return {}
        month = projection.months[-1]
        per_class: dict[str, dict[str, float]] = {}
        for dist, rule in zip(month.distributions, rules):
            target = dist.get("target")
            if not target:
                continue
            atype = rule.get("amount_type", "principal")
            bucket = "interest" if atype == "interest" else "principal"
            pc = per_class.setdefault(target, {"interest": 0.0, "principal": 0.0})
            pc[bucket] += float(dist.get("amount", 0) or 0)
        for cls, bal in month.class_balances.items():
            pc = per_class.setdefault(cls, {"interest": 0.0, "principal": 0.0})
            pc["beginning_balance"] = float(bal.get("original_balance", 0) or 0)
            pc["ending_balance"] = float(bal.get("current_balance", 0) or 0)
        return per_class

    def _classes_from_artifacts(self, store: DealStore, deal_id: str) -> list[dict[str, Any]]:
        classes: list[dict[str, Any]] = []
        for art in store.list_sep_artifacts(deal_id, "certificates"):
            v = parse_json_lenient(art.get("value") or "") or {}
            if not isinstance(v, dict):
                continue
            name = v.get("class_name") or v.get("class")
            if not name:
                continue
            classes.append({
                "class_name": str(name),
                "original_balance": _parse_amount(v.get("original_balance")),
                "coupon_rate": _parse_rate(v.get("accrual_formula", v.get("pass_through_rate", v.get("certificate_rate")))),
            })
        return classes

    def _waterfall_from_artifacts(
        self, store: DealStore, deal_id: str, classes: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        # Best-effort: a standard interest-then-principal waterfall by class order.
        rules: list[dict[str, Any]] = []
        for c in classes:
            rules.append({"step": f"int_{c['class_name']}", "target": c["class_name"], "amount_type": "interest"})
        for c in classes:
            rules.append({"step": f"prin_{c['class_name']}", "target": c["class_name"], "amount_type": "principal"})
        return rules

    @staticmethod
    def _load_monthly_csv(path: Path) -> list[dict[str, Any]]:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Monthly input CSV not found: {path}")
        rows: list[dict[str, Any]] = []
        with open(path, newline="", encoding="utf-8") as f:
            for row in _csv.DictReader(f):
                rows.append({k: (v if v == "" else _coerce(v)) for k, v in row.items()})
        return rows


def _coerce(value: str) -> Any:
    try:
        return float(value) if ("." in value or "e" in value.lower()) else int(value)
    except (ValueError, TypeError):
        return value
