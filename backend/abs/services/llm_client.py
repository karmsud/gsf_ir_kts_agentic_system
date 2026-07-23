"""
LLM client abstraction for the ABS service layer.

The production LLM is GitHub Copilot, reached through the VS Code Language
Model API: the Python backend emits an ``llm_request`` over JSON-lines IPC and
the extension fulfils it. Services must not depend on that transport directly —
they depend on the small :class:`LLMClient` interface here.

Implementations
---------------
* :class:`CallableLLMClient` — adapts any sync/async callable (e.g. the IPC
  bridge supplied by the extension) to the async interface.
* :class:`StubLLMClient` — deterministic, offline client for tests and for
  running the system without a live LLM.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, Protocol, Union


@dataclass
class LLMResult:
    """Outcome of a single completion."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "model": self.model,
        }


class LLMClient(Protocol):
    """Minimal async completion interface used by all services/agents."""

    async def complete(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> LLMResult:
        ...


# A bridge callable may be sync or async and may return a str or a dict.
BridgeCallable = Callable[..., Union[str, dict, Awaitable[Union[str, dict]]]]


class CallableLLMClient:
    """Adapt a sync/async callable (the IPC bridge) to :class:`LLMClient`."""

    def __init__(self, fn: BridgeCallable, *, model: str = "ghcp") -> None:
        self._fn = fn
        self._model = model

    async def complete(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> LLMResult:
        kwargs = {
            "system_prompt": system,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if inspect.iscoroutinefunction(self._fn):
            raw = await self._fn(prompt, **kwargs)
        else:
            raw = await asyncio.to_thread(self._fn, prompt, **kwargs)
        return self._coerce(raw)

    def _coerce(self, raw: Union[str, dict]) -> LLMResult:
        if isinstance(raw, dict):
            return LLMResult(
                text=raw.get("text", ""),
                input_tokens=int(raw.get("input_tokens", 0) or 0),
                output_tokens=int(raw.get("output_tokens", 0) or 0),
                model=raw.get("model", self._model),
            )
        return LLMResult(text=str(raw), model=self._model)


class StubLLMClient:
    """Deterministic offline LLM for tests / no-LLM operation.

    By default echoes a compact, inspectable response. A ``responder`` may be
    supplied to script specific behaviour, e.g. returning JSON for an agent.
    """

    def __init__(self, responder: Optional[Callable[[str, Optional[str]], str]] = None) -> None:
        self._responder = responder
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> LLMResult:
        self.calls.append({"prompt": prompt, "system": system, "temperature": temperature})
        if self._responder is not None:
            text = self._responder(prompt, system)
        else:
            text = f"[stub] {prompt[:120]}"
        return LLMResult(
            text=text,
            input_tokens=max(1, len(prompt) // 4),
            output_tokens=max(1, len(text) // 4),
            model="stub",
        )
