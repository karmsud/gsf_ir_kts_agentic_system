"""
ABSOrchestrator — Unified convergence layer for ABS operations.

Both the CLI and the VS Code chat participant delegate to this class.
Each method is stateless: it creates its own agents with the current
config and an optional LLM callable, then tears them down on exit.

Result dataclasses are defined here so callers need only import from
this one module.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from config.settings import KTSConfig


# ──────────────────────────────────────────────────────────────────────────────
# Result Dataclasses
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class IngestResult:
    """Returned by ABSOrchestrator.ingest()."""

    deal_id: str
    item_count: int
    section_count: int
    node_count: int
    edge_count: int
    elapsed_seconds: float
    skipped: bool = False
    message: str = ""


@dataclass
class GenerateResult:
    """Returned by ABSOrchestrator.generate()."""

    deal_id: str
    output_path: Path
    validation_summary: str
    quality_score: float
    elapsed_seconds: float = 0.0


@dataclass
class AuditResult:
    """Returned by ABSOrchestrator.audit()."""

    deal_id: str
    report: str
    confidence: float
    rules_matched: int
    rules_total: int
    elapsed_seconds: float = 0.0


@dataclass
class QAResult:
    """Returned by ABSOrchestrator.qa()."""

    deal_id: str
    answer: str
    sources: list[str] = field(default_factory=list)
    confidence: float = 0.0
    follow_ups: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


@dataclass
class StatusResult:
    """Returned by ABSOrchestrator.status()."""

    status_report: str
    deals: list[dict] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────────────────────


class ABSOrchestrator:
    """
    Convergence layer for ABS operations.

    Parameters
    ----------
    config:
        KTSConfig instance (can be a plain ``KTSConfig()`` with defaults,
        or one patched by a CLI command).
    llm_callable:
        Optional callable produced by ``create_llm_callable()``.
        When *None*, agents run in deterministic mode (no LLM calls).
    """

    def __init__(
        self,
        config: Optional[KTSConfig] = None,
        llm_callable: Optional[Callable] = None,
    ) -> None:
        self.config: KTSConfig = config or KTSConfig()
        self.llm: Optional[Callable] = llm_callable

    # ------------------------------------------------------------------
    # ingest
    # ------------------------------------------------------------------

    def ingest(
        self,
        deal_id: str,
        source_dir: Path,
        *,
        force: bool = False,
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> IngestResult:
        """
        Ingest deal documents from *source_dir* into the knowledge base.

        Delegates to ``IngestionPipelineAgent._run()`` via a task dict.

        Parameters
        ----------
        deal_id:
            Canonical deal identifier (e.g. ``bear_stearns_2006_he1``).
        source_dir:
            Directory containing raw PDF / text documents.
        force:
            Re-ingest even if the manifest already shows a complete status.
        progress_callback:
            Optional ``(step: str, status: str) -> None`` called for
            each pipeline stage.
        """
        from backend.abs.deal_scope import DealScope
        from backend.abs.deal_manifest import DealManifest
        from backend.abs.agents.ingestion_pipeline_agent import IngestionPipelineAgent
        from backend.agents.agent_tools import ToolRegistry

        start = time.time()

        # Resolve deal path
        deal_path = Path(source_dir)
        scope = DealScope(deal_id=deal_id, deals_root=deal_path.parent)

        # Skip if already ingested (unless forced)
        if not force:
            try:
                manifest = DealManifest.load(deal_path)
                if manifest.is_ready_for_model_generation():
                    return IngestResult(
                        deal_id=deal_id,
                        item_count=len(manifest.list_documents()),
                        section_count=0,
                        node_count=0,
                        edge_count=0,
                        elapsed_seconds=time.time() - start,
                        skipped=True,
                        message="Deal already ingested. Use --force to re-ingest.",
                    )
            except (FileNotFoundError, KeyError, json.JSONDecodeError):
                pass  # No manifest yet — proceed normally

        if progress_callback:
            progress_callback("initialise", "in-progress")

        registry = ToolRegistry()
        agent = IngestionPipelineAgent(
            config=self.config,
            deal_scope=scope,
            tool_registry=registry,
            llm_callable=self.llm,
        )

        task: dict[str, Any] = {
            "deal_id": deal_id,
            "source_dir": str(deal_path),
            "documents": [str(p) for p in deal_path.glob("*") if p.is_file()],
        }

        if progress_callback:
            progress_callback("ingesting", "in-progress")

        raw = agent._run(task)

        if progress_callback:
            progress_callback("complete", "done")

        elapsed = time.time() - start

        # Normalise raw result to IngestResult
        item_count = raw.get("item_count", raw.get("documents_processed", 0))
        section_count = raw.get("section_count", raw.get("sections_extracted", 0))
        node_count = raw.get("node_count", raw.get("graph_nodes", 0))
        edge_count = raw.get("edge_count", raw.get("graph_edges", 0))

        return IngestResult(
            deal_id=deal_id,
            item_count=item_count,
            section_count=section_count,
            node_count=node_count,
            edge_count=edge_count,
            elapsed_seconds=elapsed,
        )

    # ------------------------------------------------------------------
    # generate
    # ------------------------------------------------------------------

    def generate(
        self,
        deal_id: str,
        output_dir: Optional[Path] = None,
        *,
        max_retries: int = 3,
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> GenerateResult:
        """
        Generate a payment waterfall Python model for a deal.

        Delegates to ``ModelCreationAgent._run()``.
        """
        from backend.abs.deal_scope import DealScope
        from backend.abs.agents.model_creation_agent import ModelCreationAgent
        from backend.agents.agent_tools import ToolRegistry

        start = time.time()
        deal_path = self._resolve_deal_path(deal_id)
        scope = DealScope(deal_id=deal_id, deals_root=deal_path.parent)

        if output_dir is None:
            output_dir = deal_path / "models"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback("generating model", "in-progress")

        registry = ToolRegistry()
        agent = ModelCreationAgent(
            config=self.config,
            deal_scope=scope,
            tool_registry=registry,
            llm_callable=self.llm,
        )

        task: dict[str, Any] = {
            "deal_id": deal_id,
            "deal_path": str(deal_path),
            "output_dir": str(output_dir),
            "max_retries": max_retries,
        }

        raw = agent._run(task)

        if progress_callback:
            progress_callback("complete", "done")

        output_path = Path(raw.get("output_path", str(output_dir / f"{deal_id}_model.py")))
        quality_score = float(raw.get("quality_score", raw.get("score", 0.0)))
        validation_summary = raw.get("validation", raw.get("validation_summary", "ok"))

        return GenerateResult(
            deal_id=deal_id,
            output_path=output_path,
            validation_summary=str(validation_summary),
            quality_score=quality_score,
            elapsed_seconds=time.time() - start,
        )

    # ------------------------------------------------------------------
    # audit
    # ------------------------------------------------------------------

    def audit(
        self,
        deal_id: str,
        model_path: Optional[Path] = None,
        expected_csv: Optional[Path] = None,
        *,
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> AuditResult:
        """
        Audit a generated payment model against deal governing documents.

        Delegates to ``ModelAuditorAgent._run()``.
        """
        from backend.abs.deal_scope import DealScope
        from backend.abs.agents.model_auditor_agent import ModelAuditorAgent
        from backend.agents.agent_tools import ToolRegistry

        start = time.time()
        deal_path = self._resolve_deal_path(deal_id)
        scope = DealScope(deal_id=deal_id, deals_root=deal_path.parent)

        if progress_callback:
            progress_callback("auditing", "in-progress")

        registry = ToolRegistry()
        agent = ModelAuditorAgent(
            config=self.config,
            deal_scope=scope,
            tool_registry=registry,
            llm_callable=self.llm,
        )

        task: dict[str, Any] = {
            "deal_id": deal_id,
            "deal_path": str(deal_path),
            "model_path": str(model_path) if model_path else None,
            "expected_csv": str(expected_csv) if expected_csv else None,
        }

        raw = agent._run(task)

        if progress_callback:
            progress_callback("complete", "done")

        report = raw.get("report", raw.get("audit_report", "Audit complete."))
        confidence = float(raw.get("confidence", raw.get("confidence_score", 0.0)))
        rules_matched = int(raw.get("rules_matched", raw.get("checks_passed", 0)))
        rules_total = int(raw.get("rules_total", raw.get("checks_total", 0)))

        return AuditResult(
            deal_id=deal_id,
            report=str(report),
            confidence=confidence,
            rules_matched=rules_matched,
            rules_total=rules_total,
            elapsed_seconds=time.time() - start,
        )

    # ------------------------------------------------------------------
    # qa
    # ------------------------------------------------------------------

    def qa(
        self,
        deal_id: str,
        query: str,
        *,
        max_results: int = 10,
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> QAResult:
        """
        Answer a natural-language question about a deal.

        Delegates to ``QAAgent._run()``.
        """
        from backend.abs.deal_scope import DealScope
        from backend.abs.agents.qa_agent import QAAgent
        from backend.agents.agent_tools import ToolRegistry

        start = time.time()
        deal_path = self._resolve_deal_path(deal_id)
        scope = DealScope(deal_id=deal_id, deals_root=deal_path.parent)

        if progress_callback:
            progress_callback("searching", "in-progress")

        registry = ToolRegistry()
        agent = QAAgent(
            config=self.config,
            deal_scope=scope,
            tool_registry=registry,
            llm_callable=self.llm,
        )

        task: dict[str, Any] = {
            "deal_id": deal_id,
            "deal_path": str(deal_path),
            "question": query,
            "max_results": max_results,
        }

        raw = agent._run(task)

        if progress_callback:
            progress_callback("complete", "done")

        answer = raw.get("answer", raw.get("response", "No answer found."))
        sources = raw.get("sources", raw.get("citations", []))
        confidence = float(raw.get("confidence", raw.get("confidence_score", 0.0)))
        follow_ups = raw.get("follow_ups", raw.get("follow_up_questions", []))

        return QAResult(
            deal_id=deal_id,
            answer=str(answer),
            sources=list(sources),
            confidence=confidence,
            follow_ups=list(follow_ups),
            elapsed_seconds=time.time() - start,
        )

    # ------------------------------------------------------------------
    # status
    # ------------------------------------------------------------------

    def status(
        self,
        deal_id: Optional[str] = None,
    ) -> StatusResult:
        """
        Return processing status for one deal or all deals.

        Reads DealManifest files from the deals directory.
        """
        from backend.abs.deal_manifest import DealManifest

        deals_root = Path(self.config.abs_deals_root) if hasattr(self.config, "abs_deals_root") else Path("deals")

        deals: list[dict] = []

        if deal_id:
            # Single deal
            candidates = [
                deals_root / deal_id,
                Path(deal_id),
            ]
            deal_path = next((p for p in candidates if p.exists()), None)
            if deal_path is None:
                return StatusResult(
                    status_report=f"Deal '{deal_id}' not found.\nSearched: {[str(p) for p in candidates]}\n",
                    deals=[],
                )
            deals = [self._summarise_deal(deal_path, deal_id)]
        else:
            # All deals
            if deals_root.exists():
                for p in sorted(deals_root.iterdir()):
                    if p.is_dir() and not p.name.startswith("."):
                        deals.append(self._summarise_deal(p, p.name))

        if not deals:
            return StatusResult(
                status_report="No deals found.\nRun: kts abs ingest --deal-id <id> --source-dir <path>\n",
                deals=[],
            )

        # Build markdown report
        lines: list[str] = ["## ABS Deal Status\n"]
        lines.append(f"{'Deal ID':<30} {'Documents':>10} {'Ready':>8} {'Status':<20}")
        lines.append("-" * 75)
        for d in deals:
            lines.append(
                f"{d['deal_id']:<30} {d['document_count']:>10} "
                f"{str(d['ready']):>8} {d['status']:<20}"
            )

        return StatusResult(status_report="\n".join(lines) + "\n", deals=deals)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_deal_path(self, deal_id: str) -> Path:
        """Find deals directory on disk, falling back to CWD."""
        deals_root = Path(self.config.abs_deals_root) if hasattr(self.config, "abs_deals_root") else Path("deals")
        candidate = deals_root / deal_id
        if candidate.exists():
            return candidate
        # Fallback: path-as-given (for absolute paths or custom dirs)
        return Path(deal_id)

    def _summarise_deal(self, deal_path: Path, deal_id: str) -> dict:
        """Return a status summary dict for one deal."""
        from backend.abs.deal_manifest import DealManifest

        try:
            manifest = DealManifest.load(deal_path)
            doc_count = len(manifest.list_documents())
            ready = manifest.is_ready_for_model_generation()
            errors = manifest.validate()
            status = "ready" if ready else ("errors" if errors else "incomplete")
        except (FileNotFoundError, KeyError, json.JSONDecodeError):
            doc_count = 0
            ready = False
            status = "not-ingested"

        return {
            "deal_id": deal_id,
            "deal_path": str(deal_path),
            "document_count": doc_count,
            "ready": ready,
            "status": status,
        }
