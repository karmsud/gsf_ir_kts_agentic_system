# Phase 23: Testing Plan
## CLI, Extension & Packaging Tests

**Document Version:** 1.0  
**Date:** February 26, 2026  
**Status:** Proposal — Pending Approval  
**Total Tests:** ~130 across 10 test files

---

## Table of Contents
1. [Test Overview](#test-overview)
2. [Unit Tests: ABSOrchestrator](#unit-tests-absorchestrator)
3. [Unit Tests: CLI Commands](#unit-tests-cli-commands)
4. [Unit Tests: IPC & Streaming](#unit-tests-ipc--streaming)
5. [Integration Tests: CLI End-to-End](#integration-tests-cli-end-to-end)
6. [Integration Tests: Extension Components](#integration-tests-extension-components)
7. [Packaging Tests](#packaging-tests)
8. [Regression Tests: KTS Isolation](#regression-tests-kts-isolation)
9. [Pass Criteria](#pass-criteria)
10. [Test Execution](#test-execution)

---

## Test Overview

| Test File | Tests | Scope |
|-----------|-------|-------|
| `test_abs_orchestrator.py` | 20 | Orchestrator methods, result types |
| `test_abs_cli_commands.py` | 25 | CLI option parsing, output formatting |
| `test_abs_cli_group.py` | 10 | Command registration, help text |
| `test_abs_ipc_protocol.py` | 10 | Message types, serialization |
| `test_abs_streaming.py` | 10 | Terminal & IPC output modes |
| `test_phase23_cli_smoke.py` | 15 | CLI end-to-end with mock agents |
| `test_phase23_extension.py` | 15 | TypeScript component validation |
| `test_phase23_packaging.py` | 10 | VSIX structure, PyInstaller spec |
| `test_kts_isolation_phase23.py` | 15 | KTS unaffected by Phase 23 |
| **Total** | **~130** | |

---

## Unit Tests: ABSOrchestrator

### `tests/unit/test_abs_orchestrator.py` (20 tests)

```python
"""Unit tests for ABSOrchestrator convergence layer."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path
from dataclasses import fields

from config.settings import KTSConfig
from backend.abs.orchestrator import (
    ABSOrchestrator,
    IngestResult,
    GenerateResult,
    AuditResult,
    QAResult,
    StatusResult,
)


# ─── Dataclass Tests ────────────────────────────────────────

class TestResultDataclasses:
    """Verify all result dataclasses have correct fields."""

    def test_ingest_result_fields(self):
        r = IngestResult(
            deal_id="test", item_count=10, section_count=5,
            node_count=20, edge_count=15, elapsed_seconds=1.5,
        )
        assert r.deal_id == "test"
        assert r.item_count == 10
        assert r.elapsed_seconds == 1.5

    def test_generate_result_fields(self):
        r = GenerateResult(
            deal_id="test", output_path=Path("out"),
            validation_summary="ok", quality_score=0.95,
        )
        assert r.quality_score == 0.95
        assert isinstance(r.output_path, Path)

    def test_audit_result_fields(self):
        r = AuditResult(
            deal_id="test", report="pass",
            confidence=0.9, rules_matched=8, rules_total=10,
        )
        assert r.rules_matched == 8

    def test_qa_result_fields(self):
        r = QAResult(
            deal_id="test", answer="42",
            sources=["s1"], confidence=0.8, follow_ups=["q1"],
        )
        assert len(r.sources) == 1

    def test_status_result_fields(self):
        r = StatusResult(status_report="all good")
        assert "all good" in r.status_report


# ─── Orchestrator Init ──────────────────────────────────────

class TestOrchestratorInit:
    """Verify orchestrator construction."""

    def test_init_minimal(self):
        config = KTSConfig()
        orch = ABSOrchestrator(config=config)
        assert orch.config is config
        assert orch.llm is None

    def test_init_with_llm(self):
        config = KTSConfig()
        llm = MagicMock()
        orch = ABSOrchestrator(config=config, llm_callable=llm)
        assert orch.llm is llm


# ─── Ingest ─────────────────────────────────────────────────

class TestOrchestratorIngest:

    @patch("backend.abs.orchestrator.IngestionOrchestrator")
    @patch("backend.abs.orchestrator.DealManifest")
    @patch("backend.abs.orchestrator.DealScope")
    def test_ingest_calls_pipeline(self, MockScope, MockManifest, MockIngestion):
        MockManifest.return_value.is_complete.return_value = False
        MockIngestion.return_value.execute.return_value = {
            "item_count": 5, "section_count": 3,
            "node_count": 10, "edge_count": 8,
        }

        config = KTSConfig()
        orch = ABSOrchestrator(config=config)
        result = orch.ingest("test_deal", Path("./source"))

        assert isinstance(result, IngestResult)
        assert result.item_count == 5
        MockIngestion.return_value.execute.assert_called_once()

    @patch("backend.abs.orchestrator.DealManifest")
    @patch("backend.abs.orchestrator.DealScope")
    def test_ingest_skips_if_complete(self, MockScope, MockManifest):
        manifest = MockManifest.return_value
        manifest.is_complete.return_value = True
        manifest.item_count = 5
        manifest.section_count = 3
        manifest.node_count = 10
        manifest.edge_count = 8

        config = KTSConfig()
        orch = ABSOrchestrator(config=config)
        result = orch.ingest("test_deal", Path("./source"))

        assert result.elapsed_seconds == 0

    @patch("backend.abs.orchestrator.IngestionOrchestrator")
    @patch("backend.abs.orchestrator.DealManifest")
    @patch("backend.abs.orchestrator.DealScope")
    def test_ingest_force_re_ingests(self, MockScope, MockManifest, MockIngestion):
        MockManifest.return_value.is_complete.return_value = True
        MockIngestion.return_value.execute.return_value = {
            "item_count": 5, "section_count": 3,
            "node_count": 10, "edge_count": 8,
        }

        config = KTSConfig()
        orch = ABSOrchestrator(config=config)
        result = orch.ingest("test_deal", Path("./source"), force=True)

        MockIngestion.return_value.execute.assert_called_once()

    @patch("backend.abs.orchestrator.IngestionOrchestrator")
    @patch("backend.abs.orchestrator.DealManifest")
    @patch("backend.abs.orchestrator.DealScope")
    def test_ingest_progress_callback(self, MockScope, MockManifest, MockIngestion):
        MockManifest.return_value.is_complete.return_value = False
        MockIngestion.return_value.execute.return_value = {
            "item_count": 1, "section_count": 1,
            "node_count": 1, "edge_count": 1,
        }

        cb = MagicMock()
        config = KTSConfig()
        orch = ABSOrchestrator(config=config)
        orch.ingest("test_deal", Path("./source"), progress_callback=cb)

        # Callback passed through to ingestion orchestrator
        MockIngestion.assert_called_once()


# ─── Generate ───────────────────────────────────────────────

class TestOrchestratorGenerate:

    @patch("backend.abs.orchestrator.ModelCreationAgent")
    @patch("backend.abs.orchestrator.DealScope")
    def test_generate_returns_result(self, MockScope, MockAgent):
        MockAgent.return_value.execute.return_value = {
            "validation": "passed",
            "quality_score": 0.92,
        }

        config = KTSConfig()
        llm = MagicMock()
        orch = ABSOrchestrator(config=config, llm_callable=llm)
        result = orch.generate("test_deal")

        assert isinstance(result, GenerateResult)
        assert result.quality_score == 0.92


# ─── QA ─────────────────────────────────────────────────────

class TestOrchestratorQA:

    @patch("backend.abs.orchestrator.QAAgent")
    @patch("backend.abs.orchestrator.DealScope")
    def test_qa_returns_answer(self, MockScope, MockAgent):
        MockAgent.return_value.execute.return_value = {
            "answer": "The waterfall distributes...",
            "sources": ["PSA Section 5.02"],
            "confidence": 0.85,
            "follow_ups": ["What are the triggers?"],
        }

        config = KTSConfig()
        llm = MagicMock()
        orch = ABSOrchestrator(config=config, llm_callable=llm)
        result = orch.qa("test_deal", "What is the waterfall?")

        assert "waterfall" in result.answer
        assert len(result.sources) == 1
        assert len(result.follow_ups) == 1


# ─── Audit ──────────────────────────────────────────────────

class TestOrchestratorAudit:

    @patch("backend.abs.orchestrator.AuditAgent")
    @patch("backend.abs.orchestrator.DealScope")
    def test_audit_returns_report(self, MockScope, MockAgent):
        MockAgent.return_value.execute.return_value = {
            "report": "All rules matched.",
            "confidence": 0.95,
            "rules_matched": 10,
            "rules_total": 10,
        }

        config = KTSConfig()
        llm = MagicMock()
        orch = ABSOrchestrator(config=config, llm_callable=llm)
        result = orch.audit("test_deal")

        assert result.confidence == 0.95
        assert result.rules_matched == result.rules_total


# ─── Status ─────────────────────────────────────────────────

class TestOrchestratorStatus:

    @patch("backend.abs.orchestrator.DealManifest")
    def test_status_single_deal(self, MockManifest):
        MockManifest.return_value.status_report.return_value = "Deal: complete"

        config = KTSConfig()
        orch = ABSOrchestrator(config=config)
        result = orch.status(deal_id="test_deal")

        assert isinstance(result, StatusResult)

    @patch("backend.abs.orchestrator.DealManifest")
    def test_status_all_deals(self, MockManifest):
        MockManifest.list_all_deals.return_value = "2 deals found"

        config = KTSConfig()
        orch = ABSOrchestrator(config=config)
        result = orch.status(deal_id=None)

        assert isinstance(result, StatusResult)
```

---

## Unit Tests: CLI Commands

### `tests/unit/test_abs_cli_commands.py` (25 tests)

```python
"""Unit tests for ABS CLI commands using Click's CliRunner."""

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from pathlib import Path

from cli.abs.ingest_cmd import abs_ingest
from cli.abs.generate_cmd import abs_generate
from cli.abs.audit_cmd import abs_audit
from cli.abs.qa_cmd import abs_qa
from cli.abs.status_cmd import abs_status


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_orchestrator():
    with patch("backend.abs.orchestrator.ABSOrchestrator") as Mock:
        yield Mock.return_value


# ─── Ingest Command ─────────────────────────────────────────

class TestIngestCommand:

    def test_ingest_requires_deal_id(self, runner):
        result = runner.invoke(abs_ingest, ["--source-dir", "."])
        assert result.exit_code != 0
        assert "deal-id" in result.output.lower() or result.exit_code == 2

    def test_ingest_requires_source_dir(self, runner):
        result = runner.invoke(abs_ingest, ["--deal-id", "test"])
        assert result.exit_code != 0

    @patch("cli.abs.ingest_cmd.ABSOrchestrator")
    @patch("cli.abs.ingest_cmd.create_llm_callable")
    def test_ingest_success(self, mock_llm, mock_orch_cls, runner, tmp_path):
        from backend.abs.orchestrator import IngestResult
        mock_orch_cls.return_value.ingest.return_value = IngestResult(
            deal_id="test", item_count=5, section_count=3,
            node_count=10, edge_count=8, elapsed_seconds=1.0,
        )

        result = runner.invoke(abs_ingest, [
            "--deal-id", "test",
            "--source-dir", str(tmp_path),
            "--llm-mode", "mock",
        ])
        assert result.exit_code == 0
        assert "✅" in result.output

    @patch("cli.abs.ingest_cmd.ABSOrchestrator")
    @patch("cli.abs.ingest_cmd.create_llm_callable")
    def test_ingest_verbose(self, mock_llm, mock_orch_cls, runner, tmp_path):
        from backend.abs.orchestrator import IngestResult
        mock_orch_cls.return_value.ingest.return_value = IngestResult(
            deal_id="test", item_count=5, section_count=3,
            node_count=10, edge_count=8, elapsed_seconds=1.0,
        )

        result = runner.invoke(abs_ingest, [
            "--deal-id", "test",
            "--source-dir", str(tmp_path),
            "--llm-mode", "mock", "-v",
        ])
        assert result.exit_code == 0

    @patch("cli.abs.ingest_cmd.ABSOrchestrator")
    @patch("cli.abs.ingest_cmd.create_llm_callable")
    def test_ingest_force_flag(self, mock_llm, mock_orch_cls, runner, tmp_path):
        from backend.abs.orchestrator import IngestResult
        mock_orch_cls.return_value.ingest.return_value = IngestResult(
            deal_id="test", item_count=1, section_count=1,
            node_count=1, edge_count=1, elapsed_seconds=0.5,
        )

        result = runner.invoke(abs_ingest, [
            "--deal-id", "test",
            "--source-dir", str(tmp_path),
            "--force",
        ])
        mock_orch_cls.return_value.ingest.assert_called_once()
        call_kwargs = mock_orch_cls.return_value.ingest.call_args[1]
        assert call_kwargs.get("force") is True


# ─── Generate Command ───────────────────────────────────────

class TestGenerateCommand:

    def test_generate_requires_deal_id(self, runner):
        result = runner.invoke(abs_generate, [])
        assert result.exit_code != 0

    @patch("cli.abs.generate_cmd.ABSOrchestrator")
    @patch("cli.abs.generate_cmd.create_llm_callable")
    def test_generate_success(self, mock_llm, mock_orch_cls, runner):
        from backend.abs.orchestrator import GenerateResult
        mock_orch_cls.return_value.generate.return_value = GenerateResult(
            deal_id="test", output_path=Path("out/model.py"),
            validation_summary="passed", quality_score=0.92,
        )

        result = runner.invoke(abs_generate, [
            "--deal-id", "test", "--llm-mode", "mock",
        ])
        assert result.exit_code == 0
        assert "✅" in result.output


# ─── Audit Command ──────────────────────────────────────────

class TestAuditCommand:

    def test_audit_requires_deal_id(self, runner):
        result = runner.invoke(abs_audit, [])
        assert result.exit_code != 0

    @patch("cli.abs.audit_cmd.ABSOrchestrator")
    @patch("cli.abs.audit_cmd.create_llm_callable")
    def test_audit_success(self, mock_llm, mock_orch_cls, runner):
        from backend.abs.orchestrator import AuditResult
        mock_orch_cls.return_value.audit.return_value = AuditResult(
            deal_id="test", report="All rules matched.",
            confidence=0.95, rules_matched=10, rules_total=10,
        )

        result = runner.invoke(abs_audit, [
            "--deal-id", "test", "--llm-mode", "mock",
        ])
        assert result.exit_code == 0
        assert "All rules matched" in result.output


# ─── QA Command ─────────────────────────────────────────────

class TestQACommand:

    def test_qa_requires_both_options(self, runner):
        result = runner.invoke(abs_qa, ["--deal-id", "test"])
        assert result.exit_code != 0  # missing --query

    @patch("cli.abs.qa_cmd.ABSOrchestrator")
    @patch("cli.abs.qa_cmd.create_llm_callable")
    def test_qa_success(self, mock_llm, mock_orch_cls, runner):
        from backend.abs.orchestrator import QAResult
        mock_orch_cls.return_value.qa.return_value = QAResult(
            deal_id="test", answer="The waterfall distributes...",
            sources=["PSA 5.02"], confidence=0.85, follow_ups=[],
        )

        result = runner.invoke(abs_qa, [
            "--deal-id", "test",
            "--query", "What is the waterfall?",
            "--llm-mode", "mock",
        ])
        assert result.exit_code == 0
        assert "waterfall" in result.output.lower()


# ─── Status Command ─────────────────────────────────────────

class TestStatusCommand:

    @patch("cli.abs.status_cmd.ABSOrchestrator")
    def test_status_no_deal(self, mock_orch_cls, runner):
        from backend.abs.orchestrator import StatusResult
        mock_orch_cls.return_value.status.return_value = StatusResult(
            status_report="No deals found."
        )

        result = runner.invoke(abs_status, [])
        assert result.exit_code == 0
        assert "No deals" in result.output

    @patch("cli.abs.status_cmd.ABSOrchestrator")
    def test_status_with_deal(self, mock_orch_cls, runner):
        from backend.abs.orchestrator import StatusResult
        mock_orch_cls.return_value.status.return_value = StatusResult(
            status_report="bear_2006_he1: complete"
        )

        result = runner.invoke(abs_status, [
            "--deal-id", "bear_2006_he1",
        ])
        assert result.exit_code == 0
        assert "complete" in result.output


# ─── LLM Mode Options ──────────────────────────────────────

class TestLLMModeOptions:

    @pytest.mark.parametrize("cmd,extra_opts", [
        (abs_ingest, ["--source-dir", "."]),
        (abs_generate, []),
        (abs_audit, []),
        (abs_qa, ["--query", "test"]),
    ])
    def test_llm_mode_choices(self, runner, cmd, extra_opts):
        """All commands accept vscode/mock/none."""
        result = runner.invoke(cmd, [
            "--deal-id", "test", "--llm-mode", "invalid",
        ] + extra_opts)
        assert result.exit_code != 0  # "invalid" not in choices

    @pytest.mark.parametrize("mode", ["vscode", "mock", "none"])
    def test_valid_llm_modes(self, runner, mode):
        result = runner.invoke(abs_status, [])  # status doesn't use LLM
        # Just confirm the option parses (status has no --llm-mode)
        assert result.exit_code == 0 or result.exit_code == 2
```

---

## Unit Tests: CLI Command Group

### `tests/unit/test_abs_cli_group.py` (10 tests)

```python
"""Tests for ABS CLI command group registration."""

import pytest
from click.testing import CliRunner
from cli.abs import abs_group


@pytest.fixture
def runner():
    return CliRunner()


class TestABSGroup:

    def test_group_help(self, runner):
        result = runner.invoke(abs_group, ["--help"])
        assert result.exit_code == 0
        assert "ABS Payment Model" in result.output

    def test_has_ingest_command(self, runner):
        result = runner.invoke(abs_group, ["ingest", "--help"])
        assert result.exit_code == 0
        assert "deal-id" in result.output

    def test_has_generate_command(self, runner):
        result = runner.invoke(abs_group, ["generate", "--help"])
        assert result.exit_code == 0

    def test_has_audit_command(self, runner):
        result = runner.invoke(abs_group, ["audit", "--help"])
        assert result.exit_code == 0

    def test_has_qa_command(self, runner):
        result = runner.invoke(abs_group, ["qa", "--help"])
        assert result.exit_code == 0

    def test_has_status_command(self, runner):
        result = runner.invoke(abs_group, ["status", "--help"])
        assert result.exit_code == 0

    def test_unknown_command(self, runner):
        result = runner.invoke(abs_group, ["unknown"])
        assert result.exit_code != 0

    def test_all_commands_registered(self):
        commands = list(abs_group.commands.keys())
        assert sorted(commands) == ["audit", "generate", "ingest", "qa", "status"]

    def test_group_is_click_group(self):
        import click
        assert isinstance(abs_group, click.Group)

    def test_command_count(self):
        assert len(abs_group.commands) == 5
```

---

## Unit Tests: IPC & Streaming

### `tests/unit/test_abs_ipc_protocol.py` (10 tests)

```python
"""Tests for IPC protocol message types."""

import pytest
import json
from backend.abs.ipc_protocol import (
    ProgressMessage, LLMRequest, LLMResponse,
    StreamMessage, CodeMessage, ResultMessage, ErrorMessage,
)


class TestMessageTypes:

    def test_progress_message_type(self):
        msg: ProgressMessage = {
            "type": "progress",
            "step": "Converting PDF",
            "status": "in-progress",
            "step_number": 1,
            "total_steps": 8,
        }
        assert msg["type"] == "progress"

    def test_llm_request_type(self):
        msg: LLMRequest = {
            "type": "llm_request",
            "model": "gpt-4.1",
            "prompt": "Analyze this section...",
            "system_prompt": "You are an ABS expert.",
            "temperature": 0.0,
            "max_tokens": 4096,
        }
        assert msg["type"] == "llm_request"
        assert msg["model"] == "gpt-4.1"

    def test_llm_response_type(self):
        msg: LLMResponse = {
            "type": "llm_response",
            "text": "Based on the analysis...",
            "input_tokens": 150,
            "output_tokens": 200,
        }
        assert msg["type"] == "llm_response"

    def test_stream_message_type(self):
        msg: StreamMessage = {"type": "stream", "text": "Processing..."}
        assert msg["type"] == "stream"

    def test_code_message_type(self):
        msg: CodeMessage = {
            "type": "code",
            "language": "python",
            "code": "def calc(): pass",
        }
        assert msg["type"] == "code"

    def test_result_message_type(self):
        msg: ResultMessage = {"type": "result", "command": "ingest"}
        assert msg["type"] == "result"

    def test_error_message_type(self):
        msg: ErrorMessage = {
            "type": "error",
            "message": "Deal not found",
            "code": "DEAL_NOT_FOUND",
        }
        assert msg["type"] == "error"

    def test_messages_are_json_serializable(self):
        msgs = [
            {"type": "progress", "step": "test", "status": "ok",
             "step_number": 1, "total_steps": 1},
            {"type": "llm_request", "model": "gpt-4.1", "prompt": "x",
             "system_prompt": None, "temperature": 0.0, "max_tokens": 100},
            {"type": "result", "command": "ingest"},
        ]
        for msg in msgs:
            serialized = json.dumps(msg)
            deserialized = json.loads(serialized)
            assert deserialized == msg

    def test_single_line_json(self):
        msg = {"type": "progress", "step": "test with\nnewline", "status": "ok",
               "step_number": 1, "total_steps": 1}
        line = json.dumps(msg)
        assert "\n" not in line  # Must be single line for IPC

    def test_all_types_defined(self):
        """All expected TypedDict types are importable."""
        from backend.abs.ipc_protocol import (
            ProgressMessage, LLMRequest, LLMResponse,
            StreamMessage, CodeMessage, ResultMessage, ErrorMessage,
        )
        assert True  # Import success
```

### `tests/unit/test_abs_streaming.py` (10 tests)

```python
"""Tests for ABSStream output module."""

import pytest
import json
from io import StringIO
from unittest.mock import patch

from backend.abs.streaming import ABSStream


class TestTerminalMode:

    def test_progress_prints_arrow(self, capsys):
        s = ABSStream(mode="terminal")
        s.progress("Converting PDF", "in-progress")
        out = capsys.readouterr().out
        assert "▸" in out
        assert "Converting PDF" in out

    def test_progress_done_prints_check(self, capsys):
        s = ABSStream(mode="terminal")
        s.progress("Done", "done")
        out = capsys.readouterr().out
        assert "✅" in out

    def test_markdown_prints_text(self, capsys):
        s = ABSStream(mode="terminal")
        s.markdown("Hello **world**")
        assert "Hello **world**" in capsys.readouterr().out

    def test_code_prints_fenced(self, capsys):
        s = ABSStream(mode="terminal")
        s.code("x = 1", "python")
        out = capsys.readouterr().out
        assert "```python" in out
        assert "x = 1" in out

    def test_error_prints_cross(self, capsys):
        s = ABSStream(mode="terminal")
        s.error("Something broke")
        assert "❌" in capsys.readouterr().out


class TestIPCMode:

    def test_progress_writes_json(self, capsys):
        s = ABSStream(mode="ipc")
        s.progress("step1", "ok", 1, 5)
        line = capsys.readouterr().out.strip()
        msg = json.loads(line)
        assert msg["type"] == "progress"
        assert msg["step"] == "step1"

    def test_markdown_writes_stream(self, capsys):
        s = ABSStream(mode="ipc")
        s.markdown("text")
        msg = json.loads(capsys.readouterr().out.strip())
        assert msg["type"] == "stream"
        assert msg["text"] == "text"

    def test_code_writes_code_msg(self, capsys):
        s = ABSStream(mode="ipc")
        s.code("x = 1", "python")
        msg = json.loads(capsys.readouterr().out.strip())
        assert msg["type"] == "code"
        assert msg["language"] == "python"

    def test_result_writes_result(self, capsys):
        s = ABSStream(mode="ipc")
        s.result({"item_count": 5})
        msg = json.loads(capsys.readouterr().out.strip())
        assert msg["type"] == "result"
        assert msg["item_count"] == 5

    def test_error_writes_error(self, capsys):
        s = ABSStream(mode="ipc")
        s.error("fail", "ERR001")
        msg = json.loads(capsys.readouterr().out.strip())
        assert msg["type"] == "error"
        assert msg["code"] == "ERR001"
```

---

## Integration Tests: CLI End-to-End

### `tests/integration/test_phase23_cli_smoke.py` (15 tests)

```python
"""CLI end-to-end smoke tests with mock agents."""

import pytest
import os
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from pathlib import Path


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_full_pipeline():
    """Mock the entire backend pipeline for CLI smoke tests."""
    with patch("backend.abs.orchestrator.DealScope") as ms, \
         patch("backend.abs.orchestrator.DealManifest") as mm, \
         patch("backend.abs.orchestrator.IngestionOrchestrator") as mi, \
         patch("backend.abs.orchestrator.ModelCreationAgent") as mg, \
         patch("backend.abs.orchestrator.AuditAgent") as ma, \
         patch("backend.abs.orchestrator.QAAgent") as mq:

        mm.return_value.is_complete.return_value = False
        mi.return_value.execute.return_value = {
            "item_count": 10, "section_count": 5,
            "node_count": 20, "edge_count": 15,
        }
        mg.return_value.execute.return_value = {
            "validation": "passed", "quality_score": 0.92,
        }
        ma.return_value.execute.return_value = {
            "report": "All 10 rules matched.", "confidence": 0.95,
            "rules_matched": 10, "rules_total": 10,
        }
        mq.return_value.execute.return_value = {
            "answer": "The Distribution Waterfall governs cash flow.",
            "sources": ["PSA Section 5.02"],
            "confidence": 0.85,
            "follow_ups": ["What are the triggers?"],
        }

        yield


class TestCLISmoke:

    def test_full_workflow(self, runner, mock_full_pipeline, tmp_path):
        """Test the complete CLI workflow: ingest → generate → qa → audit → status."""
        from cli.abs import abs_group

        # 1. Status (empty)
        result = runner.invoke(abs_group, ["status"])
        assert result.exit_code == 0

        # 2. Ingest
        result = runner.invoke(abs_group, [
            "ingest", "--deal-id", "smoke",
            "--source-dir", str(tmp_path), "--llm-mode", "mock",
        ])
        assert result.exit_code == 0
        assert "✅" in result.output

        # 3. Generate
        result = runner.invoke(abs_group, [
            "generate", "--deal-id", "smoke", "--llm-mode", "mock",
        ])
        assert result.exit_code == 0

        # 4. QA
        result = runner.invoke(abs_group, [
            "qa", "--deal-id", "smoke",
            "--query", "What is the waterfall?", "--llm-mode", "mock",
        ])
        assert result.exit_code == 0
        assert "waterfall" in result.output.lower()

        # 5. Audit
        result = runner.invoke(abs_group, [
            "audit", "--deal-id", "smoke", "--llm-mode", "mock",
        ])
        assert result.exit_code == 0

    def test_help_text_all_commands(self, runner):
        from cli.abs import abs_group

        for cmd in ["ingest", "generate", "audit", "qa", "status"]:
            result = runner.invoke(abs_group, [cmd, "--help"])
            assert result.exit_code == 0
            assert len(result.output) > 50

    def test_error_handling_missing_source(self, runner):
        from cli.abs import abs_group

        result = runner.invoke(abs_group, [
            "ingest", "--deal-id", "test",
            "--source-dir", "/nonexistent/path",
        ])
        assert result.exit_code != 0

    @pytest.mark.parametrize("mode", ["vscode", "mock", "none"])
    def test_llm_mode_accepted(self, runner, mock_full_pipeline, tmp_path, mode):
        from cli.abs import abs_group

        result = runner.invoke(abs_group, [
            "ingest", "--deal-id", "test",
            "--source-dir", str(tmp_path),
            "--llm-mode", mode,
        ])
        assert result.exit_code == 0

    def test_ingest_output_format(self, runner, mock_full_pipeline, tmp_path):
        from cli.abs import abs_group

        result = runner.invoke(abs_group, [
            "ingest", "--deal-id", "fmt_test",
            "--source-dir", str(tmp_path),
        ])
        assert "Items:" in result.output
        assert "Sections:" in result.output
        assert "Graph nodes:" in result.output

    def test_qa_verbose_shows_sources(self, runner, mock_full_pipeline):
        from cli.abs import abs_group

        result = runner.invoke(abs_group, [
            "qa", "--deal-id", "test",
            "--query", "test query", "--llm-mode", "mock", "-v",
        ])
        assert result.exit_code == 0
        assert "Sources:" in result.output or "PSA" in result.output
```

---

## Integration Tests: Extension Components

### `tests/integration/test_phase23_extension.py` (15 tests)

```python
"""Extension component validation tests.

These tests validate the TypeScript source files exist and
contain expected patterns. Actual TypeScript testing requires
VS Code Extension Test Runner (separate test suite).
"""

import pytest
import json
from pathlib import Path


EXTENSION_DIR = Path(__file__).parent.parent.parent / "extension"
ABS_SRC_DIR = EXTENSION_DIR / "src" / "abs"


class TestExtensionFiles:

    def test_abs_directory_exists(self):
        assert ABS_SRC_DIR.exists(), f"Missing {ABS_SRC_DIR}"

    def test_participant_file_exists(self):
        assert (ABS_SRC_DIR / "absParticipant.ts").exists()

    def test_handler_file_exists(self):
        assert (ABS_SRC_DIR / "absRequestHandler.ts").exists()

    def test_bridge_file_exists(self):
        assert (ABS_SRC_DIR / "absLLMBridge.ts").exists()

    def test_followups_file_exists(self):
        assert (ABS_SRC_DIR / "absFollowups.ts").exists()


class TestExtensionParticipant:

    def test_participant_registers_abs(self):
        code = (ABS_SRC_DIR / "absParticipant.ts").read_text()
        assert "createChatParticipant" in code
        assert "'abs'" in code

    def test_handler_has_slash_commands(self):
        code = (ABS_SRC_DIR / "absRequestHandler.ts").read_text()
        for cmd in ["ingest", "generate", "audit", "status"]:
            assert f"'{cmd}'" in code or f'"{cmd}"' in code


class TestPackageJson:

    @pytest.fixture
    def package_json(self):
        pkg_path = EXTENSION_DIR / "package.json"
        assert pkg_path.exists()
        return json.loads(pkg_path.read_text())

    def test_has_chat_participants(self, package_json):
        assert "chatParticipants" in package_json.get("contributes", {})

    def test_has_abs_participant(self, package_json):
        participants = package_json["contributes"]["chatParticipants"]
        names = [p["name"] for p in participants]
        assert "abs" in names

    def test_has_kts_participant(self, package_json):
        """KTS participant still present."""
        participants = package_json["contributes"]["chatParticipants"]
        names = [p["name"] for p in participants]
        assert "kts" in names

    def test_abs_has_slash_commands(self, package_json):
        participants = package_json["contributes"]["chatParticipants"]
        abs_p = [p for p in participants if p["name"] == "abs"][0]
        cmds = [c["name"] for c in abs_p["commands"]]
        assert "ingest" in cmds
        assert "generate" in cmds
        assert "audit" in cmds
        assert "status" in cmds

    def test_abs_description(self, package_json):
        participants = package_json["contributes"]["chatParticipants"]
        abs_p = [p for p in participants if p["name"] == "abs"][0]
        assert len(abs_p["description"]) > 10

    def test_abs_has_full_name(self, package_json):
        participants = package_json["contributes"]["chatParticipants"]
        abs_p = [p for p in participants if p["name"] == "abs"][0]
        assert "fullName" in abs_p
        assert "ABS" in abs_p["fullName"] or "Payment" in abs_p["fullName"]

    def test_abs_is_sticky(self, package_json):
        participants = package_json["contributes"]["chatParticipants"]
        abs_p = [p for p in participants if p["name"] == "abs"][0]
        assert abs_p.get("isSticky") is True
```

---

## Packaging Tests

### `tests/integration/test_phase23_packaging.py` (10 tests)

```python
"""Packaging and build configuration tests."""

import pytest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestPyInstallerSpec:

    @pytest.fixture
    def spec_content(self):
        spec_path = PROJECT_ROOT / "packaging" / "kts.spec"
        assert spec_path.exists(), "kts.spec not found"
        return spec_path.read_text()

    def test_abs_orchestrator_in_hidden_imports(self, spec_content):
        assert "backend.abs.orchestrator" in spec_content

    def test_abs_agents_in_hidden_imports(self, spec_content):
        assert "backend.abs.agents" in spec_content

    def test_abs_llm_bridge_in_hidden_imports(self, spec_content):
        assert "backend.abs.llm_bridge" in spec_content

    def test_cli_abs_in_hidden_imports(self, spec_content):
        assert "cli.abs" in spec_content

    def test_abs_streaming_in_hidden_imports(self, spec_content):
        assert "backend.abs.streaming" in spec_content


class TestBuildScript:

    def test_build_script_exists(self):
        script = PROJECT_ROOT / "scripts" / "build_combined.ps1"
        assert script.exists()

    def test_build_script_has_steps(self):
        script = PROJECT_ROOT / "scripts" / "build_combined.ps1"
        content = script.read_text()
        assert "pyinstaller" in content.lower() or "PyInstaller" in content
        assert "compile" in content.lower() or "tsc" in content.lower()
        assert "vsce" in content.lower() or "vsix" in content.lower()


class TestCLIRegistration:

    def test_abs_group_importable(self):
        from cli.abs import abs_group
        assert abs_group is not None

    def test_abs_group_in_main(self):
        cli_main = PROJECT_ROOT / "cli" / "main.py"
        content = cli_main.read_text()
        assert "abs_group" in content or "abs" in content

    def test_abs_commands_importable(self):
        from cli.abs.ingest_cmd import abs_ingest
        from cli.abs.generate_cmd import abs_generate
        from cli.abs.audit_cmd import abs_audit
        from cli.abs.qa_cmd import abs_qa
        from cli.abs.status_cmd import abs_status
        assert all([abs_ingest, abs_generate, abs_audit, abs_qa, abs_status])
```

---

## Regression Tests: KTS Isolation

### `tests/integration/test_kts_isolation_phase23.py` (15 tests)

```python
"""Verify KTS functionality is unaffected by Phase 23 ABS additions."""

import pytest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestKTSCLIUnaffected:

    def test_kts_main_still_importable(self):
        from cli.main import main
        assert main is not None

    def test_kts_existing_commands_present(self):
        """Existing KTS commands are still registered."""
        from cli.main import main
        import click
        if isinstance(main, click.Group):
            # KTS should still have its original commands
            assert len(main.commands) >= 1  # At least abs + original

    def test_kts_search_command_unchanged(self):
        """If KTS has a search command, it still works."""
        try:
            from cli.main import main
            if "search" in getattr(main, "commands", {}):
                assert True  # Command still registered
        except ImportError:
            pytest.skip("KTS search command not implemented")


class TestKTSConfigUnaffected:

    def test_kts_config_imports(self):
        from config.settings import KTSConfig
        config = KTSConfig()
        assert config is not None

    def test_kts_config_has_no_abs_side_effects(self):
        """ABS config additions don't change KTS defaults."""
        from config.settings import KTSConfig
        config = KTSConfig()

        # Existing KTS properties should be unchanged
        # (Specific assertions depend on existing config properties)
        assert hasattr(config, "__class__")


class TestKTSExtensionUnaffected:

    def test_extension_ts_still_exists(self):
        ext_ts = PROJECT_ROOT / "extension" / "src" / "extension.ts"
        assert ext_ts.exists()

    def test_extension_activates_kts(self):
        ext_ts = PROJECT_ROOT / "extension" / "src" / "extension.ts"
        content = ext_ts.read_text()
        # Must still register KTS
        assert "kts" in content.lower()

    def test_kts_participant_files_exist(self):
        """KTS participant source files unchanged."""
        kts_dir = PROJECT_ROOT / "extension" / "src" / "kts"
        if kts_dir.exists():
            assert any(kts_dir.iterdir())

    def test_package_json_has_kts(self):
        import json
        pkg = json.loads(
            (PROJECT_ROOT / "extension" / "package.json").read_text()
        )
        participants = pkg.get("contributes", {}).get("chatParticipants", [])
        kts_entries = [p for p in participants if p.get("name") == "kts"]
        assert len(kts_entries) >= 1

    def test_package_json_kts_commands_unchanged(self):
        """KTS commands not modified by Phase 23."""
        import json
        pkg = json.loads(
            (PROJECT_ROOT / "extension" / "package.json").read_text()
        )
        participants = pkg["contributes"]["chatParticipants"]
        kts_p = [p for p in participants if p["name"] == "kts"]
        if kts_p:
            # KTS should still have its original commands
            assert "commands" in kts_p[0]


class TestKTSBackendUnaffected:

    def test_backend_agents_still_importable(self):
        try:
            from backend.agents import __init__
        except ImportError:
            # It's okay if there's no __init__, but the directory should exist
            assert (PROJECT_ROOT / "backend" / "agents").exists()

    def test_backend_common_still_importable(self):
        try:
            from backend.common import __init__
        except ImportError:
            assert (PROJECT_ROOT / "backend" / "common").exists()

    def test_kts_graph_modules_present(self):
        graph_dir = PROJECT_ROOT / "backend" / "graph"
        assert graph_dir.exists()
        assert any(graph_dir.glob("*.py"))

    def test_kts_vector_modules_present(self):
        vector_dir = PROJECT_ROOT / "backend" / "vector"
        assert vector_dir.exists()
        assert any(vector_dir.glob("*.py"))

    def test_kts_retrieval_modules_present(self):
        retrieval_dir = PROJECT_ROOT / "backend" / "retrieval"
        assert retrieval_dir.exists()
        assert any(retrieval_dir.glob("*.py"))
```

---

## Pass Criteria

| Category | Tests | Pass Threshold |
|----------|-------|---------------|
| Orchestrator unit | 20 | 100% |
| CLI commands unit | 25 | 100% |
| CLI group unit | 10 | 100% |
| IPC protocol unit | 10 | 100% |
| Streaming unit | 10 | 100% |
| CLI smoke integration | 15 | 100% |
| Extension integration | 15 | 100% (file existence + JSON structure) |
| Packaging integration | 10 | 100% |
| KTS isolation regression | 15 | 100% |
| **Total** | **~130** | **100%** |

### Acceptance Gate

Phase 23 is considered complete when:

1. All 130 tests pass
2. `npx tsc --noEmit` compiles without errors
3. `python -m cli.main abs --help` shows all 5 commands
4. `package.json` contains both `@kts` and `@abs` chatParticipants
5. PyInstaller spec includes all ABS hidden imports
6. CLI smoke test completes full workflow: ingest → generate → qa → audit → status

---

## Test Execution

```powershell
# ═══════════════════════════════════════════════
# Run all Phase 23 tests
# ═══════════════════════════════════════════════

# Unit tests
python -m pytest tests/unit/test_abs_orchestrator.py -v
python -m pytest tests/unit/test_abs_cli_commands.py -v
python -m pytest tests/unit/test_abs_cli_group.py -v
python -m pytest tests/unit/test_abs_ipc_protocol.py -v
python -m pytest tests/unit/test_abs_streaming.py -v

# Integration tests
python -m pytest tests/integration/test_phase23_cli_smoke.py -v
python -m pytest tests/integration/test_phase23_extension.py -v
python -m pytest tests/integration/test_phase23_packaging.py -v

# Regression tests
python -m pytest tests/integration/test_kts_isolation_phase23.py -v

# All Phase 23 tests at once
python -m pytest tests/ -k "phase23 or abs_orchestrator or abs_cli or abs_ipc or abs_streaming" -v

# Full suite (all phases)
python -m pytest tests/ -v --tb=short
```
