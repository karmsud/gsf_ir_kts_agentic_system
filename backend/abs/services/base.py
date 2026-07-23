"""
ABS service layer — stateless, async integration boundary.

Services are the API surface that the VS Code extension (via JSON-lines IPC)
and the CLI call into. They sit above the data store, agents, and skills.

Architectural rules
--------------------
* **Stateless** — a service instance carries no per-deal mutable state. Deal
  context is passed in (or resolved fresh) on every call, so any worker /
  process can serve any request. This is what enables horizontal scaling.
* **Async** — every public method is ``async`` and off-loads blocking work
  (disk, CPU, LLM) to threads, keeping the event loop responsive.
* **Uniform envelope** — every method returns a :class:`ServiceResult` so the
  transport layer has one shape to serialise.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from backend.abs.deal_scope import DealScope
from backend.abs.store import DealStore


# ---------------------------------------------------------------------------
# Deal context — immutable, cheap to construct, resolves fresh handles per call
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ServiceContext:
    """Immutable handle identifying which deal an operation targets."""

    deal_id: str
    deals_root: Path

    @property
    def deal_path(self) -> Path:
        return Path(self.deals_root) / self.deal_id

    def store(self, *, init: bool = True) -> DealStore:
        """Return a fresh (stateless) data-store handle for this deal."""
        return DealStore.for_deal_dir(self.deal_path, init=init)

    def scope(self, *, read_only: bool = False) -> DealScope:
        """Return a DealScope enforcing this deal's boundary."""
        if read_only:
            return DealScope.create_read_only(self.deal_id, Path(self.deals_root))
        return DealScope.create(self.deal_id, Path(self.deals_root))


# ---------------------------------------------------------------------------
# Result envelope
# ---------------------------------------------------------------------------

@dataclass
class ServiceResult:
    """Uniform return shape for every service method."""

    ok: bool
    data: Any = None
    error: str = ""
    elapsed_ms: float = 0.0
    events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "events": self.events,
        }

    @classmethod
    def success(cls, data: Any = None, *, events: Optional[list] = None, elapsed_ms: float = 0.0) -> "ServiceResult":
        return cls(ok=True, data=data, events=events or [], elapsed_ms=elapsed_ms)

    @classmethod
    def failure(cls, error: str, *, elapsed_ms: float = 0.0) -> "ServiceResult":
        return cls(ok=False, error=error, elapsed_ms=elapsed_ms)


# Progress callback: a service may emit incremental events as it works.
ProgressFn = Callable[[dict[str, Any]], None]


class ABSService:
    """Base class for stateless async services."""

    #: Human-readable service name (used in logs / IPC routing).
    name: str = "service"

    async def _to_thread(self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
        """Run a blocking callable off the event loop."""
        return await asyncio.to_thread(fn, *args, **kwargs)

    @staticmethod
    def _timer() -> Callable[[], float]:
        start = time.perf_counter()
        return lambda: (time.perf_counter() - start) * 1000.0

    async def guard(self, coro: Awaitable[Any]) -> ServiceResult:
        """Await a coroutine and wrap success/exception into a ServiceResult."""
        elapsed = self._timer()
        try:
            data = await coro
            if isinstance(data, ServiceResult):
                data.elapsed_ms = data.elapsed_ms or elapsed()
                return data
            return ServiceResult.success(data, elapsed_ms=elapsed())
        except Exception as exc:  # noqa: BLE001 — boundary: convert to envelope
            return ServiceResult.failure(f"{type(exc).__name__}: {exc}", elapsed_ms=elapsed())
