"""Phase 17 — Result Attribution tests (Step 11)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.agents.diff_engine import DiffEngine
from backend.agents.aggregation_engine import AggregationEngine


# ---------------------------------------------------------------------------
# Fixtures — sample results_by_scope data
# ---------------------------------------------------------------------------

@pytest.fixture()
def two_scope_results():
    """Two scopes with differing distribution-date language."""
    return {
        "fin_deal1": [
            {"text": "The Distribution Date shall be the 25th day of each month following the Closing Date.", "section_number": "2.01"},
        ],
        "fin_deal2": [
            {"text": "The Distribution Date shall be the last business day of each calendar month.", "section_number": "2.01"},
        ],
    }


@pytest.fixture()
def three_scope_results():
    """Three scopes — two similar, one outlier."""
    return {
        "deal_a": [
            {"text": "Distribution Date is the 25th day of each month."},
        ],
        "deal_b": [
            {"text": "Distribution Date is the 25th day of each month."},
        ],
        "deal_c": [
            {"text": "Distribution Date is the last business day of each month."},
        ],
    }


@pytest.fixture()
def five_scope_results():
    """Five scopes — majority share same text, one outlier."""
    common_text = "The Servicer shall remit on the 25th day of each month."
    return {
        "deal_alpha": [{"text": common_text}],
        "deal_beta": [{"text": common_text}],
        "deal_gamma": [{"text": common_text}],
        "deal_delta": [{"text": common_text}],
        "deal_outlier": [{"text": "The Servicer shall remit on the last business day, with a 5% penalty for late payments."}],
    }


# ---------------------------------------------------------------------------
# DiffEngine tests
# ---------------------------------------------------------------------------

class TestDiffEngineAttribution:

    def test_single_scope_result_has_deal_field(self, two_scope_results):
        """Diff output carries scope_count identifying how many scopes were compared."""
        engine = DiffEngine()
        result = engine.diff(two_scope_results, query="distribution date")

        assert "scope_count" in result
        assert result["scope_count"] == 2

    def test_single_scope_result_has_doc_prefix(self, two_scope_results):
        """Each diff entry's 'values' dict is keyed by scope slug (doc_name_prefix)."""
        engine = DiffEngine()
        result = engine.diff(two_scope_results, query="distribution date")

        # At least one diff should exist (texts differ)
        assert len(result["diffs"]) > 0
        first_diff = result["diffs"][0]
        # Values dict keys are the scope slugs
        assert "fin_deal1" in first_diff["values"]
        assert "fin_deal2" in first_diff["values"]

    def test_multi_scope_results_have_attribution(self, three_scope_results):
        """All scope slugs appear somewhere in the diff output (diffs or common)."""
        engine = DiffEngine()
        result = engine.diff(three_scope_results, query="distribution date")

        # Collect all scope names referenced across diffs and common
        referenced_scopes: set[str] = set()
        for diff_entry in result.get("diffs", []):
            referenced_scopes.update(diff_entry.get("values", {}).keys())
        for common_entry in result.get("common", []):
            referenced_scopes.update(common_entry.get("scopes", []))

        for scope in three_scope_results:
            assert scope in referenced_scopes, f"Scope '{scope}' not attributed in output"

    def test_compare_results_grouped_by_scope(self, two_scope_results):
        """Pairwise diff results reference scope_a and scope_b via values keys."""
        engine = DiffEngine()
        result = engine.diff(two_scope_results, query="distribution date")

        for diff_entry in result["diffs"]:
            scope_keys = list(diff_entry["values"].keys())
            assert len(scope_keys) == 2
            assert "fin_deal1" in scope_keys
            assert "fin_deal2" in scope_keys

    def test_diff_results_reference_source_scope(self, two_scope_results):
        """field_diffs carry the scope slug in each value mapping."""
        engine = DiffEngine()
        result = engine.diff(two_scope_results, query="distribution date")

        for diff_entry in result["diffs"]:
            # Every diff entry must have a 'values' dict keyed by scope
            assert isinstance(diff_entry["values"], dict)
            for scope_key in diff_entry["values"]:
                assert scope_key in two_scope_results, (
                    f"Diff references unknown scope '{scope_key}'"
                )

    def test_diff_summary_includes_scope_names(self, two_scope_results):
        """Summary string mentions the number of scopes compared."""
        engine = DiffEngine()
        result = engine.diff(two_scope_results, query="distribution date")

        summary = result["summary"]
        # Summary should reference the count of scopes
        assert "2" in summary or "two" in summary.lower()


# ---------------------------------------------------------------------------
# AggregationEngine tests
# ---------------------------------------------------------------------------

class TestAggregationEngineAttribution:

    def test_aggregate_outliers_have_deal_id(self, five_scope_results):
        """Each outlier dict contains a 'deal' key identifying the scope."""
        engine = AggregationEngine()
        result = engine.aggregate(five_scope_results, query="servicer remittance")

        assert len(result["outliers"]) >= 1
        for outlier in result["outliers"]:
            assert "deal" in outlier, "Outlier missing 'deal' key"
            # The deal value should be a known scope slug
            assert outlier["deal"] in five_scope_results

    def test_aggregate_summary_mentions_deal_count(self, five_scope_results):
        """Summary mentions how many deals/scopes were analysed."""
        engine = AggregationEngine()
        result = engine.aggregate(five_scope_results, query="servicer remittance")

        summary = result["summary"]
        deal_count = result["deal_count"]
        assert deal_count == 5
        # Summary should reference the total count
        assert str(len(five_scope_results)) in summary
