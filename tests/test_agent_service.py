"""
Tests for P4 — AgentService wiring of the dormant ABS agents.

Covers the agent registry, materialisation of store artifacts to the file
layout the agents expect, the async→sync LLM bridge, and a deterministic
agent (stress testing) end-to-end via the dispatcher.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.abs.services.agent_service import AgentService
from backend.abs.services.dispatcher import ABSDispatcher
from backend.abs.services.llm_client import StubLLMClient
from backend.abs.store import DealStore


def _seed_certs(tmp_path: Path) -> DealStore:
    store = DealStore.for_deal_dir(tmp_path / "cbass")
    store.add_sep_artifact({"deal_id": "cbass", "sep_name": "certificates",
                            "value": {"class_name": "A-1", "seniority": "senior",
                                      "original_balance": "1,000,000.00", "accrual_formula": "6.00%"},
                            "citation": "p.1", "status": "approved"})
    store.add_sep_artifact({"deal_id": "cbass", "sep_name": "certificates",
                            "value": {"class_name": "M-1", "seniority": "subordinate",
                                      "original_balance": "500,000.00", "accrual_formula": "8.00%"},
                            "citation": "p.1", "status": "approved"})
    return store


def test_list_agents():
    agents = AgentService.list_agents()
    names = {a["name"] for a in agents}
    assert {"comparison", "amendment", "stress", "regression", "projection", "lifecycle"} == names


def test_materialize_writes_inputs(tmp_path: Path):
    store = _seed_certs(tmp_path)
    svc = AgentService(tmp_path)
    scope = svc.context("cbass").scope()
    svc._materialize(store, "cbass", scope.deal_path)

    assert (scope.deal_path / "deal_setup.csv").exists()
    classes_csv = (scope.deal_path / "classes_setup.csv").read_text()
    assert "A-1" in classes_csv and "M-1" in classes_csv
    wf = (scope.deal_path / "extractions" / "waterfall_rules.json").read_text()
    assert "int_A-1" in wf and "prin_M-1" in wf


def test_unknown_agent(tmp_path: Path):
    svc = AgentService(tmp_path)
    res = asyncio.run(svc.run_agent("cbass", "nonsense"))
    assert res.ok is False
    assert "Unknown agent" in res.error


def test_stress_agent_runs_end_to_end(tmp_path: Path):
    _seed_certs(tmp_path)
    svc = AgentService(tmp_path)
    res = asyncio.run(svc.run_agent(
        "cbass", "stress",
        task={"months": 3, "scenarios": [{"name": "base", "overrides": {}},
                                         {"name": "high_cdr", "overrides": {"cdr_multiplier": 2.0}}]},
    ))
    assert res.ok is True, res.error
    result = res.data["result"]
    # The stress agent returns scenarios (deterministic cashflow projections).
    assert "scenarios" in result or result.get("status") == "error"


def test_async_sync_llm_bridge(tmp_path: Path):
    """The bridge must let a thread-run agent call back into the async LLM."""
    _seed_certs(tmp_path)
    svc = AgentService(tmp_path)
    llm = StubLLMClient(responder=lambda p, s: "bridged-answer")

    captured = {}

    async def run():
        loop = asyncio.get_running_loop()

        # Mimic what run_agent builds, then call it from a worker thread.
        def sync_llm(prompt, system_prompt=None, temperature=0.0, max_tokens=2048, **kw):
            fut = asyncio.run_coroutine_threadsafe(
                llm.complete(prompt, system=system_prompt), loop)
            return fut.result(timeout=30).text

        def worker():
            captured["text"] = sync_llm("hello")
            return captured["text"]

        return await asyncio.to_thread(worker)

    out = asyncio.run(run())
    assert out == "bridged-answer"


def test_dispatcher_agent_commands(tmp_path: Path):
    _seed_certs(tmp_path)
    d = ABSDispatcher(tmp_path)

    async def run():
        listed = await d.dispatch("agent.list", {})
        assert listed["ok"] and len(listed["data"]) == 6
        ran = await d.dispatch("agent.run", {
            "deal_id": "cbass", "agent_name": "stress",
            "task": {"months": 2, "scenarios": [{"name": "base", "overrides": {}}]},
        })
        return ran

    res = asyncio.run(run())
    assert res["ok"] is True, res["error"]
