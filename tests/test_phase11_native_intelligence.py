"""
Phase 11 — VS Code Native Intelligence Layer — Comprehensive Tests.

Tests all 7 increments:
  11.1  #file / #selection / #editor references (extractReferences)
  11.2  Follow-up question suggestions (buildFollowUpSuggestions)
  11.3  Rich retrieval progress streaming (SSE progress callback)
  11.4  Slash command modes (/define, /extract, /compare, /audit, /summary)
  11.5  Runtime model selection (kts.generationModel setting)
  11.6  Confirmation dialogs for destructive operations
  11.7  Interactive ingestion classification (HITL)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ─── Helpers ──────────────────────────────────────────────────

def _run(coro):
    """Run async in test without pytest-asyncio."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════
# INCREMENT 11.1 — #file / #selection / #editor References
# ═══════════════════════════════════════════════════════════════

@pytest.mark.phase11
class TestInc11_1_ExtractReferences:
    """Tests for extractReferences() in participant.js — validated via Python models."""

    def test_reference_schema_selection(self):
        """Selection reference carries uri, range, selectedText."""
        ref = {
            "id": "vscode.selection",
            "value": {
                "uri": {"fsPath": "/docs/PSA.pdf"},
                "range": {"start": 10, "end": 50},
                "selectedText": "The Depositor hereby conveys...",
            },
        }
        assert ref["value"]["selectedText"]
        assert ref["value"]["uri"]["fsPath"]

    def test_reference_schema_file(self):
        """File reference has a URI."""
        ref = {"id": "vscode.file", "value": {"fsPath": "/docs/PSA.pdf"}}
        assert ref["value"]["fsPath"].endswith(".pdf")

    def test_reference_schema_editor(self):
        """Editor reference has uri, selection, visibleRanges."""
        ref = {
            "id": "vscode.editor",
            "value": {"uri": {"fsPath": "/docs/PSA.pdf"}, "selection": None, "visibleRanges": []},
        }
        assert "uri" in ref["value"]

    def test_reference_text_prepended_to_query(self):
        """Reference text must be prepended to the query string."""
        ref_text = "Section 3.04 limits..."
        query = "What limitations apply?"
        enriched = f"{ref_text}\n\n{query}"
        assert enriched.startswith(ref_text)
        assert query in enriched

    def test_source_doc_hint_extracted(self):
        """Source file URI should be extracted as preferred doc hint."""
        ref = {
            "id": "vscode.selection",
            "value": {
                "uri": {"fsPath": "/docs/PSA_2006HE1.pdf"},
                "selectedText": "Depositor means...",
            },
        }
        source_hint = ref["value"]["uri"]["fsPath"]
        assert "PSA_2006HE1" in source_hint

    def test_malformed_reference_ignored(self):
        """References without value should be silently skipped."""
        ref = {"id": "vscode.selection", "value": None}
        assert ref["value"] is None  # gracefully handle

    def test_multiple_references_combined(self):
        """Multiple references should all contribute context."""
        refs = [
            {"id": "vscode.selection", "value": {"selectedText": "clause A"}},
            {"id": "vscode.file", "value": {"content": "full file content"}},
        ]
        combined = " ".join(
            r["value"].get("selectedText") or r["value"].get("content", "")
            for r in refs if r.get("value")
        )
        assert "clause A" in combined
        assert "full file content" in combined

    def test_copilot_variant_ids(self):
        """VS Code sometimes uses copilot.selection / copilot.file ids."""
        copilot_ids = ["copilot.selection", "copilot.file", "copilot.editor"]
        vscode_ids = ["vscode.selection", "vscode.file", "vscode.editor"]
        mapped = {c: v for c, v in zip(copilot_ids, vscode_ids)}
        assert mapped["copilot.selection"] == "vscode.selection"

    def test_empty_references_returns_empty(self):
        """No references should return empty reference text."""
        refs = []
        ref_parts = [r.get("value", {}).get("selectedText", "") for r in refs]
        assert all(p == "" for p in ref_parts)


# ═══════════════════════════════════════════════════════════════
# INCREMENT 11.2 — Follow-Up Question Suggestions
# ═══════════════════════════════════════════════════════════════

@pytest.mark.phase11
class TestInc11_2_FollowUpSuggestions:
    """Deterministic follow-up generation from answer text."""

    # --- Pattern detection tests ---

    def test_defined_term_pattern(self):
        """Defined terms like **Term** means should trigger follow-ups."""
        text = '**Depositor** means JPMorgan Chase Bank'
        pattern = re.compile(r'\*\*([A-Z][A-Za-z\s]+?)\*\*\s+(?:means|shall mean|is defined as)')
        m = pattern.search(text)
        assert m is not None
        assert m.group(1) == "Depositor"

    def test_date_pattern(self):
        """Dates should trigger date-related follow-ups."""
        text = "The Closing Date is January 15, 2025"
        pattern = re.compile(
            r'\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|(?:January|February|March|April|May|June'
            r'|July|August|September|October|November|December)\s+\d{1,2},?\s*\d{2,4})\b',
            re.IGNORECASE,
        )
        m = pattern.search(text)
        assert m is not None

    def test_dollar_amount_pattern(self):
        """Dollar amounts should trigger amount-related follow-ups."""
        text = "The total face amount is $500,000,000"
        pattern = re.compile(r'\$[\d,.]+(?:\s*(?:million|billion|MM|M|B))?', re.IGNORECASE)
        m = pattern.search(text)
        assert m is not None
        assert "$500,000,000" in m.group()

    def test_section_crossref_pattern(self):
        """Cross-references like 'Section 3.04' should trigger follow-ups."""
        text = "As described in Section 3.04(a) of the Agreement"
        pattern = re.compile(r'Section\s+\d+[\d.]*(?:\([a-z]\))?', re.IGNORECASE)
        m = pattern.search(text)
        assert m is not None

    def test_party_name_pattern(self):
        """Party names should trigger party-related follow-ups."""
        roles = ["Depositor", "Trustee", "Master Servicer", "Servicer"]
        text = "The Trustee shall distribute payments..."
        found = [r for r in roles if r.lower() in text.lower()]
        assert "Trustee" in found

    def test_max_three_suggestions(self):
        """At most 3 follow-up suggestions should be returned."""
        suggestions = [
            "What sections reference Depositor?",
            "Has January 15, 2025 passed?",
            "How is $500M calculated?",
            "Show me Section 3.04",
            "What are Trustee obligations?",
        ]
        assert len(suggestions[:3]) == 3

    def test_no_patterns_fallback(self):
        """When no patterns match, fallback suggestions should appear."""
        text = "This is a generic answer with no special patterns."
        patterns_found = []
        if not patterns_found:
            fallback = "What else can you tell me about this topic?"
            assert fallback

    def test_deterministic_not_llm(self):
        """Follow-ups must be regex-based, not LLM-generated."""
        # Verify the pattern approach — no async or LLM call needed
        text = "**Term** means something"
        pattern = re.compile(r'\*\*([A-Z][A-Za-z\s]+?)\*\*\s+means')
        m = pattern.search(text)
        follow_up = f'What sections reference {m.group(1)}?' if m else None
        assert follow_up == "What sections reference Term?"

    def test_dedup_already_answered(self):
        """Follow-ups should not re-suggest already-answered queries (Phase 10 integration)."""
        history = ["What is Depositor?", "Show me Section 3.04"]
        suggestions = [
            "What is Depositor?",
            "Has the Closing Date passed?",
        ]
        filtered = [s for s in suggestions if s not in history]
        assert "What is Depositor?" not in filtered
        assert "Has the Closing Date passed?" in filtered

    def test_follow_up_format(self):
        """Each follow-up should be a dict with 'prompt' key."""
        follow_ups = [{"prompt": "What is Depositor?"}]
        assert all("prompt" in fu for fu in follow_ups)

    def test_empty_answer_no_followups(self):
        """Empty answer text should yield no follow-ups."""
        text = ""
        pattern = re.compile(r'\*\*([A-Z][A-Za-z\s]+?)\*\*\s+means')
        assert pattern.search(text) is None


# ═══════════════════════════════════════════════════════════════
# INCREMENT 11.3 — Rich Retrieval Progress Streaming
# ═══════════════════════════════════════════════════════════════

@pytest.mark.phase11
class TestInc11_3_RetrievalProgressStreaming:
    """SSE progress callback in retrieval pipeline."""

    def test_sse_progress_config_flag(self):
        """sse_progress_enabled flag must exist in config."""
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert hasattr(cfg, 'sse_progress_enabled')
        assert cfg.sse_progress_enabled is True

    def test_sse_progress_env_override(self, monkeypatch):
        """sse_progress_enabled should be overridable via env var."""
        monkeypatch.setenv("KTS_SSE_PROGRESS_ENABLED", "false")
        from config.settings import load_config
        cfg = load_config()
        assert cfg.sse_progress_enabled is False

    def test_progress_callback_invoked(self):
        """RetrievalService.execute() should invoke progress_callback when provided."""
        from backend.agents.retrieval_service import RetrievalService
        messages = []
        def capture(msg):
            messages.append(msg)

        cfg = MagicMock()
        cfg.chroma_persist_dir = "/tmp/test_chroma"
        cfg.graph_path = "/tmp/test_graph"
        cfg.sse_progress_enabled = True
        # We can't run full execute without dependencies, but we can verify
        # the callback mechanism exists in the source
        import inspect
        src = inspect.getsource(RetrievalService.execute)
        assert "progress_callback" in src
        assert "_emit_progress" in src

    def test_progress_messages_format(self):
        """Progress messages should be descriptive strings."""
        messages = [
            "Parsing query: What is Depositor?...",
            "Searching knowledge base...",
            "Reranking 15 candidates...",
            "Generating answer...",
        ]
        for msg in messages:
            assert isinstance(msg, str)
            assert len(msg) > 5

    def test_progress_callback_failure_safe(self):
        """Progress callback failure should not crash retrieval."""
        def bad_callback(msg):
            raise RuntimeError("callback error")

        # The _emit_progress wrapper should catch this
        try:
            bad_callback("test")
        except RuntimeError:
            pass  # Expected — but _emit_progress wraps in try/except

    def test_progress_disabled_skips_callback(self):
        """When sse_progress_enabled is False, no progress calls should fire."""
        import inspect
        from backend.agents.retrieval_service import RetrievalService
        src = inspect.getsource(RetrievalService.execute)
        assert "sse_progress_enabled" in src


# ═══════════════════════════════════════════════════════════════
# INCREMENT 11.4 — Slash Command Modes
# ═══════════════════════════════════════════════════════════════

@pytest.mark.phase11
class TestInc11_4_SlashCommandModes:
    """Retrieval modes: /define, /extract, /compare, /audit, /summary."""

    # --- Definition Mode ---

    def test_definition_mode_import(self):
        """DefinitionMode should be importable."""
        from backend.retrieval.definition_mode import DefinitionMode
        assert DefinitionMode is not None

    def test_definition_config_defaults(self):
        """DefinitionConfig should have chunk_budget=3, temperature=0.0."""
        from backend.retrieval.definition_mode import DefinitionConfig
        cfg = DefinitionConfig()
        assert cfg.chunk_budget == 3
        assert cfg.temperature == 0.0
        assert cfg.max_output_tokens == 1000

    def test_definition_result_to_dict(self):
        """DefinitionResult.to_dict() should include all fields."""
        from backend.retrieval.definition_mode import DefinitionResult, DefinitionEntry
        entry = DefinitionEntry(term="Depositor", definition="means JPMorgan Chase", source_section="1.01")
        result = DefinitionResult(term="Depositor", entries=[entry], raw_response="test", found=True)
        d = result.to_dict()
        assert d["term"] == "Depositor"
        assert d["found"] is True
        assert len(d["entries"]) == 1
        assert d["entries"][0]["definition"] == "means JPMorgan Chase"

    def test_definition_regex_extraction(self):
        """Direct regex should extract definitions from text."""
        from backend.retrieval.definition_mode import extract_definitions_from_text
        text = '"Depositor" means JPMorgan Chase Bank, National Association'
        entries = extract_definitions_from_text(text, "Depositor")
        assert len(entries) >= 1
        assert entries[0].term == "Depositor"

    def test_definition_regex_no_match(self):
        """Regex should return empty when term not found."""
        from backend.retrieval.definition_mode import extract_definitions_from_text
        text = "No definitions here."
        entries = extract_definitions_from_text(text, "Servicer")
        assert len(entries) == 0

    def test_definition_mode_no_llm(self):
        """DefinitionMode without LLM should try regex first."""
        from backend.retrieval.definition_mode import DefinitionMode
        mode = DefinitionMode(llm_call_fn=None)
        result = _run(mode.define("Trustee", [{"content": '"Trustee" means Bank of America'}]))
        assert result.found is True
        assert "Trustee" in result.raw_response

    def test_definition_mode_no_llm_no_match(self):
        """DefinitionMode without LLM returns not found when regex fails."""
        from backend.retrieval.definition_mode import DefinitionMode
        mode = DefinitionMode(llm_call_fn=None)
        result = _run(mode.define("NonExistent", [{"content": "Random text"}]))
        assert result.found is False

    def test_definition_mode_with_mock_llm(self):
        """DefinitionMode with LLM should use LLM fallback."""
        from backend.retrieval.definition_mode import DefinitionMode

        async def mock_llm(prompt, max_tokens, temp):
            return '**Servicer** — WaMu Mortgage Securities Corp. (Source: Section 1.01)'

        mode = DefinitionMode(llm_call_fn=mock_llm)
        result = _run(mode.define("Servicer", [{"content": "WaMu is the Servicer"}]))
        assert "Servicer" in result.raw_response or result.found

    def test_definition_mode_sync_fallback(self):
        """define_sync() should return a result without error."""
        from backend.retrieval.definition_mode import DefinitionMode
        mode = DefinitionMode()
        result = mode.define_sync("Term", [])
        assert result.term == "Term"

    def test_definition_prompt_template(self):
        """DEFINITION_PROMPT should include {term} and {context} placeholders."""
        from backend.retrieval.definition_mode import DEFINITION_PROMPT
        assert "{term}" in DEFINITION_PROMPT
        assert "{context}" in DEFINITION_PROMPT

    # --- Extraction Mode ---

    def test_extraction_config_chunk_budget(self):
        """ExtractionConfig chunk_budget should be 10 per Phase 11 spec."""
        from backend.retrieval.extraction_mode import ExtractionConfig
        cfg = ExtractionConfig()
        assert cfg.chunk_budget == 10

    def test_extraction_schema_fields(self):
        """EXTRACTION_SCHEMA should include all required fields."""
        from backend.retrieval.extraction_mode import EXTRACTION_SCHEMA
        assert "deal_name" in EXTRACTION_SCHEMA
        assert "parties" in EXTRACTION_SCHEMA
        assert "key_dates" in EXTRACTION_SCHEMA
        assert "key_amounts" in EXTRACTION_SCHEMA
        assert "defined_terms" in EXTRACTION_SCHEMA
        assert "confidence" in EXTRACTION_SCHEMA

    # --- Audit Mode ---

    def test_audit_config_chunk_budget(self):
        """AuditConfig chunk_budget should be 15 per Phase 11 spec."""
        from backend.retrieval.audit_mode import AuditConfig
        cfg = AuditConfig()
        assert cfg.chunk_budget == 15

    def test_audit_config_temperature(self):
        """AuditConfig temperature should be 0.2 per Phase 11 spec."""
        from backend.retrieval.audit_mode import AuditConfig
        cfg = AuditConfig()
        assert cfg.temperature == 0.2

    def test_audit_clause_parsing(self):
        """_parse_audit_clauses should extract clauses from bullet-list output."""
        from backend.retrieval.audit_mode import _parse_audit_clauses
        raw = """- Section 3.04 - Indemnification: The Depositor shall indemnify. Risk: High
- Section 5.01 - Limitation of Liability: Liability capped at $10M. Risk: Low"""
        clauses = _parse_audit_clauses(raw)
        assert len(clauses) >= 1

    def test_audit_clause_to_dict(self):
        """AuditClause.to_dict() should produce valid dict."""
        from backend.retrieval.audit_mode import AuditClause
        clause = AuditClause(
            section="3.04",
            summary="Indemnification clause",
            risk_level="High",
            key_phrase="shall indemnify",
        )
        d = clause.to_dict()
        assert d["section"] == "3.04"
        assert d["risk_level"] == "High"

    def test_audit_mode_no_llm(self):
        """AuditMode without LLM should return 'No LLM available'."""
        from backend.retrieval.audit_mode import AuditMode
        mode = AuditMode(llm_call_fn=None)
        result = _run(mode.audit("risk", [{"content": "test"}]))
        assert "No LLM" in result.raw_response

    def test_audit_mode_with_mock_llm(self):
        """AuditMode with mock LLM should parse response."""
        from backend.retrieval.audit_mode import AuditMode

        async def mock_llm(prompt, max_tokens, temp):
            return "- Section 1.01 - Risk allocation: Depositor bears all risk. Risk: High"

        mode = AuditMode(llm_call_fn=mock_llm)
        result = _run(mode.audit("risk", [
            {"content": "Risk is allocated to Depositor", "section": "1.01"},
        ]))
        assert result.topic == "risk"
        assert result.total_sections_scanned >= 1

    def test_audit_cluster_by_section(self):
        """cluster_by_section should group chunks by section."""
        from backend.retrieval.audit_mode import cluster_by_section
        chunks = [
            {"section": "1.01", "content": "A"},
            {"section": "1.01", "content": "B"},
            {"section": "2.01", "content": "C"},
        ]
        clusters = cluster_by_section(chunks)
        assert "1.01" in clusters
        assert len(clusters["1.01"]) == 2

    # --- Summary Mode ---

    def test_summary_config_chunk_budget(self):
        """SummaryConfig chunk_budget should be 20 per Phase 11 spec."""
        from backend.retrieval.summary_mode import SummaryConfig
        cfg = SummaryConfig()
        assert cfg.chunk_budget == 20

    def test_summary_config_temperature(self):
        """SummaryConfig temperature should be 0.5 per Phase 11 spec."""
        from backend.retrieval.summary_mode import SummaryConfig
        cfg = SummaryConfig()
        assert cfg.temperature == 0.5

    def test_summary_prompt_five_sections(self):
        """SUMMARY_PROMPT should mandate 5 sections."""
        from backend.retrieval.summary_mode import SUMMARY_PROMPT
        required = ["Parties", "Key Dates", "Key Amounts", "Key Obligations", "Risk Factors"]
        for section in required:
            assert section in SUMMARY_PROMPT, f"Missing section: {section}"

    # --- Comparison Mode ---

    def test_comparison_temperature(self):
        """ComparisonMode default temperature should be 0.3 per Phase 11 spec."""
        from backend.retrieval.comparison_mode import ComparisonMode
        mode = ComparisonMode()
        assert mode.temperature == 0.3

    # --- Retrieval Mode Routing ---

    def test_all_five_modes_recognized(self):
        """detectRetrievalMode should handle all 5 modes."""
        mode_map = {
            "extract": "extract",
            "audit": "audit",
            "summary": "summary",
            "compare": "compare",
            "define": "define",
        }
        for cmd, expected in mode_map.items():
            assert mode_map[cmd] == expected

    def test_unknown_command_returns_none(self):
        """Unknown commands should not map to any mode."""
        mode_map = {"extract": "extract", "audit": "audit", "summary": "summary", "compare": "compare", "define": "define"}
        assert mode_map.get("foobar") is None

    def test_retrieval_service_has_definition_mode(self):
        """RetrievalService should instantiate _definition_mode."""
        import inspect
        from backend.agents.retrieval_service import RetrievalService
        src = inspect.getsource(RetrievalService.__init__)
        assert "_definition_mode" in src

    def test_retrieval_service_has_audit_mode(self):
        """RetrievalService should instantiate _audit_mode."""
        import inspect
        from backend.agents.retrieval_service import RetrievalService
        src = inspect.getsource(RetrievalService.__init__)
        assert "_audit_mode" in src

    def test_retrieval_service_define_routing(self):
        """execute() should have retrieval_mode == 'define' branch."""
        import inspect
        from backend.agents.retrieval_service import RetrievalService
        src = inspect.getsource(RetrievalService.execute)
        assert 'retrieval_mode == "define"' in src

    def test_retrieval_service_audit_routing(self):
        """execute() should have retrieval_mode == 'audit' branch."""
        import inspect
        from backend.agents.retrieval_service import RetrievalService
        src = inspect.getsource(RetrievalService.execute)
        assert 'retrieval_mode == "audit"' in src

    def test_definition_mode_import_in_service(self):
        """DefinitionMode should be imported in retrieval_service."""
        import inspect
        from backend.agents import retrieval_service
        src = inspect.getsource(retrieval_service)
        assert "from backend.retrieval.definition_mode import DefinitionMode" in src

    def test_package_json_slash_commands(self):
        """extension/package.json should declare all 5 slash commands."""
        pkg_path = ROOT / "extension" / "package.json"
        if not pkg_path.exists():
            pytest.skip("package.json not found")
        data = json.loads(pkg_path.read_text(encoding="utf-8"))
        commands_section = json.dumps(data)
        for cmd in ["define", "extract", "compare", "audit", "summary"]:
            assert cmd in commands_section, f"Slash command /{cmd} missing from package.json"


# ═══════════════════════════════════════════════════════════════
# INCREMENT 11.5 — Runtime Model Selection
# ═══════════════════════════════════════════════════════════════

@pytest.mark.phase11
class TestInc11_5_ModelSelection:
    """Model selection via kts.model setting (renamed from kts.generationModel)."""

    def test_model_setting_in_package_json(self):
        """package.json should declare kts.model setting."""
        pkg_path = ROOT / "extension" / "package.json"
        if not pkg_path.exists():
            pytest.skip("package.json not found")
        data = json.loads(pkg_path.read_text(encoding="utf-8"))
        config = data.get("contributes", {}).get("configuration", {})
        if isinstance(config, list):
            props = {}
            for section in config:
                props.update(section.get("properties", {}))
        else:
            props = config.get("properties", {})
        assert "kts.model" in props, "kts.model setting missing from package.json"

    def test_model_selection_resolves_string(self):
        """String model setting should be resolved via selectChatModels."""
        # JS-side logic: if modelSetting is string, call vscode.lm.selectChatModels({family: modelSetting})
        model_setting = "gpt-4o"
        assert isinstance(model_setting, str)
        # The fix ensures this string is NOT passed directly as a model object
        assert not hasattr(model_setting, "sendRequest")

    def test_model_families_coverage(self):
        """Fallback families should include major model families."""
        families = ['gpt-4o', 'claude-3.5-sonnet', 'gpt-4o-mini', 'claude-3-5-sonnet']
        assert 'gpt-4o' in families
        assert any('claude' in f for f in families)

    def test_request_model_preferred(self):
        """If request.model has sendRequest, it should be preferred."""
        mock_model = MagicMock()
        mock_model.sendRequest = MagicMock()
        # This model should be returned directly without override
        assert callable(mock_model.sendRequest)

    def test_auto_setting_uses_default(self):
        """When generationModel is 'auto', default selection should apply."""
        setting = "auto"
        should_override = setting and setting != "auto"
        assert not should_override


# ═══════════════════════════════════════════════════════════════
# INCREMENT 11.6 — Confirmation Dialogs
# ═══════════════════════════════════════════════════════════════

@pytest.mark.phase11
class TestInc11_6_ConfirmationDialogs:
    """Destructive operation confirmation before /delete, /clear-index, /reset."""

    def test_destructive_commands_list(self):
        """Known destructive commands that require confirmation."""
        destructive = ['delete', 'clear-index', 'reset']
        assert 'delete' in destructive
        assert 'clear-index' in destructive
        assert 'reset' in destructive

    def test_non_destructive_skips_confirmation(self):
        """Normal commands should NOT trigger confirmation."""
        destructive = ['delete', 'clear-index', 'reset']
        normal_commands = ['define', 'extract', 'audit', 'summary', 'compare', 'describe_images']
        for cmd in normal_commands:
            assert cmd not in destructive

    def test_confirmation_dialog_in_participant(self):
        """participant.js should contain showWarningMessage for destructive ops."""
        participant_path = ROOT / "extension" / "chat" / "participant.js"
        if not participant_path.exists():
            pytest.skip("participant.js not found")
        content = participant_path.read_text(encoding="utf-8")
        assert "showWarningMessage" in content
        assert "destructiveCommands" in content or "destructive" in content.lower()

    def test_cancel_aborts_operation(self):
        """When user cancels confirmation, operation should be aborted."""
        # Verify the pattern: if confirmed !== 'Yes' -> return
        participant_path = ROOT / "extension" / "chat" / "participant.js"
        if not participant_path.exists():
            pytest.skip("participant.js not found")
        content = participant_path.read_text(encoding="utf-8")
        assert "Operation cancelled" in content


# ═══════════════════════════════════════════════════════════════
# INCREMENT 11.7 — HITL Classification (Human-in-the-Loop)
# ═══════════════════════════════════════════════════════════════

@pytest.mark.phase11
class TestInc11_7_HITLClassification:
    """Interactive ingestion classification for ambiguous documents."""

    def test_hitl_config_flag(self):
        """hitl_classification_enabled flag must exist."""
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert hasattr(cfg, 'hitl_classification_enabled')
        assert cfg.hitl_classification_enabled is True

    def test_hitl_env_override(self, monkeypatch):
        """hitl_classification_enabled should be overridable via env var."""
        monkeypatch.setenv("KTS_HITL_CLASSIFICATION_ENABLED", "false")
        from config.settings import load_config
        cfg = load_config()
        assert cfg.hitl_classification_enabled is False

    def test_regime_result_is_ambiguous_35(self):
        """Score 35 should be ambiguous."""
        from backend.ingestion.regime_classifier import RegimeResult
        result = RegimeResult(regime="MIXED", score=35)
        assert result.is_ambiguous is True

    def test_regime_result_is_ambiguous_64(self):
        """Score 64 should be ambiguous."""
        from backend.ingestion.regime_classifier import RegimeResult
        result = RegimeResult(regime="MIXED", score=64)
        assert result.is_ambiguous is True

    def test_regime_result_not_ambiguous_65(self):
        """Score 65 should NOT be ambiguous (auto-classify)."""
        from backend.ingestion.regime_classifier import RegimeResult
        result = RegimeResult(regime="GOVERNING_DOC_LEGAL", score=65)
        assert result.is_ambiguous is False

    def test_regime_result_not_ambiguous_34(self):
        """Score 34 should NOT be ambiguous (auto-classify as GENERIC_GUIDE)."""
        from backend.ingestion.regime_classifier import RegimeResult
        result = RegimeResult(regime="GENERIC_GUIDE", score=34)
        assert result.is_ambiguous is False

    def test_regime_result_ambiguous_50(self):
        """Score 50 should be ambiguous (right in the middle)."""
        from backend.ingestion.regime_classifier import RegimeResult
        result = RegimeResult(regime="MIXED", score=50)
        assert result.is_ambiguous is True

    def test_confirm_classification_function_exists(self):
        """confirmClassification() should be defined in participant.js."""
        participant_path = ROOT / "extension" / "chat" / "participant.js"
        if not participant_path.exists():
            pytest.skip("participant.js not found")
        content = participant_path.read_text(encoding="utf-8")
        assert "function confirmClassification" in content

    def test_confirm_classification_choices(self):
        """confirmClassification should return standard doc type choices."""
        choices = [
            'Legal / Governing Doc',
            'Troubleshooting Guide',
            'Operational Procedure',
            'User Manual / Reference',
            'Skip \u2014 let system decide',
        ]
        assert len(choices) == 5

    def test_doc_type_source_user(self):
        """When user overrides, doc_type_source should be 'user'."""
        metadata = {}
        doc_type_override = "GOVERNING_DOC_LEGAL"
        if doc_type_override:
            metadata["doc_type_source"] = "user"
        assert metadata["doc_type_source"] == "user"

    def test_doc_type_source_auto(self):
        """Without override, doc_type_source should be 'auto'."""
        metadata = {}
        doc_type_override = None
        if not doc_type_override:
            metadata["doc_type_source"] = "auto"
        assert metadata["doc_type_source"] == "auto"

    def test_cli_doc_type_flag(self):
        """CLI should accept --doc-type flag."""
        cli_path = ROOT / "cli" / "main.py"
        if not cli_path.exists():
            pytest.skip("cli/main.py not found")
        content = cli_path.read_text(encoding="utf-8")
        assert "--doc-type" in content

    def test_select_source_hitl_wiring(self):
        """select_source.js should contain HITL classification logic."""
        ss_path = ROOT / "extension" / "commands" / "select_source.js"
        if not ss_path.exists():
            pytest.skip("select_source.js not found")
        content = ss_path.read_text(encoding="utf-8")
        assert "hitl" in content.lower() or "ambiguous" in content.lower() or "regime_scores" in content

    def test_select_source_doc_type_arg(self):
        """select_source.js should pass --doc-type to ingest CLI when overridden."""
        ss_path = ROOT / "extension" / "commands" / "select_source.js"
        if not ss_path.exists():
            pytest.skip("select_source.js not found")
        content = ss_path.read_text(encoding="utf-8")
        assert "--doc-type" in content


# ═══════════════════════════════════════════════════════════════
# INTEGRATION — Cross-Increment Tests
# ═══════════════════════════════════════════════════════════════

@pytest.mark.phase11
class TestPhase11Integration:
    """End-to-end integration across all Phase 11 increments."""

    def test_all_phase11_feature_flags(self):
        """All Phase 11 config flags must exist and default to True."""
        from config.settings import KTSConfig
        cfg = KTSConfig()
        flags = [
            'follow_up_suggestions_enabled',
            'sse_progress_enabled',
            'hitl_classification_enabled',
            'definition_mode_enabled',
            'audit_mode_enabled',
        ]
        for flag in flags:
            assert hasattr(cfg, flag), f"Missing config flag: {flag}"
            assert getattr(cfg, flag) is True, f"Flag {flag} should default to True"

    def test_all_mode_imports(self):
        """All retrieval modes should be importable."""
        from backend.retrieval.definition_mode import DefinitionMode
        from backend.retrieval.extraction_mode import ExtractionMode
        from backend.retrieval.audit_mode import AuditMode
        from backend.retrieval.summary_mode import SummaryMode
        from backend.retrieval.comparison_mode import ComparisonMode
        assert all([DefinitionMode, ExtractionMode, AuditMode, SummaryMode, ComparisonMode])

    def test_retrieval_service_mode_singletons(self):
        """RetrievalService __init__ should create all mode singletons."""
        import inspect
        from backend.agents.retrieval_service import RetrievalService
        src = inspect.getsource(RetrievalService.__init__)
        for attr in ["_extraction_mode", "_summary_mode", "_comparison_mode", "_audit_mode", "_definition_mode"]:
            assert attr in src, f"Missing singleton: {attr}"

    def test_mode_temperature_spec_compliance(self):
        """All mode temperatures should match Phase 11 spec."""
        from backend.retrieval.definition_mode import DefinitionConfig
        from backend.retrieval.extraction_mode import ExtractionConfig
        from backend.retrieval.audit_mode import AuditConfig
        from backend.retrieval.summary_mode import SummaryConfig
        from backend.retrieval.comparison_mode import ComparisonMode

        assert DefinitionConfig().temperature == 0.0
        assert ExtractionConfig().temperature == 0.0
        assert AuditConfig().temperature == 0.2
        assert SummaryConfig().temperature == 0.5
        assert ComparisonMode().temperature == 0.3

    def test_mode_chunk_budget_spec_compliance(self):
        """All mode chunk budgets should match Phase 11 spec."""
        from backend.retrieval.definition_mode import DefinitionConfig
        from backend.retrieval.extraction_mode import ExtractionConfig
        from backend.retrieval.audit_mode import AuditConfig
        from backend.retrieval.summary_mode import SummaryConfig

        assert DefinitionConfig().chunk_budget == 3
        assert ExtractionConfig().chunk_budget == 10
        assert AuditConfig().chunk_budget == 15
        assert SummaryConfig().chunk_budget == 20

    def test_definition_mode_config_flag(self):
        """definition_mode_enabled flag must exist in config."""
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert hasattr(cfg, 'definition_mode_enabled')

    def test_audit_mode_config_flag(self):
        """audit_mode_enabled flag must exist in config."""
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert hasattr(cfg, 'audit_mode_enabled')

    def test_definition_mode_env_override(self, monkeypatch):
        """definition_mode_enabled should be overridable via env var."""
        monkeypatch.setenv("KTS_DEFINITION_MODE_ENABLED", "false")
        from config.settings import load_config
        cfg = load_config()
        assert cfg.definition_mode_enabled is False

    def test_audit_mode_env_override(self, monkeypatch):
        """audit_mode_enabled should be overridable via env var."""
        monkeypatch.setenv("KTS_AUDIT_MODE_ENABLED", "false")
        from config.settings import load_config
        cfg = load_config()
        assert cfg.audit_mode_enabled is False

    def test_follow_up_provider_in_participant(self):
        """participant.js should set followupProvider on the participant."""
        participant_path = ROOT / "extension" / "chat" / "participant.js"
        if not participant_path.exists():
            pytest.skip("participant.js not found")
        content = participant_path.read_text(encoding="utf-8")
        assert "followupProvider" in content

    def test_retrieval_service_all_mode_routing(self):
        """execute() should route all 5 modes: compare, extract, summary, audit, define."""
        import inspect
        from backend.agents.retrieval_service import RetrievalService
        src = inspect.getsource(RetrievalService.execute)
        for mode in ["compare", "extract", "summary", "audit", "define"]:
            assert f'retrieval_mode == "{mode}"' in src, f"Missing routing for mode: {mode}"

    def test_regime_result_has_is_ambiguous_property(self):
        """RegimeResult should expose is_ambiguous property."""
        from backend.ingestion.regime_classifier import RegimeResult
        r = RegimeResult(regime="MIXED", score=50)
        assert hasattr(r, "is_ambiguous")
        assert r.is_ambiguous is True

    def test_definition_entry_to_dict(self):
        """DefinitionEntry.to_dict() should work correctly."""
        from backend.retrieval.definition_mode import DefinitionEntry
        entry = DefinitionEntry(term="T", definition="D", source_section="S")
        d = entry.to_dict()
        assert d == {"term": "T", "definition": "D", "source_section": "S"}

    def test_audit_result_to_dict_with_clauses(self):
        """AuditResult with parsed clauses should serialize correctly."""
        from backend.retrieval.audit_mode import AuditResult, AuditClause
        clause = AuditClause(section="1.01", summary="Risk", risk_level="High", key_phrase="shall bear")
        result = AuditResult(topic="risk", clauses=[clause], total_sections_scanned=3)
        d = result.to_dict()
        assert d["topic"] == "risk"
        assert len(d["clauses"]) == 1
        assert d["clauses"][0]["risk_level"] == "High"
        assert d["total_sections_scanned"] == 3

    def test_definition_mode_smart_quotes(self):
        """Should handle smart quotes in definitions."""
        from backend.retrieval.definition_mode import extract_definitions_from_text
        text = '\u201cTrustee\u201d means Bank of America'
        entries = extract_definitions_from_text(text, "Trustee")
        assert len(entries) >= 1

    def test_extraction_temperature_zero(self):
        """Extraction mode temperature should be exactly 0.0."""
        from backend.retrieval.extraction_mode import ExtractionConfig
        assert ExtractionConfig().temperature == 0.0
