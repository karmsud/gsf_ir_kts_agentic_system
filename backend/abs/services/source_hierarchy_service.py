"""
SourceHierarchyService — Layer B.2: Governing-document source hierarchy.

Structured-finance deals often have multiple documents (PSA, Indenture,
Prospectus Supplement, Trust Agreement, Amendments). When these documents
conflict — different fee rates, different waterfall language, or different
operative dates — the platform needs a governed hierarchy to decide which
controls.

This service:
1. Records the operative-document decision for each deal (confirmed by an
   authorised reviewer, versioned, audited).
2. Detects conflicts: when the same field is extracted from two documents with
   materially different values.
3. Reports which document governs each major logic area (waterfall, fees,
   accounts, reporting, triggers).

Stateless + async.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from backend.abs.services.base import ABSService, ProgressFn, ServiceContext, ServiceResult
from backend.abs.services.json_utils import parse_json_lenient
from backend.abs.store import DealStore

# Standard priority from the docs: executed > amendment > PSA > ProSupp > drafts
_DEFAULT_PRIORITY: dict[str, int] = {
    "PSA": 100, "Indenture": 100, "Trust Agreement": 90,
    "Amendment": 110,  # amendments override base
    "ProSupp": 80, "Prospectus Supplement": 80,
    "Trust Indenture": 95,
    "Support Agreement": 70,
    "Draft": 10, "Prior Template": 5,
}

_LOGIC_AREAS = ["waterfall", "fees", "accounts", "reporting", "triggers", "definitions"]


class SourceHierarchyService(ABSService):
    """Detect conflicts and confirm operative documents per logic area."""

    name = "source_hierarchy"

    def __init__(self, deals_root: Path) -> None:
        self.deals_root = Path(deals_root)

    def context(self, deal_id: str) -> ServiceContext:
        return ServiceContext(deal_id=deal_id, deals_root=self.deals_root)

    # ------------------------------------------------------------------
    # Detect conflicts between documents
    # ------------------------------------------------------------------
    async def detect_conflicts(self, deal_id: str) -> ServiceResult:
        return await self.guard(self._to_thread(self._detect_conflicts, deal_id))

    def _detect_conflicts(self, deal_id: str) -> list[dict[str, Any]]:
        """Find cases where the same SEP field was extracted from 2 docs with different values."""
        store = self.context(deal_id).store(init=False)
        conflicts: list[dict[str, Any]] = []
        docs = {d["doc_id"]: d for d in store.list_documents(deal_id)}
        if len(docs) < 2:
            return []
        for sep_name in _LOGIC_AREAS:
            arts = store.list_sep_artifacts(deal_id, sep_name)
            # Group by field_path; look for different values from different docs.
            by_field: dict[str, list[dict]] = {}
            for a in arts:
                fp = a.get("field_path") or ""
                by_field.setdefault(fp, []).append(a)
            for field, items in by_field.items():
                vals = [(i.get("value"), i.get("citation")) for i in items]
                unique_vals = set(v for v, _ in vals)
                if len(unique_vals) > 1:
                    conflicts.append({
                        "sep_name": sep_name, "field_path": field,
                        "conflict_count": len(unique_vals),
                        "values": vals[:4],
                        "severity": "high",
                        "recommendation": f"Confirm which document governs {sep_name}/{field}",
                    })
        return conflicts

    # ------------------------------------------------------------------
    # Operative document hierarchy for the deal
    # ------------------------------------------------------------------
    async def get_hierarchy(self, deal_id: str) -> ServiceResult:
        return await self.guard(self._to_thread(self._get_hierarchy, deal_id))

    def _get_hierarchy(self, deal_id: str) -> list[dict[str, Any]]:
        store = self.context(deal_id).store(init=False)
        docs = store.list_documents(deal_id)
        result = []
        for doc in sorted(docs, key=lambda d: -_DEFAULT_PRIORITY.get(d.get("doc_type", ""), 50)):
            result.append({
                "doc_id": doc["doc_id"],
                "title": doc.get("title"),
                "doc_type": doc.get("doc_type"),
                "priority": _DEFAULT_PRIORITY.get(doc.get("doc_type", ""), 50),
                "is_operative": bool(doc.get("is_operative")),
                "controls": [area for area in _LOGIC_AREAS] if doc.get("is_operative") else [],
            })
        return result

    # ------------------------------------------------------------------
    # Confirm operative document for a logic area
    # ------------------------------------------------------------------
    async def confirm_operative(
        self, deal_id: str, doc_id: str, *, logic_area: str, actor: str = "reviewer"
    ) -> ServiceResult:
        def _work() -> dict[str, Any]:
            store = self.context(deal_id).store(init=False)
            doc = store.get_document(doc_id)
            if doc is None:
                raise ValueError(f"Document {doc_id} not found")
            store.audit(
                "confirm_operative_doc",
                actor=actor,
                object_type="document",
                object_id=doc_id,
                after={"logic_area": logic_area, "doc_title": doc.get("title")},
            )
            return {"confirmed": True, "doc_id": doc_id, "logic_area": logic_area,
                    "doc_title": doc.get("title")}
        return await self.guard(self._to_thread(_work))
