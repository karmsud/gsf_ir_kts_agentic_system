"""
Unit tests for ABSOrchestrator — Phase 23 convergence layer.

Tests focus on:
- Dataclass correctness (all required fields)
- Orchestrator instantiation (minimal + with LLM)
- Ingest delegation to IngestionPipelineAgent
- Generate delegation to ModelCreationAgent
- Audit delegation to ModelAuditorAgent
- QA delegation to QAAgent
- Status returning correct report strings
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config.settings import KTSConfig
from backend.abs.orchestrator import (
    ABSOrchestrator,
    AuditResult,
    GenerateResult,
    IngestResult,
    QAResult,
    StatusResult,
)


# ─── Dataclass Tests ────────────────────────────────────────────────────────


class TestResultDataclasses:
    """Verify all result dataclasses have correct fields and defaults."""

    def test_ingest_result_fields(self):
        r = IngestResult(
            deal_id="test_deal",
            item_count=10,
            section_count=5,
            node_count=20,
            edge_count=15,
            elapsed_seconds=1.5,
        )
        assert r.deal_id == "test_deal"
        assert r.item_count == 10
        assert r.section_count == 5
        assert r.node_count == 20
        assert r.edge_count == 15
        assert r.elapsed_seconds == 1.5
        assert r.skipped is False  # default
        assert r.message == ""     # default

    def test_generate_result_fields(self):
        r = GenerateResult(
            deal_id="test_deal",
            output_path=Path("out/model.py"),
            validation_summary="ok",
            quality_score=0.95,
        )
        assert r.quality_score == 0.95
        assert isinstance(r.output_path, Path)
        assert r.elapsed_seconds == 0.0  # default

    def test_audit_result_fields(self):
        r = AuditResult(
            deal_id="test_deal",
            report="pass",
            confidence=0.9,
            rules_matched=8,
            rules_total=10,
        )
        assert r.rules_matched == 8
        assert r.rules_total == 10
        assert r.report == "pass"

    def test_qa_result_fields(self):
        r = QAResult(
            deal_id="test_deal",
            answer="42",
            sources=["s1"],
            confidence=0.8,
            follow_ups=["q1"],
        )
        assert len(r.sources) == 1
        assert r.answer == "42"
        assert r.confidence == 0.8

    def test_status_result_fields(self):
        r = StatusResult(status_report="all good")
        assert "all good" in r.status_report
        assert r.deals == []  # default

    def test_ingest_result_skipped_flag(self):
        r = IngestResult(
            deal_id="x",
            item_count=5,
            section_count=2,
            node_count=8,
            edge_count=4,
            elapsed_seconds=0.1,
            skipped=True,
            message="Already done.",
        )
        assert r.skipped is True
        assert "done" in r.message


# ─── Orchestrator Instantiation ─────────────────────────────────────────────


class TestOrchestratorInit:
    """Verify orchestrator construction (minimal and with LLM)."""

    def test_init_minimal(self):
        config = KTSConfig()
        orch = ABSOrchestrator(config=config)
        assert orch.config is config
        assert orch.llm is None

    def test_init_no_args(self):
        # Should create a default KTSConfig
        orch = ABSOrchestrator()
        assert isinstance(orch.config, KTSConfig)

    def test_init_with_llm(self):
        config = KTSConfig()
        llm = MagicMock()
        orch = ABSOrchestrator(config=config, llm_callable=llm)
        assert orch.llm is llm
        assert orch.llm is not None


# ─── Ingest ─────────────────────────────────────────────────────────────────


class TestOrchestratorIngest:

    @patch("backend.abs.agents.ingestion_pipeline_agent.IngestionPipelineAgent.__init__", return_value=None)
    @patch("backend.abs.agents.ingestion_pipeline_agent.IngestionPipelineAgent._run")
    @patch("backend.abs.deal_manifest.DealManifest.load")
    def test_ingest_returns_ingest_result(
        self, mock_load, mock_run, mock_init
    ):
        mock_load.side_effect = FileNotFoundError("no manifest")
        mock_run.return_value = {
            "item_count": 3,
            "section_count": 7,
            "node_count": 12,
            "edge_count": 10,
        }

        orch = ABSOrchestrator(config=KTSConfig())
        result = orch.ingest("test_deal", Path("."))

        assert isinstance(result, IngestResult)
        assert result.item_count == 3
        assert result.section_count == 7
        assert result.node_count == 12
        assert result.edge_count == 10
        mock_run.assert_called_once()

    @patch("backend.abs.deal_manifest.DealManifest.load")
    def test_ingest_skips_if_ready(self, mock_load):
        manifest = mock_load.return_value
        manifest.is_ready_for_model_generation.return_value = True
        manifest.list_documents.return_value = ["doc1.pdf", "doc2.pdf"]

        orch = ABSOrchestrator(config=KTSConfig())
        result = orch.ingest("test_deal", Path("."))

        assert result.skipped is True
        assert result.item_count == 2  # len(["doc1.pdf", "doc2.pdf"])

    @patch("backend.abs.agents.ingestion_pipeline_agent.IngestionPipelineAgent.__init__", return_value=None)
    @patch("backend.abs.agents.ingestion_pipeline_agent.IngestionPipelineAgent._run")
    @patch("backend.abs.deal_manifest.DealManifest.load")
    def test_ingest_force_re_ingests(
        self, mock_load, mock_run, mock_init
    ):
        manifest = mock_load.return_value
        manifest.is_ready_for_model_generation.return_value = True
        mock_run.return_value = {
            "item_count": 1, "section_count": 1,
            "node_count": 1, "edge_count": 1,
        }

        orch = ABSOrchestrator(config=KTSConfig())
        result = orch.ingest("test_deal", Path("."), force=True)

        # Agent _run should be called even though manifest shows ready
        mock_run.assert_called_once()
        assert result.skipped is False

    @patch("backend.abs.agents.ingestion_pipeline_agent.IngestionPipelineAgent.__init__", return_value=None)
    @patch("backend.abs.agents.ingestion_pipeline_agent.IngestionPipelineAgent._run")
    @patch("backend.abs.deal_manifest.DealManifest.load")
    def test_ingest_progress_callback_called(
        self, mock_load, mock_run, mock_init
    ):
        mock_load.side_effect = FileNotFoundError
        mock_run.return_value = {
            "item_count": 1, "section_count": 1,
            "node_count": 1, "edge_count": 1,
        }
        cb = MagicMock()
        orch = ABSOrchestrator(config=KTSConfig())
        orch.ingest("test_deal", Path("."), progress_callback=cb)

        assert cb.call_count >= 1


# ─── Generate ───────────────────────────────────────────────────────────────


class TestOrchestratorGenerate:

    @patch("backend.abs.agents.model_creation_agent.ModelCreationAgent.__init__", return_value=None)
    @patch("backend.abs.agents.model_creation_agent.ModelCreationAgent._run")
    def test_generate_returns_generate_result(self, mock_run, mock_init):
        mock_run.return_value = {
            "output_path": "/tmp/model.py",
            "quality_score": 0.92,
            "validation_summary": "ok",
        }

        orch = ABSOrchestrator(config=KTSConfig())
        result = orch.generate("test_deal", output_dir=Path("/tmp"))

        assert isinstance(result, GenerateResult)
        assert result.quality_score == 0.92
        mock_run.assert_called_once()

    @patch("backend.abs.agents.model_creation_agent.ModelCreationAgent.__init__", return_value=None)
    @patch("backend.abs.agents.model_creation_agent.ModelCreationAgent._run")
    def test_generate_uses_default_output_dir(self, mock_run, mock_init):
        mock_run.return_value = {
            "quality_score": 0.85,
            "validation_summary": "ok",
        }
        orch = ABSOrchestrator(config=KTSConfig())
        result = orch.generate("test_deal")  # no output_dir

        assert isinstance(result, GenerateResult)


# ─── Audit ──────────────────────────────────────────────────────────────────


class TestOrchestratorAudit:

    @patch("backend.abs.agents.model_auditor_agent.ModelAuditorAgent.__init__", return_value=None)
    @patch("backend.abs.agents.model_auditor_agent.ModelAuditorAgent._run")
    def test_audit_returns_audit_result(self, mock_run, mock_init):
        mock_run.return_value = {
            "report": "All rules match.",
            "confidence": 0.88,
            "rules_matched": 9,
            "rules_total": 10,
        }

        orch = ABSOrchestrator(config=KTSConfig())
        result = orch.audit("test_deal")

        assert isinstance(result, AuditResult)
        assert result.confidence == 0.88
        assert result.rules_matched == 9
        mock_run.assert_called_once()


# ─── QA ─────────────────────────────────────────────────────────────────────


class TestOrchestratorQA:

    @patch("backend.abs.agents.qa_agent.QAAgent.__init__", return_value=None)
    @patch("backend.abs.agents.qa_agent.QAAgent._run")
    def test_qa_returns_qa_result(self, mock_run, mock_init):
        mock_run.return_value = {
            "answer": "The waterfall distributes pro-rata.",
            "sources": ["doc1.pdf#42", "doc2.pdf#17"],
            "confidence": 0.91,
            "follow_ups": ["What are the OC triggers?"],
        }

        orch = ABSOrchestrator(config=KTSConfig())
        result = orch.qa("test_deal", "What is the waterfall?")

        assert isinstance(result, QAResult)
        assert "waterfall" in result.answer
        assert len(result.sources) == 2
        assert result.confidence == 0.91


# ─── Status ─────────────────────────────────────────────────────────────────


class TestOrchestratorStatus:

    def test_status_no_deal_not_found(self):
        orch = ABSOrchestrator(config=KTSConfig())
        result = orch.status(deal_id="nonexistent_2099_zz1")
        assert isinstance(result, StatusResult)
        assert "not found" in result.status_report.lower() or "not-ingested" in result.status_report.lower()

    def test_status_all_deals_empty(self, tmp_path):
        config = KTSConfig()
        config.abs_deals_root = str(tmp_path)
        orch = ABSOrchestrator(config=config)
        result = orch.status()
        assert "No deals found" in result.status_report

    @patch("backend.abs.deal_manifest.DealManifest.load")
    def test_status_all_deals_nonempty(self, mock_load, tmp_path):
        config = KTSConfig()
        config.abs_deals_root = str(tmp_path)

        # Create one fake deal dir
        deal_dir = tmp_path / "test_2024_he1"
        deal_dir.mkdir()

        manifest = mock_load.return_value
        manifest.list_documents.return_value = ["doc.pdf"]
        manifest.is_ready_for_model_generation.return_value = True
        manifest.validate.return_value = []

        orch = ABSOrchestrator(config=config)
        result = orch.status()

        assert "test_2024_he1" in result.status_report
        assert len(result.deals) == 1
        assert result.deals[0]["ready"] is True
