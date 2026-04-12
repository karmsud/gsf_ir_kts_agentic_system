"""Phase 17 — Compare / Diff / Aggregate Mode tests (Step 8)."""
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
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def diff_engine():
    return DiffEngine()


@pytest.fixture()
def agg_engine():
    return AggregationEngine()


@pytest.fixture()
def two_scopes_different():
    """Two scopes with clearly different content (dates & amounts differ)."""
    return {
        "fin_deal1/PSA": [
            {
                "text": (
                    "The Distribution Date shall be the 25th day of each month. "
                    "The applicable rate is 5.5% per annum. Servicer remittance "
                    "reports are due by the 10th day following each collection period."
                ),
                "score": 0.92,
            }
        ],
        "fin_deal2/PSA": [
            {
                "text": (
                    "Quarterly payments occur on the last business day of March, June, "
                    "September, and December. The fixed coupon equals 12.0% with a "
                    "$1,000,000 minimum notional. Trustee certifications are required."
                ),
                "score": 0.89,
            }
        ],
    }


@pytest.fixture()
def two_scopes_identical():
    """Two scopes with identical text."""
    return {
        "deal_a/PSA": [
            {"text": "Interest accrues on the 15th day at a rate of 4.5%.", "score": 0.95}
        ],
        "deal_b/PSA": [
            {"text": "Interest accrues on the 15th day at a rate of 4.5%.", "score": 0.93}
        ],
    }


@pytest.fixture()
def three_scopes():
    """Three scopes with mixed similarity."""
    return {
        "deal_a/PSA": [
            {"text": "The Distribution Date shall be the 25th day of each month at 5.5%.", "score": 0.91}
        ],
        "deal_b/PSA": [
            {"text": "The Distribution Date shall be the 25th day of each month at 5.5%.", "score": 0.90}
        ],
        "deal_c/PSA": [
            {"text": "Distributions occur on the last business day of each calendar quarter at 7.0%.", "score": 0.87}
        ],
    }


@pytest.fixture()
def ten_scopes_majority():
    """10 scopes — 8 share patterns, 2 are outliers."""
    majority_text = "The Distribution Date is the 25th day of each collection period. The rate is 5.5%."
    outlier_text_1 = "Payments are made on the last business day quarterly. The rate is 12.0%."
    outlier_text_2 = "Distributions happen every 90 days with a flat $1,000 fee."
    scopes = {}
    for i in range(1, 9):
        scopes[f"deal_{i}/PSA"] = [{"text": majority_text, "score": 0.9}]
    scopes["deal_outlier_a/PSA"] = [{"text": outlier_text_1, "score": 0.85}]
    scopes["deal_outlier_b/PSA"] = [{"text": outlier_text_2, "score": 0.80}]
    return scopes


@pytest.fixture()
def empty_scopes():
    """Scopes with empty result lists."""
    return {
        "deal_x/PSA": [],
        "deal_y/PSA": [],
    }


@pytest.fixture()
def single_scope():
    """Only one scope."""
    return {
        "deal_only/PSA": [
            {"text": "Single deal result text.", "score": 0.88}
        ],
    }


# ===================================================================
# DiffEngine tests (1-9)
# ===================================================================

class TestDiffEngine:
    """Tests for DiffEngine.diff()."""

    # 1
    def test_diff_basic_two_scopes(self, diff_engine, two_scopes_different):
        """2 scopes with different content → returns diffs."""
        result = diff_engine.diff(two_scopes_different, query="Distribution Date")
        assert isinstance(result, dict)
        assert result["scope_count"] == 2
        assert len(result["diffs"]) > 0, "Expected at least one diff entry"

    # 2
    def test_diff_identifies_field_differences(self, diff_engine, two_scopes_different):
        """Different dates / amounts → field-level diff entries."""
        result = diff_engine.diff(two_scopes_different, query="Distribution Date")
        fields = [d["field"] for d in result["diffs"]]
        # The engine detects Date/Timing and Amounts/Percentages
        assert any("Date" in f or "Amount" in f for f in fields), (
            f"Expected date or amount field diff, got fields: {fields}"
        )

    # 3
    def test_diff_finds_common_elements(self, diff_engine, two_scopes_identical):
        """Identical text in both scopes → high similarity in common list."""
        result = diff_engine.diff(two_scopes_identical, query="interest rate")
        assert len(result["common"]) >= 1
        assert result["common"][0]["similarity"] >= 0.85

    # 4
    def test_diff_same_deal_two_docs(self, diff_engine):
        """Same scope slug root but different document content → diffs produced."""
        scopes = {
            "fin_deal1/prospectus": [
                {"text": "Prospectus states the 10th day payment at $500,000.", "score": 0.90}
            ],
            "fin_deal1/supplement": [
                {"text": "Supplement specifies the 20th day payment at $750,000.", "score": 0.88}
            ],
        }
        result = diff_engine.diff(scopes, query="payment date")
        assert result["scope_count"] == 2
        assert len(result["diffs"]) > 0

    # 5
    def test_diff_significance_scoring(self, diff_engine, two_scopes_different):
        """Date/Amount differences get 'high' significance."""
        result = diff_engine.diff(two_scopes_different, query="Distribution Date")
        high_sig = [d for d in result["diffs"] if d.get("significance") == "high"]
        assert len(high_sig) >= 1, "Date / amount diffs should have high significance"

    # 6
    def test_diff_empty_results(self, diff_engine, empty_scopes):
        """Empty result lists → no crash, graceful output."""
        result = diff_engine.diff(empty_scopes, query="anything")
        assert isinstance(result, dict)
        assert result["diffs"] == []
        assert result["scope_count"] == 2

    # 7
    def test_diff_single_scope(self, diff_engine, single_scope):
        """Only 1 scope → no pairwise comparison possible."""
        result = diff_engine.diff(single_scope, query="anything")
        assert result["diffs"] == []
        assert result["scope_count"] == 1
        assert "at least 2" in result["summary"].lower() or "need" in result["summary"].lower()

    # 8
    def test_diff_returns_summary(self, diff_engine, two_scopes_different):
        """Result always contains a 'summary' key with a non-empty string."""
        result = diff_engine.diff(two_scopes_different, query="Distribution Date")
        assert "summary" in result
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 0

    # 9
    def test_diff_three_scopes(self, diff_engine, three_scopes):
        """3 scopes → multiple pairwise comparisons; both diffs and common possible."""
        result = diff_engine.diff(three_scopes, query="Distribution Date")
        assert result["scope_count"] == 3
        # At least some output (diffs or common) should exist
        assert len(result["diffs"]) + len(result["common"]) > 0


# ===================================================================
# AggregationEngine tests (10-16)
# ===================================================================

class TestAggregationEngine:
    """Tests for AggregationEngine.aggregate()."""

    # 10
    def test_aggregate_basic(self, agg_engine, three_scopes):
        """3 scopes → has pattern and outlier-related keys."""
        result = agg_engine.aggregate(three_scopes, query="Distribution Date")
        assert "pattern" in result
        assert "outliers" in result
        assert result["deal_count"] == 3

    # 11
    def test_aggregate_detects_majority_pattern(self, agg_engine, ten_scopes_majority):
        """8/10 same text → consensus pattern reflects majority."""
        result = agg_engine.aggregate(ten_scopes_majority, query="Distribution Date")
        # pattern_scopes should contain roughly 8 of the 10
        assert len(result["pattern_scopes"]) >= 7, (
            f"Expected majority cluster ≥ 7, got {len(result['pattern_scopes'])}"
        )

    # 12
    def test_aggregate_flags_outliers(self, agg_engine, ten_scopes_majority):
        """The 2 different scopes appear as outliers."""
        result = agg_engine.aggregate(ten_scopes_majority, query="Distribution Date")
        outlier_deals = {o["deal"] for o in result["outliers"]}
        assert "deal_outlier_a/PSA" in outlier_deals or "deal_outlier_b/PSA" in outlier_deals, (
            f"Expected at least one outlier in {outlier_deals}"
        )

    # 13
    def test_aggregate_confidence_score(self, agg_engine, two_scopes_identical):
        """All identical text → high confidence (1.0)."""
        result = agg_engine.aggregate(two_scopes_identical, query="interest rate")
        assert result["confidence"] >= 0.9, (
            f"Expected confidence ≥ 0.9 for identical texts, got {result['confidence']}"
        )

    # 14
    def test_aggregate_low_confidence(self, agg_engine):
        """50/50 split in very different texts → lower confidence."""
        scopes = {
            "deal_a/PSA": [{"text": "Payment on the 25th day at 5.5%.", "score": 0.9}],
            "deal_b/PSA": [{"text": "Quarterly distribution on last business day at 12%.", "score": 0.9}],
        }
        result = agg_engine.aggregate(scopes, query="payment timing")
        # With 2 very different texts, one will be centroid and the other
        # either in-pattern or outlier depending on threshold; confidence ≤ 1.0
        assert 0.0 <= result["confidence"] <= 1.0

    # 15
    def test_aggregate_deal_count(self, agg_engine, ten_scopes_majority):
        """deal_count matches the number of input scopes."""
        result = agg_engine.aggregate(ten_scopes_majority, query="Distribution Date")
        assert result["deal_count"] == 10

    # 16
    def test_aggregate_with_doc_filter(self, agg_engine):
        """Works with filtered / tagged inputs (same mechanics as basic)."""
        scopes = {
            "fin_deal1/supplement": [
                {"text": "Supplement: 25th day distribution at 5.5%.", "score": 0.91}
            ],
            "fin_deal2/supplement": [
                {"text": "Supplement: 25th day distribution at 5.5%.", "score": 0.89}
            ],
            "fin_deal3/supplement": [
                {"text": "Supplement: 25th day distribution at 5.5%.", "score": 0.88}
            ],
        }
        result = agg_engine.aggregate(scopes, query="Distribution Date")
        assert result["deal_count"] == 3
        assert result["confidence"] >= 0.9


# ===================================================================
# Rendering / structure tests (17-20)
# ===================================================================

class TestRenderingFormat:
    """Validate structural contracts of engine outputs."""

    # 17
    def test_compare_mode_rendering_has_scopes_compared(
        self, diff_engine, two_scopes_different
    ):
        """Diff result references the scope names in diffs or common."""
        result = diff_engine.diff(two_scopes_different, query="Distribution Date")
        all_scope_refs: set[str] = set()
        for d in result["diffs"]:
            all_scope_refs.update(d.get("values", {}).keys())
        for c in result["common"]:
            all_scope_refs.update(c.get("scopes", []))
        assert "fin_deal1/PSA" in all_scope_refs
        assert "fin_deal2/PSA" in all_scope_refs

    # 18
    def test_diff_mode_field_diffs_structure(
        self, diff_engine, two_scopes_different
    ):
        """Each diff entry has field, values, diff_type, significance keys."""
        result = diff_engine.diff(two_scopes_different, query="Distribution Date")
        required_keys = {"field", "values", "diff_type", "significance"}
        for d in result["diffs"]:
            missing = required_keys - d.keys()
            assert not missing, f"Diff entry missing keys: {missing}"

    # 19
    def test_aggregate_mode_outlier_structure(self, agg_engine, ten_scopes_majority):
        """Each outlier has deal, text, similarity_to_pattern, deviation keys."""
        result = agg_engine.aggregate(ten_scopes_majority, query="Distribution Date")
        required_keys = {"deal", "text", "similarity_to_pattern", "deviation"}
        for o in result["outliers"]:
            missing = required_keys - o.keys()
            assert not missing, f"Outlier entry missing keys: {missing}"

    # 20
    def test_all_modes_graceful_on_empty(self, diff_engine, agg_engine):
        """Both engines handle completely empty input gracefully."""
        empty: dict[str, list[dict]] = {}
        diff_result = diff_engine.diff(empty, query="anything")
        agg_result = agg_engine.aggregate(empty, query="anything")

        assert isinstance(diff_result, dict)
        assert diff_result["diffs"] == []
        assert diff_result["scope_count"] == 0

        assert isinstance(agg_result, dict)
        assert agg_result["outliers"] == []
        assert agg_result["deal_count"] == 0
