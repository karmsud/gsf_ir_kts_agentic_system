"""Phase 6 configuration — feature flags & tuning knobs.

Centralises all Phase 6 parameters so that ``config/settings.py`` only
needs a thin ``phase6_*`` shim layer.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_bool(key: str, default: bool) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in {"true", "1", "yes"}


def _env_float(key: str, default: float) -> float:
    val = os.environ.get(key)
    if val is None:
        return default
    return float(val)


def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    if val is None:
        return default
    return int(val)


@dataclass
class Phase6Config:
    """All Phase 6 parameters with sane defaults."""

    # ── Master toggle (Phase 6 is now ALWAYS on) ───────────────────
    enabled: bool = field(default_factory=lambda: _env_bool("KTS_PHASE6_ENABLED", True))

    # ── Dual vector store ─────────────────────────────────────────
    chroma_dir: str = field(
        default_factory=lambda: os.environ.get("KTS_PHASE6_CHROMA_DIR", ".kts/vectors/phase6")
    )

    # ── Iterative retrieval ───────────────────────────────────────
    max_iterations: int = field(default_factory=lambda: _env_int("KTS_PHASE6_MAX_ITERATIONS", 5))
    min_confidence: float = field(default_factory=lambda: _env_float("KTS_PHASE6_MIN_CONFIDENCE", 0.85))
    min_improvement: float = field(default_factory=lambda: _env_float("KTS_PHASE6_MIN_IMPROVEMENT", 0.03))
    result_threshold: float = field(default_factory=lambda: _env_float("KTS_PHASE6_RESULT_THRESHOLD", 0.70))

    # ── Hybrid scoring weights ────────────────────────────────────
    content_weight: float = field(default_factory=lambda: _env_float("KTS_PHASE6_CONTENT_WEIGHT", 0.6))
    pagerank_weight: float = field(default_factory=lambda: _env_float("KTS_PHASE6_PAGERANK_WEIGHT", 0.2))
    graph_proximity_weight: float = field(
        default_factory=lambda: _env_float("KTS_PHASE6_GRAPH_PROXIMITY_WEIGHT", 0.2)
    )

    # ── PageRank ──────────────────────────────────────────────────
    pagerank_alpha: float = field(default_factory=lambda: _env_float("KTS_PHASE6_PAGERANK_ALPHA", 0.85))

    # ── Graph expansion ───────────────────────────────────────────
    bfs_depth_limit: int = field(default_factory=lambda: _env_int("KTS_PHASE6_BFS_DEPTH", 2))

    # ── Logging verbosity ─────────────────────────────────────────
    verbose_logging: bool = field(default_factory=lambda: _env_bool("KTS_PHASE6_VERBOSE", True))


def load_phase6_config() -> Phase6Config:
    """Construct a ``Phase6Config`` populated from environment variables."""
    return Phase6Config()
