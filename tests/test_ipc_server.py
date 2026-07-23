"""
Tests for IPCServer — the JSON-lines bridge + async GHCP LLM round trip.

A fake "extension" collects emitted messages and answers ``llm_request`` with a
scripted ``llm_response``, exactly as the VS Code side would.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.abs.services.dispatcher import ABSDispatcher
from backend.abs.services.ipc_server import IPCServer


PAGES = [
    'ARTICLE I DEFINITIONS\n\n"Available Funds" means the Net Interest plus principal.\n\n',
    "ARTICLE V DISTRIBUTIONS\n\nOn each Distribution Date pay interest to Class A first.\n\n",
]


class FakeExtension:
    """Collects emitted messages and auto-answers llm_requests."""

    def __init__(self, answer: str = "Answer [Article V p.2]") -> None:
        self.messages: list[dict] = []
        self.answer = answer
        self.server: IPCServer | None = None

    async def emit(self, msg: dict) -> None:
        self.messages.append(msg)
        if msg.get("type") == "llm_request" and self.server is not None:
            await self.server.handle_message({
                "type": "llm_response",
                "llm_id": msg["llm_id"],
                "text": self.answer,
                "input_tokens": 10,
                "output_tokens": 5,
                "model": "ghcp-test",
            })

    def results(self) -> list[dict]:
        return [m for m in self.messages if m["type"] == "result"]


def test_ipc_simple_command_no_llm(tmp_path: Path):
    ext = FakeExtension()
    server = IPCServer(ABSDispatcher(tmp_path), ext.emit)
    ext.server = server

    async def run():
        await server.handle_message({"type": "command", "id": "r1", "command": "deal.create", "params": {"deal_id": "cbass"}})
        await server.join()

    asyncio.run(run())
    res = ext.results()
    assert len(res) == 1
    assert res[0]["id"] == "r1"
    assert res[0]["result"]["ok"] is True


def test_ipc_llm_bridge_round_trip(tmp_path: Path):
    ext = FakeExtension(answer="Interest is paid to Class A first [Article V p.2].")
    server = IPCServer(ABSDispatcher(tmp_path), ext.emit)
    ext.server = server

    async def run():
        # Seed data with non-LLM commands.
        await server.handle_message({"type": "command", "id": "c1", "command": "deal.create", "params": {"deal_id": "cbass"}})
        await server.join()
        await server.handle_message({"type": "command", "id": "c2", "command": "ingest.document", "params": {"deal_id": "cbass", "pages": PAGES}})
        await server.join()
        # Now an LLM-backed command.
        await server.handle_message({"type": "command", "id": "c3", "command": "qa.ask", "params": {"deal_id": "cbass", "question": "What is paid first?"}})
        await server.join()

    asyncio.run(run())

    # An llm_request was emitted and answered.
    assert any(m["type"] == "llm_request" for m in ext.messages)
    qa_result = next(m for m in ext.results() if m["id"] == "c3")
    assert qa_result["result"]["ok"] is True
    assert "Class A" in qa_result["result"]["data"]["answer"]


def test_ipc_unknown_message_logs(tmp_path: Path):
    ext = FakeExtension()
    server = IPCServer(ABSDispatcher(tmp_path), ext.emit)

    asyncio.run(server.handle_message({"type": "bogus"}))
    assert any(m["type"] == "log" and m["level"] == "warn" for m in ext.messages)


def test_ipc_progress_events_emitted(tmp_path: Path):
    ext = FakeExtension()
    server = IPCServer(ABSDispatcher(tmp_path), ext.emit)
    ext.server = server

    async def run():
        await server.handle_message({"type": "command", "id": "c1", "command": "deal.create", "params": {"deal_id": "cbass"}})
        await server.join()
        await server.handle_message({"type": "command", "id": "c2", "command": "ingest.document", "params": {"deal_id": "cbass", "pages": PAGES}})
        await server.join()
        await asyncio.sleep(0.02)  # flush fire-and-forget progress tasks

    asyncio.run(run())
    progress = [m for m in ext.messages if m["type"] == "progress"]
    assert any(p["event"]["stage"] == "extract" for p in progress)


def test_ipc_concurrent_commands(tmp_path: Path):
    ext = FakeExtension()
    server = IPCServer(ABSDispatcher(tmp_path), ext.emit)
    ext.server = server

    async def run():
        # Two deal.create commands in flight at once.
        await server.handle_message({"type": "command", "id": "a", "command": "deal.create", "params": {"deal_id": "deal_a"}})
        await server.handle_message({"type": "command", "id": "b", "command": "deal.create", "params": {"deal_id": "deal_b"}})
        await server.join()

    asyncio.run(run())
    ids = {m["id"] for m in ext.results()}
    assert ids == {"a", "b"}
