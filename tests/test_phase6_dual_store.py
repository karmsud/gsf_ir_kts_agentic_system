"""
Phase 6 — DualVectorStore tests.

Tests dual ChromaDB collection management (items + sections).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.vector.dual_vector_store import DualVectorStore


class TestDualVectorStore:
    @pytest.fixture
    def store(self, tmp_path):
        return DualVectorStore(str(tmp_path / "phase6_vectors"))

    @pytest.fixture
    def sample_items(self):
        return [
            {"id": "item1", "text": "The Trustee shall distribute funds.", "metadata": {"item_type": "Obligation", "document_id": "doc1", "section_number": "2.01"}},
            {"id": "item2", "text": "Available Funds means collected amounts.", "metadata": {"item_type": "Definition", "document_id": "doc1", "section_number": "1.01"}},
            {"id": "item3", "text": "The Servicer shall not commingle funds.", "metadata": {"item_type": "Prohibition", "document_id": "doc1", "section_number": "3.01"}},
        ]

    @pytest.fixture
    def sample_sections(self):
        return [
            {"id": "sec1", "text": "Definitions section with key terms.", "metadata": {"section_number": "1.01", "document_id": "doc1"}},
            {"id": "sec2", "text": "Distribution procedures and rules.", "metadata": {"section_number": "2.01", "document_id": "doc1"}},
        ]

    def test_add_and_search_items(self, store, sample_items):
        store.add_items(sample_items)
        results = store.search_items("distribute funds", top_k=3)
        assert len(results) > 0
        assert any("item1" == r.get("id") for r in results)

    def test_add_and_search_sections(self, store, sample_sections):
        store.add_sections(sample_sections)
        results = store.search_sections("definitions", top_k=2)
        assert len(results) > 0

    def test_unified_search(self, store, sample_items, sample_sections):
        store.add_items(sample_items)
        store.add_sections(sample_sections)
        results = store.search("funds", top_k=5)
        assert len(results) > 0

    def test_get_by_id(self, store, sample_items):
        store.add_items(sample_items)
        result = store.get_by_id("item1")
        assert result is not None

    def test_delete_document(self, store, sample_items, sample_sections):
        store.add_items(sample_items)
        store.add_sections(sample_sections)
        store.delete_document("doc1")
        # After delete, search should return empty
        results = store.search_items("distribute funds", top_k=3)
        assert len(results) == 0

    def test_reset(self, store, sample_items):
        store.add_items(sample_items)
        store.reset()
        results = store.search_items("distribute", top_k=3)
        assert len(results) == 0

    def test_empty_search(self, store):
        results = store.search_items("anything", top_k=5)
        assert results == []

    def test_idempotent_add(self, store, sample_items):
        store.add_items(sample_items)
        store.add_items(sample_items)  # Add same items again
        results = store.search_items("distribute", top_k=10)
        # Should not duplicate — ChromaDB upserts by ID
        ids = [r.get("id") for r in results]
        assert len(set(ids)) == len(ids)
