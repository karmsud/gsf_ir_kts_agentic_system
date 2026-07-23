"""
IPCServer — JSON-lines bridge between the VS Code extension and the backend.

Message protocol (newline-delimited JSON, both directions):

Extension → backend
    {"type": "command", "id": <req>, "command": "qa.ask", "params": {...}}
    {"type": "llm_response", "llm_id": <id>, "text": "...", "input_tokens": n, ...}
    {"type": "cancel", "id": <req>}

Backend → extension
    {"type": "progress", "id": <req>, "event": {...}}
    {"type": "llm_request", "id": <req>, "llm_id": <id>, "prompt": "...", ...}
    {"type": "result", "id": <req>, "result": {...}}
    {"type": "log", "level": "...", "message": "..."}

The LLM is GitHub Copilot: when a service needs a completion the server emits an
``llm_request`` and awaits the matching ``llm_response`` — so the model call is
fully async and never blocks other in-flight commands. The server is stateless
across deals and runs every command as an independent task, enabling concurrency.
"""

from __future__ import annotations

import asyncio
import itertools
from typing import Any, Awaitable, Callable, Optional

from backend.abs.services.dispatcher import ABSDispatcher
from backend.abs.services.llm_client import LLMResult

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]


class _IPCLLMClient:
    """LLMClient that fulfils completions via the IPC channel (GHCP)."""

    def __init__(self, server: "IPCServer", req_id: str) -> None:
        self._server = server
        self._req_id = req_id

    async def complete(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> LLMResult:
        llm_id = self._server._next_llm_id()
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._server._pending_llm[llm_id] = future
        await self._server.emit({
            "type": "llm_request",
            "id": self._req_id,
            "llm_id": llm_id,
            "prompt": prompt,
            "system_prompt": system,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        payload = await future  # resolved when llm_response arrives
        return LLMResult(
            text=str(payload.get("text", "")),
            input_tokens=int(payload.get("input_tokens", 0) or 0),
            output_tokens=int(payload.get("output_tokens", 0) or 0),
            model=str(payload.get("model", "ghcp")),
        )


class IPCServer:
    """Route IPC messages to the dispatcher and bridge LLM calls to GHCP."""

    def __init__(self, dispatcher: ABSDispatcher, emit: EmitFn) -> None:
        self.dispatcher = dispatcher
        self.emit = emit
        self._pending_llm: dict[str, asyncio.Future] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._llm_counter = itertools.count(1)

    def _next_llm_id(self) -> str:
        return f"llm{next(self._llm_counter)}"

    # ------------------------------------------------------------------
    # Incoming message handling
    # ------------------------------------------------------------------
    async def handle_message(self, msg: dict[str, Any]) -> None:
        mtype = msg.get("type")
        if mtype == "command":
            await self._start_command(msg)
        elif mtype == "llm_response":
            self._resolve_llm(msg)
        elif mtype == "cancel":
            self._cancel(msg.get("id", ""))
        else:
            await self.emit({"type": "log", "level": "warn", "message": f"Unknown message type: {mtype}"})

    async def _start_command(self, msg: dict[str, Any]) -> None:
        req_id = str(msg.get("id", ""))
        command = str(msg.get("command", ""))
        params = msg.get("params") or {}
        task = asyncio.ensure_future(self._run_command(req_id, command, params))
        self._tasks[req_id] = task

    async def _run_command(self, req_id: str, command: str, params: dict[str, Any]) -> None:
        llm = _IPCLLMClient(self, req_id)

        def progress(event: dict[str, Any]) -> None:
            # Fire-and-forget progress emission onto the event loop.
            asyncio.ensure_future(self.emit({"type": "progress", "id": req_id, "event": event}))

        try:
            result = await self.dispatcher.dispatch(command, params, llm=llm, progress=progress)
        except Exception as exc:  # noqa: BLE001 — boundary
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "data": None, "events": []}
        finally:
            self._tasks.pop(req_id, None)
        await self.emit({"type": "result", "id": req_id, "result": result})

    def _resolve_llm(self, msg: dict[str, Any]) -> None:
        llm_id = str(msg.get("llm_id", ""))
        future = self._pending_llm.pop(llm_id, None)
        if future is not None and not future.done():
            future.set_result(msg)

    def _cancel(self, req_id: str) -> None:
        task = self._tasks.pop(req_id, None)
        if task is not None and not task.done():
            task.cancel()

    async def join(self) -> None:
        """Await all in-flight command tasks (used by tests / graceful shutdown)."""
        if self._tasks:
            await asyncio.gather(*list(self._tasks.values()), return_exceptions=True)


# ---------------------------------------------------------------------------
# Real stdio loop (used by the frozen backend entry point)
# ---------------------------------------------------------------------------

async def run_stdio(deals_root: str) -> None:  # pragma: no cover - exercised in production
    """Run the IPC server over stdin/stdout (newline-delimited JSON)."""
    import json
    import sys
    from pathlib import Path

    loop = asyncio.get_event_loop()
    out_lock = asyncio.Lock()

    async def emit(message: dict[str, Any]) -> None:
        line = json.dumps(message, ensure_ascii=False)
        async with out_lock:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()

    dispatcher = ABSDispatcher(Path(deals_root))
    server = IPCServer(dispatcher, emit)
    await emit({"type": "ready", "message": "ABS backend ready"})

    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line = await reader.readline()
        if not line:
            break
        text = line.decode("utf-8").strip()
        if not text:
            continue
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            await emit({"type": "log", "level": "error", "message": f"Bad JSON: {text[:120]}"})
            continue
        await server.handle_message(message)
