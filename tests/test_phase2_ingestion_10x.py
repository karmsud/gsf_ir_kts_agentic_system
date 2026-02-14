from __future__ import annotations

from pathlib import Path

import pytest

from backend.agents import IngestionAgent
from config import load_config


def _mk(path: Path, text: str = "sample"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_ingestion_10_scenarios(tmp_path: Path):
    cfg = load_config()
    cfg.knowledge_base_path = str(tmp_path / "kb")
    cfg.chroma_persist_dir = str(tmp_path / "kb" / "vectors" / "chroma")

    agent = IngestionAgent(cfg)

    md = tmp_path / "guide.md"
    txt = tmp_path / "guide.txt"
    html = tmp_path / "guide.html"
    empty = tmp_path / "empty.md"
    unsupported = tmp_path / "bad.xlsx"

    _mk(md, "# Header\n\nToolX onboarding support")
    _mk(txt, "ToolY deployment runbook")
    _mk(html, "<html><body><h1>ToolZ</h1><p>incident support</p><img src='x.png' /></body></html>")
    _mk(empty, "   \n\n ")
    _mk(unsupported, "unsupported")

    results = [
        agent.execute({"path": str(md)}),
        agent.execute({"path": str(txt)}),
        agent.execute({"path": str(html)}),
        agent.execute({"path": str(empty)}),
        agent.execute({"path": str(unsupported)}),
        agent.execute({"path": str(tmp_path / "missing.md")}),
        agent.execute({"path": str(md), "doc_id": "doc_custom_1"}),
        agent.execute({"path": str(md), "version": 2}),
        agent.execute({"path": str(md)}),
        agent.execute({"path": str(txt)}),
    ]

    assert len(results) == 10
    assert results[0].success and results[0].data["chunk_count"] >= 1
    assert results[1].success
    assert results[2].success
    assert not results[3].success
    assert not results[4].success
    assert not results[5].success
    assert results[6].success and results[6].data["document"].doc_id == "doc_custom_1"
    assert results[7].success and results[7].data["document"].version == 2
    assert results[8].success
    assert results[9].success
