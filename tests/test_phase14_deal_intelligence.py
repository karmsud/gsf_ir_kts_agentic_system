"""
Phase 14 — Structured Deal Intelligence Layer — Comprehensive Tests.

Covers all four increments:
  14.1 — Session Deal Summary Cache (DealSummary, progressive population, cache-first)
  14.2 — Temporal Reasoning (TemporalReasoner, signals, date injection)
  14.3 — Structured Extraction Mode (ExtractionMode, JSON schema, gap tracking)
  14.4 — Deal Summary Mode (SummaryMode, 5-section template, source parsing)

Plus integration tests for retrieval_service wiring, extension rendering,
config flags, and __init__.py exports.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch
from typing import Dict, Any, List

import pytest

# ── Helpers ───────────────────────────────────────────────────

def run_async(coro):
    """Run an async coroutine synchronously (no pytest-asyncio needed)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════
# 14.1 — Session Deal Summary Cache
# ═══════════════════════════════════════════════════════════════

class TestPhase14_1_DealSummary:
    """Tests for the DealSummary dataclass and progressive population."""

    def test_default_construction(self):
        from backend.retrieval.session_memory import DealSummary
        ds = DealSummary()
        assert ds.scope == ""
        assert ds.deal_name is None
        assert ds.parties == {}
        assert ds.key_dates == {}
        assert ds.key_amounts == {}
        assert ds.defined_terms == {}
        assert ds.cited_sections == set()
        assert ds.turn_count == 0

    def test_update_from_answer_terms(self):
        from backend.retrieval.session_memory import DealSummary
        ds = DealSummary(scope="test_deal")
        ds.update_from_answer(terms={"Determination Date": "25th of month"})
        assert ds.defined_terms["Determination Date"] == "25th of month"
        assert ds.turn_count == 1
        assert ds.last_updated is not None

    def test_update_from_answer_parties(self):
        from backend.retrieval.session_memory import DealSummary
        ds = DealSummary()
        ds.update_from_answer(parties={"Trustee": "Deutsche Bank"})
        assert ds.parties["Trustee"] == "Deutsche Bank"

    def test_update_from_answer_dates(self):
        from backend.retrieval.session_memory import DealSummary
        ds = DealSummary()
        ds.update_from_answer(dates={"Closing Date": "2006-03-15"})
        assert ds.key_dates["Closing Date"] == "2006-03-15"

    def test_update_from_answer_amounts(self):
        from backend.retrieval.session_memory import DealSummary
        ds = DealSummary()
        ds.update_from_answer(amounts={"Certificate Balance": "$500M"})
        assert ds.key_amounts["Certificate Balance"] == "$500M"

    def test_update_from_answer_sections(self):
        from backend.retrieval.session_memory import DealSummary
        ds = DealSummary()
        ds.update_from_answer(sections=["1.01", "2.03"])
        assert "1.01" in ds.cited_sections
        assert "2.03" in ds.cited_sections

    def test_progressive_population_accumulates(self):
        from backend.retrieval.session_memory import DealSummary
        ds = DealSummary(scope="bear_stearns_2006_HE1")
        ds.update_from_answer(terms={"Determination Date": "25th of month"})
        ds.update_from_answer(parties={"Trustee": "Deutsche Bank"})
        ds.update_from_answer(
            dates={"Closing Date": "2006-03-15"},
            sections=["1.01"],
        )
        assert ds.turn_count == 3
        assert len(ds.defined_terms) == 1
        assert len(ds.parties) == 1
        assert len(ds.key_dates) == 1
        assert "1.01" in ds.cited_sections

    def test_update_from_answer_overwrites_existing(self):
        from backend.retrieval.session_memory import DealSummary
        ds = DealSummary()
        ds.update_from_answer(terms={"Term A": "v1"})
        ds.update_from_answer(terms={"Term A": "v2"})
        assert ds.defined_terms["Term A"] == "v2"

    def test_lookup_term_case_insensitive(self):
        from backend.retrieval.session_memory import DealSummary
        ds = DealSummary()
        ds.update_from_answer(terms={"Determination Date": "25th of month"})
        assert ds.lookup_term("determination date") == "25th of month"
        assert ds.lookup_term("DETERMINATION DATE") == "25th of month"
        assert ds.lookup_term("  Determination Date  ") == "25th of month"

    def test_lookup_term_not_found(self):
        from backend.retrieval.session_memory import DealSummary
        ds = DealSummary()
        assert ds.lookup_term("NonExistent") is None

    def test_to_dict(self):
        from backend.retrieval.session_memory import DealSummary
        ds = DealSummary(scope="test", deal_name="Test Deal")
        ds.update_from_answer(terms={"T1": "v1"}, sections=["1.01"])
        d = ds.to_dict()
        assert d["scope"] == "test"
        assert d["deal_name"] == "Test Deal"
        assert d["defined_terms"]["T1"] == "v1"
        assert "1.01" in d["cited_sections"]

    def test_update_with_none_args_no_error(self):
        from backend.retrieval.session_memory import DealSummary
        ds = DealSummary()
        ds.update_from_answer(terms=None, parties=None, dates=None, amounts=None, sections=None)
        assert ds.turn_count == 1  # still increments


class TestPhase14_1_SessionMemoryIntegration:
    """Tests for DealSummary integration with SessionMemory."""

    def test_session_memory_has_deal_summary(self):
        from backend.retrieval.session_memory import SessionMemory
        mem = SessionMemory(session_id="test-session")
        assert hasattr(mem, "deal_summary")
        assert mem.deal_summary.scope == ""

    def test_get_cached_term_from_resolved_terms(self):
        from backend.retrieval.session_memory import SessionMemory
        mem = SessionMemory(session_id="test-session")
        mem.resolve_term("Record Date", "last day of prior month")
        assert mem.get_cached_term("Record Date") == "last day of prior month"

    def test_get_cached_term_falls_through_to_deal_summary(self):
        from backend.retrieval.session_memory import SessionMemory
        mem = SessionMemory(session_id="test-session")
        mem.deal_summary.update_from_answer(terms={"Determination Date": "25th"})
        assert mem.get_cached_term("Determination Date") == "25th"

    def test_get_cached_term_prioritizes_resolved_terms(self):
        from backend.retrieval.session_memory import SessionMemory
        mem = SessionMemory(session_id="test-session")
        mem.resolve_term("Date X", "from_resolved")
        mem.deal_summary.update_from_answer(terms={"Date X": "from_deal_summary"})
        # resolved_terms checked first
        assert mem.get_cached_term("Date X") == "from_resolved"

    def test_session_to_dict_includes_deal_summary(self):
        from backend.retrieval.session_memory import SessionMemory
        mem = SessionMemory(session_id="test-session")
        mem.deal_summary.update_from_answer(terms={"T": "V"})
        d = mem.to_dict()
        assert "deal_summary" in d
        assert d["deal_summary"]["defined_terms"]["T"] == "V"


class TestPhase14_1_SessionStoreProgressivePopulation:
    """Tests for SessionStore.update_from_answer (progressive population)."""

    def test_update_from_answer_extracts_parties(self):
        from backend.retrieval.session_memory import SessionStore
        store = SessionStore()
        answer = "The Trustee is Deutsche Bank National Trust Company. The Depositor: Bear Stearns."
        store.update_from_answer("s1", answer, [])
        mem = store.get_or_create("s1")
        assert "Trustee" in mem.deal_summary.parties
        assert "Deutsche Bank" in mem.deal_summary.parties["Trustee"]

    def test_update_from_answer_extracts_dates(self):
        from backend.retrieval.session_memory import SessionStore
        store = SessionStore()
        answer = "The Distribution Date is the 25th of each month."
        store.update_from_answer("s1", answer, [])
        mem = store.get_or_create("s1")
        assert "Distribution Date" in mem.deal_summary.key_dates

    def test_update_from_answer_extracts_defined_terms(self):
        from backend.retrieval.session_memory import SessionStore
        store = SessionStore()
        answer = '"Determination Date" means the 20th day of each calendar month.'
        store.update_from_answer("s1", answer, [])
        mem = store.get_or_create("s1")
        assert "Determination Date" in mem.deal_summary.defined_terms

    def test_update_from_answer_extracts_section_refs(self):
        from backend.retrieval.session_memory import SessionStore
        store = SessionStore()
        answer = "As defined in Section 1.01 and Section 2.03."
        store.update_from_answer("s1", answer, [])
        mem = store.get_or_create("s1")
        assert "1.01" in mem.deal_summary.cited_sections
        assert "2.03" in mem.deal_summary.cited_sections

    def test_update_from_answer_tracks_source_documents(self):
        from backend.retrieval.session_memory import SessionStore
        store = SessionStore()
        chunks = [{"content": "text", "source": "/docs/psa.pdf"}]
        store.update_from_answer("s1", "Answer.", chunks)
        mem = store.get_or_create("s1")
        assert "/docs/psa.pdf" in mem.active_documents

    def test_update_from_answer_empty_text(self):
        from backend.retrieval.session_memory import SessionStore
        store = SessionStore()
        store.update_from_answer("s1", "", [])
        mem = store.get_or_create("s1")
        assert mem.deal_summary.turn_count == 1


# ═══════════════════════════════════════════════════════════════
# 14.2 — Temporal Reasoning
# ═══════════════════════════════════════════════════════════════

class TestPhase14_2_TemporalReasoner:
    """Tests for TemporalReasoner: detection, injection, date extraction."""

    def test_default_current_date_is_today(self):
        from backend.retrieval.temporal_reasoner import TemporalReasoner
        r = TemporalReasoner()
        assert r.current_date == date.today()

    def test_date_override(self):
        from backend.retrieval.temporal_reasoner import TemporalReasoner
        override = date(2026, 2, 18)
        r = TemporalReasoner(current_date_override=override)
        assert r.current_date == override

    def test_current_date_str_format(self):
        from backend.retrieval.temporal_reasoner import TemporalReasoner
        r = TemporalReasoner(current_date_override=date(2026, 2, 18))
        assert r.current_date_str == "February 18, 2026"

    def test_is_temporal_query_true(self):
        from backend.retrieval.temporal_reasoner import TemporalReasoner
        r = TemporalReasoner()
        assert r.is_temporal_query("Has the Optional Termination date passed?")
        assert r.is_temporal_query("Is the deal still active?")
        assert r.is_temporal_query("How long until the maturity date?")
        assert r.is_temporal_query("When does the period end?")

    def test_is_temporal_query_false(self):
        from backend.retrieval.temporal_reasoner import TemporalReasoner
        r = TemporalReasoner()
        assert not r.is_temporal_query("What is DSCR?")
        assert not r.is_temporal_query("Who is the Trustee?")
        assert not r.is_temporal_query("Define the Certificate Balance")

    def test_get_temporal_context_contains_date(self):
        from backend.retrieval.temporal_reasoner import TemporalReasoner
        r = TemporalReasoner(current_date_override=date(2026, 2, 18))
        ctx = r.get_temporal_context()
        assert "February 18, 2026" in ctx
        assert "Today's date" in ctx

    def test_get_temporal_evaluation_instruction(self):
        from backend.retrieval.temporal_reasoner import TemporalReasoner
        r = TemporalReasoner(current_date_override=date(2026, 2, 18))
        instr = r.get_temporal_evaluation_instruction()
        assert "February 18, 2026" in instr
        assert "temporal reasoning" in instr.lower()

    def test_build_temporal_prompt_prefix_non_temporal(self):
        from backend.retrieval.temporal_reasoner import TemporalReasoner
        r = TemporalReasoner(current_date_override=date(2026, 2, 18))
        prefix = r.build_temporal_prompt_prefix("What is DSCR?")
        assert "February 18, 2026" in prefix
        # Non-temporal should NOT include evaluation instruction
        assert "temporal reasoning" not in prefix.lower()

    def test_build_temporal_prompt_prefix_temporal(self):
        from backend.retrieval.temporal_reasoner import TemporalReasoner
        r = TemporalReasoner(current_date_override=date(2026, 2, 18))
        prefix = r.build_temporal_prompt_prefix("Has the closing date passed?")
        assert "February 18, 2026" in prefix
        assert "temporal reasoning" in prefix.lower()

    def test_extract_dates_from_text(self):
        from backend.retrieval.temporal_reasoner import TemporalReasoner
        r = TemporalReasoner()
        text = "The Closing Date is March 15, 2006. Settlement is 2023-03-15."
        dates = r.extract_dates_from_text(text)
        assert len(dates) >= 2

    def test_extract_dates_no_dates(self):
        from backend.retrieval.temporal_reasoner import TemporalReasoner
        r = TemporalReasoner()
        dates = r.extract_dates_from_text("No dates here.")
        assert dates == []


class TestPhase14_2_TemporalSignals:
    """Tests for TEMPORAL_SIGNALS constant coverage."""

    def test_signals_list_not_empty(self):
        from backend.retrieval.temporal_reasoner import TEMPORAL_SIGNALS
        assert len(TEMPORAL_SIGNALS) >= 13  # spec has 13 base signals

    def test_signals_are_lowercase(self):
        from backend.retrieval.temporal_reasoner import TEMPORAL_SIGNALS
        for sig in TEMPORAL_SIGNALS:
            assert sig == sig.lower(), f"Signal '{sig}' is not lowercase"

    def test_core_spec_signals_present(self):
        from backend.retrieval.temporal_reasoner import TEMPORAL_SIGNALS
        required = ["passed", "expired", "active", "current", "how long", "period"]
        for sig in required:
            assert sig in TEMPORAL_SIGNALS, f"'{sig}' missing from TEMPORAL_SIGNALS"


class TestPhase14_2_TemporalSystemContext:
    """Tests for the TEMPORAL_SYSTEM_CONTEXT template."""

    def test_template_has_placeholder(self):
        from backend.retrieval.temporal_reasoner import TEMPORAL_SYSTEM_CONTEXT
        assert "{current_date}" in TEMPORAL_SYSTEM_CONTEXT

    def test_template_instructs_about_past_dates(self):
        from backend.retrieval.temporal_reasoner import TEMPORAL_SYSTEM_CONTEXT
        assert "past" in TEMPORAL_SYSTEM_CONTEXT.lower() or "passed" in TEMPORAL_SYSTEM_CONTEXT.lower()

    def test_template_instructs_about_future_dates(self):
        from backend.retrieval.temporal_reasoner import TEMPORAL_SYSTEM_CONTEXT
        assert "future" in TEMPORAL_SYSTEM_CONTEXT.lower() or "remaining" in TEMPORAL_SYSTEM_CONTEXT.lower()


# ═══════════════════════════════════════════════════════════════
# 14.3 — Structured Extraction Mode
# ═══════════════════════════════════════════════════════════════

class TestPhase14_3_ExtractionSchema:
    """Tests for the EXTRACTION_SCHEMA and EXTRACTION_PROMPT."""

    def test_schema_has_required_fields(self):
        from backend.retrieval.extraction_mode import EXTRACTION_SCHEMA
        required = ["deal_name", "deal_type", "closing_date", "parties",
                     "key_dates", "confidence", "extraction_gaps"]
        for field in required:
            assert field in EXTRACTION_SCHEMA, f"'{field}' missing from EXTRACTION_SCHEMA"

    def test_schema_parties_has_roles(self):
        from backend.retrieval.extraction_mode import EXTRACTION_SCHEMA
        parties = EXTRACTION_SCHEMA["parties"]
        assert "Depositor" in parties
        assert "Trustee" in parties
        assert "Master Servicer" in parties

    def test_schema_key_dates_has_entries(self):
        from backend.retrieval.extraction_mode import EXTRACTION_SCHEMA
        dates = EXTRACTION_SCHEMA["key_dates"]
        assert "Closing Date" in dates
        assert "Distribution Date" in dates
        assert "Determination Date" in dates

    def test_prompt_template(self):
        from backend.retrieval.extraction_mode import EXTRACTION_PROMPT
        assert "{schema_json}" in EXTRACTION_PROMPT
        assert "{context}" in EXTRACTION_PROMPT
        assert "extraction_gaps" in EXTRACTION_PROMPT
        assert "ONLY the JSON" in EXTRACTION_PROMPT


class TestPhase14_3_ExtractionConfig:
    """Tests for ExtractionConfig defaults."""

    def test_defaults(self):
        from backend.retrieval.extraction_mode import ExtractionConfig
        cfg = ExtractionConfig()
        assert cfg.chunk_budget == 10
        assert cfg.temperature == 0.0
        assert cfg.max_output_tokens == 2000

    def test_custom_config(self):
        from backend.retrieval.extraction_mode import ExtractionConfig
        cfg = ExtractionConfig(chunk_budget=20, temperature=0.3, max_output_tokens=3000)
        assert cfg.chunk_budget == 20


class TestPhase14_3_ExtractionResult:
    """Tests for ExtractionResult dataclass."""

    def test_basic_construction(self):
        from backend.retrieval.extraction_mode import ExtractionResult
        r = ExtractionResult(data={"deal_name": "Test"}, raw_response="json", parsed_ok=True)
        assert r.data["deal_name"] == "Test"
        assert r.parsed_ok

    def test_to_dict(self):
        from backend.retrieval.extraction_mode import ExtractionResult
        r = ExtractionResult(
            data={"deal_name": "X"},
            raw_response="raw",
            parsed_ok=True,
            extraction_gaps=["Record Date"],
        )
        d = r.to_dict()
        assert d["parsed_ok"]
        assert "Record Date" in d["extraction_gaps"]

    def test_default_gaps_empty(self):
        from backend.retrieval.extraction_mode import ExtractionResult
        r = ExtractionResult(data={}, raw_response="", parsed_ok=False)
        assert r.extraction_gaps == []


class TestPhase14_3_ExtractionMode:
    """Tests for ExtractionMode.extract() with mocked LLM."""

    def test_no_llm_returns_empty(self):
        from backend.retrieval.extraction_mode import ExtractionMode
        mode = ExtractionMode(llm_call_fn=None)
        result = run_async(mode.extract([{"content": "test"}]))
        assert not result.parsed_ok
        assert "No LLM" in result.extraction_gaps[0]

    def test_successful_extraction(self):
        from backend.retrieval.extraction_mode import ExtractionMode
        mock_json = json.dumps({
            "deal_name": "Test Deal",
            "deal_type": "PSA",
            "closing_date": "2006-03-15",
            "parties": {"Trustee": "Deutsche Bank"},
            "key_dates": {"Closing Date": "2006-03-15"},
            "key_amounts": {},
            "defined_terms": {"DSCR": "Debt Service Coverage Ratio"},
            "source_sections": ["Section 1.01"],
            "confidence": "High",
            "extraction_gaps": ["Record Date"],
        })

        async def mock_llm(prompt, max_tokens, temp):
            return mock_json

        mode = ExtractionMode(llm_call_fn=mock_llm)
        result = run_async(mode.extract([{"content": "test chunk"}]))
        assert result.parsed_ok
        assert result.data["deal_name"] == "Test Deal"
        assert result.extraction_gaps == ["Record Date"]

    def test_markdown_code_block_stripping(self):
        from backend.retrieval.extraction_mode import ExtractionMode
        raw_json = json.dumps({"deal_name": "Test"})

        async def mock_llm(prompt, max_tokens, temp):
            return f"```json\n{raw_json}\n```"

        mode = ExtractionMode(llm_call_fn=mock_llm)
        result = run_async(mode.extract([{"content": "test"}]))
        assert result.parsed_ok
        assert result.data["deal_name"] == "Test"

    def test_json_parse_failure_returns_raw(self):
        from backend.retrieval.extraction_mode import ExtractionMode

        async def mock_llm(prompt, max_tokens, temp):
            return "This is not JSON at all"

        mode = ExtractionMode(llm_call_fn=mock_llm)
        result = run_async(mode.extract([{"content": "test"}]))
        assert not result.parsed_ok
        assert "JSON parse failed" in result.extraction_gaps

    def test_llm_exception_handled(self):
        from backend.retrieval.extraction_mode import ExtractionMode

        async def mock_llm(prompt, max_tokens, temp):
            raise RuntimeError("LLM offline")

        mode = ExtractionMode(llm_call_fn=mock_llm)
        result = run_async(mode.extract([{"content": "test"}]))
        assert not result.parsed_ok
        assert any("LLM error" in g for g in result.extraction_gaps)

    def test_chunk_budget_limits_context(self):
        from backend.retrieval.extraction_mode import ExtractionMode, ExtractionConfig

        captured_prompt = []

        async def mock_llm(prompt, max_tokens, temp):
            captured_prompt.append(prompt)
            return json.dumps({"deal_name": "X"})

        config = ExtractionConfig(chunk_budget=2)
        mode = ExtractionMode(llm_call_fn=mock_llm, config=config)
        chunks = [{"content": f"chunk-{i}"} for i in range(10)]
        run_async(mode.extract(chunks))
        # Only 2 chunks should appear in prompt
        prompt = captured_prompt[0]
        assert "chunk-0" in prompt
        assert "chunk-1" in prompt
        assert "chunk-2" not in prompt

    def test_extract_sync_fallback(self):
        from backend.retrieval.extraction_mode import ExtractionMode
        mode = ExtractionMode()
        result = mode.extract_sync([{"content": "test"}])
        assert not result.parsed_ok
        assert "Sync mode" in result.extraction_gaps[0]


# ═══════════════════════════════════════════════════════════════
# 14.4 — Deal Summary Mode
# ═══════════════════════════════════════════════════════════════

class TestPhase14_4_SummaryPrompt:
    """Tests for the SUMMARY_PROMPT template."""

    def test_prompt_has_5_sections(self):
        from backend.retrieval.summary_mode import SUMMARY_PROMPT
        for section in ["Parties", "Key Dates", "Key Amounts", "Key Obligations", "Risk Factors"]:
            assert section in SUMMARY_PROMPT

    def test_prompt_has_temporal_placeholder(self):
        from backend.retrieval.summary_mode import SUMMARY_PROMPT
        assert "{temporal_context}" in SUMMARY_PROMPT

    def test_prompt_has_context_placeholder(self):
        from backend.retrieval.summary_mode import SUMMARY_PROMPT
        assert "{context}" in SUMMARY_PROMPT

    def test_prompt_requests_confidence(self):
        from backend.retrieval.summary_mode import SUMMARY_PROMPT
        assert "Confidence" in SUMMARY_PROMPT


class TestPhase14_4_SummaryConfig:
    """Tests for SummaryConfig defaults."""

    def test_defaults(self):
        from backend.retrieval.summary_mode import SummaryConfig
        cfg = SummaryConfig()
        assert cfg.chunk_budget == 20
        assert cfg.temperature == 0.5
        assert cfg.max_output_tokens == 4000


class TestPhase14_4_SummaryResult:
    """Tests for SummaryResult dataclass."""

    def test_basic_construction(self):
        from backend.retrieval.summary_mode import SummaryResult
        r = SummaryResult(scope="test_deal")
        assert r.scope == "test_deal"
        assert r.raw_markdown == ""
        assert r.confidence == "Low"

    def test_to_dict(self):
        from backend.retrieval.summary_mode import SummaryResult
        r = SummaryResult(
            scope="test",
            raw_markdown="# Summary",
            sections_found=["Parties", "Key Dates"],
            source_sections=["Section 1.01"],
            confidence="High",
        )
        d = r.to_dict()
        assert d["scope"] == "test"
        assert d["confidence"] == "High"
        assert "Section 1.01" in d["source_sections"]


class TestPhase14_4_SummaryMode:
    """Tests for SummaryMode.summarize() with mocked LLM."""

    def test_no_llm_returns_message(self):
        from backend.retrieval.summary_mode import SummaryMode
        mode = SummaryMode(llm_call_fn=None)
        result = run_async(mode.summarize(scope="test", chunks=[]))
        assert "No LLM" in result.raw_markdown

    def test_successful_summary_with_all_sections(self):
        from backend.retrieval.summary_mode import SummaryMode

        raw_md = """## Deal Summary
### 1. Parties
| Role | Entity |
|------|--------|
| Trustee | Deutsche Bank |

### 2. Key Dates
| Date | Value | Status |
|------|-------|--------|
| Closing Date | 2006-03-15 | Passed |

### 3. Key Amounts
| Item | Amount |
|------|--------|
| Certificate Balance | $500M |

### 4. Key Obligations
- Service mortgage loans

### 5. Risk Factors
- Credit risk

*Confidence: High | Sources: Section 1.01, Section 2.03 | Extraction gaps: Optional Termination Date*"""

        async def mock_llm(prompt, max_tokens, temp):
            return raw_md

        mode = SummaryMode(llm_call_fn=mock_llm, temporal_context="Today is Feb 18, 2026")
        result = run_async(mode.summarize(scope="bear_stearns_2006_HE1", chunks=[{"content": "test"}]))
        assert result.confidence == "High"
        assert len(result.sections_found) == 5
        assert result.scope == "bear_stearns_2006_HE1"

    def test_source_sections_parsed_from_confidence_line(self):
        from backend.retrieval.summary_mode import SummaryMode

        raw_md = """### 1. Parties
| Role | Entity |
|------|--------|
| Trustee | DB |

*Confidence: High | Sources: Section 1.01, Section 2.03, Section 11.01 | Extraction gaps: none*"""

        async def mock_llm(prompt, max_tokens, temp):
            return raw_md

        mode = SummaryMode(llm_call_fn=mock_llm)
        result = run_async(mode.summarize(scope="test", chunks=[{"content": "test"}]))
        assert "Section 1.01" in result.source_sections
        assert "Section 2.03" in result.source_sections
        assert "Section 11.01" in result.source_sections

    def test_low_confidence_detection(self):
        from backend.retrieval.summary_mode import SummaryMode

        async def mock_llm(prompt, max_tokens, temp):
            return "### 1. Parties\nNone found\n*Confidence: Low*"

        mode = SummaryMode(llm_call_fn=mock_llm)
        result = run_async(mode.summarize(scope="test", chunks=[{"content": "x"}]))
        assert result.confidence == "Low"

    def test_partial_sections(self):
        from backend.retrieval.summary_mode import SummaryMode

        async def mock_llm(prompt, max_tokens, temp):
            return "### 1. Parties\n| Role | Entity |\n### 2. Key Dates\nNone\n*Confidence: Medium*"

        mode = SummaryMode(llm_call_fn=mock_llm)
        result = run_async(mode.summarize(scope="test", chunks=[{"content": "x"}]))
        assert "Parties" in result.sections_found
        assert "Key Dates" in result.sections_found
        assert "Risk Factors" not in result.sections_found

    def test_llm_exception_handled(self):
        from backend.retrieval.summary_mode import SummaryMode

        async def mock_llm(prompt, max_tokens, temp):
            raise ValueError("LLM crash")

        mode = SummaryMode(llm_call_fn=mock_llm)
        result = run_async(mode.summarize(scope="test", chunks=[{"content": "x"}]))
        assert "failed" in result.raw_markdown.lower()

    def test_temporal_context_injected_in_prompt(self):
        from backend.retrieval.summary_mode import SummaryMode

        captured_prompts = []

        async def mock_llm(prompt, max_tokens, temp):
            captured_prompts.append(prompt)
            return "### 1. Parties\nNone\n*Confidence: Low*"

        mode = SummaryMode(llm_call_fn=mock_llm, temporal_context="Today is February 18, 2026.")
        run_async(mode.summarize(scope="test", chunks=[{"content": "x"}]))
        assert "February 18, 2026" in captured_prompts[0]

    def test_chunk_budget_limits_context(self):
        from backend.retrieval.summary_mode import SummaryMode, SummaryConfig

        captured_prompts = []

        async def mock_llm(prompt, max_tokens, temp):
            captured_prompts.append(prompt)
            return "*Confidence: Low*"

        config = SummaryConfig(chunk_budget=3)
        mode = SummaryMode(llm_call_fn=mock_llm, config=config)
        chunks = [{"content": f"chunk-{i}"} for i in range(10)]
        run_async(mode.summarize(scope="test", chunks=chunks))
        prompt = captured_prompts[0]
        assert "chunk-0" in prompt
        assert "chunk-2" in prompt
        assert "chunk-3" not in prompt

    def test_summarize_sync_fallback(self):
        from backend.retrieval.summary_mode import SummaryMode
        mode = SummaryMode()
        result = mode.summarize_sync("test", [])
        assert "Sync mode" in result.raw_markdown


# ═══════════════════════════════════════════════════════════════
# Config Feature Flags
# ═══════════════════════════════════════════════════════════════

class TestPhase14_Config:
    """Tests for Phase 14 feature flags in KTSConfig."""

    def test_deal_summary_cache_flag_exists(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert hasattr(cfg, "deal_summary_cache_enabled")
        assert cfg.deal_summary_cache_enabled is True

    def test_temporal_reasoning_flag_exists(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert hasattr(cfg, "temporal_reasoning_enabled")
        assert cfg.temporal_reasoning_enabled is True

    def test_extraction_mode_flag_exists(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert hasattr(cfg, "extraction_mode_enabled")
        assert cfg.extraction_mode_enabled is True

    def test_summary_mode_flag_exists(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert hasattr(cfg, "summary_mode_enabled")
        assert cfg.summary_mode_enabled is True

    def test_flags_env_override(self):
        """Feature flags should support env var override."""
        import os
        from config.settings import load_config
        os.environ["KTS_TEMPORAL_REASONING_ENABLED"] = "false"
        try:
            cfg = load_config()
            assert cfg.temporal_reasoning_enabled is False
        finally:
            os.environ.pop("KTS_TEMPORAL_REASONING_ENABLED", None)


# ═══════════════════════════════════════════════════════════════
# __init__.py Exports
# ═══════════════════════════════════════════════════════════════

class TestPhase14_Exports:
    """Tests for Phase 14 module exports in backend/retrieval/__init__.py."""

    def test_temporal_reasoner_exported(self):
        from backend.retrieval import TemporalReasoner, TEMPORAL_SIGNALS, TEMPORAL_SYSTEM_CONTEXT
        assert TemporalReasoner is not None
        assert isinstance(TEMPORAL_SIGNALS, list)
        assert isinstance(TEMPORAL_SYSTEM_CONTEXT, str)

    def test_extraction_mode_exported(self):
        from backend.retrieval import ExtractionMode, ExtractionConfig, ExtractionResult, EXTRACTION_SCHEMA
        assert ExtractionMode is not None
        assert ExtractionConfig is not None
        assert ExtractionResult is not None
        assert isinstance(EXTRACTION_SCHEMA, dict)

    def test_summary_mode_exported(self):
        from backend.retrieval import SummaryMode, SummaryConfig, SummaryResult
        assert SummaryMode is not None
        assert SummaryConfig is not None
        assert SummaryResult is not None

    def test_deal_summary_exported(self):
        from backend.retrieval import DealSummary
        ds = DealSummary()
        assert ds.scope == ""


# ═══════════════════════════════════════════════════════════════
# Extension Rendering
# ═══════════════════════════════════════════════════════════════

class TestPhase14_ExtensionRendering:
    """Structural tests for Phase 14 JS rendering functions."""

    def _read_participant_js(self):
        import os
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "extension", "chat", "participant.js",
        )
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_buildExtractionBlock_defined(self):
        src = self._read_participant_js()
        assert "function buildExtractionBlock(" in src

    def test_buildSummaryBlock_defined(self):
        src = self._read_participant_js()
        assert "function buildSummaryBlock(" in src

    def test_getTemporalContextForPrompt_defined(self):
        src = self._read_participant_js()
        assert "function getTemporalContextForPrompt(" in src

    def test_extract_mode_detection(self):
        src = self._read_participant_js()
        assert "'extract': 'extract'" in src or '"extract": "extract"' in src

    def test_summary_mode_detection(self):
        src = self._read_participant_js()
        assert "'summary': 'summary'" in src or '"summary": "summary"' in src

    def test_functions_exported(self):
        src = self._read_participant_js()
        assert "buildExtractionBlock" in src.split("module.exports")[-1]
        assert "buildSummaryBlock" in src.split("module.exports")[-1]
        assert "getTemporalContextForPrompt" in src.split("module.exports")[-1]

    def test_cached_terms_preamble_injection(self):
        """New: cached terms should be injected into the LLM prompt."""
        src = self._read_participant_js()
        assert "cached_terms" in src
        assert "Previously Resolved Terms" in src

    def test_extraction_block_renders_parties_table(self):
        src = self._read_participant_js()
        # buildExtractionBlock should build a parties table
        block_start = src.index("function buildExtractionBlock(")
        block_end = src.index("function buildSummaryBlock(")
        block = src[block_start:block_end]
        assert "Parties" in block or "parties" in block
        assert "Role" in block

    def test_extraction_block_renders_dates_table(self):
        src = self._read_participant_js()
        block_start = src.index("function buildExtractionBlock(")
        block_end = src.index("function buildSummaryBlock(")
        block = src[block_start:block_end]
        assert "Key Dates" in block or "key_dates" in block

    def test_extraction_block_renders_gaps(self):
        src = self._read_participant_js()
        block_start = src.index("function buildExtractionBlock(")
        block_end = src.index("function buildSummaryBlock(")
        block = src[block_start:block_end]
        assert "Extraction Gaps" in block or "extraction_gaps" in block


# ═══════════════════════════════════════════════════════════════
# Integration: Retrieval Service Wiring
# ═══════════════════════════════════════════════════════════════

class TestPhase14_RetrievalServiceWiring:
    """Structural tests for Phase 14 integration in retrieval_service.py."""

    def _read_service(self):
        import os
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "backend", "agents", "retrieval_service.py",
        )
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_temporal_reasoner_imported(self):
        src = self._read_service()
        assert "from backend.retrieval.temporal_reasoner import TemporalReasoner" in src

    def test_extraction_mode_imported(self):
        src = self._read_service()
        assert "from backend.retrieval.extraction_mode import ExtractionMode" in src

    def test_summary_mode_imported(self):
        src = self._read_service()
        assert "from backend.retrieval.summary_mode import SummaryMode" in src

    def test_extract_entities_imported(self):
        """Cache-first should use extract_entities, not query.split()."""
        src = self._read_service()
        assert "extract_entities" in src

    def test_temporal_reasoner_singleton(self):
        src = self._read_service()
        assert "_temporal_reasoner = TemporalReasoner()" in src

    def test_extraction_mode_singleton(self):
        src = self._read_service()
        assert "_extraction_mode = ExtractionMode()" in src

    def test_summary_mode_singleton(self):
        src = self._read_service()
        assert "_summary_mode = SummaryMode(" in src

    def test_cache_first_uses_extract_entities(self):
        """Verify cache-first lookup uses extract_entities, not query.split()."""
        src = self._read_service()
        # Find the Phase 14.1 cache block
        idx = src.index("Phase 14.1: Cache-first retrieval")
        block = src[idx:idx + 600]
        assert "extract_entities(query)" in block
        assert "query.split()" not in block

    def test_temporal_context_injection_main_path(self):
        src = self._read_service()
        assert "payload[\"temporal_context\"]" in src
        assert "payload[\"temporal_evaluation\"]" in src

    def test_extract_mode_handler(self):
        src = self._read_service()
        assert 'retrieval_mode == "extract"' in src

    def test_summary_mode_handler(self):
        src = self._read_service()
        assert 'retrieval_mode == "summary"' in src

    def test_progressive_population_after_extract(self):
        src = self._read_service()
        # After extraction, session memory should be updated
        idx = src.index("Phase 14.3: Structured Extraction")
        block = src[idx:idx + 1500]
        assert "update_from_answer" in block

    def test_cached_terms_added_to_payload(self):
        src = self._read_service()
        assert 'payload["cached_terms"]' in src


# ═══════════════════════════════════════════════════════════════
# End-to-End Scenarios
# ═══════════════════════════════════════════════════════════════

class TestPhase14_EndToEnd:
    """End-to-end scenario tests verifying Phase 14 data flows."""

    def test_cache_first_flow(self):
        """Simulate: Turn 1 resolves a term, Turn 5 gets it from cache."""
        from backend.retrieval.session_memory import SessionStore
        store = SessionStore()

        # Turn 1: User asks about Determination Date → system resolves it
        store.update_from_answer(
            "session-001",
            '"Determination Date" means the 20th day of each calendar month.',
            [{"content": "Section 1.01...", "source": "psa.pdf"}],
        )

        # Turn 5: Cache lookup should find it
        mem = store.get_or_create("session-001")
        cached = mem.get_cached_term("Determination Date")
        assert cached is not None
        assert "20th day" in cached

    def test_temporal_augmented_retrieval_flow(self):
        """Temporal reasoner augments prompts with date context."""
        from backend.retrieval.temporal_reasoner import TemporalReasoner
        r = TemporalReasoner(current_date_override=date(2026, 2, 18))

        query = "Has the Optional Termination Date passed?"
        assert r.is_temporal_query(query)
        prefix = r.build_temporal_prompt_prefix(query)
        assert "February 18, 2026" in prefix
        assert "temporal reasoning" in prefix.lower()

    def test_extraction_to_cache_flow(self):
        """Extraction results populate the session deal summary."""
        from backend.retrieval.session_memory import SessionStore

        store = SessionStore()
        mem = store.get_or_create("session-001")

        # Simulate extraction result populating cache
        mem.deal_summary.update_from_answer(
            terms={"DSCR": "Debt Service Coverage Ratio"},
            parties={"Trustee": "Deutsche Bank"},
            dates={"Closing Date": "2006-03-15"},
            sections=["1.01", "11.01"],
        )

        assert mem.deal_summary.defined_terms["DSCR"] == "Debt Service Coverage Ratio"
        assert mem.deal_summary.parties["Trustee"] == "Deutsche Bank"
        assert mem.get_cached_term("DSCR") is not None

    def test_summary_with_temporal_context(self):
        """Summary mode receives temporal context when available."""
        from backend.retrieval.summary_mode import SummaryMode

        captured = []

        async def mock_llm(prompt, max_tokens, temp):
            captured.append(prompt)
            return "### 1. Parties\nNone\n*Confidence: Low*"

        mode = SummaryMode(
            llm_call_fn=mock_llm,
            temporal_context="Today's date is February 18, 2026.",
        )
        run_async(mode.summarize(scope="test", chunks=[{"content": "test"}]))
        assert "February 18, 2026" in captured[0]

    def test_full_session_lifecycle(self):
        """Multiple turns build up a rich deal summary."""
        from backend.retrieval.session_memory import SessionStore

        store = SessionStore()
        sid = "session-042"

        # Turn 1: Resolve a party
        store.update_from_answer(sid, "The Trustee is Deutsche Bank.", [])

        # Turn 2: Resolve a date
        store.update_from_answer(sid, "The Closing Date is March 15, 2006.", [])

        # Turn 3: Resolve a defined term
        store.update_from_answer(sid, '"Business Day" means any day other than Saturday.', [])

        # Turn 4: Resolve a section
        store.update_from_answer(sid, "See Section 1.01 and Section 2.03 for details.", [])

        mem = store.get_or_create(sid)
        ds = mem.deal_summary
        assert ds.turn_count >= 4
        assert "Trustee" in ds.parties
        assert "Closing Date" in ds.key_dates
        assert "Business Day" in ds.defined_terms
        assert "1.01" in ds.cited_sections
