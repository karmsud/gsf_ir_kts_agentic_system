"""
Tests for P5 — Layer B governance:
  - AI exception / learning loop (correction_events)
  - AI cost tracking (llm_costs + automatic dispatcher wrapping)
  - Deal-level RBAC (entitlements)
  - Portfolio dashboard (cross-deal aggregation)
  - Selective regeneration (supersede + re-run)
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.abs.services import (
    GovernanceService,
    IngestionService,
    RegenerationService,
    SEPService,
    StubLLMClient,
)
from backend.abs.services.deal_service import DealService
from backend.abs.services.dispatcher import ABSDispatcher
from backend.abs.services.pdf_extract import extracted_from_pages
from backend.abs.store import DealStore


PAGES = [
    "ARTICLE V DISTRIBUTIONS\n\nOn each Distribution Date pay interest to Class A first.\n\n",
]


def _ingest(tmp_path: Path, deal_id: str = "cbass") -> None:
    doc = extracted_from_pages(PAGES)
    asyncio.run(IngestionService(tmp_path).ingest_document(deal_id, extracted=doc, doc_type="PSA"))


# ---------------------------------------------------------------------------
# AI exception / learning loop
# ---------------------------------------------------------------------------

def test_log_and_list_correction_events(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")
    svc = GovernanceService(tmp_path)
    res = asyncio.run(svc.log_correction(
        "cbass", object_type="sep_artifact", object_id="a1",
        lifecycle_stage="extraction", original_value="5.0%", corrected_value="5.02956%",
        root_cause="OCR error", severity="high", actor="reviewer",
    ))
    assert res.ok is True
    assert res.data["event_id"] >= 1

    events = asyncio.run(svc.list_corrections("cbass"))
    assert events.ok is True
    assert len(events.data) == 1
    e = events.data[0]
    assert e["severity"] == "high"
    assert e["root_cause"] == "OCR error"
    assert e["status"] == "open"


def test_correction_event_via_dispatcher(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")
    d = ABSDispatcher(tmp_path)
    res = asyncio.run(d.dispatch("governance.log_correction", {
        "deal_id": "cbass", "object_type": "sep_artifact", "object_id": "a1",
        "original_value": {"rate": 0.05}, "corrected_value": {"rate": 0.0502956},
        "root_cause": "extraction error", "severity": "medium", "actor": "user",
    }))
    assert res["ok"] is True
    corrections = asyncio.run(d.dispatch("governance.corrections", {"deal_id": "cbass"}))
    assert corrections["ok"] and len(corrections["data"]) == 1


# ---------------------------------------------------------------------------
# AI cost tracking
# ---------------------------------------------------------------------------

def test_cost_tracking_records_per_command(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")
    svc = GovernanceService(tmp_path)
    asyncio.run(svc.record_cost("cbass", command="qa.ask", model="ghcp", input_tokens=120, output_tokens=50))
    asyncio.run(svc.record_cost("cbass", command="qa.ask", model="ghcp", input_tokens=100, output_tokens=40))
    asyncio.run(svc.record_cost("cbass", command="sep.run", model="ghcp", input_tokens=300, output_tokens=200))

    summary = asyncio.run(svc.cost_summary("cbass"))
    assert summary.ok is True
    d = summary.data
    assert d["calls"] == 3
    assert d["total_tokens"] == 120 + 50 + 100 + 40 + 300 + 200
    assert len(d["by_command"]) == 2


def test_dispatcher_auto_records_llm_cost(tmp_path: Path):
    """The dispatcher's _CostTrackingLLM wrapper auto-records costs on every LLM call."""
    _ingest(tmp_path)
    d = ABSDispatcher(tmp_path)
    llm = StubLLMClient(responder=lambda p, s: "answer [Article V].")
    asyncio.run(d.dispatch("qa.ask", {"deal_id": "cbass", "question": "What is paid first?"}, llm=llm))

    cost = asyncio.run(d.dispatch("governance.cost", {"deal_id": "cbass"}))
    assert cost["ok"] is True
    assert cost["data"]["calls"] >= 1


# ---------------------------------------------------------------------------
# RBAC entitlements
# ---------------------------------------------------------------------------

def test_rbac_grant_and_check(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")
    svc = GovernanceService(tmp_path)

    asyncio.run(svc.grant("cbass", actor="alice", role="approver", by="admin"))
    asyncio.run(svc.grant("cbass", actor="bob", role="viewer", by="admin"))

    ok_approver = asyncio.run(svc.check("cbass", actor="alice", permission="approve"))
    ok_viewer_read = asyncio.run(svc.check("cbass", actor="bob", permission="view"))
    deny_viewer_approve = asyncio.run(svc.check("cbass", actor="bob", permission="approve"))

    assert ok_approver.data["allowed"] is True
    assert ok_viewer_read.data["allowed"] is True
    assert deny_viewer_approve.data["allowed"] is False


def test_open_mode_allows_all_when_no_entitlements(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")
    svc = GovernanceService(tmp_path)
    res = asyncio.run(svc.check("cbass", actor="anyone", permission="approve"))
    assert res.data["allowed"] is True  # open mode: no entitlements configured


def test_rbac_unknown_role_fails(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")
    svc = GovernanceService(tmp_path)
    res = asyncio.run(svc.grant("cbass", actor="x", role="superuser"))
    assert res.ok is False and "Unknown role" in res.error


# ---------------------------------------------------------------------------
# Portfolio dashboard
# ---------------------------------------------------------------------------

def test_portfolio_aggregates_all_deals(tmp_path: Path):
    svc = DealService(tmp_path)

    async def _setup():
        await svc.create_deal("deal_a")
        await svc.create_deal("deal_b")
        await svc.create_deal("deal_c")
        return await svc.portfolio()

    res = asyncio.run(_setup())
    assert res.ok is True
    assert res.data["totals"]["deals"] == 3
    assert {d["deal_id"] for d in res.data["deals"]} == {"deal_a", "deal_b", "deal_c"}


def test_portfolio_via_dispatcher(tmp_path: Path):
    asyncio.run(DealService(tmp_path).create_deal("cbass"))
    d = ABSDispatcher(tmp_path)
    res = asyncio.run(d.dispatch("deal.portfolio", {}))
    assert res["ok"] is True
    assert res["data"]["totals"]["deals"] == 1


# ---------------------------------------------------------------------------
# Selective regeneration
# ---------------------------------------------------------------------------

def test_regeneration_supersedes_old_artifacts(tmp_path: Path):
    _ingest(tmp_path)
    store = DealStore.for_deal_dir(tmp_path / "cbass", init=False)
    store.add_sep_artifact({"deal_id": "cbass", "sep_name": "fees",
                            "value": {"fee_name": "Old Fee"}, "status": "approved"})
    svc = RegenerationService(tmp_path)
    llm = StubLLMClient(responder=lambda p, s: '[{"fee_name": "New Fee", "citation": "Art III p.1"}]')

    res = asyncio.run(svc.regenerate("cbass", "sep:fees", llm=llm,
                                     reason="corrected extraction", actor="reviewer"))
    assert res.ok is True, res.error

    arts = store.list_sep_artifacts("cbass", "fees")
    statuses = {a["status"] for a in arts}
    assert "superseded" in statuses  # old artifact superseded
    assert "pending_review" in statuses  # new artifact pending review


def test_regeneration_logs_correction_event(tmp_path: Path):
    _ingest(tmp_path)
    svc = RegenerationService(tmp_path)
    llm = StubLLMClient(responder=lambda p, s: '[{"fee_name": "X", "citation": "p.1"}]')
    asyncio.run(svc.regenerate("cbass", "sep:fees", llm=llm, reason="test regen", actor="user"))

    events = asyncio.run(GovernanceService(tmp_path).list_corrections("cbass"))
    assert any(e["lifecycle_stage"] == "sep:fees" for e in events.data)


def test_regeneration_unknown_target_fails(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")
    svc = RegenerationService(tmp_path)
    res = asyncio.run(svc.regenerate("cbass", "garbage"))
    assert res.ok is False
    assert "Unknown regeneration target" in res.error


def test_regeneration_via_dispatcher(tmp_path: Path):
    _ingest(tmp_path)
    d = ABSDispatcher(tmp_path)
    llm = StubLLMClient(responder=lambda p, s: '[{"fee_name": "Fee", "citation": "p.1"}]')
    res = asyncio.run(d.dispatch("regenerate", {"deal_id": "cbass", "target": "sep:fees",
                                                "reason": "ui trigger", "actor": "user"}, llm=llm))
    assert res["ok"] is True
