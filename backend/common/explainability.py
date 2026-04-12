"""
AI Explainability Logger for Phase 6.

Provides structured, human-readable logging for all ingestion and
retrieval steps so that operators can understand *what* the system is
doing and *why* at every stage.

Output appears in the VS Code Output channel ("KTS Backend") and can
also be written to a JSON-lines file for audit.

Usage::

    from backend.common.explainability import ExplainabilityLogger

    xlog = ExplainabilityLogger("ingestion")
    xlog.step("convert", "Converting PDF using PyMuPDF", detail={"pages": 12})
    xlog.step("classify", "Regime classified as GOVERNING_DOC_LEGAL", detail={"score": 87})
    xlog.done(summary={"total_chunks": 34, "items": 120})
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("kts.explainability")


class ExplainabilityLogger:
    """
    Structured step-by-step logger for AI explainability.

    Each step records:
    - step_name: short identifier (e.g. "convert", "classify")
    - description: human-readable explanation of what is happening and why
    - detail: optional dict with metrics / parameters
    - elapsed_ms: time since last step
    """

    def __init__(self, pipeline: str, *, doc_id: str = "", verbose: bool = True) -> None:
        self.pipeline = pipeline
        self.doc_id = doc_id
        self.verbose = verbose
        self._steps: List[Dict[str, Any]] = []
        self._start = time.perf_counter()
        self._last = self._start

        if verbose:
            logger.info(
                "━━━ [%s] Pipeline started %s━━━",
                pipeline.upper(),
                f"(doc_id={doc_id}) " if doc_id else "",
            )

    def step(
        self,
        step_name: str,
        description: str,
        *,
        detail: Optional[Dict[str, Any]] = None,
        why: str = "",
    ) -> None:
        """Log a pipeline step."""
        now = time.perf_counter()
        elapsed_ms = (now - self._last) * 1000
        self._last = now

        entry = {
            "step": step_name,
            "description": description,
            "why": why,
            "detail": detail or {},
            "elapsed_ms": round(elapsed_ms, 1),
        }
        self._steps.append(entry)

        if self.verbose:
            detail_str = ""
            if detail:
                detail_str = " | " + ", ".join(f"{k}={v}" for k, v in detail.items())
            why_str = f" — WHY: {why}" if why else ""
            logger.info(
                "  [%s] %s: %s%s%s (%.0fms)",
                self.pipeline,
                step_name,
                description,
                detail_str,
                why_str,
                elapsed_ms,
            )

    def warn(self, step_name: str, message: str) -> None:
        """Log a warning during pipeline execution."""
        logger.warning("  [%s] ⚠ %s: %s", self.pipeline, step_name, message)
        self._steps.append({"step": step_name, "warning": message})

    def done(self, *, summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Mark pipeline complete and return full trace.

        Returns a dict suitable for JSON serialization.
        """
        total_ms = (time.perf_counter() - self._start) * 1000

        trace = {
            "pipeline": self.pipeline,
            "doc_id": self.doc_id,
            "steps": self._steps,
            "total_ms": round(total_ms, 1),
            "summary": summary or {},
        }

        if self.verbose:
            summary_str = ""
            if summary:
                summary_str = " — " + ", ".join(f"{k}={v}" for k, v in summary.items())
            logger.info(
                "━━━ [%s] Pipeline complete in %.0fms%s ━━━",
                self.pipeline.upper(),
                total_ms,
                summary_str,
            )

        return trace

    def save_trace(self, log_dir: str | Path) -> Path:
        """Append the current trace to a JSONL audit log."""
        log_path = Path(log_dir) / "explainability.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        trace = self.done()
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(trace) + "\n")
        return log_path
