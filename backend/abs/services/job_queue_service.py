"""
JobQueueService — Layer B.12: Async job management.

Today every dispatcher command runs inline (blocking the response until done).
For long-running operations — full ingestion, running all SEPs, generating
projections across many scenarios — this is acceptable in the POC but needs a
job queue for scale.

This service provides a lightweight SQLite-backed job queue: enqueue a command,
get a job_id immediately, run the command in the background, and poll for status.
The WebView can show a live job-status panel. Stateless + async.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional

from backend.abs.services.base import ABSService, ServiceContext, ServiceResult
from backend.abs.store import DealStore


DispatchFn = Callable[..., Coroutine[Any, Any, dict[str, Any]]]


class JobQueueService(ABSService):
    """Enqueue long-running commands and track their status."""

    name = "job_queue"

    def __init__(self, deals_root: Path, dispatch_fn: Optional[DispatchFn] = None) -> None:
        self.deals_root = Path(deals_root)
        self._dispatch = dispatch_fn  # The ABSDispatcher.dispatch method

    def context(self, deal_id: Optional[str]) -> ServiceContext:
        return ServiceContext(deal_id=deal_id or "global", deals_root=self.deals_root)

    def _get_store(self, deal_id: Optional[str]) -> DealStore:
        """Use deal store if we have a deal_id, else use a shared global store."""
        if deal_id:
            return DealStore.for_deal_dir(self.deals_root / deal_id, init=False)
        return DealStore.for_deal_dir(self.deals_root / ".global", init=True)

    # ------------------------------------------------------------------
    # Enqueue
    # ------------------------------------------------------------------
    async def enqueue(
        self, command: str, params: dict[str, Any], *, actor: str = "user"
    ) -> ServiceResult:
        deal_id = params.get("deal_id")
        def _work() -> dict[str, Any]:
            store = self._get_store(deal_id)
            job_id = store.enqueue_job(deal_id, command, params, actor=actor)
            return {"job_id": job_id, "status": "queued", "command": command}
        return await self.guard(self._to_thread(_work))

    # ------------------------------------------------------------------
    # Run a queued job in the background (fires and forgets into asyncio)
    # ------------------------------------------------------------------
    async def run_background(
        self, job_id: str, deal_id: Optional[str], command: str, params: dict[str, Any],
        llm: Any = None, progress: Any = None
    ) -> None:
        """Start the job running in the background. Non-blocking."""
        asyncio.ensure_future(self._execute_job(job_id, deal_id, command, params, llm, progress))

    async def _execute_job(
        self, job_id: str, deal_id: Optional[str],
        command: str, params: dict[str, Any], llm: Any, progress: Any
    ) -> None:
        store = self._get_store(deal_id)
        store.update_job(job_id, status="running")
        try:
            if self._dispatch is None:
                raise RuntimeError("No dispatch function registered with JobQueueService")
            result = await self._dispatch(command, params, llm=llm, progress=progress)
            store.update_job(job_id, status="done", result=result)
        except Exception as exc:  # noqa: BLE001
            store.update_job(job_id, status="failed", error=f"{type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------
    # Status + listing
    # ------------------------------------------------------------------
    async def get_job(self, job_id: str, deal_id: Optional[str] = None) -> ServiceResult:
        store = self._get_store(deal_id)
        return await self.guard(self._to_thread(store.get_job, job_id))

    async def list_jobs(
        self, deal_id: Optional[str] = None, *, status: Optional[str] = None
    ) -> ServiceResult:
        store = self._get_store(deal_id)
        return await self.guard(self._to_thread(store.list_jobs, deal_id, status=status))

    async def cancel_job(self, job_id: str, deal_id: Optional[str] = None) -> ServiceResult:
        def _work() -> dict[str, Any]:
            store = self._get_store(deal_id)
            job = store.get_job(job_id)
            if not job:
                raise ValueError(f"Job {job_id} not found")
            if job.get("status") in ("done", "failed", "cancelled"):
                return {"cancelled": False, "status": job["status"]}
            store.update_job(job_id, status="cancelled")
            return {"cancelled": True, "job_id": job_id}
        return await self.guard(self._to_thread(_work))
