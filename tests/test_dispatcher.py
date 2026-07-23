"""
Integration tests for ABSDispatcher — the single async gateway the UI calls.

Includes a full end-to-end pipeline driven entirely through dispatch commands,
proving the services compose into one coherent system.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend.abs.services.dispatcher import ABSDispatcher
from backend.abs.services.llm_client import StubLLMClient


PAGES = [
    'ARTICLE I DEFINITIONS\n\n"Available Funds" means the Net Interest plus principal.\n\n'
    '"Net Interest" means the Stated Interest less the Servicing Fee.\n\n',
    "ARTICLE V DISTRIBUTIONS\n\nOn each Distribution Date the Trustee shall pay Available Funds: "
    "first interest to Class A, then principal. The Servicing Fee is 0.50% per annum.\n\n",
]


def _smart_llm() -> StubLLMClient:
    """A responder that returns plausible JSON/code depending on the prompt."""

    def responder(prompt: str, system: str) -> str:
        s = (system or "").lower()
        if "extraction agent" in s:  # SEP
            return json.dumps([{"citation": "Article V p.2", "name": "x", "confidence": 0.9}])
        if "operational specification" in s:  # governing doc
            return json.dumps({"plain_english": "pay interest then principal",
                                "math_formula": "rate/12*bal", "code_hint": "pay()"})
        if "model engineer" in s:  # model gen
            return "class WaterfallModel:\n    def run_month(self, inputs):\n        return {}\n"
        if "model auditor" in s:
            return json.dumps({"checks": [{"item": "interest", "pass": True, "source": "p.2", "note": ""}], "verdict": "pass"})
        if "explainability" in s:
            return "Class A interest = rate/12 * balance [Article V p.2]."
        if "analyst" in s and "rewrite" in s:  # resolution
            return "resolved meaning"
        return "ok"

    return StubLLMClient(responder=responder)


def test_unknown_command(tmp_path: Path):
    d = ABSDispatcher(tmp_path)
    res = asyncio.run(d.dispatch("does.not.exist", {}))
    assert res["ok"] is False
    assert "Unknown command" in res["error"]


def test_missing_param(tmp_path: Path):
    d = ABSDispatcher(tmp_path)
    res = asyncio.run(d.dispatch("deal.status", {}))
    assert res["ok"] is False
    assert "Missing required param" in res["error"]


def test_llm_required_command_without_llm(tmp_path: Path):
    d = ABSDispatcher(tmp_path)
    asyncio.run(d.dispatch("deal.create", {"deal_id": "x"}))
    res = asyncio.run(d.dispatch("qa.ask", {"deal_id": "x", "question": "?"}))
    assert res["ok"] is False
    assert "requires an LLM" in res["error"]


def test_full_pipeline_through_dispatcher(tmp_path: Path):
    d = ABSDispatcher(tmp_path)
    llm = _smart_llm()

    async def run():
        # 1. Create deal.
        assert (await d.dispatch("deal.create", {"deal_id": "cbass", "deal_name": "C-BASS", "series": "2002-CB4"}))["ok"]
        # 2. Ingest (synthetic pages).
        ing = await d.dispatch("ingest.document", {"deal_id": "cbass", "pages": PAGES, "doc_type": "PSA"})
        assert ing["ok"], ing["error"]
        assert ing["data"]["sections"] >= 1
        # 3. Definitions + resolution.
        defs = await d.dispatch("definitions.build", {"deal_id": "cbass", "text": "".join(PAGES), "resolve": True}, llm=llm)
        assert defs["ok"], defs["error"]
        assert defs["data"]["terms"] >= 2
        # 4. Definition tree for a top-level term.
        top = await d.dispatch("definitions.top_level", {"deal_id": "cbass"})
        assert top["ok"] and len(top["data"]) >= 1
        tree = await d.dispatch("definitions.tree", {"deal_id": "cbass", "term_id": top["data"][0]["term_id"]})
        assert tree["ok"] and "children" in tree["data"]
        # 5. SEPs.
        sep = await d.dispatch("sep.run", {"deal_id": "cbass", "sep_name": "fees"}, llm=llm)
        assert sep["ok"], sep["error"]
        arts = await d.dispatch("sep.list", {"deal_id": "cbass", "sep_name": "fees"})
        assert arts["ok"] and len(arts["data"]) >= 1
        # 6. Approve an artifact (human in the loop).
        appr = await d.dispatch("sep.approve", {"deal_id": "cbass", "artifact_id": arts["data"][0]["artifact_id"], "actor": "reviewer"})
        assert appr["ok"] and appr["data"] is True
        # 7. Governing doc.
        gov = await d.dispatch("governing.generate", {"deal_id": "cbass"}, llm=llm)
        assert gov["ok"], gov["error"]
        # 8. Model generate + audit.
        gen = await d.dispatch("model.generate", {"deal_id": "cbass"}, llm=llm)
        assert gen["ok"], gen["error"]
        aud = await d.dispatch("model.audit", {"deal_id": "cbass"}, llm=llm)
        assert aud["ok"] and aud["data"]["verdict"] == "pass"
        # 9. Report.
        rep = await d.dispatch("report.generate", {"deal_id": "cbass", "results": {"A-1": {"interest": 100.0, "principal": 50.0, "ending_balance": 900.0}}, "distribution_date": "2024-09-25", "deal_name": "C-BASS"})
        assert rep["ok"], rep["error"]
        # 10. Q&A + explainability traceback.
        qa = await d.dispatch("qa.ask", {"deal_id": "cbass", "question": "What is paid first?"}, llm=llm)
        assert qa["ok"] and qa["data"]["answer"]
        ex = await d.dispatch("qa.explain", {"deal_id": "cbass", "target": "Class A interest"}, llm=llm)
        assert ex["ok"] and ex["data"]["answer"]
        # 11. Audit log populated.
        al = await d.dispatch("audit.list", {"deal_id": "cbass"})
        assert al["ok"] and len(al["data"]) >= 5

    asyncio.run(run())


def test_progress_events_forwarded(tmp_path: Path):
    d = ABSDispatcher(tmp_path)
    asyncio.run(d.dispatch("deal.create", {"deal_id": "cbass"}))
    events: list[dict] = []
    res = asyncio.run(d.dispatch("ingest.document", {"deal_id": "cbass", "pages": PAGES}, progress=events.append))
    assert res["ok"]
    assert {"extract", "sections", "store"}.issubset({e["stage"] for e in events})
