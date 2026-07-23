"""
Tests for the SEP extraction engine and lenient JSON parsing.

A scripted StubLLMClient returns JSON per profile so extraction, citation
capture, persistence in pending_review, and the approval workflow are all
exercised offline.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend.abs.services import IngestionService, SEPService, StubLLMClient, extract_items, parse_json_lenient
from backend.abs.services.pdf_extract import extracted_from_pages
from backend.abs.store import DealStore


# ---------------------------------------------------------------------------
# JSON utils
# ---------------------------------------------------------------------------

def test_parse_json_direct():
    assert parse_json_lenient('{"a": 1}') == {"a": 1}


def test_parse_json_in_fence():
    text = "Here you go:\n```json\n[{\"x\": 1}]\n```\nDone."
    assert parse_json_lenient(text) == [{"x": 1}]


def test_parse_json_embedded_in_prose():
    text = 'The answer is [{"k": "v"}] hope that helps'
    assert parse_json_lenient(text) == [{"k": "v"}]


def test_extract_items_from_array_object_and_wrapped():
    assert extract_items('[{"a":1},{"a":2}]') == [{"a": 1}, {"a": 2}]
    assert extract_items('{"a": 1}') == [{"a": 1}]
    assert extract_items('{"items": [{"a": 1}]}', list_key="items") == [{"a": 1}]


def test_extract_items_bad_returns_empty():
    assert extract_items("not json at all") == []


# ---------------------------------------------------------------------------
# SEP service
# ---------------------------------------------------------------------------

PSA_PAGES = [
    "ARTICLE III FEES\n\nThe Servicing Fee equals 0.50% per annum of the pool balance, "
    "payable monthly to the Servicer. The Trustee Fee is $5,000 per year.\n\n",
    "ARTICLE V DISTRIBUTIONS\n\nOn each Distribution Date funds are distributed in priority: "
    "first interest to Class A, then principal.\n\n",
]


def _ingest(tmp_path: Path) -> None:
    ing = IngestionService(tmp_path)
    doc = extracted_from_pages(PSA_PAGES)
    asyncio.run(ing.ingest_document("cbass", extracted=doc, doc_type="PSA"))


def _fees_responder(prompt: str, system: str) -> str:
    if "Servicing Fee" in prompt or "fee" in prompt.lower():
        return json.dumps([
            {"fee_name": "Servicing Fee", "parties": "Servicer", "frequency": "monthly",
             "formula": "0.50% * pool_balance / 12", "citation": "Article III p.1", "confidence": 0.95},
            {"fee_name": "Trustee Fee", "parties": "Trustee", "frequency": "annual",
             "formula": "5000", "citation": "Article III p.1", "confidence": 0.9},
        ])
    return "[]"


def test_run_sep_fees_creates_pending_artifacts(tmp_path: Path):
    _ingest(tmp_path)
    svc = SEPService(tmp_path)
    llm = StubLLMClient(responder=_fees_responder)
    events: list[dict] = []

    res = asyncio.run(svc.run_sep("cbass", "fees", llm, progress=events.append))
    assert res.ok is True, res.error
    assert res.data["items"] == 2

    store = DealStore.for_deal_dir(tmp_path / "cbass", init=False)
    fees = store.list_sep_artifacts("cbass", "fees")
    assert len(fees) == 2
    assert all(f["status"] == "pending_review" for f in fees)
    assert all(f["citation"] for f in fees)
    values = [json.loads(f["value"]) for f in fees]
    assert any(v["fee_name"] == "Servicing Fee" for v in values)
    assert {"in-progress", "done"} == {e["status"] for e in events}


def test_run_all_seps(tmp_path: Path):
    _ingest(tmp_path)
    svc = SEPService(tmp_path)
    # Generic responder: one item with a citation for any profile.
    llm = StubLLMClient(responder=lambda p, s: json.dumps([{"citation": "Article III p.1", "x": 1}]))
    res = asyncio.run(svc.run_all("cbass", llm))
    assert res.ok is True
    assert res.data["total"] >= 6  # one item per core profile
    assert set(res.data["profiles"].keys()) >= {"fees", "certificates", "accounts", "waterfall_rules", "reporting", "term_functions"}


def test_run_sep_unknown_profile_fails(tmp_path: Path):
    _ingest(tmp_path)
    svc = SEPService(tmp_path)
    res = asyncio.run(svc.run_sep("cbass", "nonsense", StubLLMClient()))
    assert res.ok is False
    assert "Unknown SEP" in res.error


def test_sep_approval_workflow_end_to_end(tmp_path: Path):
    _ingest(tmp_path)
    svc = SEPService(tmp_path)
    asyncio.run(svc.run_sep("cbass", "fees", StubLLMClient(responder=_fees_responder)))
    store = DealStore.for_deal_dir(tmp_path / "cbass", init=False)
    art = store.list_sep_artifacts("cbass", "fees")[0]
    assert store.approve_sep_artifact(art["artifact_id"], actor="reviewer") is True
    assert store.get_sep_artifact(art["artifact_id"])["status"] == "approved"
