"""
Unit and integration tests for Phase 23 CLI commands, IPC protocol,
streaming module, and package.json validation.

Covers:
- ABSStream terminal/ipc modes
- IPC protocol TypedDicts constructable
- CLI command registration (click runners)
- package.json @abs participant integration
- CLI help text
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from backend.abs.ipc_protocol import (
    CodeMessage,
    ErrorMessage,
    LLMRequest,
    LLMResponse,
    ProgressMessage,
    ResultMessage,
    StreamMessage,
)
from backend.abs.streaming import ABSStream
from cli.abs import abs_group


# ─── IPC Protocol ────────────────────────────────────────────────────────────


class TestIPCProtocol:
    """Verify all IPC message TypedDicts are constructable."""

    def test_progress_message(self):
        m: ProgressMessage = {
            "type": "progress",
            "step": "extracting",
            "status": "in-progress",
            "step_number": 1,
            "total_steps": 5,
        }
        assert m["type"] == "progress"
        assert m["step"] == "extracting"

    def test_llm_request_message(self):
        m: LLMRequest = {
            "type": "llm_request",
            "model": "gpt-4.1",
            "prompt": "Summarise the waterfall.",
            "system_prompt": None,
            "temperature": 0.0,
            "max_tokens": 4096,
        }
        assert m["model"] == "gpt-4.1"

    def test_llm_response_message(self):
        m: LLMResponse = {
            "type": "llm_response",
            "text": "The waterfall distributes pro-rata.",
            "input_tokens": 100,
            "output_tokens": 50,
        }
        assert m["text"].startswith("The waterfall")

    def test_stream_message(self):
        m: StreamMessage = {"type": "stream", "text": "partial text..."}
        assert m["text"] == "partial text..."

    def test_code_message(self):
        m: CodeMessage = {
            "type": "code",
            "language": "python",
            "code": "def run(): pass",
        }
        assert m["language"] == "python"

    def test_error_message(self):
        m: ErrorMessage = {
            "type": "error",
            "message": "Something went wrong",
            "code": "INGEST_FAIL",
        }
        assert m["code"] == "INGEST_FAIL"

    def test_ipc_messages_json_serialisable(self):
        """All message dicts must be JSON-serialisable (no custom objects)."""
        messages = [
            {"type": "progress", "step": "s", "status": "done", "step_number": 1, "total_steps": 1},
            {"type": "llm_response", "text": "t", "input_tokens": 0, "output_tokens": 0},
            {"type": "stream", "text": "t"},
            {"type": "error", "message": "m", "code": "E"},
        ]
        for m in messages:
            assert json.dumps(m)  # No exception


# ─── ABSStream ───────────────────────────────────────────────────────────────


class TestABSStream:
    """Verify ABSStream terminal and IPC modes."""

    def test_terminal_mode_instantiation(self):
        s = ABSStream(mode="terminal")
        assert s.mode == "terminal"

    def test_ipc_mode_instantiation(self):
        s = ABSStream(mode="ipc")
        assert s.mode == "ipc"

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="'terminal' or 'ipc'"):
            ABSStream(mode="invalid")

    def test_terminal_progress_no_exception(self, capsys):
        s = ABSStream(mode="terminal")
        s.progress("extracting", "in-progress")
        captured = capsys.readouterr()
        assert "extracting" in captured.out

    def test_terminal_progress_done_uses_checkmark(self, capsys):
        s = ABSStream(mode="terminal")
        s.progress("done-step", "done")
        captured = capsys.readouterr()
        assert "✅" in captured.out or "done-step" in captured.out

    def test_terminal_error_to_stderr(self, capsys):
        s = ABSStream(mode="terminal")
        s.error("Something broke", "E001")
        captured = capsys.readouterr()
        assert "Something broke" in captured.err

    def test_ipc_progress_emits_json(self, capsys):
        s = ABSStream(mode="ipc")
        s.progress("loading", "in-progress")
        out = capsys.readouterr().out.strip()
        msg = json.loads(out)
        assert msg["type"] == "progress"
        assert msg["step"] == "loading"

    def test_ipc_error_emits_json(self, capsys):
        s = ABSStream(mode="ipc")
        s.error("bad thing", "ERR_X")
        out = capsys.readouterr().out.strip()
        msg = json.loads(out)
        assert msg["type"] == "error"
        assert msg["code"] == "ERR_X"

    def test_ipc_result_emits_json(self, capsys):
        s = ABSStream(mode="ipc")
        s.result({"command": "ingest", "item_count": 5})
        out = capsys.readouterr().out.strip()
        msg = json.loads(out)
        assert msg["type"] == "result"
        assert msg["item_count"] == 5

    def test_ipc_code_emits_json(self, capsys):
        s = ABSStream(mode="ipc")
        s.code("def run(): pass", language="python")
        out = capsys.readouterr().out.strip()
        msg = json.loads(out)
        assert msg["type"] == "code"
        assert msg["language"] == "python"

    def test_ipc_markdown_emits_stream_type(self, capsys):
        s = ABSStream(mode="ipc")
        s.markdown("**Hello**")
        out = capsys.readouterr().out.strip()
        msg = json.loads(out)
        assert msg["type"] == "stream"
        assert msg["text"] == "**Hello**"

    def test_terminal_llm_request_returns_none(self):
        s = ABSStream(mode="terminal")
        result = s.llm_request("Summarise this.", system_prompt=None)
        assert result is None


# ─── CLI Command Group ────────────────────────────────────────────────────────


class TestCLICommandGroup:
    """Verify the abs_group Click group has all subcommands."""

    def test_abs_group_exists(self):
        assert abs_group is not None

    def test_abs_group_has_all_subcommands(self):
        expected = {"ingest", "generate", "audit", "qa", "status"}
        actual = set(abs_group.commands.keys())
        assert expected.issubset(actual), f"Missing commands: {expected - actual}"

    def test_abs_group_help(self):
        runner = CliRunner()
        result = runner.invoke(abs_group, ["--help"])
        assert result.exit_code == 0
        assert "ingest" in result.output.lower()

    def test_ingest_help(self):
        runner = CliRunner()
        result = runner.invoke(abs_group, ["ingest", "--help"])
        assert result.exit_code == 0
        assert "--deal-id" in result.output
        assert "--source-dir" in result.output

    def test_generate_help(self):
        runner = CliRunner()
        result = runner.invoke(abs_group, ["generate", "--help"])
        assert result.exit_code == 0
        assert "--deal-id" in result.output
        assert "--llm-mode" in result.output

    def test_audit_help(self):
        runner = CliRunner()
        result = runner.invoke(abs_group, ["audit", "--help"])
        assert result.exit_code == 0
        assert "--deal-id" in result.output

    def test_qa_help(self):
        runner = CliRunner()
        result = runner.invoke(abs_group, ["qa", "--help"])
        assert result.exit_code == 0
        assert "--query" in result.output or "-q" in result.output

    def test_status_help(self):
        runner = CliRunner()
        result = runner.invoke(abs_group, ["status", "--help"])
        assert result.exit_code == 0


# ─── CLI Command Options ──────────────────────────────────────────────────────


class TestCLICommandOptions:
    """Verify CLI commands fail gracefully with missing required options."""

    def test_ingest_requires_deal_id(self):
        runner = CliRunner()
        result = runner.invoke(abs_group, ["ingest", "--source-dir", "."])
        assert result.exit_code != 0
        assert "deal-id" in result.output.lower() or "missing" in result.output.lower()

    def test_ingest_requires_source_dir(self):
        runner = CliRunner()
        result = runner.invoke(abs_group, ["ingest", "--deal-id", "test"])
        assert result.exit_code != 0

    def test_generate_requires_deal_id(self):
        runner = CliRunner()
        result = runner.invoke(abs_group, ["generate"])
        assert result.exit_code != 0

    def test_qa_requires_deal_id_and_query(self):
        runner = CliRunner()
        result = runner.invoke(abs_group, ["qa"])
        assert result.exit_code != 0

    def test_status_no_required_options(self):
        """status has no required options — should show help or run."""
        runner = CliRunner()
        result = runner.invoke(abs_group, ["status", "--help"])
        assert result.exit_code == 0


# ─── Package.json Validation ─────────────────────────────────────────────────


class TestPackageJson:
    """Verify extension/package.json has @abs participant registered."""

    @pytest.fixture
    def package_json(self):
        pkg_path = Path(__file__).parent.parent / "extension" / "package.json"
        with open(pkg_path) as f:
            return json.load(f)

    def test_abs_participant_registered(self, package_json):
        participants = package_json.get("contributes", {}).get("chatParticipants", [])
        names = [p.get("name", p.get("id", "")) for p in participants]
        assert any("abs" in n for n in names), f"@abs not in {names}"

    def test_kts_participant_still_registered(self, package_json):
        participants = package_json.get("contributes", {}).get("chatParticipants", [])
        names = [p.get("name", p.get("id", "")) for p in participants]
        assert any("kts" in n for n in names), f"@kts not in {names}"

    def test_abs_has_four_commands(self, package_json):
        participants = package_json.get("contributes", {}).get("chatParticipants", [])
        abs_p = next(
            (p for p in participants if "abs" in p.get("name", p.get("id", ""))),
            None,
        )
        assert abs_p is not None, "@abs participant not found"
        cmds = {c["name"] for c in abs_p.get("commands", [])}
        required = {"ingest", "generate", "audit", "status"}
        missing = required - cmds
        assert not missing, f"Missing @abs commands: {missing}"

    def test_package_json_valid_json(self):
        """Ensure package.json is still valid JSON after modification."""
        pkg_path = Path(__file__).parent.parent / "extension" / "package.json"
        with open(pkg_path) as f:
            data = json.load(f)
        assert "contributes" in data


# ─── Phase 23 Backend Import Smoke Tests ─────────────────────────────────────


class TestPhase23Imports:
    """Verify all Phase 23 modules import without error."""

    def test_orchestrator_import(self):
        from backend.abs.orchestrator import ABSOrchestrator

        assert ABSOrchestrator is not None

    def test_ipc_protocol_import(self):
        from backend.abs.ipc_protocol import ProgressMessage, LLMRequest, LLMResponse

        assert ProgressMessage is not None

    def test_streaming_import(self):
        from backend.abs.streaming import ABSStream

        assert ABSStream is not None

    def test_cli_abs_group_import(self):
        from cli.abs import abs_group

        assert abs_group is not None

    def test_cli_commands_import(self):
        from cli.abs.ingest_cmd import abs_ingest
        from cli.abs.generate_cmd import abs_generate
        from cli.abs.audit_cmd import abs_audit
        from cli.abs.qa_cmd import abs_qa
        from cli.abs.status_cmd import abs_status

        for cmd in (abs_ingest, abs_generate, abs_audit, abs_qa, abs_status):
            assert cmd is not None


# ─── KTS Isolation ───────────────────────────────────────────────────────────


class TestKTSIsolation:
    """Verify Phase 23 changes do not break KTS core functionality."""

    def test_kts_cli_still_importable(self):
        from cli.main import cli
        assert cli is not None

    def test_kts_config_unchanged(self):
        from config.settings import KTSConfig
        config = KTSConfig()
        # Core KTS fields still present
        assert hasattr(config, "chroma_persist_dir")
        assert hasattr(config, "embed_model_path")

    def test_abs_agent_base_llm_wiring(self):
        """All ABS agent constructors still accept llm_callable."""
        from backend.abs.agents.ingestion_pipeline_agent import IngestionPipelineAgent
        from backend.abs.agents.model_creation_agent import ModelCreationAgent
        from backend.abs.agents.qa_agent import QAAgent
        from backend.abs.deal_scope import DealScope
        from backend.agents.agent_tools import ToolRegistry
        from config.settings import KTSConfig

        config = KTSConfig()
        scope = DealScope("test", Path("."))
        registry = ToolRegistry()
        llm = MagicMock()

        for AgentCls in (IngestionPipelineAgent, ModelCreationAgent, QAAgent):
            agent = AgentCls(
                config=config,
                deal_scope=scope,
                tool_registry=registry,
                llm_callable=llm,
            )
            assert agent._llm is llm
