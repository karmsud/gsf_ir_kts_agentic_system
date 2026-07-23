"""
Tests for P3 — citation jump-to-source backend (store.get_source_context +
dispatcher source.get command).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.abs.services.dispatcher import ABSDispatcher
from backend.abs.store import DealStore


def _seed(tmp_path: Path) -> tuple[DealStore, str, str]:
    store = DealStore.for_deal_dir(tmp_path / "cbass")
    doc_id = store.add_document({"deal_id": "cbass", "doc_type": "PSA", "title": "C-BASS PSA",
                                 "source_path": "/deals/cbass/source/PSA.pdf"})
    store.add_sections([{"section_id": "s1", "doc_id": doc_id, "section_path": "Article V",
                         "title": "Distributions", "ordinal": 0, "page_start": 62, "page_end": 64}])
    store.add_chunks([{"chunk_id": "c1", "doc_id": doc_id, "section_id": "s1", "ordinal": 0,
                       "text": "On each Distribution Date, pay interest to Class A.",
                       "page_start": 62, "page_end": 62}])
    return store, doc_id, "c1"


def test_get_source_context_by_chunk(tmp_path: Path):
    store, _, chunk_id = _seed(tmp_path)
    ctx = store.get_source_context(chunk_id=chunk_id)
    assert ctx is not None
    assert ctx["text"].startswith("On each Distribution Date")
    assert ctx["page_start"] == 62
    assert ctx["section_path"] == "Article V"
    assert ctx["doc_title"] == "C-BASS PSA"
    assert ctx["source_path"].endswith("PSA.pdf")


def test_get_source_context_by_section(tmp_path: Path):
    store, _, _ = _seed(tmp_path)
    ctx = store.get_source_context(section_id="s1")
    assert ctx is not None
    assert "Class A" in ctx["text"]
    assert ctx["page_start"] == 62


def test_get_source_context_missing(tmp_path: Path):
    store, _, _ = _seed(tmp_path)
    assert store.get_source_context(chunk_id="nope") is None


def test_dispatcher_source_get(tmp_path: Path):
    _seed(tmp_path)
    d = ABSDispatcher(tmp_path)
    res = asyncio.run(d.dispatch("source.get", {"deal_id": "cbass", "chunk_id": "c1"}))
    assert res["ok"] is True
    assert res["data"]["page_start"] == 62


def test_dispatcher_source_get_not_found(tmp_path: Path):
    _seed(tmp_path)
    d = ABSDispatcher(tmp_path)
    res = asyncio.run(d.dispatch("source.get", {"deal_id": "cbass", "chunk_id": "missing"}))
    assert res["ok"] is False
