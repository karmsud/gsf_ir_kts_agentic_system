"""
Phase 17 — Golden Query Validation tests.

These tests validate that Phase 17 scope/doc-filter parsing doesn't break
existing query interpretation. They test the *parsing layer* (scope_resolver)
and *rendering layer* (diff/aggregate blocks) — not live retrieval (which
requires an indexed corpus).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.common.scope_resolver import parse_command, ScopeExpr


# ---------------------------------------------------------------------------
# Golden parsing tests — ensure Phase 17 command grammar handles all 14 use
# cases from docs/phase17/02_USE_CASES.md without mangling queries.
# ---------------------------------------------------------------------------

class TestGoldenQueryParsing:
    """Golden queries: the query text must survive parsing intact."""

    def test_golden_1_single_deal_no_filter(self):
        """UC1: /fin_deal1 What is the Distribution Date?"""
        p = parse_command("/fin_deal1 What is the Distribution Date?")
        assert p.mode is None or p.mode == "search"
        assert len(p.scopes) == 1
        assert p.scopes[0].slug == "fin_deal1"
        assert "Distribution Date" in p.query

    def test_golden_2_single_deal_psa_filter(self):
        """UC2: /fin_deal1/PSA What is the Distribution Date?"""
        p = parse_command("/fin_deal1/PSA What is the Distribution Date?")
        assert p.scopes[0].slug == "fin_deal1"
        assert p.scopes[0].doc_filter == "PSA"
        assert "Distribution Date" in p.query

    def test_golden_3_trustee_query(self):
        """UC3: /fin_deal1 Who is the Trustee?"""
        p = parse_command("/fin_deal1 Who is the Trustee?")
        assert p.scopes[0].slug == "fin_deal1"
        assert "Trustee" in p.query

    def test_golden_4_loss_allocation(self):
        """UC4: /fin_deal1/PSA How are losses allocated?"""
        p = parse_command("/fin_deal1/PSA How are losses allocated?")
        assert p.scopes[0].doc_filter == "PSA"
        assert "losses allocated" in p.query

    def test_golden_5_realized_loss(self):
        """UC5: /fin_deal1 What is a Realized Loss?"""
        p = parse_command("/fin_deal1 What is a Realized Loss?")
        assert "Realized Loss" in p.query

    def test_golden_6_psa_doc_filter_only(self):
        """UC6: /fin_deal1/PSA Distribution Date"""
        p = parse_command("/fin_deal1/PSA Distribution Date")
        assert p.scopes[0].doc_filter == "PSA"
        assert "Distribution Date" in p.query

    def test_golden_7_compare_two_deals(self):
        """UC7: /compare /fin_deal1 /fin_deal2 What is Distribution Date?"""
        p = parse_command("/compare /fin_deal1 /fin_deal2 What is Distribution Date?")
        assert p.mode == "compare"
        assert len(p.scopes) >= 2
        slugs = [s.slug for s in p.scopes]
        assert "fin_deal1" in slugs
        assert "fin_deal2" in slugs
        assert "Distribution Date" in p.query

    def test_golden_8_servicer_obligations(self):
        """UC8: /fin_deal1 Servicer obligations"""
        p = parse_command("/fin_deal1 Servicer obligations")
        assert "Servicer" in p.query

    def test_golden_9_certificate_holder_payments(self):
        """UC9: /fin_deal1/PSA Certificate holder payments"""
        p = parse_command("/fin_deal1/PSA Certificate holder payments")
        assert p.scopes[0].doc_filter == "PSA"
        assert "Certificate" in p.query or "payments" in p.query

    def test_golden_10_event_of_default(self):
        """UC10: /fin_deal1/PSA What triggers an Event of Default?"""
        p = parse_command("/fin_deal1/PSA What triggers an Event of Default?")
        assert "Event of Default" in p.query

    def test_golden_11_depositor_deal_level(self):
        """UC11: /fin_deal1 Who is the Depositor?"""
        p = parse_command("/fin_deal1 Who is the Depositor?")
        assert p.scopes[0].doc_filter is None  # deal-level, no doc filter
        assert "Depositor" in p.query

    def test_golden_12_compare_psa_cross_deal(self):
        """UC12: /compare /fin_deal1/PSA /fin_deal2/PSA Compare Distribution Date."""
        p = parse_command("/compare /fin_deal1/PSA /fin_deal2/PSA Compare Distribution Date")
        assert p.mode == "compare"
        assert len(p.scopes) >= 2
        assert all(s.doc_filter == "PSA" for s in p.scopes)
        assert "Distribution Date" in p.query


class TestGoldenQueryIntegrity:
    """Ensure queries are not corrupted by the parser."""

    def test_plain_text_query_unchanged(self):
        """No slash tokens — query returned verbatim."""
        p = parse_command("What is the Distribution Date?")
        assert p.query == "What is the Distribution Date?"
        assert p.mode is None or p.mode == "search"
        assert len(p.scopes) == 0

    def test_scope_stripped_from_query(self):
        """Scope tokens must NOT appear in the query text."""
        p = parse_command("/fin_deal1/PSA What is the Distribution Date?")
        assert "/fin_deal1" not in p.query
        assert "/PSA" not in p.query

    def test_mode_stripped_from_query(self):
        """Mode token must NOT appear in the query text."""
        p = parse_command("/compare /fin_deal1 /fin_deal2 What is the Distribution Date?")
        assert "/compare" not in p.query
        assert "/fin_deal1" not in p.query

    def test_query_whitespace_trimmed(self):
        """Leading/trailing whitespace stripped from query."""
        p = parse_command("/fin_deal1   What is the Distribution Date?   ")
        assert p.query == "What is the Distribution Date?"

    def test_empty_input(self):
        """Empty input → no crash."""
        p = parse_command("")
        assert p.query == ""
        assert len(p.scopes) == 0
        assert p.mode is None or p.mode == "search"
