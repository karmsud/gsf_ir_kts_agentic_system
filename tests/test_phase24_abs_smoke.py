"""
Phase 24 ABS Smoke Tests
========================
Fast, dependency-free unit tests covering the core ABS subsystem:
  - DealScope (directory isolation + path enforcement)
  - DealManifest (JSON round-trip)
  - LLM Bridge (factory modes + usage stats)
  - ABS Agents (instantiation + configuration)
  - Config flags (regression: abs_deals_root, abs_llm_mode)

All tests run without a real knowledge base, vector store, or LLM.
Average runtime target: < 5 seconds total.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ── Lazy imports so collection never fails even inside CI ─────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# Helper fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def deals_root(tmp_path: Path) -> Path:
    """Return an empty deals/ root under tmp_path."""
    d = tmp_path / "deals"
    d.mkdir()
    return d


@pytest.fixture()
def deal_scope(deals_root: Path):
    """A writable DealScope for `test_deal_2024_he1`."""
    from backend.abs.deal_scope import DealScope
    return DealScope.create("test_deal_2024_he1", deals_root)


@pytest.fixture()
def kts_config():
    """Minimal KTSConfig suitable for ABS agents."""
    from config import load_config
    return load_config()


@pytest.fixture()
def tool_registry():
    from backend.agents.agent_tools import ToolRegistry
    return ToolRegistry()


# ─────────────────────────────────────────────────────────────────────────────
# DealScope tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.abs_smoke
def test_deal_scope_create_creates_dirs(deal_scope, deals_root: Path):
    """DealScope.create() must create the deal directory structure."""
    deal_path = deals_root / "test_deal_2024_he1"
    assert deal_path.exists(), "Deal root directory should be created"
    # Check a representative subset of REQUIRED_SUBDIRS
    for subdir in ("data", "vectorstore", "graph", "runs", "logs"):
        assert (deal_path / subdir).exists(), f"Expected subdir '{subdir}' to exist"


@pytest.mark.abs_smoke
def test_deal_scope_resolve_within_boundary(deal_scope, deals_root: Path):
    """DealScope.resolve() returns an absolute path inside the deal folder."""
    from backend.abs.deal_scope import DealScope
    resolved = deal_scope.resolve("data/cashflows.csv")
    expected_prefix = deals_root / "test_deal_2024_he1"
    # resolved must be a descendant of the deal folder
    assert str(resolved).startswith(str(expected_prefix))


@pytest.mark.abs_smoke
def test_deal_scope_resolve_escape_raises(deal_scope):
    """DealScope.resolve() must raise DealScopingViolation on path escape."""
    from backend.abs.deal_scope import DealScopingViolation
    with pytest.raises(DealScopingViolation):
        deal_scope.resolve("../../other_deal/secret.txt")


@pytest.mark.abs_smoke
def test_deal_scope_vector_collection_name(deals_root: Path):
    """get_vector_collection() sanitizes the deal ID for Chroma."""
    from backend.abs.deal_scope import DealScope
    scope = DealScope.create("Bear-Stearns 2006 HE1", deals_root)
    collection = scope.get_vector_collection()
    assert " " not in collection
    assert "-" not in collection


@pytest.mark.abs_smoke
def test_deal_scope_equality(deals_root: Path):
    """Two DealScope objects with same id and root are equal."""
    from backend.abs.deal_scope import DealScope
    a = DealScope.create("deal_a_2024_x1", deals_root)
    b = DealScope("deal_a_2024_x1", deals_root, read_only=True)
    assert a == b
    assert a != DealScope.create("deal_b_2024_x2", deals_root)


@pytest.mark.abs_smoke
def test_deal_scope_repr(deal_scope):
    """DealScope repr includes deal_id and RW/RO mode."""
    r = repr(deal_scope)
    assert "test_deal_2024_he1" in r
    assert "RW" in r


# ─────────────────────────────────────────────────────────────────────────────
# DealManifest tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.abs_smoke
def test_deal_manifest_save_and_load_roundtrip(deal_scope):
    """DealManifest.save() + .load() preserves all fields."""
    from backend.abs.deal_manifest import DealManifest

    manifest = DealManifest(
        deal_id="test_deal_2024_he1",
        deal_name="Test Deal 2024 HE1",
        issuer="Test Issuer Inc.",
        series="2024-HE1",
        shelf="TDI",
        closing_date="2024-01-15",
    )
    manifest.save(deal_scope.deal_path)

    loaded = DealManifest.load(deal_scope.deal_path)
    assert loaded.deal_id == "test_deal_2024_he1"
    assert loaded.issuer == "Test Issuer Inc."
    assert loaded.series == "2024-HE1"
    assert loaded.closing_date == "2024-01-15"


@pytest.mark.abs_smoke
def test_deal_manifest_load_missing_raises(deals_root: Path):
    """DealManifest.load() raises FileNotFoundError for a missing manifest."""
    from backend.abs.deal_manifest import DealManifest
    with pytest.raises(FileNotFoundError):
        DealManifest.load(deals_root / "nonexistent_deal")


# ─────────────────────────────────────────────────────────────────────────────
# LLM Bridge tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.abs_smoke
def test_llm_bridge_none_mode_returns_none():
    """create_llm_callable('none') must return None."""
    from backend.abs.llm_bridge import create_llm_callable
    result = create_llm_callable(mode="none")
    assert result is None


@pytest.mark.abs_smoke
def test_llm_bridge_mock_mode_returns_callable():
    """create_llm_callable('mock') must return a callable."""
    from backend.abs.llm_bridge import create_llm_callable
    fn = create_llm_callable(mode="mock")
    assert callable(fn), "Mock mode should return a callable"


@pytest.mark.abs_smoke
def test_llm_bridge_mock_callable_produces_string():
    """Mock callable should return a non-empty string."""
    from backend.abs.llm_bridge import create_llm_callable
    fn = create_llm_callable(mode="mock")
    result = fn("What is the waterfall order?", None)
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.abs_smoke
def test_llm_usage_stats_record_and_avg():
    """LLMUsageStats.record() updates totals and avg_latency works."""
    from backend.abs.llm_bridge import LLMUsageStats
    stats = LLMUsageStats()
    stats.record(input_tokens=100, output_tokens=50, latency_ms=200.0)
    stats.record(input_tokens=200, output_tokens=80, latency_ms=400.0)
    assert stats.total_calls == 2
    assert stats.total_input_tokens == 300
    assert stats.avg_latency_ms() == pytest.approx(300.0)


# ─────────────────────────────────────────────────────────────────────────────
# Agent instantiation smoke tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.abs_smoke
def test_ingestion_pipeline_agent_instantiates(kts_config, deal_scope, tool_registry):
    """IngestionPipelineAgent must instantiate without errors."""
    from backend.abs.agents.ingestion_pipeline_agent import IngestionPipelineAgent
    agent = IngestionPipelineAgent(
        config=kts_config,
        deal_scope=deal_scope,
        tool_registry=tool_registry,
        llm_callable=None,
    )
    assert agent.agent_name == "ingestion_pipeline"
    # Mission string should be non-empty
    assert len(agent._get_mission()) > 10


@pytest.mark.abs_smoke
def test_model_creation_agent_instantiates(kts_config, deal_scope, tool_registry):
    """ModelCreationAgent must instantiate without errors."""
    from backend.abs.agents.model_creation_agent import ModelCreationAgent
    agent = ModelCreationAgent(
        config=kts_config,
        deal_scope=deal_scope,
        tool_registry=tool_registry,
        llm_callable=None,
    )
    assert agent.agent_name == "model_creation"


@pytest.mark.abs_smoke
def test_model_auditor_agent_handles_missing_model(kts_config, deal_scope, tool_registry):
    """ModelAuditorAgent._run() returns a fail result (not crash) when
    no payment_model.py exists yet."""
    from backend.abs.agents.model_auditor_agent import ModelAuditorAgent
    agent = ModelAuditorAgent(
        config=kts_config,
        deal_scope=deal_scope,
        tool_registry=tool_registry,
        llm_callable=None,
    )
    # Call _run() directly to bypass the quality-gate retry loop
    result = agent._run({})
    assert result.get("audit_result") == "fail"
    assert any("not found" in issue.lower() for issue in result.get("issues", []))


@pytest.mark.abs_smoke
def test_model_auditor_agent_passes_valid_model(kts_config, deal_scope, tool_registry):
    """ModelAuditorAgent._run() reports syntax_valid=True for a valid model."""
    from backend.abs.agents.model_auditor_agent import ModelAuditorAgent

    # Write a minimal valid payment model
    model_dir = deal_scope.deal_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_file = model_dir / "payment_model.py"
    model_file.write_text(
        '"""Minimal test model."""\n'
        "def run(data_path, month):\n"
        '    """Run payment model."""\n'
        "    return 'class_a,42.0\\n'\n",
        encoding="utf-8",
    )

    agent = ModelAuditorAgent(
        config=kts_config,
        deal_scope=deal_scope,
        tool_registry=tool_registry,
        llm_callable=None,
    )
    # Call _run() directly to bypass the quality-gate retry loop
    result = agent._run({})
    # Syntax check must pass even if other checks fail
    syntax_check = next(
        (c for c in result.get("checks", []) if c["name"] == "syntax_valid"),
        None,
    )
    assert syntax_check is not None, "syntax_valid check not found in result"
    assert syntax_check["passed"] is True


@pytest.mark.abs_smoke
def test_qa_agent_extract_questions_dict(kts_config, deal_scope, tool_registry):
    """QAAgent._extract_questions must handle question/questions keys."""
    from backend.abs.agents.qa_agent import QAAgent
    agent = QAAgent(
        config=kts_config,
        deal_scope=deal_scope,
        tool_registry=tool_registry,
        llm_callable=None,
    )
    assert agent._extract_questions({"question": "What is the cut-off date?"}) == [
        "What is the cut-off date?"
    ]
    assert agent._extract_questions({"questions": ["A?", "B?"]}) == ["A?", "B?"]
    # No question key — default fallback
    default = agent._extract_questions({})
    assert isinstance(default, list)
    assert len(default) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Config flags regression tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.abs_smoke
def test_config_abs_llm_mode_default_is_vscode(kts_config):
    """abs_llm_mode should default to 'vscode', not 'none'."""
    assert kts_config.abs_llm_mode == "vscode", (
        "abs_llm_mode default changed — update config/settings.py"
    )


@pytest.mark.abs_smoke
def test_config_abs_deals_root_exists(kts_config):
    """KTSConfig must expose abs_deals_root (not the old abs_data_dir)."""
    assert hasattr(kts_config, "abs_deals_root"), (
        "abs_deals_root field missing from KTSConfig"
    )


@pytest.mark.abs_smoke
def test_config_no_abs_data_dir_alias(kts_config):
    """abs_data_dir must NOT exist on KTSConfig (regression for naming bug)."""
    assert not hasattr(kts_config, "abs_data_dir"), (
        "abs_data_dir still present on KTSConfig — remove it to avoid "
        "the orchestrator naming bug from Phase 22"
    )
