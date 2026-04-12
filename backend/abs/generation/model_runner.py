"""
Model runner for the ABS Waterfall AI pipeline.

Executes a payment model module against prepared monthly data,
captures outputs, and persists run metadata.

Ported from PayGen pipeline.generation.model_runner → backend.abs.generation
"""

from __future__ import annotations

import importlib.util
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

from backend.abs.skills.document_hasher import compute_text_hash

logger = logging.getLogger(__name__)


# ── Data Classes ─────────────────────────────────────────────────────────

@dataclass
class RunResult:
    """Outcome of a single monthly model run."""

    month: int
    output_path: Path
    run_metadata: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "month": self.month,
            "output_path": str(self.output_path),
            "run_metadata": self.run_metadata,
            "success": self.success,
            "error": self.error,
        }


# ── Helpers ──────────────────────────────────────────────────────────────

def _load_model_module(model_path: Path) -> ModuleType:
    """Dynamically import a payment model Python file."""
    model_path = Path(model_path)
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    spec = importlib.util.spec_from_file_location("payment_model", model_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create module spec for {model_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _hash_file(path: Path) -> str:
    """Return SHA-256 hex digest of a file's text content."""
    return compute_text_hash(path.read_text(encoding="utf-8"))


# ── Single-Month Run ────────────────────────────────────────────────────

def run_model_for_month(
    model_path: Path,
    data_path: Path,
    month: int,
    output_dir: Path,
) -> RunResult:
    """Execute the payment model for a single month.

    The model module must expose a ``run(data_path, month)`` callable
    that returns a CSV-formatted string of results.

    Outputs are saved to ``<output_dir>/runs/month_<N>/output.csv``.
    """
    model_path = Path(model_path)
    data_path = Path(data_path)
    output_dir = Path(output_dir)

    month_dir = output_dir / f"runs/month_{month}"
    month_dir.mkdir(parents=True, exist_ok=True)
    output_csv = month_dir / "output.csv"

    try:
        module = _load_model_module(model_path)
        result_csv: str = module.run(data_path, month)  # type: ignore[attr-defined]
        output_csv.write_text(result_csv, encoding="utf-8")

        metadata = {
            "month": month,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model_hash": _hash_file(model_path),
            "input_hash": _hash_file(data_path) if data_path.is_file() else "",
            "output_hash": compute_text_hash(result_csv),
            "output_path": str(output_csv),
        }
        meta_path = month_dir / "run_metadata.json"
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        logger.info("Month %d completed — output at %s", month, output_csv)
        return RunResult(
            month=month,
            output_path=output_csv,
            run_metadata=metadata,
            success=True,
        )

    except Exception as exc:
        logger.error("Month %d failed: %s", month, exc)
        return RunResult(
            month=month,
            output_path=output_csv,
            run_metadata={},
            success=False,
            error=str(exc),
        )


# ── Multi-Month Sequence ────────────────────────────────────────────────

def run_model_sequence(
    model_path: Path,
    data_root: Path,
    months: list[int],
    output_dir: Path,
) -> list[RunResult]:
    """Run the model sequentially for each month in *months*.

    Each month's output is written before the next month begins,
    so month N can reference month N-1's results.
    """
    results: list[RunResult] = []
    for month in months:
        result = run_model_for_month(model_path, data_root, month, output_dir)
        results.append(result)
        if not result.success:
            logger.warning("Stopping sequence at month %d due to failure", month)
            break
    return results
