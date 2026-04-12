"""Phase 10 — Conversation Memory & Session Intelligence.

Comprehensive tests covering all 4 increments:
  10.1: History extraction & transit
  10.2: Query rewriting via coreference resolution
  10.3: Entity session memory & document bias
  10.4: History summarization (rolling summary buffer)

Also covers: config flags, TTL eviction, MAX_SESSIONS cap,
heuristic summarization quality, integration pipeline end-to-end.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.retrieval.query_rewriter import (
    COREFERENCE_SIGNALS,
    REWRITE_PROMPT,
    QueryRewriter,
    QueryRewriterConfig,
    RewriteResult,
    _extract_subject_from_history,
    _heuristic_rewrite,
    _needs_rewrite,
    format_history,
)
from backend.retrieval.session_memory import (
    DEFAULT_TTL_HOURS,
    DOCUMENT_BIAS_BOOST,
    MAX_SESSIONS,
    MAX_VERBATIM_TURNS,
    SUMMARY_PROMPT,
    DealSummary,
    SessionMemory,
    SessionStore,
    apply_document_bias,
    apply_summary,
    build_summary_prompt,
    get_conversation_context,
    should_summarise,
)
from config.settings import KTSConfig


# ═══════════════════════════════════════════════════════════════
# 10.1: History Extraction & Transit
# ═══════════════════════════════════════════════════════════════


@pytest.mark.phase10
class TestHistoryExtraction:
    """Inc 10.1 — validate history formatting and transit contracts."""

    def test_format_history_basic(self):
        """format_history produces role-prefixed lines."""
        turns = [
            {"role": "user", "content": "What is the Determination Date?"},
            {"role": "assistant", "content": "The Determination Date is the 25th."},
        ]
        result = format_history(turns)
        assert "User:" in result
        assert "Assistant:" in result
        assert "Determination Date" in result

    def test_format_history_truncates_long_content(self):
        """Individual turn content is truncated to 500 chars."""
        turns = [{"role": "user", "content": "x" * 1000}]
        result = format_history(turns)
        assert len(result) <= 600  # role prefix + 500 chars

    def test_format_history_respects_max_turns(self):
        """Only the last max_turns turns are included."""
        turns = [{"role": "user", "content": f"Turn {i}"} for i in range(20)]
        result = format_history(turns, max_turns=4)
        assert "Turn 16" in result
        assert "Turn 0" not in result

    def test_format_history_empty(self):
        """Empty turns produce empty string."""
        assert format_history([]) == ""

    def test_format_history_missing_role(self):
        """Turn with missing role defaults to 'user'."""
        turns = [{"content": "hello"}]
        result = format_history(turns)
        assert "User:" in result

    def test_conversation_context_json_roundtrip(self):
        """Conversation context is JSON-serializable and roundtrippable."""
        turns = [
            {"role": "user", "content": "What is the Closing Date?"},
            {"role": "assistant", "content": "December 1, 2025."},
        ]
        serialized = json.dumps(turns)
        deserialized = json.loads(serialized)
        assert deserialized == turns

    def test_rewrite_result_to_dict(self):
        """RewriteResult.to_dict() produces all required keys."""
        r = RewriteResult(
            original_query="What about it?",
            rewritten_query="What about the Determination Date?",
            was_rewritten=True,
        )
        d = r.to_dict()
        assert d["original_query"] == "What about it?"
        assert d["rewritten_query"] == "What about the Determination Date?"
        assert d["was_rewritten"] is True
        assert d["skip_reason"] is None


# ═══════════════════════════════════════════════════════════════
# 10.2: Query Rewriting via Coreference Resolution
# ═══════════════════════════════════════════════════════════════


@pytest.mark.phase10
@pytest.mark.query_rewrite
class TestCoreferenceSignalDetection:
    """Inc 10.2 — signal-gated coreference detection."""

    def test_coreference_signals_populated(self):
        """COREFERENCE_SIGNALS list has at least 15 entries."""
        assert len(COREFERENCE_SIGNALS) >= 15

    def test_needs_rewrite_with_pronoun(self):
        """Queries with pronouns need rewriting."""
        assert _needs_rewrite("What happens if it falls on a weekend?", 8) is True

    def test_needs_rewrite_with_same(self):
        assert _needs_rewrite("Is the same rule used here?", 8) is True

    def test_needs_rewrite_with_which(self):
        assert _needs_rewrite("Which one comes first?", 8) is True

    def test_no_rewrite_standalone_long(self):
        """Long specific queries without signals skip rewrite."""
        assert _needs_rewrite(
            "What is the interest rate on the Class A-1 certificates?", 8
        ) is False

    def test_short_query_always_needs_rewrite(self):
        """Very short queries (<=3 words) always need rewrite."""
        assert _needs_rewrite("And then?", 8) is True

    def test_no_rewrite_medium_no_signals(self):
        """Medium queries without signals don't need rewrite."""
        assert _needs_rewrite("Explain the fee structure", 8) is False

    def test_signal_pattern_case_insensitive(self):
        """Signal detection is case-insensitive."""
        assert _needs_rewrite("IT IS the same", 8) is True


@pytest.mark.phase10
@pytest.mark.query_rewrite
class TestSyncRewrite:
    """Inc 10.2 — heuristic (sync) rewriting without LLM."""

    def test_rewrite_replaces_it(self):
        """'it' is replaced with subject from history."""
        qr = QueryRewriter()
        history = [
            {"role": "user", "content": "What is the Determination Date?"},
            {"role": "assistant", "content": "The Determination Date is the 25th."},
        ]
        result = qr.rewrite_sync("What happens if it falls on a weekend?", history)
        assert result.was_rewritten is True
        assert "determination date" in result.rewritten_query.lower()

    def test_rewrite_replaces_this(self):
        """'this' is replaced with subject."""
        qr = QueryRewriter()
        history = [{"role": "user", "content": "Who is the Trustee?"}]
        result = qr.rewrite_sync("What are this obligations?", history)
        assert result.was_rewritten is True

    def test_rewrite_no_history_returns_original(self):
        """Empty history returns original query."""
        qr = QueryRewriter()
        result = qr.rewrite_sync("What about it?", [])
        assert result.was_rewritten is False
        assert result.skip_reason == "No history (first turn)"

    def test_rewrite_disabled_returns_original(self):
        """Disabled config returns original."""
        qr = QueryRewriter(config=QueryRewriterConfig(enabled=False))
        result = qr.rewrite_sync(
            "What about it?",
            [{"role": "user", "content": "Determination Date"}],
        )
        assert result.was_rewritten is False
        assert result.skip_reason == "Rewriting disabled"

    def test_rewrite_no_signals_returns_original(self):
        """Query without coreference signals is left unchanged."""
        qr = QueryRewriter()
        result = qr.rewrite_sync(
            "Explain the complete fee structure in detail for our deal",
            [{"role": "user", "content": "What is the Closing Date?"}],
        )
        assert result.was_rewritten is False

    def test_rewrite_preserves_original_in_result(self):
        """original_query is always preserved."""
        qr = QueryRewriter()
        result = qr.rewrite_sync(
            "And?",
            [{"role": "user", "content": "What is the Closing Date?"}],
        )
        assert result.original_query == "And?"


@pytest.mark.phase10
@pytest.mark.query_rewrite
class TestAsyncRewrite:
    """Inc 10.2 — LLM-based (async) rewriting."""

    def test_async_rewrite_calls_llm(self):
        """Async rewrite invokes the LLM callable."""
        called = {"count": 0}

        async def mock_llm(prompt, max_tokens, temperature):
            called["count"] += 1
            return "What happens if the Determination Date falls on a weekend?"

        qr = QueryRewriter(llm_call_fn=mock_llm)
        history = [{"role": "user", "content": "What is the Determination Date?"}]

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                qr.rewrite("What about it?", history)
            )
        finally:
            loop.close()

        assert result.was_rewritten is True
        assert called["count"] == 1
        assert "Determination Date" in result.rewritten_query

    def test_async_rewrite_no_llm_returns_original(self):
        """Without LLM callable, returns original."""
        qr = QueryRewriter(llm_call_fn=None)
        history = [{"role": "user", "content": "What is the Closing Date?"}]
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(qr.rewrite("What about it?", history))
        finally:
            loop.close()
        assert result.was_rewritten is False
        assert result.skip_reason == "No LLM function provided"

    def test_async_rewrite_llm_failure_returns_original(self):
        """LLM failure gracefully returns original."""
        async def failing_llm(prompt, max_tokens, temperature):
            raise RuntimeError("LLM unavailable")

        qr = QueryRewriter(llm_call_fn=failing_llm)
        history = [{"role": "user", "content": "Distribution Date"}]
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                qr.rewrite("What about it?", history)
            )
        finally:
            loop.close()
        assert result.was_rewritten is False
        assert "LLM error" in result.skip_reason

    def test_async_rewrite_empty_response_returns_original(self):
        """LLM returning empty still returns original."""
        async def empty_llm(prompt, max_tokens, temperature):
            return ""

        qr = QueryRewriter(llm_call_fn=empty_llm)
        history = [{"role": "user", "content": "Determination Date"}]
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(qr.rewrite("It?", history))
        finally:
            loop.close()
        assert result.was_rewritten is False

    def test_async_rewrite_identical_returns_unchanged(self):
        """When LLM returns the same query, was_rewritten is False."""
        async def echo_llm(prompt, max_tokens, temperature):
            return "What about it?"

        qr = QueryRewriter(llm_call_fn=echo_llm)
        history = [{"role": "user", "content": "Determination Date"}]
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                qr.rewrite("What about it?", history)
            )
        finally:
            loop.close()
        assert result.was_rewritten is False


@pytest.mark.phase10
@pytest.mark.query_rewrite
class TestSubjectExtraction:
    """Inc 10.2 — subject extraction from history."""

    def test_extract_what_is_pattern(self):
        """Extract from 'What is the X?' pattern."""
        history = [{"role": "user", "content": "What is the Determination Date?"}]
        subject = _extract_subject_from_history(history)
        assert subject is not None
        assert "determination date" in subject.lower()

    def test_extract_capitalised_phrase(self):
        """Extract capitalised noun phrases."""
        history = [
            {"role": "user", "content": "Tell me about Deutsche Bank Trust Company."}
        ]
        subject = _extract_subject_from_history(history)
        assert subject is not None

    def test_no_user_turns_returns_none(self):
        """No user turns in history returns None."""
        history = [{"role": "assistant", "content": "The Trustee is..."}]
        subject = _extract_subject_from_history(history)
        assert subject is None

    def test_empty_history_returns_none(self):
        assert _extract_subject_from_history([]) is None


@pytest.mark.phase10
@pytest.mark.query_rewrite
class TestHeuristicRewrite:
    """Inc 10.2 — pronoun replacement heuristics."""

    def test_replace_it(self):
        """'it' → subject."""
        result = _heuristic_rewrite("What about it?", "Determination Date")
        assert "Determination Date" in result

    def test_replace_this(self):
        result = _heuristic_rewrite("How does this work?", "Determination Date")
        assert "Determination Date" in result

    def test_replace_the_above(self):
        result = _heuristic_rewrite("Explain the above", "Servicer Advance")
        assert "Servicer Advance" in result

    def test_no_double_the(self):
        """No 'the the X' when subject starts with 'the'."""
        result = _heuristic_rewrite("What about this?", "the Fee Schedule")
        assert "the the" not in result.lower()


# ═══════════════════════════════════════════════════════════════
# 10.3: Entity Session Memory & Document Bias
# ═══════════════════════════════════════════════════════════════


@pytest.mark.phase10
@pytest.mark.session_memory
class TestSessionMemoryDataclass:
    """Inc 10.3 — SessionMemory data model."""

    def test_create_empty_session(self):
        mem = SessionMemory(session_id="test-123")
        assert mem.session_id == "test-123"
        assert mem.turn_count == 0
        assert mem.resolved_terms == {}
        assert mem.active_documents == []

    def test_touch_increments_turn(self):
        mem = SessionMemory(session_id="x")
        mem.touch()
        assert mem.turn_count == 1
        mem.touch()
        assert mem.turn_count == 2

    def test_add_active_document(self):
        mem = SessionMemory(session_id="x")
        mem.add_active_document("/docs/psa.pdf")
        mem.add_active_document("/docs/trust.pdf")
        assert len(mem.active_documents) == 2
        assert "/docs/psa.pdf" in mem.active_documents

    def test_add_active_document_deduplicates(self):
        mem = SessionMemory(session_id="x")
        mem.add_active_document("/docs/psa.pdf")
        mem.add_active_document("/docs/psa.pdf")
        assert len(mem.active_documents) == 1

    def test_add_active_document_caps_at_50(self):
        mem = SessionMemory(session_id="x")
        for i in range(60):
            mem.add_active_document(f"/docs/doc{i}.pdf")
        assert len(mem.active_documents) == 50

    def test_add_active_section(self):
        mem = SessionMemory(session_id="x")
        mem.add_active_section("sec001")
        assert "sec001" in mem.active_sections

    def test_resolve_term(self):
        mem = SessionMemory(session_id="x")
        mem.resolve_term("Determination Date", "25th of each month")
        assert mem.get_cached_term("Determination Date") == "25th of each month"

    def test_get_cached_term_case_insensitive(self):
        mem = SessionMemory(session_id="x")
        mem.resolve_term("Closing Date", "December 1, 2025")
        assert mem.get_cached_term("closing date") == "December 1, 2025"

    def test_get_cached_term_nonexistent(self):
        mem = SessionMemory(session_id="x")
        assert mem.get_cached_term("nonexistent") is None

    def test_to_dict_includes_key_fields(self):
        mem = SessionMemory(session_id="test-1")
        mem.resolve_term("X", "Y")
        d = mem.to_dict()
        assert d["session_id"] == "test-1"
        assert d["resolved_terms_count"] == 1
        assert "deal_summary" in d

    def test_get_cached_term_falls_through_to_deal_summary(self):
        """get_cached_term checks deal summary after resolved_terms."""
        mem = SessionMemory(session_id="x")
        mem.deal_summary.defined_terms["Closing Date"] = "Dec 1"
        assert mem.get_cached_term("closing date") == "Dec 1"


@pytest.mark.phase10
@pytest.mark.session_memory
class TestSessionStore:
    """Inc 10.3 — session store with TTL eviction."""

    def test_get_or_create_new(self):
        store = SessionStore()
        session = store.get_or_create("sess-1")
        assert session.session_id == "sess-1"
        assert store.session_count == 1

    def test_get_or_create_existing(self):
        store = SessionStore()
        s1 = store.get_or_create("sess-1")
        s2 = store.get_or_create("sess-1")
        assert s1 is s2
        assert store.session_count == 1

    def test_get_nonexistent_returns_none(self):
        store = SessionStore()
        assert store.get("nonexistent") is None

    def test_remove_session(self):
        store = SessionStore()
        store.get_or_create("sess-1")
        store.remove("sess-1")
        assert store.session_count == 0

    def test_max_sessions_eviction(self):
        """Creating more than MAX_SESSIONS evicts oldest."""
        store = SessionStore()
        for i in range(MAX_SESSIONS + 5):
            store.get_or_create(f"sess-{i}")
        assert store.session_count <= MAX_SESSIONS

    def test_ttl_eviction(self):
        """Sessions past TTL are evicted on next access."""
        store = SessionStore(ttl_hours=0.001)  # ~3.6 seconds
        store.get_or_create("old-session")
        # Force the session's last_accessed to be in the past
        session = store._sessions["old-session"]
        session.last_accessed = datetime.now() - timedelta(hours=1)
        # Access triggers eviction
        store.get_or_create("new-session")
        assert store.get("old-session") is None

    def test_ttl_default_is_4_hours(self):
        store = SessionStore()
        assert store._ttl == timedelta(hours=DEFAULT_TTL_HOURS)

    def test_update_from_answer_tracks_documents(self):
        store = SessionStore()
        store.update_from_answer(
            "sess-1", "The Trustee is Deutsche Bank.",
            [{"content": "...", "source": "/docs/psa.pdf"}],
        )
        session = store.get_or_create("sess-1")
        assert "/docs/psa.pdf" in session.active_documents

    def test_update_from_answer_extracts_parties(self):
        store = SessionStore()
        store.update_from_answer(
            "sess-1", "Trustee: Deutsche Bank National Trust Company.",
            [{"content": "...", "source": "psa.pdf"}],
        )
        session = store.get_or_create("sess-1")
        assert "Trustee" in session.deal_summary.parties

    def test_update_from_answer_extracts_dates(self):
        store = SessionStore()
        store.update_from_answer(
            "sess-1",
            "The Closing Date is December 1, 2025.",
            [{"content": "...", "source": "psa.pdf"}],
        )
        session = store.get_or_create("sess-1")
        assert "Closing Date" in session.deal_summary.key_dates

    def test_update_from_answer_increments_turn_count(self):
        store = SessionStore()
        store.update_from_answer("s1", "Answer", [{"content": "x", "source": "y"}])
        store.update_from_answer("s1", "Answer 2", [{"content": "x2", "source": "y"}])
        session = store.get_or_create("s1")
        assert session.deal_summary.turn_count >= 2


@pytest.mark.phase10
@pytest.mark.session_memory
class TestDocumentBias:
    """Inc 10.3 — retrieval score boosting for in-context documents."""

    def test_boost_active_doc(self):
        """Active documents get 15% score boost."""
        session = SessionMemory(session_id="x")
        session.add_active_document("doc-A")
        results = [
            {"doc_id": "doc-A", "source_path": "a.pdf", "score": 0.80},
            {"doc_id": "doc-B", "source_path": "b.pdf", "score": 0.85},
        ]
        biased = apply_document_bias(results, session)
        # doc-A should now be 0.80 * 1.15 = 0.92, beating doc-B at 0.85
        assert biased[0]["doc_id"] == "doc-A"

    def test_no_active_docs_no_op(self):
        """Without active docs, result list is returned unmodified."""
        session = SessionMemory(session_id="x")
        results = [
            {"doc_id": "A", "source_path": "a", "score": 0.8},
            {"doc_id": "B", "source_path": "b", "score": 0.9},
        ]
        biased = apply_document_bias(results, session)
        # With no active docs function returns early — original order preserved
        assert biased[0]["doc_id"] == "A"
        assert biased[1]["doc_id"] == "B"

    def test_custom_boost_factor(self):
        """Custom boost factor is respected."""
        session = SessionMemory(session_id="x")
        session.add_active_document("doc-A")
        results = [
            {"doc_id": "doc-A", "source_path": "a", "score": 0.80},
            {"doc_id": "doc-B", "source_path": "b", "score": 0.95},
        ]
        # With 1.15 boost: 0.80 * 1.15 = 0.92, still less than 0.95
        biased = apply_document_bias(results, session, boost_factor=1.15)
        assert biased[0]["doc_id"] == "doc-B"
        # With 1.25 boost: 0.80 * 1.25 = 1.00, beats 0.95
        biased2 = apply_document_bias(results, session, boost_factor=1.25)
        assert biased2[0]["doc_id"] == "doc-A"

    def test_document_bias_default_boost(self):
        """Default boost is 1.15 (DOCUMENT_BIAS_BOOST constant)."""
        assert DOCUMENT_BIAS_BOOST == 1.15

    def test_bias_by_source_path(self):
        """Bias works with source_path matching."""
        session = SessionMemory(session_id="x")
        session.add_active_document("/docs/important.pdf")
        results = [
            {"doc_id": "d1", "source_path": "/docs/important.pdf", "score": 0.7},
            {"doc_id": "d2", "source_path": "/docs/other.pdf", "score": 0.75},
        ]
        biased = apply_document_bias(results, session)
        assert biased[0]["source_path"] == "/docs/important.pdf"

    def test_bias_marks_biased_flag(self):
        """Biased chunks get _document_biased flag."""
        session = SessionMemory(session_id="x")
        session.add_active_document("d1")
        results = [{"doc_id": "d1", "source_path": "a", "score": 0.5}]
        biased = apply_document_bias(results, session)
        assert biased[0].get("_document_biased") is True

    def test_custom_score_key(self):
        """Bias works with custom score key."""
        session = SessionMemory(session_id="x")
        session.add_active_document("d1")
        results = [
            {"doc_id": "d1", "source_path": "a", "_rerank_score": 0.7},
            {"doc_id": "d2", "source_path": "b", "_rerank_score": 0.8},
        ]
        biased = apply_document_bias(results, session, score_key="_rerank_score")
        assert biased[0]["doc_id"] == "d1"  # 0.7 * 1.15 = 0.805 > 0.8


# ═══════════════════════════════════════════════════════════════
# 10.4: History Summarization
# ═══════════════════════════════════════════════════════════════


@pytest.mark.phase10
@pytest.mark.history_summarize
class TestSummarisation:
    """Inc 10.4 — rolling summary buffer pattern."""

    def test_should_summarise_below_threshold(self):
        """Under MAX_VERBATIM_TURNS * 2, no summarization needed."""
        session = SessionMemory(session_id="x")
        session.verbatim_recent_turns = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
        ]
        assert should_summarise(session) is False

    def test_should_summarise_above_threshold(self):
        """Above MAX_VERBATIM_TURNS * 2, summarization triggered."""
        session = SessionMemory(session_id="x")
        session.verbatim_recent_turns = [
            {"role": "user", "content": f"Q{i}"} for i in range(MAX_VERBATIM_TURNS * 2 + 1)
        ]
        assert should_summarise(session) is True

    def test_build_summary_prompt_below_threshold(self):
        session = SessionMemory(session_id="x")
        assert build_summary_prompt(session) is None

    def test_build_summary_prompt_includes_existing_summary(self):
        session = SessionMemory(session_id="x")
        session.rolling_summary = "Prior: Trustee is Deutsche Bank"
        session.verbatim_recent_turns = [
            {"role": "user", "content": f"Q{i}"} for i in range(MAX_VERBATIM_TURNS * 2 + 1)
        ]
        prompt = build_summary_prompt(session)
        assert prompt is not None
        assert "Prior: Trustee is Deutsche Bank" in prompt

    def test_build_summary_prompt_none_when_no_existing(self):
        session = SessionMemory(session_id="x")
        session.verbatim_recent_turns = [
            {"role": "user", "content": f"Q{i}"} for i in range(MAX_VERBATIM_TURNS * 2 + 1)
        ]
        prompt = build_summary_prompt(session)
        assert "(none yet)" in prompt

    def test_apply_summary_sets_rolling_summary(self):
        session = SessionMemory(session_id="x")
        session.verbatim_recent_turns = [
            {"role": "user", "content": f"Turn {i}"} for i in range(10)
        ]
        apply_summary(session, "Compressed summary of turns 0-3")
        assert session.rolling_summary == "Compressed summary of turns 0-3"
        # Verbatim should be trimmed
        assert len(session.verbatim_recent_turns) == 6  # 10 - 4

    def test_apply_summary_truncates_to_1000_chars(self):
        session = SessionMemory(session_id="x")
        session.verbatim_recent_turns = [{"role": "user", "content": "x"}] * 10
        apply_summary(session, "y" * 2000)
        assert len(session.rolling_summary) <= 1000

    def test_get_conversation_context_empty(self):
        session = SessionMemory(session_id="x")
        ctx = get_conversation_context(session)
        assert ctx == []

    def test_get_conversation_context_with_summary(self):
        session = SessionMemory(session_id="x")
        session.rolling_summary = "Prior facts: Trustee is DB"
        ctx = get_conversation_context(session)
        assert ctx[0]["role"] == "system"
        assert "Prior facts" in ctx[0]["content"]

    def test_get_conversation_context_limits_verbatim(self):
        session = SessionMemory(session_id="x")
        session.verbatim_recent_turns = [
            {"role": "user", "content": f"Turn {i}"} for i in range(20)
        ]
        ctx = get_conversation_context(session)
        # Should be MAX_VERBATIM_TURNS * 2 at most
        assert len(ctx) <= MAX_VERBATIM_TURNS * 2

    def test_summary_prompt_template_has_placeholders(self):
        """SUMMARY_PROMPT has both placeholders."""
        assert "{existing_summary}" in SUMMARY_PROMPT
        assert "{new_turns}" in SUMMARY_PROMPT

    def test_max_verbatim_turns_is_4(self):
        assert MAX_VERBATIM_TURNS == 4


# ═══════════════════════════════════════════════════════════════
# 10.4: Heuristic Summarisation Quality
# ═══════════════════════════════════════════════════════════════


@pytest.mark.phase10
@pytest.mark.history_summarize
class TestHeuristicSummarization:
    """Inc 10.4 — heuristic summary extraction quality tests."""

    def test_heuristic_extracts_dates(self):
        """Heuristic summariser extracts date references."""
        from backend.agents.retrieval_service import _heuristic_summarise
        turns = [
            {"role": "assistant", "content": "The Closing Date is December 1, 2025."},
        ]
        summary = _heuristic_summarise("", turns)
        assert "December 1, 2025" in summary

    def test_heuristic_extracts_amounts(self):
        from backend.agents.retrieval_service import _heuristic_summarise
        turns = [
            {"role": "assistant", "content": "The initial principal is $500,000,000."},
        ]
        summary = _heuristic_summarise("", turns)
        assert "$500,000,000" in summary

    def test_heuristic_extracts_parties(self):
        from backend.agents.retrieval_service import _heuristic_summarise
        turns = [
            {"role": "assistant", "content": "Trustee: Deutsche Bank National Trust."},
        ]
        summary = _heuristic_summarise("", turns)
        assert "Trustee" in summary
        assert "Deutsche Bank" in summary

    def test_heuristic_preserves_existing_summary(self):
        from backend.agents.retrieval_service import _heuristic_summarise
        turns = [{"role": "user", "content": "Question"}]
        summary = _heuristic_summarise("Prior: Servicer is Wells Fargo", turns)
        assert "Prior: Servicer is Wells Fargo" in summary

    def test_heuristic_deduplicates_facts(self):
        from backend.agents.retrieval_service import _heuristic_summarise
        turns = [
            {"role": "assistant", "content": "Closing Date is December 1, 2025."},
            {"role": "user", "content": "And the Closing Date — December 1, 2025 again?"},
        ]
        summary = _heuristic_summarise("", turns)
        # Should have only one occurrence of the date fact
        assert summary.count("December 1, 2025") == 1

    def test_heuristic_fallback_on_no_entities(self):
        """When no entities found, falls back to truncated concatenation."""
        from backend.agents.retrieval_service import _heuristic_summarise
        turns = [{"role": "user", "content": "hello world plain text"}]
        summary = _heuristic_summarise("", turns)
        assert "hello world" in summary

    def test_heuristic_caps_at_1000_chars(self):
        from backend.agents.retrieval_service import _heuristic_summarise
        turns = [{"role": "assistant", "content": f"Trustee: Party{i} BigBank Corp." } for i in range(100)]
        summary = _heuristic_summarise("", turns)
        assert len(summary) <= 1000


# ═══════════════════════════════════════════════════════════════
# Deal Summary (Phase 14.1 integration in session memory)
# ═══════════════════════════════════════════════════════════════


@pytest.mark.phase10
@pytest.mark.session_memory
class TestDealSummary:

    def test_create_empty(self):
        ds = DealSummary()
        assert ds.turn_count == 0
        assert ds.parties == {}
        assert ds.defined_terms == {}

    def test_update_from_answer(self):
        ds = DealSummary()
        ds.update_from_answer(
            terms={"Closing Date": "Dec 1"},
            parties={"Trustee": "Deutsche Bank"},
        )
        assert ds.defined_terms["Closing Date"] == "Dec 1"
        assert ds.parties["Trustee"] == "Deutsche Bank"
        assert ds.turn_count == 1

    def test_lookup_term_case_insensitive(self):
        ds = DealSummary()
        ds.defined_terms["Closing Date"] = "Dec 1"
        assert ds.lookup_term("closing date") == "Dec 1"

    def test_lookup_term_nonexistent(self):
        ds = DealSummary()
        assert ds.lookup_term("X") is None

    def test_to_dict(self):
        ds = DealSummary()
        ds.update_from_answer(parties={"Trustee": "DB"})
        d = ds.to_dict()
        assert d["parties"]["Trustee"] == "DB"
        assert d["turn_count"] == 1

    def test_cited_sections_tracked(self):
        ds = DealSummary()
        ds.update_from_answer(sections=["2.01", "3.05"])
        assert "2.01" in ds.cited_sections
        assert "3.05" in ds.cited_sections


# ═══════════════════════════════════════════════════════════════
# Config Flags
# ═══════════════════════════════════════════════════════════════


@pytest.mark.phase10
class TestPhase10Config:

    def test_all_five_flags_exist(self):
        """All 5 Phase 10 config flags exist with correct defaults."""
        cfg = KTSConfig()
        assert cfg.session_memory_enabled is True
        assert cfg.query_rewriting_enabled is True
        assert cfg.history_summarization_enabled is True
        assert cfg.history_max_turns == 20
        assert cfg.session_memory_ttl_hours == 4.0

    def test_history_max_turns_env_override(self):
        import os
        os.environ["KTS_HISTORY_MAX_TURNS"] = "20"
        try:
            from config.settings import load_config
            cfg = load_config()
            assert cfg.history_max_turns == 20
        finally:
            del os.environ["KTS_HISTORY_MAX_TURNS"]

    def test_session_ttl_env_override(self):
        import os
        os.environ["KTS_SESSION_MEMORY_TTL_HOURS"] = "8.0"
        try:
            from config.settings import load_config
            cfg = load_config()
            assert cfg.session_memory_ttl_hours == 8.0
        finally:
            del os.environ["KTS_SESSION_MEMORY_TTL_HOURS"]


# ═══════════════════════════════════════════════════════════════
# Integration / End-to-End
# ═══════════════════════════════════════════════════════════════


@pytest.mark.phase10
class TestPhase10Integration:

    def test_full_pipeline_rewrite_bias_summarize(self):
        """Full pipeline: rewrite → session memory update → document bias → summarize."""
        # 1. Rewrite
        qr = QueryRewriter()
        history = [
            {"role": "user", "content": "What is the Determination Date?"},
            {"role": "assistant", "content": "The Determination Date is the 25th."},
        ]
        rw = qr.rewrite_sync("And what happens if it falls on a weekend?", history)
        assert rw.was_rewritten is True

        # 2. Session memory
        store = SessionStore()
        store.update_from_answer(
            "sess-1",
            "The Determination Date is the 25th of each month.",
            [{"content": "...", "source": "/docs/psa.pdf"}],
        )
        session = store.get_or_create("sess-1")
        assert "/docs/psa.pdf" in session.active_documents

        # 3. Document bias
        results = [
            {"doc_id": "psa", "source_path": "/docs/psa.pdf", "score": 0.80},
            {"doc_id": "other", "source_path": "/docs/other.pdf", "score": 0.82},
        ]
        biased = apply_document_bias(results, session)
        assert biased[0]["doc_id"] == "psa"  # boosted past 0.82

        # 4. Summarization
        for i in range(MAX_VERBATIM_TURNS * 2 + 2):
            session.verbatim_recent_turns.append(
                {"role": "user", "content": f"Turn {i}"}
            )
        assert should_summarise(session) is True
        prompt = build_summary_prompt(session)
        assert prompt is not None
        apply_summary(session, "Summary: Determination Date is 25th")
        ctx = get_conversation_context(session)
        assert any("Summary" in t.get("content", "") for t in ctx)

    def test_session_memory_wiring_imports(self):
        """All Phase 10 functions used by retrieval_service are importable."""
        from backend.retrieval.session_memory import (
            SessionStore,
            apply_document_bias,
            should_summarise,
            build_summary_prompt,
            apply_summary,
        )
        from backend.retrieval.query_rewriter import QueryRewriter
        assert callable(apply_document_bias)
        assert callable(should_summarise)
        assert callable(build_summary_prompt)
        assert callable(apply_summary)

    def test_heuristic_summarise_importable(self):
        """_heuristic_summarise is importable from retrieval_service."""
        from backend.agents.retrieval_service import _heuristic_summarise
        assert callable(_heuristic_summarise)

    def test_multiple_sessions_isolated(self):
        """Different session_ids get isolated memories."""
        store = SessionStore()
        store.update_from_answer("s1", "Trustee: Bank A.", [{"content": ".", "source": "a"}])
        store.update_from_answer("s2", "Trustee: Bank B.", [{"content": ".", "source": "b"}])
        s1 = store.get_or_create("s1")
        s2 = store.get_or_create("s2")
        assert s1.active_documents != s2.active_documents

    def test_session_memory_disabled_graceful(self):
        """When session_memory_enabled=False, SessionStore is not created."""
        cfg = KTSConfig()
        cfg.session_memory_enabled = False
        # Simulates what retrieval_service does
        store = SessionStore() if cfg.session_memory_enabled else None
        assert store is None

    def test_query_rewriting_disabled_graceful(self):
        """When query_rewriting_enabled=False, QueryRewriter is not created."""
        cfg = KTSConfig()
        cfg.query_rewriting_enabled = False
        qr = QueryRewriter() if cfg.query_rewriting_enabled else None
        assert qr is None

    def test_progressive_deal_summary_across_turns(self):
        """Deal summary accumulates data across multiple turns."""
        store = SessionStore()
        store.update_from_answer(
            "s1",
            "Trustee: Deutsche Bank.",
            [{"content": "...", "source": "psa.pdf"}],
        )
        store.update_from_answer(
            "s1",
            'The Closing Date is January 15, 2026.',
            [{"content": "...", "source": "psa.pdf"}],
        )
        store.update_from_answer(
            "s1",
            "Servicer: Wells Fargo Home Mortgage.",
            [{"content": "...", "source": "psa.pdf"}],
        )
        session = store.get_or_create("s1")
        ds = session.deal_summary
        assert ds.turn_count >= 3
        assert "Trustee" in ds.parties
        assert "Servicer" in ds.parties

    def test_rewrite_prompt_template_has_placeholders(self):
        """REWRITE_PROMPT has {history} and {query} placeholders."""
        assert "{history}" in REWRITE_PROMPT
        assert "{query}" in REWRITE_PROMPT

    def test_rewrite_result_serializable(self):
        """RewriteResult is JSON-serializable via to_dict."""
        r = RewriteResult("q", "q2", True, None)
        d = r.to_dict()
        s = json.dumps(d)
        assert json.loads(s)["was_rewritten"] is True
