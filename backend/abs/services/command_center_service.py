"""
CommandCenterService — Layer B.9: Daily Deal Operations Command Center.

Aggregates the day-to-day action items across all deals into a single
prioritised queue:

* Pending artifact reviews (pending_review status)
* Failed extractions / low-confidence items
* Open correction events (AI exceptions)
* Model approval tasks
* Stale artifacts (superseded, not yet regenerated)
* Monthly run readiness warnings

Returns a structured "work queue" the WebView can render as the daily
operations dashboard. Stateless + async.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.abs.services.base import ABSService, ServiceResult


class CommandCenterService(ABSService):
    """Cross-deal daily operations queue."""

    name = "command_center"

    def __init__(self, deals_root: Path) -> None:
        self.deals_root = Path(deals_root)

    async def queue(self, *, actor: str = "user", max_per_type: int = 50) -> ServiceResult:
        return await self.guard(self._to_thread(self._build_queue, actor, max_per_type))

    def _build_queue(self, actor: str, max_per_type: int) -> dict[str, Any]:
        from backend.abs.store import DealStore

        root = Path(self.deals_root)
        items: list[dict[str, Any]] = []

        if not root.exists():
            return {"items": [], "total": 0, "by_type": {}}

        for child in sorted(root.iterdir()):
            db = child / "data" / "deal_store.db"
            if not (child.is_dir() and db.exists()):
                continue
            deal_id = child.name
            store = DealStore.for_deal_dir(child, init=False)

            # 1. Pending reviews
            for art in store.list_sep_artifacts(deal_id):
                if art.get("status") == "pending_review":
                    items.append({
                        "type": "pending_review",
                        "priority": "high",
                        "deal_id": deal_id,
                        "artifact_id": art["artifact_id"],
                        "sep_name": art["sep_name"],
                        "field_path": art.get("field_path"),
                        "citation": art.get("citation"),
                        "action": "Review & Approve",
                    })

            # 2. Open correction events (AI exceptions)
            for ev in store.list_correction_events(deal_id):
                if ev.get("status") == "open":
                    items.append({
                        "type": "ai_exception",
                        "priority": ev.get("severity", "medium"),
                        "deal_id": deal_id,
                        "event_id": ev.get("id"),
                        "root_cause": ev.get("root_cause"),
                        "object_type": ev.get("object_type"),
                        "action": "Review AI Correction",
                    })

            # 3. Model approval tasks
            model = store.get_latest_payment_model(deal_id)
            if model and model.get("validation_status") == "pending_review":
                items.append({
                    "type": "model_approval",
                    "priority": "high",
                    "deal_id": deal_id,
                    "model_id": model["model_id"],
                    "model_version": model.get("version"),
                    "action": "Approve Payment Model",
                })

            # 4. Stale definitions (extracted but not resolved)
            unresolved = [d for d in store.list_definitions(deal_id)
                          if not d.get("resolved_definition") and d.get("status") == "draft"]
            if unresolved:
                items.append({
                    "type": "unresolved_definitions",
                    "priority": "low",
                    "deal_id": deal_id,
                    "count": len(unresolved),
                    "action": "Run Definition Resolution",
                })

        # Sort by priority
        _priority_order = {"high": 0, "medium": 1, "low": 2}
        items.sort(key=lambda x: _priority_order.get(str(x.get("priority", "low")), 2))
        items = items[:max_per_type * 4]

        by_type: dict[str, int] = {}
        for item in items:
            by_type[item["type"]] = by_type.get(item["type"], 0) + 1

        return {"items": items, "total": len(items), "by_type": by_type}
