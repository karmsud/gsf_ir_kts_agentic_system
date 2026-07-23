"""
Tests for P2 — model execution loop: ModelRunService drives the deterministic
cashflow engine from artifacts/explicit inputs and produces class-level numbers
that feed the distribution report.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend.abs.services import ModelRunService, ReportingService, SEPService, StubLLMClient
from backend.abs.services.model_run_service import _parse_amount, _parse_rate
from backend.abs.store import DealStore


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def test_parse_rate_from_percent():
    assert abs(_parse_rate("5.02956%") - 0.0502956) < 1e-9
    assert _parse_rate(0.05) == 0.05
    assert _parse_rate(None) == 0.0


def test_parse_amount():
    assert _parse_amount("90,650,000.00") == 90650000.0
    assert _parse_amount("$1,000") == 1000.0
    assert _parse_amount(250) == 250.0


# ---------------------------------------------------------------------------
# ModelRunService — explicit inputs
# ---------------------------------------------------------------------------

def test_run_with_explicit_inputs_produces_results(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")  # init deal
    svc = ModelRunService(tmp_path)
    classes = [
        {"class_name": "A-1", "original_balance": 1_000_000.0, "coupon_rate": 0.06},
        {"class_name": "M-1", "original_balance": 500_000.0, "coupon_rate": 0.08},
    ]
    waterfall = [
        {"step": "int_A", "target": "A-1", "amount_type": "interest"},
        {"step": "prin_A", "target": "A-1", "amount_type": "principal"},
    ]
    monthly = [{"interest_collections": 10_000.0, "principal_collections": 50_000.0, "realized_losses": 0.0}]

    res = asyncio.run(svc.run("cbass", monthly_inputs=monthly, classes_setup=classes,
                              waterfall_rules=waterfall, run_date="2024-09-25"))
    assert res.ok is True, res.error
    results = res.data["results"]
    assert "A-1" in results
    assert results["A-1"]["ending_balance"] == 1_000_000.0
    # A run was persisted.
    store = DealStore.for_deal_dir(tmp_path / "cbass", init=False)
    assert len(store.list_monthly_runs("cbass")) == 1


def test_run_requires_inputs(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")
    svc = ModelRunService(tmp_path)
    res = asyncio.run(svc.run("cbass"))
    assert res.ok is False
    assert "monthly_inputs or csv_path" in res.error


# ---------------------------------------------------------------------------
# ModelRunService — derive classes from approved Certificate artifacts
# ---------------------------------------------------------------------------

def test_run_derives_classes_from_artifacts(tmp_path: Path):
    store = DealStore.for_deal_dir(tmp_path / "cbass")
    store.add_sep_artifact({"deal_id": "cbass", "sep_name": "certificates",
                            "value": {"class_name": "A-1", "original_balance": "90,650,000.00",
                                      "accrual_formula": "5.02956%"}, "citation": "p.1", "status": "approved"})
    store.add_sep_artifact({"deal_id": "cbass", "sep_name": "certificates",
                            "value": {"class_name": "M-1", "original_balance": "16,930,000.00",
                                      "accrual_formula": "6.00%"}, "citation": "p.1", "status": "approved"})
    svc = ModelRunService(tmp_path)
    monthly = [{"interest_collections": 100_000.0, "principal_collections": 200_000.0}]
    res = asyncio.run(svc.run("cbass", monthly_inputs=monthly))
    assert res.ok is True, res.error
    assert set(res.data["results"].keys()) == {"A-1", "M-1"}
    assert res.data["results"]["A-1"]["beginning_balance"] == 90_650_000.0


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def test_run_from_csv(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")
    csv_path = tmp_path / "monthly.csv"
    csv_path.write_text(
        "month,interest_collections,principal_collections,realized_losses\n"
        "1,10000,50000,0\n2,9500,48000,1000\n",
        encoding="utf-8",
    )
    svc = ModelRunService(tmp_path)
    classes = [{"class_name": "A-1", "original_balance": 1_000_000.0, "coupon_rate": 0.06}]
    res = asyncio.run(svc.run("cbass", csv_path=str(csv_path), classes_setup=classes))
    assert res.ok is True, res.error
    assert res.data["total_months"] == 2


# ---------------------------------------------------------------------------
# Full loop: run model → report consumes the stored run
# ---------------------------------------------------------------------------

def test_model_run_feeds_report(tmp_path: Path):
    store = DealStore.for_deal_dir(tmp_path / "cbass")
    store.add_sep_artifact({"deal_id": "cbass", "sep_name": "certificates",
                            "value": {"class_name": "A-1", "cusip": "12489WEX8",
                                      "original_balance": 1_000_000.0, "accrual_formula": "6.00%"},
                            "citation": "p.1", "status": "approved"})
    runner = ModelRunService(tmp_path)
    run = asyncio.run(runner.run("cbass", monthly_inputs=[{"interest_collections": 5000.0, "principal_collections": 20000.0}],
                                 run_date="2024-09-25"))
    assert run.ok is True, run.error

    report = ReportingService(tmp_path)
    rep = asyncio.run(report.generate_statement("cbass", run_id=run.data["run_id"], deal_name="C-BASS"))
    assert rep.ok is True, rep.error
    assert any(r["class_name"] == "A-1" for r in rep.data["rows"])
