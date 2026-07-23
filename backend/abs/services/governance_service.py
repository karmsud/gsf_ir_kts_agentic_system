"""
GovernanceService — Layer B controls.

Bundles three cross-cutting governance capabilities over the SQLite store:

* **AI exception / learning loop** — capture human corrections as governed
  ``correction_events`` with root cause + severity for later review.
* **AI cost management** — record and summarise LLM token usage per deal/command.
* **Deal-level RBAC** — grant roles and check permissions for sensitive actions.

Stateless + async.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from backend.abs.services.base import ABSService, ServiceContext, ServiceResult

# role → permitted actions. "viewer" can only read.
_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"view", "run", "regenerate", "override", "approve", "publish", "grant"},
    "approver": {"view", "run", "regenerate", "override", "approve", "publish"},
    "reviewer": {"view", "run", "regenerate", "override"},
    "viewer": {"view"},
}


class GovernanceService(ABSService):
    """AI exception loop, cost tracking, and RBAC."""

    name = "governance"

    def __init__(self, deals_root: Path) -> None:
        self.deals_root = Path(deals_root)

    def context(self, deal_id: str) -> ServiceContext:
        return ServiceContext(deal_id=deal_id, deals_root=self.deals_root)

    # ------------------------------------------------------------------
    # AI exception / learning loop
    # ------------------------------------------------------------------
    async def log_correction(
        self,
        deal_id: str,
        *,
        object_type: str = "",
        object_id: str = "",
        lifecycle_stage: str = "",
        original_value: Any = None,
        corrected_value: Any = None,
        root_cause: str = "",
        severity: str = "medium",
        actor: str = "user",
    ) -> ServiceResult:
        def _work() -> dict[str, Any]:
            store = self.context(deal_id).store(init=False)
            event_id = store.add_correction_event({
                "deal_id": deal_id, "object_type": object_type, "object_id": object_id,
                "lifecycle_stage": lifecycle_stage, "original_value": original_value,
                "corrected_value": corrected_value, "root_cause": root_cause,
                "severity": severity, "actor": actor,
            })
            store.audit("log_correction", actor=actor, object_type=object_type, object_id=object_id,
                        after={"event_id": event_id, "root_cause": root_cause, "severity": severity})
            return {"event_id": event_id}

        return await self.guard(self._to_thread(_work))

    async def list_corrections(self, deal_id: str) -> ServiceResult:
        store = self.context(deal_id).store(init=False)
        return await self.guard(self._to_thread(store.list_correction_events, deal_id))

    # ------------------------------------------------------------------
    # AI cost management
    # ------------------------------------------------------------------
    async def record_cost(
        self, deal_id: str, *, command: str, model: str, input_tokens: int, output_tokens: int
    ) -> ServiceResult:
        def _work() -> dict[str, Any]:
            store = self.context(deal_id).store(init=False)
            store.record_llm_cost(deal_id=deal_id, command=command, model=model,
                                  input_tokens=input_tokens, output_tokens=output_tokens)
            return {"recorded": True}

        return await self.guard(self._to_thread(_work))

    async def cost_summary(self, deal_id: str) -> ServiceResult:
        store = self.context(deal_id).store(init=False)
        return await self.guard(self._to_thread(store.cost_summary, deal_id))

    # ------------------------------------------------------------------
    # RBAC
    # ------------------------------------------------------------------
    async def grant(self, deal_id: str, *, actor: str, role: str, by: str = "admin") -> ServiceResult:
        if role not in _ROLE_PERMISSIONS:
            return ServiceResult.failure(f"Unknown role: {role}. Known: {list(_ROLE_PERMISSIONS)}")

        def _work() -> dict[str, Any]:
            store = self.context(deal_id).store(init=False)
            store.set_entitlement(actor, deal_id, role)
            store.audit("grant_role", actor=by, object_type="entitlement", object_id=actor,
                        after={"role": role})
            return {"actor": actor, "role": role}

        return await self.guard(self._to_thread(_work))

    async def check(self, deal_id: str, *, actor: str, permission: str) -> ServiceResult:
        def _work() -> dict[str, Any]:
            store = self.context(deal_id).store(init=False)
            role = store.get_role(actor, deal_id)
            allowed = self.is_allowed(store, deal_id, actor, permission)
            return {"actor": actor, "role": role, "permission": permission, "allowed": allowed}

        return await self.guard(self._to_thread(_work))

    @staticmethod
    def is_allowed(store: Any, deal_id: str, actor: str, permission: str) -> bool:
        """Permission check with open-mode default.

        If no entitlements are configured for the deal at all, the deal runs in
        open mode (single-user local) and everything is allowed. Once any
        entitlement exists, access is enforced by role.
        """
        role = store.get_role(actor, deal_id)
        if role is not None:
            return permission in _ROLE_PERMISSIONS.get(role, set())
        # No explicit role for this actor — open mode unless the deal is locked down.
        return not _deal_has_entitlements(store, deal_id)


def _deal_has_entitlements(store: Any, deal_id: str) -> bool:
    with store._connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM entitlements WHERE deal_id=?", (deal_id,)
        ).fetchone()
        return bool(row and int(row["n"]) > 0)
