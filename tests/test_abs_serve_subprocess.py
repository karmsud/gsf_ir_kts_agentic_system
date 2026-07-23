"""
Subprocess smoke test for the production IPC entry point (backend.abs.serve).

Spawns the real backend the VS Code extension launches and drives it over
stdin/stdout JSON-lines — including the GHCP LLM bridge round trip (simulated
here by answering the llm_request as the extension would).
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


class ServeProc:
    """Manage a backend.abs.serve subprocess with line-based IPC."""

    def __init__(self, deals_root: Path):
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "backend.abs.serve", "--deals-root", str(deals_root)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, cwd=str(REPO_ROOT),
        )
        self._q: "queue.Queue[dict]" = queue.Queue()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self):
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._q.put(json.loads(line))
            except json.JSONDecodeError:
                pass

    def send(self, obj: dict):
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def wait_for(self, predicate, timeout=20.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                msg = self._q.get(timeout=deadline - time.time())
            except queue.Empty:
                break
            if predicate(msg):
                return msg
        raise AssertionError("Timed out waiting for message")

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


@pytest.fixture()
def serve(tmp_path):
    p = ServeProc(tmp_path)
    p.wait_for(lambda m: m.get("type") == "ready", timeout=30)
    yield p
    p.close()


def test_serve_ready_and_deal_create(serve: ServeProc):
    serve.send({"type": "command", "id": "1", "command": "deal.create", "params": {"deal_id": "cbass"}})
    result = serve.wait_for(lambda m: m.get("type") == "result" and m.get("id") == "1")
    assert result["result"]["ok"] is True
    # deal.list reflects it.
    serve.send({"type": "command", "id": "2", "command": "deal.list", "params": {}})
    listed = serve.wait_for(lambda m: m.get("type") == "result" and m.get("id") == "2")
    assert any(d["deal_id"] == "cbass" for d in listed["result"]["data"])


def test_serve_llm_bridge_round_trip(serve: ServeProc):
    serve.send({"type": "command", "id": "a", "command": "deal.create", "params": {"deal_id": "cbass"}})
    serve.wait_for(lambda m: m.get("type") == "result" and m.get("id") == "a")
    serve.send({"type": "command", "id": "b", "command": "ingest.document",
                "params": {"deal_id": "cbass", "pages": ["ARTICLE V\n\nPay interest to Class A first.\n\n"]}})
    serve.wait_for(lambda m: m.get("type") == "result" and m.get("id") == "b")

    # qa.ask triggers an llm_request; answer it as the extension would.
    serve.send({"type": "command", "id": "c", "command": "qa.ask",
                "params": {"deal_id": "cbass", "question": "What is paid first?"}})
    req = serve.wait_for(lambda m: m.get("type") == "llm_request")
    serve.send({"type": "llm_response", "llm_id": req["llm_id"],
                "text": "Interest to Class A first [Article V].", "model": "test"})
    result = serve.wait_for(lambda m: m.get("type") == "result" and m.get("id") == "c")
    assert result["result"]["ok"] is True
    assert "Class A" in result["result"]["data"]["answer"]
