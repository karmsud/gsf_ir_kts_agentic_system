"""
Tests for P1 — hybrid retrieval: embeddings (HashEmbedder), the RetrievalService
(dense cosine + BM25 + keyword RRF), enhancement markdown, and QA wiring.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.abs.services import (
    HashEmbedder,
    IngestionService,
    QAService,
    RetrievalService,
    StubLLMClient,
    cosine,
    get_default_embedder,
)
from backend.abs.services.pdf_extract import extracted_from_pages
from backend.abs.store import DealStore


PAGES = [
    "ARTICLE V DISTRIBUTIONS\n\nOn each Distribution Date the Trustee shall pay interest "
    "to the Class A Certificates first, then principal.\n\n",
    "ARTICLE III FEES\n\nThe Servicing Fee equals 0.50% per annum of the pool balance and is "
    "paid monthly to the Servicer.\n\n",
]


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def test_hash_embedder_deterministic_and_normalised():
    e = HashEmbedder(dims=64)
    v1 = e.embed_query("the servicing fee is paid monthly")
    v2 = e.embed_query("the servicing fee is paid monthly")
    assert v1 == v2  # deterministic
    assert abs(sum(x * x for x in v1) ** 0.5 - 1.0) < 1e-6  # L2 normalised


def test_cosine_similar_texts_score_higher():
    e = HashEmbedder(dims=128)
    fee = e.embed_documents(["servicing fee paid monthly to the servicer"])[0]
    q_close = e.embed_query("servicing fee monthly")
    q_far = e.embed_query("zebra giraffe ocean mountain")
    assert cosine(q_close, fee) > cosine(q_far, fee)


def test_get_default_embedder_falls_back():
    e = get_default_embedder()
    assert e.dims > 0
    assert e.embed_query("hello")  # works without BGE model


# ---------------------------------------------------------------------------
# RetrievalService
# ---------------------------------------------------------------------------

def _ingest(tmp_path: Path) -> None:
    doc = extracted_from_pages(PAGES)
    asyncio.run(IngestionService(tmp_path).ingest_document("cbass", extracted=doc, doc_type="PSA"))


def test_index_creates_vectors(tmp_path: Path):
    _ingest(tmp_path)
    svc = RetrievalService(tmp_path)
    res = asyncio.run(svc.index("cbass", embedder=HashEmbedder()))
    assert res.ok is True, res.error
    assert res.data["vectors"] >= 1

    store = DealStore.for_deal_dir(tmp_path / "cbass", init=False)
    assert store.count_chunk_vectors("cbass") == res.data["vectors"]


def test_search_returns_relevant_with_citation(tmp_path: Path):
    _ingest(tmp_path)
    svc = RetrievalService(tmp_path)
    asyncio.run(svc.index("cbass", embedder=HashEmbedder()))
    res = asyncio.run(svc.search("cbass", "What is the servicing fee?", embedder=HashEmbedder(), top_k=3))
    assert res.ok is True, res.error
    hits = res.data
    assert hits
    # The fee chunk should rank first.
    assert "Servicing Fee" in hits[0]["text"]
    assert hits[0]["citation"]
    assert "signals" in hits[0]


def test_search_without_index_falls_back(tmp_path: Path):
    _ingest(tmp_path)  # no index() call
    svc = RetrievalService(tmp_path)
    res = asyncio.run(svc.search("cbass", "interest to Class A", top_k=3))
    assert res.ok is True
    assert res.data  # sparse/keyword fallback still returns hits


def test_enhancement_markdown_generated(tmp_path: Path):
    _ingest(tmp_path)
    svc = RetrievalService(tmp_path)
    llm = StubLLMClient(responder=lambda p, s: "servicing fee, monthly, servicer, 0.50%")
    res = asyncio.run(svc.index("cbass", embedder=HashEmbedder(), llm=llm, enhance=True))
    assert res.ok is True
    assert res.data["enhanced"] >= 1
    store = DealStore.for_deal_dir(tmp_path / "cbass", init=False)
    chunks = store.list_chunks_for_deal("cbass")
    assert any((c.get("enhancement_md") or "") for c in chunks)


# ---------------------------------------------------------------------------
# QA wiring
# ---------------------------------------------------------------------------

def test_qa_uses_hybrid_retrieval(tmp_path: Path):
    _ingest(tmp_path)
    asyncio.run(RetrievalService(tmp_path).index("cbass", embedder=HashEmbedder()))
    captured = {}

    def responder(prompt: str, system: str) -> str:
        captured["prompt"] = prompt
        return "The Servicing Fee is 0.50% per annum [Article III]."

    svc = QAService(tmp_path)
    res = asyncio.run(svc.ask("cbass", "What is the servicing fee?", StubLLMClient(responder=responder)))
    assert res.ok is True, res.error
    assert res.data["citations"]
    # Hybrid retrieval surfaced the fee chunk into the prompt.
    assert "Servicing Fee" in captured["prompt"]
    # Signals present in citations (proof of fusion).
    assert "signals" in res.data["citations"][0]
