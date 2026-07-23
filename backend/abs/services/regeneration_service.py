"""
RegenerationService — selective regeneration (Layer B §6).

Implements practical levels of the selective-regeneration model: rather than
re-running the whole lifecycle when one thing changes, regenerate only the
impacted artifact family. Supported targets:

* ``sep:<name>`` — supersede the profile's current artifacts and re-extract.
* ``definitions`` — rebuild the defined-term graph.
* ``governing``  — regenerate the governing-document clauses.
* ``model``      — regenerate the Python payment model.

Each regeneration logs a governed correction event for the learning loop.
Stateless + async.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from backend.abs.services.base import ABSService, ProgressFn, ServiceContext, ServiceResult
from backend.abs.services.llm_client import LLMClient


class RegenerationService(ABSService):
    """Selectively regenerate impacted downstream artifacts."""

    name = "regeneration"

    def __init__(self, deals_root: Path) -> None:
        self.deals_root = Path(deals_root)

    def context(self, deal_id: str) -> ServiceContext:
        return ServiceContext(deal_id=deal_id, deals_root=self.deals_root)

    async def regenerate(
        self,
        deal_id: str,
        target: str,
        *,
        llm: Optional[LLMClient] = None,
        reason: str = "",
        actor: str = "user",
        progress: Optional[ProgressFn] = None,
    ) -> ServiceResult:
        return await self.guard(self._regenerate(deal_id, target, llm, reason, actor, progress))

    async def _regenerate(
        self, deal_id: str, target: str, llm: Optional[LLMClient],
        reason: str, actor: str, progress: Optional[ProgressFn],
    ) -> dict[str, Any]:
        from backend.abs.services.definition_service import DefinitionService
        from backend.abs.services.governance_service import GovernanceService
        from backend.abs.services.governing_doc_service import GoverningDocService
        from backend.abs.services.model_service import ModelService
        from backend.abs.services.sep_service import SEPService

        if progress:
            progress({"stage": f"regenerate:{target}", "status": "in-progress"})

        outcome: dict[str, Any]
        if target.startswith("sep:"):
            sep_name = target.split(":", 1)[1]
            superseded = await self._to_thread(
                self.context(deal_id).store(init=False).supersede_sep_artifacts, deal_id, sep_name
            )
            res = await SEPService(self.deals_root).run_sep(deal_id, sep_name, self._require(llm), actor=actor)
            outcome = {"target": target, "superseded": superseded,
                       "regenerated": res.data if res.ok else None, "ok": res.ok}
        elif target == "definitions":
            res = await DefinitionService(self.deals_root).build_definitions(
                deal_id, llm=llm, resolve=llm is not None, actor=actor)
            outcome = {"target": target, "regenerated": res.data if res.ok else None, "ok": res.ok}
        elif target == "governing":
            res = await GoverningDocService(self.deals_root).generate(deal_id, self._require(llm), actor=actor)
            outcome = {"target": target, "regenerated": res.data if res.ok else None, "ok": res.ok}
        elif target == "model":
            res = await ModelService(self.deals_root).generate(deal_id, self._require(llm), actor=actor)
            outcome = {"target": target, "regenerated": res.data if res.ok else None, "ok": res.ok}
        else:
            raise ValueError(f"Unknown regeneration target: {target!r}")

        # Log a governed correction event for the learning loop.
        await GovernanceService(self.deals_root).log_correction(
            deal_id, object_type="regeneration", object_id=target,
            lifecycle_stage=target, root_cause=reason or "user-requested regeneration",
            severity="low", actor=actor,
        )
        if progress:
            progress({"stage": f"regenerate:{target}", "status": "done"})
        return outcome

    @staticmethod
    def _require(llm: Optional[LLMClient]) -> LLMClient:
        if llm is None:
            raise ValueError("Regeneration of this target requires an LLM connection.")
        return llm
