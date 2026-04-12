"""
Phase 6 — Config & Explainability tests.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.common.config_phase6 import Phase6Config, load_phase6_config
from backend.common.explainability import ExplainabilityLogger


# ── Phase6Config ─────────────────────────────────────────────────

class TestPhase6Config:
    def test_defaults(self):
        cfg = Phase6Config()
        # Phase 6 is now ALWAYS enabled by default
        assert cfg.enabled is True
        assert cfg.max_iterations == 5
        assert cfg.min_confidence == 0.85
        assert 0 < cfg.content_weight <= 1.0
        assert 0 < cfg.pagerank_weight <= 1.0

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("KTS_PHASE6_ENABLED", "true")
        monkeypatch.setenv("KTS_PHASE6_MAX_ITERATIONS", "5")
        monkeypatch.setenv("KTS_PHASE6_MIN_CONFIDENCE", "0.9")
        cfg = load_phase6_config()
        assert cfg.enabled is True
        assert cfg.max_iterations == 5
        assert cfg.min_confidence == 0.9

    def test_alpha_range(self):
        cfg = Phase6Config()
        assert 0 < cfg.pagerank_alpha < 1.0

    def test_weights_sum_to_one(self):
        cfg = Phase6Config()
        total = cfg.content_weight + cfg.pagerank_weight + cfg.graph_proximity_weight
        assert abs(total - 1.0) < 0.01


# ── KTSConfig Phase 6 fields ────────────────────────────────────

class TestKTSConfigPhase6:
    def test_phase6_fields_exist(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert hasattr(cfg, "phase6_enabled")
        assert hasattr(cfg, "phase6_chroma_dir")
        assert hasattr(cfg, "phase6_max_iterations")
        assert hasattr(cfg, "phase6_min_confidence")
        assert hasattr(cfg, "phase6_content_weight")
        assert hasattr(cfg, "phase6_pagerank_weight")
        assert hasattr(cfg, "phase6_verbose_logging")

    def test_phase6_defaults(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        # Phase 6 is now ALWAYS enabled by default
        assert cfg.phase6_enabled is True
        assert cfg.phase6_max_iterations == 10
        assert cfg.phase6_min_confidence == 0.85

    def test_load_config_with_phase6(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KTS_PHASE6_ENABLED", "true")
        monkeypatch.setenv("KTS_KB_PATH", str(tmp_path))
        from config.settings import load_config
        cfg = load_config(tmp_path)
        assert cfg.phase6_enabled is True


# ── ExplainabilityLogger ─────────────────────────────────────────

class TestExplainabilityLogger:
    def test_basic_logging(self):
        xlog = ExplainabilityLogger("test", doc_id="doc1", verbose=False)
        xlog.step("step1", "First step", detail={"count": 42})
        xlog.step("step2", "Second step", why="needed for accuracy")
        trace = xlog.done(summary={"total": 2})
        assert trace["pipeline"] == "test"
        assert trace["doc_id"] == "doc1"
        assert len(trace["steps"]) == 2
        assert trace["summary"]["total"] == 2
        assert trace["total_ms"] >= 0  # timing may round to 0 on fast machines

    def test_step_timing(self):
        import time
        xlog = ExplainabilityLogger("test", verbose=False)
        time.sleep(0.01)
        xlog.step("slow_step", "Takes some time")
        trace = xlog.done()
        assert trace["steps"][0]["elapsed_ms"] > 5  # at least 5ms

    def test_warn(self):
        xlog = ExplainabilityLogger("test", verbose=False)
        xlog.warn("parse", "Could not parse section 5")
        trace = xlog.done()
        assert any("warning" in s for s in trace["steps"])

    def test_save_trace(self, tmp_path):
        xlog = ExplainabilityLogger("test", doc_id="doc1", verbose=False)
        xlog.step("s1", "step one")
        log_path = xlog.save_trace(str(tmp_path / "logs"))
        assert log_path.exists()
        content = log_path.read_text()
        data = json.loads(content.strip())
        assert data["pipeline"] == "test"
