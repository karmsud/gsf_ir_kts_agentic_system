"""
Tests for PDF page tracking and the IngestionService.

The PDF extraction is tested with synthetic page text (no real PDF needed);
the ingestion service is driven with a pre-built ExtractedDoc so section
detection, page citation, chunking, and persistence are all exercised.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.abs.services import IngestionService, char_to_page, extracted_from_pages
from backend.abs.store import DealStore


# ---------------------------------------------------------------------------
# Page mapping
# ---------------------------------------------------------------------------

def test_char_to_page_basic():
    # page 1 = [0,10), page 2 = [10,20), page 3 = [20,..)
    offsets = [0, 10, 20]
    assert char_to_page(0, offsets) == 1
    assert char_to_page(9, offsets) == 1
    assert char_to_page(10, offsets) == 2
    assert char_to_page(25, offsets) == 3


def test_char_to_page_empty_defaults_to_one():
    assert char_to_page(5, []) == 1


def test_extracted_from_pages_builds_offsets():
    doc = extracted_from_pages(["aaaa", "bbbb", "cc"])
    assert doc.page_count == 3
    assert doc.page_offsets == [0, 4, 8]
    assert doc.char_to_page(5) == 2
    assert doc.text == "aaaabbbbcc"


# ---------------------------------------------------------------------------
# Ingestion service
# ---------------------------------------------------------------------------

def _sample_psa_pages() -> list[str]:
    page1 = (
        "ARTICLE I  DEFINITIONS\n\n"
        '"Available Funds" means the amounts on deposit.\n\n'
        '"Distribution Date" means the 25th day of each month.\n\n'
    )
    page2 = (
        "ARTICLE V  DISTRIBUTIONS\n\n"
        "On each Distribution Date, the Trustee shall distribute Available Funds "
        "in the following order of priority.\n\n"
    )
    return [page1, page2]


def test_ingest_creates_document_sections_chunks(tmp_path: Path):
    svc = IngestionService(tmp_path)
    doc = extracted_from_pages(_sample_psa_pages())
    events: list[dict] = []

    async def _run():
        return await svc.ingest_document(
            "cbass", extracted=doc, doc_type="PSA", title="C-BASS PSA",
            progress=events.append,
        )

    res = asyncio.run(_run())
    assert res.ok is True, res.error
    assert res.data["pages"] == 2
    assert res.data["sections"] >= 1
    assert res.data["chunks"] >= 1

    # Progress events emitted for the animated UI.
    stages = {e["stage"] for e in events}
    assert {"extract", "sections", "store"}.issubset(stages)

    # Persisted with page citations.
    store = DealStore.for_deal_dir(tmp_path / "cbass", init=False)
    docs = store.list_documents("cbass")
    assert len(docs) == 1
    sections = store.list_sections(docs[0]["doc_id"])
    assert all(s["page_start"] >= 1 for s in sections)
    chunks = store.list_chunks(docs[0]["doc_id"])
    assert all(c["page_start"] >= 1 for c in chunks)


def test_ingest_requires_source(tmp_path: Path):
    svc = IngestionService(tmp_path)
    res = asyncio.run(svc.ingest_document("d1"))
    assert res.ok is False
    assert "pdf_path or extracted" in res.error


def test_ingest_writes_audit(tmp_path: Path):
    svc = IngestionService(tmp_path)
    doc = extracted_from_pages(_sample_psa_pages())
    asyncio.run(svc.ingest_document("cbass", extracted=doc))
    store = DealStore.for_deal_dir(tmp_path / "cbass", init=False)
    audit = store.list_audit()
    assert any(a["action"] == "ingest_document" for a in audit)
