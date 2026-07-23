"""
AssumptionsService — Layer B.4: CPR/CDR scenario library.

Manages the versioned assumption sets that drive projection and stress tests.
Each scenario is a named collection of typed assumptions (CPR rate, CDR rate,
severity, recovery lag, prepayment timing, discount rate, index curves). Every
assumption set is versioned and linked to projection outputs so any result can
be traced back to exactly the assumptions that produced it. Stateless + async.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from backend.abs.services.base import ABSService, ServiceContext, ServiceResult


_DEFAULT_SCENARIOS: dict[str, list[dict[str, Any]]] = {
    "base": [
        {"assumption_type": "cpr", "value": {"rate": 0.20, "description": "20% base CPR"}},
        {"assumption_type": "cdr", "value": {"rate": 0.01, "description": "1% base CDR"}},
        {"assumption_type": "severity", "value": {"rate": 0.40, "description": "40% loss severity"}},
        {"assumption_type": "recovery_lag", "value": {"months": 12, "description": "12-month recovery lag"}},
    ],
    "stress_high_cdr": [
        {"assumption_type": "cpr", "value": {"rate": 0.10, "description": "10% stressed CPR"}},
        {"assumption_type": "cdr", "value": {"rate": 0.05, "description": "5% stressed CDR"}},
        {"assumption_type": "severity", "value": {"rate": 0.60, "description": "60% stressed severity"}},
        {"assumption_type": "recovery_lag", "value": {"months": 18, "description": "18-month lag"}},
    ],
    "stress_high_prepay": [
        {"assumption_type": "cpr", "value": {"rate": 0.40, "description": "40% high prepay CPR"}},
        {"assumption_type": "cdr", "value": {"rate": 0.01, "description": "1% base CDR"}},
        {"assumption_type": "severity", "value": {"rate": 0.30, "description": "30% severity"}},
        {"assumption_type": "recovery_lag", "value": {"months": 12, "description": "12-month lag"}},
    ],
}


class AssumptionsService(ABSService):
    """Manage CPR/CDR scenario library for projections and stress tests."""

    name = "assumptions"

    def __init__(self, deals_root: Path) -> None:
        self.deals_root = Path(deals_root)

    def context(self, deal_id: str) -> ServiceContext:
        return ServiceContext(deal_id=deal_id, deals_root=self.deals_root)

    # ------------------------------------------------------------------
    # Seed default scenarios
    # ------------------------------------------------------------------
    async def seed_defaults(self, deal_id: str, *, actor: str = "system") -> ServiceResult:
        def _work() -> dict[str, Any]:
            store = self.context(deal_id).store()
            if store.list_scenarios(deal_id):
                return {"seeded": 0, "note": "Scenarios already exist"}
            count = 0
            for scenario_name, assumptions in _DEFAULT_SCENARIOS.items():
                for a in assumptions:
                    store.add_assumption({
                        "deal_id": deal_id, "scenario_name": scenario_name,
                        "assumption_type": a["assumption_type"], "value": a["value"],
                        "actor": actor,
                    })
                    count += 1
            return {"seeded": count, "scenarios": list(_DEFAULT_SCENARIOS.keys())}
        return await self.guard(self._to_thread(_work))

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    async def add(self, deal_id: str, *, scenario_name: str, assumption_type: str,
                  value: Any, actor: str = "user") -> ServiceResult:
        def _work() -> dict[str, Any]:
            store = self.context(deal_id).store(init=False)
            aid = store.add_assumption({"deal_id": deal_id, "scenario_name": scenario_name,
                                        "assumption_type": assumption_type, "value": value, "actor": actor})
            store.audit("add_assumption", actor=actor, object_type="assumption", object_id=aid,
                        after={"scenario": scenario_name, "type": assumption_type})
            return {"assumption_id": aid}
        return await self.guard(self._to_thread(_work))

    async def list(self, deal_id: str, scenario_name: Optional[str] = None) -> ServiceResult:
        store = self.context(deal_id).store(init=False)
        return await self.guard(self._to_thread(store.list_assumptions, deal_id, scenario_name))

    async def list_scenarios(self, deal_id: str) -> ServiceResult:
        store = self.context(deal_id).store(init=False)
        return await self.guard(self._to_thread(store.list_scenarios, deal_id))

    async def get_scenario(self, deal_id: str, scenario_name: str) -> dict[str, Any]:
        """Return a flat dict of {assumption_type: value} for use in run_projections."""
        import json as _json
        assumptions = (await self.list(deal_id, scenario_name)).data or []
        result: dict[str, Any] = {}
        for a in assumptions:
            try:
                v = _json.loads(a["value"]) if isinstance(a["value"], str) else a["value"]
            except Exception:
                v = a["value"]
            result[a["assumption_type"]] = v
        return result
