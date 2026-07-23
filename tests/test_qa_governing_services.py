"""
Tests for GoverningDocService and QAService (Q&A + Explainability Traceback).

Everything runs offline with a scripted StubLLMClient.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend.abs.services import (
    DefinitionService,
    GoverningDocService,
    IngestionService,
    QAService,
    SEPService,
    StubLLMClient,
    capitalized_terms,
)
from backend.abs.services.pdf_extract import extracted_from_pages
from backend.abs.store import DealStore


PAGES = [
    'ARTICLE I DEFINITIONS\n\n"Available Funds" means the Net Interest plus principal.\n\n'
    '"Net Interest" means the Stated Interest less the Servicing Fee.\n\n',
    "ARTICLE V DISTRIBUTIONS\n\nOn each Distribution Date, the Trustee shall pay Available Funds "
    "in priority: first, interest to Class A; second, principal to Class A.\n\n",
]


def _setup_deal(tmp_path: Path) -> None:
    doc = extracted_from_pages(PAGES)
    asyncio.run(IngestionService(tmp_path).ingest_document("cbass", extracted=doc, doc_type="PSA"))
    asyncio.run(DefinitionService(tmp_path).build_definitions("cbass", text=doc.text, extracted=doc, resolve=False))


# ---------------------------------------------------------------------------
# capitalized_terms helper
# ---------------------------------------------------------------------------

def test_capitalized_terms_detection():
    terms = capitalized_terms("The Trustee shall pay Available Funds to Class A.")
    assert "Available Funds" in terms
    assert "Trustee" in terms


# ---------------------------------------------------------------------------
# GoverningDocService
# ---------------------------------------------------------------------------

def test_governing_doc_generation(tmp_path: Path):
    _setup_deal(tmp_path)
    svc = GoverningDocService(tmp_path)

    def responder(prompt: str, system: str) -> str:
        return json.dumps({
            "plain_english": "Each Distribution Date, pay interest then principal to Class A.",
            "math_formula": "interest = rate/12 * balance",
            "code_hint": "pay(class_a, interest); pay(class_a, principal)",
        })

    res = asyncio.run(svc.generate("cbass", StubLLMClient(responder=responder)))
    assert res.ok is True, res.error
    assert res.data["clauses"] >= 1

    store = DealStore.for_deal_dir(tmp_path / "cbass", init=False)
    clauses = store.list_governing_clauses("cbass")
    assert clauses[0]["plain_english"].startswith("Each Distribution Date")
    assert clauses[0]["math_formula"]
    assert clauses[0]["citation"]
    # resolved_terms enriched from definitions (Available Funds appears in the clause).
    rt = json.loads(clauses[0]["resolved_terms"])
    assert "Available Funds" in rt


# ---------------------------------------------------------------------------
# QAService — ask
# ---------------------------------------------------------------------------

def test_qa_ask_returns_answer_with_citations(tmp_path: Path):
    _setup_deal(tmp_path)
    svc = QAService(tmp_path)

    def responder(prompt: str, system: str) -> str:
        assert "EVIDENCE:" in prompt  # grounded
        return "Interest is paid to Class A first [Article V p.2]."

    res = asyncio.run(svc.ask("cbass", "What is paid first on the distribution date?", StubLLMClient(responder=responder)))
    assert res.ok is True, res.error
    assert "Class A" in res.data["answer"]
    assert len(res.data["citations"]) >= 1
    assert all("citation" in c for c in res.data["citations"])


def test_qa_ask_includes_resolved_terms(tmp_path: Path):
    _setup_deal(tmp_path)
    svc = QAService(tmp_path)
    captured = {}

    def responder(prompt: str, system: str) -> str:
        captured["prompt"] = prompt
        return "answer"

    asyncio.run(svc.ask("cbass", "How are Available Funds computed?", StubLLMClient(responder=responder)))
    # The defined term in the question is surfaced into the prompt.
    assert "Available Funds" in captured["prompt"]


# ---------------------------------------------------------------------------
# QAService — explain (the traceback)
# ---------------------------------------------------------------------------

def test_explain_assembles_evidence_bundle(tmp_path: Path):
    _setup_deal(tmp_path)
    # Add a fees SEP artifact + a governing clause + a monthly run so the ladder has rungs.
    sep = SEPService(tmp_path)
    asyncio.run(sep.run_sep("cbass", "fees", StubLLMClient(
        responder=lambda p, s: json.dumps([{"fee_name": "Servicing Fee", "formula": "0.5%", "citation": "Art III p.1", "interest": True}])
    )))
    store = DealStore.for_deal_dir(tmp_path / "cbass", init=False)
    store.add_governing_clause({
        "deal_id": "cbass", "verbatim": "pay interest to Class A",
        "plain_english": "Class A interest = rate/12 * balance",
        "math_formula": "rate/12*balance", "citation": "Art V p.2",
    })
    store.add_monthly_run({"deal_id": "cbass", "run_date": "2024-09-25",
                           "results": {"Class A": {"interest": 100.0}}})

    svc = QAService(tmp_path)
    captured = {}

    def responder(prompt: str, system: str) -> str:
        captured["prompt"] = prompt
        return "Class A interest of 100 = rate/12 * balance [Art V p.2], using Servicing Fee [Art III p.1]."

    res = asyncio.run(svc.explain("cbass", "Class A interest", StubLLMClient(responder=responder)))
    assert res.ok is True, res.error
    bundle = res.data["evidence"]
    # The ladder pulled in artifacts, clauses, a run, and source excerpts.
    assert bundle["sep_artifacts"]
    assert bundle["governing_clauses"]
    assert bundle["monthly_runs"]
    assert "PAYMENT MODEL" in captured["prompt"] or "GOVERNING CLAUSES" in captured["prompt"]
    assert "100" in res.data["answer"]
