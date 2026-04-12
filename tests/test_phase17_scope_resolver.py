"""Phase 17 — Scope Resolution Pipeline tests (Step 5)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.common.scope_resolver import (
    ParsedCommand,
    ScopeExpr,
    parse_command,
    resolve_scopes,
)


# ── helpers ──────────────────────────────────────────────────

def _make_catalog(search_results: list[dict] | None = None,
                  all_deals: list[dict] | None = None) -> MagicMock:
    """Return a mock DealCatalog with configurable results."""
    catalog = MagicMock()
    catalog.search_deals.return_value = search_results or []
    catalog.list_all_deals.return_value = all_deals or []
    return catalog


# ── test class ───────────────────────────────────────────────

class TestScopeResolver:
    """25 comprehensive tests for parse_command / resolve_scopes."""

    # 1 ─ single scope
    def test_parse_single_scope(self) -> None:
        result = parse_command("/fin_deal1 What is Distribution Date?")
        assert len(result.scopes) == 1
        assert result.scopes[0].slug == "fin_deal1"
        assert result.scopes[0].doc_filter is None
        assert result.scopes[0].is_wildcard is False
        assert "Distribution Date" in result.query

    # 2 ─ scope + doc filter
    def test_parse_scope_with_doc_filter(self) -> None:
        result = parse_command("/fin_deal1/PSA What is Distribution Date?")
        assert len(result.scopes) == 1
        assert result.scopes[0].slug == "fin_deal1"
        assert result.scopes[0].doc_filter == "PSA"

    # 3 ─ global doc filter //DOC_TYPE
    def test_parse_global_doc_filter(self) -> None:
        result = parse_command("//PSA What is Distribution Date?")
        assert len(result.scopes) == 1
        scope = result.scopes[0]
        assert scope.slug == "*"
        assert scope.doc_filter == "PSA"

    # 4 ─ wildcard scope
    def test_parse_wildcard_scope(self) -> None:
        result = parse_command("/bear_stearns_2006* What is Distribution Date?")
        assert len(result.scopes) == 1
        assert result.scopes[0].is_wildcard is True
        assert result.scopes[0].slug == "bear_stearns_2006"

    # 5 ─ wildcard + doc filter
    def test_parse_wildcard_with_doc_filter(self) -> None:
        result = parse_command("/bear_stearns_2006*/PSA What is Distribution Date?")
        assert len(result.scopes) == 1
        scope = result.scopes[0]
        assert scope.is_wildcard is True
        assert scope.slug == "bear_stearns_2006"
        assert scope.doc_filter == "PSA"

    # 6 ─ compare mode
    def test_parse_compare_mode(self) -> None:
        result = parse_command("/compare /fin_deal1 /fin_deal2 What is Distribution Date?")
        assert result.mode == "compare"
        assert len(result.scopes) == 2
        assert result.scopes[0].slug == "fin_deal1"
        assert result.scopes[1].slug == "fin_deal2"

    # 7 ─ diff mode
    def test_parse_diff_mode(self) -> None:
        result = parse_command("/diff /fin_deal1/PSA /fin_deal2/PSA What is Distribution Date?")
        assert result.mode == "diff"
        assert len(result.scopes) == 2
        assert result.scopes[0].doc_filter == "PSA"
        assert result.scopes[1].doc_filter == "PSA"

    # 8 ─ aggregate mode
    def test_parse_aggregate_mode(self) -> None:
        result = parse_command("/aggregate /bear_stearns_2006* How is Distribution Date determined?")
        assert result.mode == "aggregate"
        assert len(result.scopes) == 1
        assert result.scopes[0].is_wildcard is True

    # 9 ─ list mode
    def test_parse_list_mode(self) -> None:
        result = parse_command("/list /fin_deal1")
        assert result.mode == "list"
        assert len(result.scopes) == 1
        assert result.scopes[0].slug == "fin_deal1"

    # 10 ─ define mode
    def test_parse_define_mode(self) -> None:
        result = parse_command("/define /fin_deal1 Distribution Date")
        assert result.mode == "define"
        assert len(result.scopes) == 1
        assert result.query == "Distribution Date"

    # 11 ─ audit mode
    def test_parse_audit_mode(self) -> None:
        result = parse_command("/audit /fin_deal1/PSA")
        assert result.mode == "audit"
        assert len(result.scopes) == 1
        assert result.scopes[0].doc_filter == "PSA"

    # 12 ─ compare with wildcard
    def test_parse_compare_wildcard(self) -> None:
        result = parse_command("/compare /bear_stearns_2006* What is Distribution Date?")
        assert result.mode == "compare"
        assert len(result.scopes) == 1
        assert result.scopes[0].is_wildcard is True

    # 13 ─ compare wildcard + doc filter
    def test_parse_compare_wildcard_with_doc(self) -> None:
        result = parse_command("/compare /bear_stearns_2006*/PSA What is Distribution Date?")
        assert result.mode == "compare"
        assert result.scopes[0].is_wildcard is True
        assert result.scopes[0].doc_filter == "PSA"

    # 14 ─ no scope → default search mode, no scopes
    def test_parse_no_scope_default(self) -> None:
        result = parse_command("What is Distribution Date?")
        assert result.mode == "search"
        assert result.scopes == []
        assert result.query == "What is Distribution Date?"

    # 15 ─ multiple explicit scopes
    def test_parse_multiple_explicit_scopes(self) -> None:
        result = parse_command("/fin_deal1 /fin_deal2 /fin_deal3 What is Distribution Date?")
        assert len(result.scopes) == 3
        slugs = [s.slug for s in result.scopes]
        assert slugs == ["fin_deal1", "fin_deal2", "fin_deal3"]

    # 16 ─ resolve wildcard via catalog (3 matches)
    def test_resolve_wildcard_via_catalog(self) -> None:
        parsed = parse_command("/bear_stearns_2006* What is Distribution Date?")
        catalog = _make_catalog(search_results=[
            {"slug": "bear_stearns_2006_1"},
            {"slug": "bear_stearns_2006_2"},
            {"slug": "bear_stearns_2006_3"},
        ])
        resolved = resolve_scopes(parsed, catalog)
        assert len(resolved) == 3
        assert all(not s.is_wildcard for s in resolved)
        catalog.search_deals.assert_called_once_with(pattern="bear_stearns_2006*")

    # 17 ─ resolve wildcard no matches
    def test_resolve_wildcard_no_matches(self) -> None:
        parsed = parse_command("/nonexistent_deal* What is Distribution Date?")
        catalog = _make_catalog(search_results=[])
        resolved = resolve_scopes(parsed, catalog)
        assert resolved == []

    # 18 ─ resolve global doc filter
    def test_resolve_global_doc_filter(self) -> None:
        all_deals = [{"slug": f"deal_{i}"} for i in range(5)]
        parsed = parse_command("//PSA What is Distribution Date?")
        catalog = _make_catalog(all_deals=all_deals)
        resolved = resolve_scopes(parsed, catalog)
        assert len(resolved) == 5
        assert all(s.doc_filter == "PSA" for s in resolved)
        catalog.list_all_deals.assert_called_once()

    # 19 ─ @kts prefix stripped
    def test_parse_strips_at_kts_prefix(self) -> None:
        result = parse_command("@kts /fin_deal1 What is Distribution Date?")
        assert len(result.scopes) == 1
        assert result.scopes[0].slug == "fin_deal1"
        assert result.query == "What is Distribution Date?"

    # 20 ─ query extraction excludes scope/mode tokens
    def test_parse_query_extraction(self) -> None:
        result = parse_command("/compare /fin_deal1/PSA /fin_deal2/PROSUPP What is Distribution Date?")
        assert "/compare" not in result.query
        assert "/fin_deal1" not in result.query
        assert "/fin_deal2" not in result.query
        assert result.query == "What is Distribution Date?"

    # 21 ─ mode is case-insensitive
    def test_parse_mode_case_insensitive(self) -> None:
        result = parse_command("/Compare /fin_deal1 /fin_deal2 What is Distribution Date?")
        assert result.mode == "compare"

    # 22 ─ scope with no query → empty query string
    def test_parse_error_no_query_after_scope(self) -> None:
        result = parse_command("/fin_deal1")
        assert len(result.scopes) == 1
        assert result.query == ""

    # 23 ─ diff same deal, two different doc types
    def test_parse_diff_same_deal_two_docs(self) -> None:
        result = parse_command("/diff /fin_deal1/PSA /fin_deal1/PROSUPP What is Distribution Date?")
        assert result.mode == "diff"
        assert len(result.scopes) == 2
        assert result.scopes[0].slug == "fin_deal1"
        assert result.scopes[0].doc_filter == "PSA"
        assert result.scopes[1].slug == "fin_deal1"
        assert result.scopes[1].doc_filter == "PROSUPP"

    # 24 ─ complex command with two wildcard scopes
    def test_parse_complex_command(self) -> None:
        result = parse_command("/compare /bear_stearns_2006*/PSA /gs_2007*/PSA What is Distribution Date?")
        assert result.mode == "compare"
        assert len(result.scopes) == 2
        assert result.scopes[0].is_wildcard is True
        assert result.scopes[0].slug == "bear_stearns_2006"
        assert result.scopes[0].doc_filter == "PSA"
        assert result.scopes[1].is_wildcard is True
        assert result.scopes[1].slug == "gs_2007"
        assert result.scopes[1].doc_filter == "PSA"

    # 25 ─ round-trip: parse then inspect all fields
    def test_round_trip_parse_to_cli_args(self) -> None:
        raw = "@kts /diff /fin_deal1/PSA /fin_deal2/PROSUPP What is Distribution Date?"
        result = parse_command(raw)
        assert result.raw_input == raw
        assert result.mode == "diff"
        assert len(result.scopes) == 2
        assert result.scopes[0] == ScopeExpr(slug="fin_deal1", doc_filter="PSA", is_wildcard=False)
        assert result.scopes[1] == ScopeExpr(slug="fin_deal2", doc_filter="PROSUPP", is_wildcard=False)
        assert result.query == "What is Distribution Date?"
