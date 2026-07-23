"""
DealService — deal lifecycle (create / list / status).

Creates the on-disk "Deal folder" (via :class:`DealScope`), initialises the
per-deal SQLite store, and reports aggregate status for dashboards. Stateless
and async like all ABS services.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from backend.abs.services.base import ABSService, ServiceContext, ServiceResult
from backend.abs.store import DealStore


class DealService(ABSService):
    """Manage deal folders and report their status."""

    name = "deal"

    def __init__(self, deals_root: Path) -> None:
        self.deals_root = Path(deals_root)

    def context(self, deal_id: str) -> ServiceContext:
        return ServiceContext(deal_id=deal_id, deals_root=self.deals_root)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    async def create_deal(
        self,
        deal_id: str,
        *,
        deal_name: str = "",
        issuer: str = "",
        series: str = "",
        actor: str = "system",
    ) -> ServiceResult:
        return await self.guard(self._create_deal(deal_id, deal_name, issuer, series, actor))

    async def _create_deal(
        self, deal_id: str, deal_name: str, issuer: str, series: str, actor: str
    ) -> dict[str, Any]:
        def _work() -> dict[str, Any]:
            ctx = self.context(deal_id)
            scope = ctx.scope()  # creates the deal folder + required subdirs
            store = ctx.store()  # initialises data/deal_store.db
            store.audit(
                "create_deal",
                actor=actor,
                object_type="deal",
                object_id=deal_id,
                after={"deal_name": deal_name, "issuer": issuer, "series": series},
            )
            return {
                "deal_id": deal_id,
                "deal_name": deal_name,
                "issuer": issuer,
                "series": series,
                "deal_path": str(scope.deal_path),
                "schema_version": store.schema_version(),
            }

        return await self._to_thread(_work)

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------
    async def list_deals(self) -> ServiceResult:
        return await self.guard(self._list_deals())

    async def _list_deals(self) -> list[dict[str, Any]]:
        def _work() -> list[dict[str, Any]]:
            deals: list[dict[str, Any]] = []
            root = self.deals_root
            if not root.exists():
                return deals
            for child in sorted(root.iterdir()):
                db = child / "data" / "deal_store.db"
                if child.is_dir() and db.exists():
                    deals.append({"deal_id": child.name, "deal_path": str(child)})
            return deals

        return await self._to_thread(_work)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    async def get_status(self, deal_id: str) -> ServiceResult:
        return await self.guard(self._get_status(deal_id))

    async def _get_status(self, deal_id: str) -> dict[str, Any]:
        def _work() -> dict[str, Any]:
            ctx = self.context(deal_id)
            if not ctx.deal_path.exists():
                raise FileNotFoundError(f"Deal not found: {deal_id}")
            store = ctx.store(init=False)
            documents = store.list_documents(deal_id)
            definitions = store.list_definitions(deal_id)
            sep = store.list_sep_artifacts(deal_id)
            by_status: dict[str, int] = {}
            for a in sep:
                by_status[a["status"]] = by_status.get(a["status"], 0) + 1
            model = store.get_latest_payment_model(deal_id)
            runs = store.list_monthly_runs(deal_id)
            return {
                "deal_id": deal_id,
                "documents": len(documents),
                "definitions": len(definitions),
                "sep_artifacts": {"total": len(sep), "by_status": by_status},
                "payment_model": {
                    "exists": model is not None,
                    "version": (model or {}).get("version"),
                    "validation_status": (model or {}).get("validation_status"),
                },
                "monthly_runs": len(runs),
            }

        return await self._to_thread(_work)

    # ------------------------------------------------------------------
    # Portfolio dashboard (management view across all deals)
    # ------------------------------------------------------------------
    async def portfolio(self) -> ServiceResult:
        return await self.guard(self._portfolio())

    async def _portfolio(self) -> dict[str, Any]:
        def _work() -> dict[str, Any]:
            deals: list[dict[str, Any]] = []
            totals = {"deals": 0, "documents": 0, "definitions": 0,
                      "pending_artifacts": 0, "approved_artifacts": 0,
                      "open_exceptions": 0, "models": 0, "runs": 0}
            root = self.deals_root
            if root.exists():
                for child in sorted(root.iterdir()):
                    db = child / "data" / "deal_store.db"
                    if not (child.is_dir() and db.exists()):
                        continue
                    store = self.context(child.name).store(init=False)
                    sep = store.list_sep_artifacts(child.name)
                    pending = sum(1 for a in sep if a["status"] == "pending_review")
                    approved = sum(1 for a in sep if a["status"] == "approved")
                    exceptions = len(store.list_correction_events(child.name))
                    model = store.get_latest_payment_model(child.name)
                    runs = store.list_monthly_runs(child.name)
                    deals.append({
                        "deal_id": child.name,
                        "documents": len(store.list_documents(child.name)),
                        "definitions": len(store.list_definitions(child.name)),
                        "pending_artifacts": pending,
                        "approved_artifacts": approved,
                        "open_exceptions": exceptions,
                        "model_status": (model or {}).get("validation_status") if model else None,
                        "monthly_runs": len(runs),
                    })
                    totals["deals"] += 1
                    totals["documents"] += len(store.list_documents(child.name))
                    totals["definitions"] += len(store.list_definitions(child.name))
                    totals["pending_artifacts"] += pending
                    totals["approved_artifacts"] += approved
                    totals["open_exceptions"] += exceptions
                    totals["models"] += 1 if model else 0
                    totals["runs"] += len(runs)
            return {"deals": deals, "totals": totals}

        return await self._to_thread(_work)
