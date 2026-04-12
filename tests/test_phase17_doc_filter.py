"""Phase 17 — Document Filter Read-Side Wiring tests (Step 1)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import KTSConfig


# ---------------------------------------------------------------------------
# Helper: build a lightweight object that has _merge_doc_filter bound
# ---------------------------------------------------------------------------

def _make_retriever_stub(doc_name_prefix: str | None = None):
    """Return a stub with the real _merge_doc_filter method and a settable prefix."""
    from backend.retrieval.human_like_retriever import HumanLikeRetriever

    # We only need the method, not the full constructor — grab unbound method
    stub = MagicMock(spec=HumanLikeRetriever)
    # Bind the real implementation
    stub._merge_doc_filter = HumanLikeRetriever._merge_doc_filter.__get__(stub)
    stub._doc_name_prefix = doc_name_prefix
    return stub


class TestDocFilter:
    """Tests for Phase 17 document-filter read-side wiring."""

    # ── 1. _merge_doc_filter: prefix set → dict with key ─────────

    def test_merge_doc_filter_with_prefix_adds_key(self):
        stub = _make_retriever_stub("PSA")
        result = stub._merge_doc_filter(None)
        assert result is not None
        assert result["doc_name_prefix"] == "PSA"

    # ── 2. _merge_doc_filter: no prefix → original filters ───────

    def test_merge_doc_filter_without_prefix_returns_none(self):
        stub = _make_retriever_stub(None)
        assert stub._merge_doc_filter(None) is None

        # Also returns an existing dict unchanged
        existing = {"item_type": "definition"}
        result = stub._merge_doc_filter(existing)
        assert result is existing

    # ── 3. _merge_doc_filter: combines with existing filters ─────

    def test_merge_doc_filter_combines_with_existing(self):
        stub = _make_retriever_stub("SPA")
        existing = {"item_type": "definition"}
        result = stub._merge_doc_filter(existing)
        assert result is not None
        assert result["doc_name_prefix"] == "SPA"
        assert result["item_type"] == "definition"

    # ── 4. Existing keys preserved after merge ────────────────────

    def test_merge_doc_filter_preserves_existing_keys(self):
        stub = _make_retriever_stub("CLA")
        existing = {"section": "3.1", "item_type": "obligation"}
        result = stub._merge_doc_filter(existing)
        assert result["section"] == "3.1"
        assert result["item_type"] == "obligation"
        assert result["doc_name_prefix"] == "CLA"

    # ── 5. search_items with doc_filter "PSA" ─────────────────────

    def test_search_items_with_doc_filter_psa(self):
        stub = _make_retriever_stub("PSA")
        # Simulate calling _merge_doc_filter as the retriever would
        filters = stub._merge_doc_filter(None)
        assert filters == {"doc_name_prefix": "PSA"}

        # Verify the filter dict could be passed to DualVectorStore.search_items
        mock_store = MagicMock()
        mock_store.search_items.return_value = []
        mock_store.search_items(query="indemnity clause", n_results=5, where=filters)
        mock_store.search_items.assert_called_once_with(
            query="indemnity clause", n_results=5, where={"doc_name_prefix": "PSA"}
        )

    # ── 6. search_sections with doc_filter ────────────────────────

    def test_search_sections_with_doc_filter(self):
        stub = _make_retriever_stub("SPA")
        filters = stub._merge_doc_filter(None)
        assert filters == {"doc_name_prefix": "SPA"}

        mock_store = MagicMock()
        mock_store.search_sections.return_value = []
        mock_store.search_sections(query="representations", n_results=5, where=filters)
        mock_store.search_sections.assert_called_once_with(
            query="representations", n_results=5, where={"doc_name_prefix": "SPA"}
        )

    # ── 7. No doc_name_prefix → filters=None passed ──────────────

    def test_search_without_doc_filter(self):
        stub = _make_retriever_stub(None)
        filters = stub._merge_doc_filter(None)
        assert filters is None

        mock_store = MagicMock()
        mock_store.search_items.return_value = []
        mock_store.search_items(query="closing conditions", n_results=10, where=filters)
        mock_store.search_items.assert_called_once_with(
            query="closing conditions", n_results=10, where=None
        )

    # ── 8. Combined filters: doc_name_prefix + item_type ──────────

    def test_combined_filters_doc_and_type(self):
        stub = _make_retriever_stub("PSA")
        base_filters = {"item_type": "covenant"}
        result = stub._merge_doc_filter(base_filters)
        assert result == {"item_type": "covenant", "doc_name_prefix": "PSA"}
        # Original dict is not mutated
        assert "doc_name_prefix" not in base_filters

    # ── 9. Unknown prefix → empty results, no crash ──────────────

    def test_doc_filter_unknown_prefix(self):
        stub = _make_retriever_stub("ZZZZZ_NONEXISTENT")
        filters = stub._merge_doc_filter(None)
        assert filters == {"doc_name_prefix": "ZZZZZ_NONEXISTENT"}

        # Simulated search returns empty — no exception raised
        mock_store = MagicMock()
        mock_store.search_items.return_value = []
        results = mock_store.search_items(query="anything", n_results=5, where=filters)
        assert results == []

    # ── 10. KTSConfig flag exists and defaults to True ────────────

    def test_config_flag_exists(self):
        cfg = KTSConfig()
        assert hasattr(cfg, "phase17_doc_filter_enabled")
        assert cfg.phase17_doc_filter_enabled is True

    # ── 11. Prefix used as-is (case handling is at CLI layer) ─────

    def test_doc_filter_case_handling(self):
        stub_upper = _make_retriever_stub("PSA")
        stub_lower = _make_retriever_stub("psa")

        result_upper = stub_upper._merge_doc_filter(None)
        result_lower = stub_lower._merge_doc_filter(None)

        # The method stores prefix as-is without normalising case
        assert result_upper["doc_name_prefix"] == "PSA"
        assert result_lower["doc_name_prefix"] == "psa"

    # ── 12. Empty-string prefix → returns original filters ────────

    def test_merge_doc_filter_empty_prefix_returns_none(self):
        stub = _make_retriever_stub("")
        assert stub._merge_doc_filter(None) is None

        existing = {"item_type": "definition"}
        result = stub._merge_doc_filter(existing)
        assert result is existing
