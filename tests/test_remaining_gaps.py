"""
Tests for the remaining-gap backend services:
 - Schema v4 (assumptions, agent_results, jobs, run_details tables)
 - AssumptionsService (Layer B.4: CPR/CDR scenario library)
 - ProjectionService (Layer A.5: multi-scenario cashflow + regression baseline)
 - TaxService (Layer A.8: OID/NPV/8-K outputs)
 - JobQueueService (Layer B.12: async job queue)
 - AgentService.get_results (stored agent outputs)
 - ModelRunService run_details (waterfall trace)
 - New dispatcher commands (assumptions.*, projection.*, tax.*, jobs.*, agent.results, run.details)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend.abs.services.assumptions_service import AssumptionsService
from backend.abs.services.dispatcher import ABSDispatcher
from backend.abs.services.agent_service import AgentService
from backend.abs.services.job_queue_service import JobQueueService
from backend.abs.services.model_run_service import ModelRunService
from backend.abs.services.projection_service import ProjectionService
from backend.abs.services.tax_service import TaxService
from backend.abs.services.deal_service import DealService
from backend.abs.store import DealStore, SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Schema v4 validation
# ---------------------------------------------------------------------------

def test_schema_v4_all_tables(tmp_path: Path):
    store = DealStore.for_deal_dir(tmp_path / "cbass")
    assert store.schema_version() == 4
    with store._connect() as conn:
        tables = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    for expected in ("assumptions", "agent_results", "jobs", "run_details"):
        assert expected in tables, f"Missing table: {expected}"


# ---------------------------------------------------------------------------
# AssumptionsService (Layer B.4)
# ---------------------------------------------------------------------------

def test_assumptions_seed_defaults(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")
    svc = AssumptionsService(tmp_path)
    res = asyncio.run(svc.seed_defaults("cbass"))
    assert res.ok is True
    assert res.data["seeded"] > 0
    assert "base" in res.data["scenarios"]
    assert "stress_high_cdr" in res.data["scenarios"]


def test_assumptions_idempotent_seed(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")
    svc = AssumptionsService(tmp_path)
    asyncio.run(svc.seed_defaults("cbass"))
    res2 = asyncio.run(svc.seed_defaults("cbass"))
    assert res2.ok and res2.data["seeded"] == 0  # idempotent


def test_assumptions_list_and_scenarios(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")
    svc = AssumptionsService(tmp_path)
    asyncio.run(svc.seed_defaults("cbass"))
    all_assums = asyncio.run(svc.list("cbass"))
    assert all_assums.ok and len(all_assums.data) >= 9  # 3 scenarios × 3+ types
    scenarios = asyncio.run(svc.list_scenarios("cbass"))
    assert {"base", "stress_high_cdr", "stress_high_prepay"} <= set(scenarios.data)


def test_assumptions_add_custom(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")
    svc = AssumptionsService(tmp_path)
    res = asyncio.run(svc.add("cbass", scenario_name="custom_scenario",
                               assumption_type="cpr", value={"rate": 0.25, "description": "25% CPR"}))
    assert res.ok and res.data["assumption_id"]
    listed = asyncio.run(svc.list("cbass", "custom_scenario"))
    assert listed.ok and any(a["assumption_type"] == "cpr" for a in listed.data)


def test_assumptions_via_dispatcher(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")
    d = ABSDispatcher(tmp_path)
    seed = asyncio.run(d.dispatch("assumptions.seed", {"deal_id": "cbass"}))
    assert seed["ok"]
    scenarios = asyncio.run(d.dispatch("assumptions.scenarios", {"deal_id": "cbass"}))
    assert scenarios["ok"] and "base" in scenarios["data"]


# ---------------------------------------------------------------------------
# ProjectionService (Layer A.5)
# ---------------------------------------------------------------------------

def _seed_certs(tmp_path: Path) -> None:
    store = DealStore.for_deal_dir(tmp_path / "cbass")
    store.add_sep_artifact({"deal_id": "cbass", "sep_name": "certificates",
                            "value": {"class_name": "A-1", "original_balance": "1000000.00", "accrual_formula": "6.00%"},
                            "citation": "p.1", "status": "approved"})
    store.add_sep_artifact({"deal_id": "cbass", "sep_name": "certificates",
                            "value": {"class_name": "M-1", "original_balance": "500000.00", "accrual_formula": "8.00%"},
                            "citation": "p.2", "status": "approved"})


def test_projection_run_base_scenario(tmp_path: Path):
    _seed_certs(tmp_path)
    asyncio.run(AssumptionsService(tmp_path).seed_defaults("cbass"))
    svc = ProjectionService(tmp_path)
    events: list[dict] = []
    res = asyncio.run(svc.run("cbass", scenarios=["base"], months=6, progress=events.append))
    assert res.ok is True, res.error
    assert "base" in res.data["scenarios"]
    assert res.data["scenarios"]["base"]["months"]
    assert len(res.data["scenarios"]["base"]["months"]) == 6
    assert {"in-progress", "done"} <= {e["status"] for e in events}


def test_projection_multi_scenario(tmp_path: Path):
    _seed_certs(tmp_path)
    asyncio.run(AssumptionsService(tmp_path).seed_defaults("cbass"))
    svc = ProjectionService(tmp_path)
    res = asyncio.run(svc.run("cbass", months=3))
    assert res.ok
    assert len(res.data["scenarios"]) >= 2  # at least base + stress


def test_projection_results_persisted(tmp_path: Path):
    _seed_certs(tmp_path)
    asyncio.run(AssumptionsService(tmp_path).seed_defaults("cbass"))
    asyncio.run(ProjectionService(tmp_path).run("cbass", scenarios=["base"], months=3))
    results = asyncio.run(ProjectionService(tmp_path).get_results("cbass", "base"))
    assert results.ok and results.data


def test_projection_regression_baseline(tmp_path: Path):
    _seed_certs(tmp_path)
    asyncio.run(AssumptionsService(tmp_path).seed_defaults("cbass"))
    svc = ProjectionService(tmp_path)
    asyncio.run(svc.run("cbass", scenarios=["base"], months=3))
    save = asyncio.run(svc.save_baseline("cbass", "base"))
    assert save.ok and save.data["saved"]
    comp = asyncio.run(svc.compare_baseline("cbass", "base"))
    assert comp.ok
    assert "diffs" in comp.data
    assert comp.data["has_drift"] is False  # same run, no drift


def test_projection_via_dispatcher(tmp_path: Path):
    _seed_certs(tmp_path)
    d = ABSDispatcher(tmp_path)
    asyncio.run(d.dispatch("assumptions.seed", {"deal_id": "cbass"}))
    res = asyncio.run(d.dispatch("projection.run", {"deal_id": "cbass", "scenarios": ["base"], "months": 3}))
    assert res["ok"] is True
    results = asyncio.run(d.dispatch("projection.results", {"deal_id": "cbass", "scenario_name": "base"}))
    assert results["ok"] and results["data"]


# ---------------------------------------------------------------------------
# TaxService (Layer A.8)
# ---------------------------------------------------------------------------

def test_tax_requires_projection_first(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")
    svc = TaxService(tmp_path)
    res = asyncio.run(svc.generate("cbass"))
    assert res.ok is False
    assert "No projection results" in res.error


def test_tax_generates_oid_npv_outputs(tmp_path: Path):
    _seed_certs(tmp_path)
    asyncio.run(AssumptionsService(tmp_path).seed_defaults("cbass"))
    asyncio.run(ProjectionService(tmp_path).run("cbass", scenarios=["base"], months=6))
    svc = TaxService(tmp_path)
    events: list[dict] = []
    res = asyncio.run(svc.generate("cbass", discount_rate=0.05, progress=events.append))
    assert res.ok is True, res.error
    assert "oid_outputs" in res.data
    assert "npv_outputs" in res.data
    assert res.data["npv_outputs"][0]["class_name"] in ("A-1", "M-1")
    assert Path(res.data["json_path"]).exists()
    assert Path(res.data["summary_path"]).exists()
    summary = Path(res.data["summary_path"]).read_text()
    assert "TAX SUPPORT OUTPUT" in summary
    assert {"in-progress", "done"} == {e["status"] for e in events}


def test_tax_via_dispatcher(tmp_path: Path):
    _seed_certs(tmp_path)
    asyncio.run(AssumptionsService(tmp_path).seed_defaults("cbass"))
    asyncio.run(ProjectionService(tmp_path).run("cbass", scenarios=["base"], months=3))
    d = ABSDispatcher(tmp_path)
    res = asyncio.run(d.dispatch("tax.generate", {"deal_id": "cbass"}))
    assert res["ok"] is True
    tax_res = asyncio.run(d.dispatch("tax.results", {"deal_id": "cbass"}))
    assert tax_res["ok"] and tax_res["data"]


# ---------------------------------------------------------------------------
# JobQueueService (Layer B.12)
# ---------------------------------------------------------------------------

def test_job_enqueue_and_get(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")
    svc = JobQueueService(tmp_path)
    enq = asyncio.run(svc.enqueue("deal.status", {"deal_id": "cbass"}, actor="user"))
    assert enq.ok
    job_id = enq.data["job_id"]
    assert enq.data["status"] == "queued"
    job = asyncio.run(svc.get_job(job_id, "cbass"))
    assert job.ok and job.data["command"] == "deal.status"


def test_job_update_status(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")
    svc = JobQueueService(tmp_path)
    enq = asyncio.run(svc.enqueue("model.run", {"deal_id": "cbass"}, actor="user"))
    job_id = enq.data["job_id"]
    store = DealStore.for_deal_dir(tmp_path / "cbass", init=False)
    store.update_job(job_id, status="done", result={"classes": 2})
    job = asyncio.run(svc.get_job(job_id, "cbass"))
    assert job.data["status"] == "done"
    assert job.data["finished_at"]


def test_job_list_by_status(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")
    svc = JobQueueService(tmp_path)
    asyncio.run(svc.enqueue("deal.status", {"deal_id": "cbass"}))
    asyncio.run(svc.enqueue("model.run", {"deal_id": "cbass"}))
    listed = asyncio.run(svc.list_jobs("cbass", status="queued"))
    assert listed.ok and len(listed.data) == 2


def test_job_cancel(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")
    svc = JobQueueService(tmp_path)
    enq = asyncio.run(svc.enqueue("deal.status", {"deal_id": "cbass"}))
    cancel = asyncio.run(svc.cancel_job(enq.data["job_id"], "cbass"))
    assert cancel.ok and cancel.data["cancelled"] is True
    job = asyncio.run(svc.get_job(enq.data["job_id"], "cbass"))
    assert job.data["status"] == "cancelled"


def test_jobs_via_dispatcher(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")
    d = ABSDispatcher(tmp_path)
    enq = asyncio.run(d.dispatch("jobs.enqueue", {"command": "deal.status", "params": {"deal_id": "cbass"}}))
    assert enq["ok"]
    listed = asyncio.run(d.dispatch("jobs.list", {"deal_id": "cbass"}))
    assert listed["ok"] and listed["data"]


# ---------------------------------------------------------------------------
# AgentService.get_results
# ---------------------------------------------------------------------------

def test_agent_results_stored_and_retrieved(tmp_path: Path):
    _seed_certs(tmp_path)
    svc = AgentService(tmp_path)
    res = asyncio.run(svc.run_agent("cbass", "stress",
                                    task={"months": 2, "scenarios": [{"name": "base", "overrides": {}}]}))
    assert res.ok is True
    results = asyncio.run(svc.get_results("cbass", "stress"))
    assert results.ok and results.data


def test_agent_results_via_dispatcher(tmp_path: Path):
    _seed_certs(tmp_path)
    d = ABSDispatcher(tmp_path)
    asyncio.run(d.dispatch("agent.run", {"deal_id": "cbass", "agent_name": "stress",
                                         "task": {"months": 2, "scenarios": [{"name": "base", "overrides": {}}]}}))
    res = asyncio.run(d.dispatch("agent.results", {"deal_id": "cbass", "agent_name": "stress"}))
    assert res["ok"] and res["data"]


# ---------------------------------------------------------------------------
# Monthly run details (waterfall trace)
# ---------------------------------------------------------------------------

def test_run_details_persisted_after_model_run(tmp_path: Path):
    store = DealStore.for_deal_dir(tmp_path / "cbass")
    store.add_sep_artifact({"deal_id": "cbass", "sep_name": "certificates",
                            "value": {"class_name": "A-1", "original_balance": "1000000.00", "accrual_formula": "6.00%"},
                            "citation": "p.1", "status": "approved"})
    svc = ModelRunService(tmp_path)
    monthly = [{"interest_collections": 5000.0, "principal_collections": 20000.0, "realized_losses": 0.0}]
    run = asyncio.run(svc.run("cbass", monthly_inputs=monthly, run_date="2024-09-25"))
    assert run.ok is True
    details = store.get_run_details(run.data["run_id"])
    assert len(details) >= 1
    assert all(r.get("class_name") for r in details)


def test_run_details_via_dispatcher(tmp_path: Path):
    store = DealStore.for_deal_dir(tmp_path / "cbass")
    store.add_sep_artifact({"deal_id": "cbass", "sep_name": "certificates",
                            "value": {"class_name": "A-1", "original_balance": "500000.00", "accrual_formula": "5.00%"},
                            "citation": "p.1", "status": "approved"})
    asyncio.run(ModelRunService(tmp_path).run("cbass",
        monthly_inputs=[{"interest_collections": 2000.0, "principal_collections": 10000.0}], run_date="2024-09"))
    d = ABSDispatcher(tmp_path)
    res = asyncio.run(d.dispatch("run.details", {"deal_id": "cbass"}))
    assert res["ok"] and res["data"]
