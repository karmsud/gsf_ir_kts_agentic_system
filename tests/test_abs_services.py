"""
Tests for the ABS service layer (base, llm_client, deal_service).

Verifies the uniform result envelope, statelessness, async behaviour, the
LLM-client abstraction (stub + callable adapter, sync and async), and the
deal lifecycle service.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.abs.services import (
    CallableLLMClient,
    DealService,
    ServiceContext,
    ServiceResult,
    StubLLMClient,
)


# ---------------------------------------------------------------------------
# ServiceResult / ServiceContext
# ---------------------------------------------------------------------------

def test_service_result_envelope():
    ok = ServiceResult.success({"x": 1}, elapsed_ms=3.0)
    assert ok.to_dict()["ok"] is True
    assert ok.to_dict()["data"] == {"x": 1}
    err = ServiceResult.failure("boom")
    assert err.to_dict()["ok"] is False
    assert "boom" in err.to_dict()["error"]


def test_service_context_resolves_fresh_handles(tmp_path: Path):
    ctx = ServiceContext(deal_id="d1", deals_root=tmp_path)
    assert ctx.deal_path == tmp_path / "d1"
    s1 = ctx.store()
    s2 = ctx.store(init=False)
    assert s1 is not s2  # stateless: a new handle each call


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------

def test_stub_llm_client():
    client = StubLLMClient()
    res = asyncio.run(client.complete("hello world", system="be terse"))
    assert res.text.startswith("[stub]")
    assert res.model == "stub"
    assert client.calls[0]["system"] == "be terse"


def test_stub_llm_with_responder():
    client = StubLLMClient(responder=lambda p, s: '{"answer": 42}')
    res = asyncio.run(client.complete("q"))
    assert res.text == '{"answer": 42}'


def test_callable_llm_client_sync():
    def bridge(prompt, system_prompt=None, temperature=0.0, max_tokens=2048):
        return {"text": f"echo:{prompt}", "input_tokens": 5, "output_tokens": 2, "model": "ghcp"}

    client = CallableLLMClient(bridge)
    res = asyncio.run(client.complete("ping"))
    assert res.text == "echo:ping"
    assert res.input_tokens == 5
    assert res.model == "ghcp"


def test_callable_llm_client_async():
    async def bridge(prompt, system_prompt=None, temperature=0.0, max_tokens=2048):
        return f"async-echo:{prompt}"

    client = CallableLLMClient(bridge)
    res = asyncio.run(client.complete("ping"))
    assert res.text == "async-echo:ping"


# ---------------------------------------------------------------------------
# DealService
# ---------------------------------------------------------------------------

def test_create_and_status(tmp_path: Path):
    svc = DealService(tmp_path)

    async def _run():
        created = await svc.create_deal("cbass_2002_cb4", deal_name="C-BASS", issuer="C-BASS", series="2002-CB4")
        assert created.ok is True
        assert created.data["deal_id"] == "cbass_2002_cb4"
        status = await svc.get_status("cbass_2002_cb4")
        return status

    status = asyncio.run(_run())
    assert status.ok is True
    assert status.data["documents"] == 0
    assert status.data["payment_model"]["exists"] is False


def test_list_deals(tmp_path: Path):
    svc = DealService(tmp_path)

    async def _run():
        await svc.create_deal("deal_a")
        await svc.create_deal("deal_b")
        return await svc.list_deals()

    res = asyncio.run(_run())
    assert res.ok is True
    ids = {d["deal_id"] for d in res.data}
    assert ids == {"deal_a", "deal_b"}


def test_status_missing_deal_is_failure(tmp_path: Path):
    svc = DealService(tmp_path)
    res = asyncio.run(svc.get_status("nope"))
    assert res.ok is False
    assert "not found" in res.error.lower()


def test_guard_converts_exception_to_envelope(tmp_path: Path):
    svc = DealService(tmp_path)

    async def _boom():
        raise RuntimeError("kaboom")

    res = asyncio.run(svc.guard(_boom()))
    assert res.ok is False
    assert "kaboom" in res.error
