"""
Tests for ModelService (generate + audit) and ReportingService (statement).

Offline via StubLLMClient. The reporting test asserts the HTML statement and a
real PDF (rendered by the bundled PyMuPDF) are produced.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend.abs.services import ModelService, ReportingService, SEPService, StubLLMClient
from backend.abs.store import DealStore


# ---------------------------------------------------------------------------
# ModelService
# ---------------------------------------------------------------------------

def _seed_contract(tmp_path: Path) -> None:
    store = DealStore.for_deal_dir(tmp_path / "cbass")
    store.add_governing_clause({
        "deal_id": "cbass", "verbatim": "pay interest to Class A",
        "plain_english": "Class A interest = rate/12 * balance",
        "math_formula": "rate/12*balance", "citation": "Art V p.2", "status": "approved",
    })
    store.add_sep_artifact({"deal_id": "cbass", "sep_name": "certificates",
                            "value": {"class_name": "A-1", "cusip": "12489WEX8",
                                      "original_balance": 90650000, "accrual_formula": "5.02956%"},
                            "citation": "Art II p.1", "status": "approved"})


def test_model_generate_stores_source(tmp_path: Path):
    _seed_contract(tmp_path)
    svc = ModelService(tmp_path)
    code = "class WaterfallModel:\n    def run_month(self, inputs):\n        return {}  # cite: Art V p.2\n"
    llm = StubLLMClient(responder=lambda p, s: "```python\n" + code + "```")
    events: list[dict] = []

    res = asyncio.run(svc.generate("cbass", llm, progress=events.append))
    assert res.ok is True, res.error

    store = DealStore.for_deal_dir(tmp_path / "cbass", init=False)
    model = store.get_latest_payment_model("cbass")
    assert model is not None
    assert "class WaterfallModel" in model["python_source"]
    assert "```" not in model["python_source"]  # fence stripped
    assert model["validation_status"] == "pending_review"
    assert {"in-progress", "done"} == {e["status"] for e in events}


def test_model_audit_pass_sets_approved(tmp_path: Path):
    _seed_contract(tmp_path)
    svc = ModelService(tmp_path)
    asyncio.run(svc.generate("cbass", StubLLMClient(responder=lambda p, s: "class WaterfallModel: pass")))

    audit_json = json.dumps({"checks": [{"item": "Class A interest", "pass": True, "source": "Art V p.2", "note": "ok"}], "verdict": "pass"})
    res = asyncio.run(svc.audit("cbass", StubLLMClient(responder=lambda p, s: audit_json)))
    assert res.ok is True
    assert res.data["verdict"] == "pass"

    store = DealStore.for_deal_dir(tmp_path / "cbass", init=False)
    model = store.get_latest_payment_model("cbass")
    assert model["validation_status"] == "approved"
    assert json.loads(model["audit_report"])["verdict"] == "pass"


def test_model_audit_without_model_fails(tmp_path: Path):
    DealStore.for_deal_dir(tmp_path / "cbass")  # empty deal
    svc = ModelService(tmp_path)
    res = asyncio.run(svc.audit("cbass", StubLLMClient()))
    assert res.ok is False
    assert "No payment model" in res.error


# ---------------------------------------------------------------------------
# ReportingService
# ---------------------------------------------------------------------------

def test_generate_statement_html_and_pdf(tmp_path: Path):
    # Seed certificate metadata so CUSIP / original balance appear.
    store = DealStore.for_deal_dir(tmp_path / "cbass")
    store.add_sep_artifact({"deal_id": "cbass", "sep_name": "certificates",
                            "value": {"class_name": "A-1", "cusip": "12489WEX8",
                                      "original_balance": 90650000, "accrual_formula": "5.02956%"},
                            "citation": "p.1", "status": "approved"})

    svc = ReportingService(tmp_path)
    results = {"A-1": {"interest": 100.0, "principal": 250.0, "ending_balance": 90649650.0, "beginning_balance": 90650000.0}}
    events: list[dict] = []
    res = asyncio.run(svc.generate_statement(
        "cbass", results=results, distribution_date="2024-09-25",
        deal_name="C-BASS Mortgage Loan ABS", series="2002-CB4", progress=events.append,
    ))
    assert res.ok is True, res.error
    assert res.data["pdf_generated"] is True
    assert Path(res.data["pdf_path"]).exists()
    assert Path(res.data["html_path"]).exists()

    html = Path(res.data["html_path"]).read_text()
    assert "Distribution Statement" in html
    assert "12489WEX8" in html       # CUSIP from certificate metadata
    assert "2002-CB4" in html
    assert "90,650,000.00" in html    # formatted original face
    assert {"in-progress", "done"} == {e["status"] for e in events}


def test_generate_statement_from_stored_run(tmp_path: Path):
    store = DealStore.for_deal_dir(tmp_path / "cbass")
    rid = store.add_monthly_run({"deal_id": "cbass", "run_date": "2024-09-25",
                                 "results": {"M-1": {"interest": 17128.51, "principal": 4032.71, "ending_balance": 1048970.52}}})
    svc = ReportingService(tmp_path)
    res = asyncio.run(svc.generate_statement("cbass", run_id=rid, deal_name="C-BASS"))
    assert res.ok is True
    assert any(r["class_name"] == "M-1" for r in res.data["rows"])
