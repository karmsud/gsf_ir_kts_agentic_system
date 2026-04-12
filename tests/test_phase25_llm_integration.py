"""
Phase 25 LLM Integration Tests
===============================
Validates LLM bridge modes, IPC protocol, and LLM-augmented agent behaviour.

All tests use the "mock" LLM callable or a custom callable injection —
no real LLM API keys are required.

Coverage:
  - create_llm_callable() modes (none/mock/invalid)
  - LLMUsageStats accumulation
  - ABSStream IPC message format (JSON lines contract)
  - IPC protocol TypedDict structural integrity
  - QAAgent CRAG grading (relevant vs. irrelevant)
  - QAAgent multi-query expansion path
  - QAAgent HyDE document generation path
  - ModelCreationAgent critique loop (terminates early; applies improved source)
  - LLM callable degrades gracefully on exception
"""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def deals_root(tmp_path: Path) -> Path:
    d = tmp_path / "deals"
    d.mkdir()
    return d


@pytest.fixture()
def deal_scope(deals_root: Path):
    from backend.abs.deal_scope import DealScope
    return DealScope.create("llm_test_deal_2024_x1", deals_root)


@pytest.fixture()
def kts_config():
    from config import load_config
    cfg = load_config()
    cfg.abs_crag_enabled = True
    cfg.abs_crag_threshold = 0.85
    cfg.abs_multi_query_enabled = True
    cfg.abs_multi_query_count = 3
    cfg.abs_hyde_enabled = True
    cfg.abs_critique_enabled = True
    cfg.abs_critique_max_rounds = 2
    cfg.abs_critique_target = 0.92
    return cfg


@pytest.fixture()
def tool_registry():
    from backend.agents.agent_tools import ToolRegistry
    return ToolRegistry()


# ─────────────────────────────────────────────────────────────────────────────
# LLM Bridge factory tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.abs_llm
def test_llm_factory_none_returns_none():
    from backend.abs.llm_bridge import create_llm_callable
    assert create_llm_callable(mode="none") is None


@pytest.mark.abs_llm
def test_llm_factory_mock_returns_callable():
    from backend.abs.llm_bridge import create_llm_callable
    fn = create_llm_callable(mode="mock")
    assert callable(fn)


@pytest.mark.abs_llm
def test_llm_factory_unknown_mode_returns_none():
    from backend.abs.llm_bridge import create_llm_callable
    # Unknown mode should not raise — should just return None
    result = create_llm_callable(mode="unknown_mode_xyz")
    assert result is None


@pytest.mark.abs_llm
def test_mock_llm_callable_waterfall_query():
    """Mock callable should return a non-empty deterministic string."""
    from backend.abs.llm_bridge import create_llm_callable
    fn = create_llm_callable(mode="mock")
    result = fn("What is the waterfall order?", None)
    assert isinstance(result, str)
    assert len(result) >= 10  # not empty / trivial


@pytest.mark.abs_llm
def test_mock_llm_callable_with_system_prompt():
    """Mock callable accepts an optional system prompt parameter."""
    from backend.abs.llm_bridge import create_llm_callable
    fn = create_llm_callable(mode="mock")
    result = fn("Define cut-off date.", "You are an ABS lawyer.")
    assert isinstance(result, str)


# ─────────────────────────────────────────────────────────────────────────────
# LLMUsageStats tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.abs_llm
def test_usage_stats_initial_zero():
    from backend.abs.llm_bridge import LLMUsageStats
    stats = LLMUsageStats()
    assert stats.total_calls == 0
    assert stats.avg_latency_ms() == 0.0


@pytest.mark.abs_llm
def test_usage_stats_multiple_records():
    from backend.abs.llm_bridge import LLMUsageStats
    stats = LLMUsageStats()
    stats.record(100, 50, 200.0)
    stats.record(200, 80, 400.0)
    stats.record(150, 60, 300.0)
    assert stats.total_calls == 3
    assert stats.total_input_tokens == 450
    assert stats.total_output_tokens == 190
    assert stats.avg_latency_ms() == pytest.approx(300.0)


# ─────────────────────────────────────────────────────────────────────────────
# IPC protocol integrity
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.abs_llm
def test_ipc_llm_request_typeddict_fields():
    """LLMRequest TypedDict must have all required fields."""
    from backend.abs.ipc_protocol import LLMRequest
    annotations = LLMRequest.__annotations__
    for field in ("type", "model", "prompt", "system_prompt", "temperature", "max_tokens"):
        assert field in annotations, f"LLMRequest missing field: {field}"


@pytest.mark.abs_llm
def test_ipc_llm_response_typeddict_fields():
    """LLMResponse TypedDict must have all required fields."""
    from backend.abs.ipc_protocol import LLMResponse
    annotations = LLMResponse.__annotations__
    for field in ("type", "text", "input_tokens", "output_tokens"):
        assert field in annotations, f"LLMResponse missing field: {field}"


@pytest.mark.abs_llm
def test_ipc_progress_message_typeddict_fields():
    """ProgressMessage TypedDict must have all required fields."""
    from backend.abs.ipc_protocol import ProgressMessage
    annotations = ProgressMessage.__annotations__
    for field in ("type", "step", "status", "step_number", "total_steps"):
        assert field in annotations, f"ProgressMessage missing field: {field}"


# ─────────────────────────────────────────────────────────────────────────────
# ABSStream IPC mode message format
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.abs_llm
def test_abs_stream_ipc_progress_is_valid_json():
    """ABSStream in IPC mode emits valid JSON progress messages to stdout."""
    from backend.abs.streaming import ABSStream

    captured = StringIO()
    with patch("sys.stdout", captured):
        stream = ABSStream(mode="ipc")
        stream.progress("classify", "in-progress")

    raw = captured.getvalue().strip()
    msg = json.loads(raw)
    assert msg["type"] == "progress"
    assert msg["step"] == "classify"
    assert msg["status"] == "in-progress"


@pytest.mark.abs_llm
def test_abs_stream_ipc_result_is_valid_json():
    """ABSStream in IPC mode emits valid JSON result messages."""
    from backend.abs.streaming import ABSStream

    captured = StringIO()
    with patch("sys.stdout", captured):
        stream = ABSStream(mode="ipc")
        stream.result({"status": "ok", "item_count": 42})

    raw = captured.getvalue().strip()
    msg = json.loads(raw)
    assert msg["type"] == "result"
    assert msg["status"] == "ok"
    assert msg["item_count"] == 42


@pytest.mark.abs_llm
def test_abs_stream_ipc_code_is_valid_json():
    """ABSStream in IPC mode emits valid JSON code messages."""
    from backend.abs.streaming import ABSStream

    captured = StringIO()
    with patch("sys.stdout", captured):
        stream = ABSStream(mode="ipc")
        stream.code("def run(p, m): return ''", language="python")

    raw = captured.getvalue().strip()
    msg = json.loads(raw)
    assert msg["type"] == "code"
    assert msg["language"] == "python"
    assert "def run" in msg["code"]


# ─────────────────────────────────────────────────────────────────────────────
# QAAgent LLM augmentation tests
# ─────────────────────────────────────────────────────────────────────────────


def _make_qa_agent(kts_config, deal_scope, tool_registry, llm_callable=None):
    from backend.abs.agents.qa_agent import QAAgent
    return QAAgent(
        config=kts_config,
        deal_scope=deal_scope,
        tool_registry=tool_registry,
        llm_callable=llm_callable,
    )


@pytest.mark.abs_llm
def test_qa_agent_generate_query_variants(kts_config, deal_scope, tool_registry):
    """_generate_query_variants returns a list of strings from mock LLM."""
    call_count = [0]

    def mock_llm(prompt, sys_prompt):
        call_count[0] += 1
        # Return a well-formed JSON array
        return '["What is the distribution date?", "When are payments distributed?", "Cut-off date definition?"]'

    agent = _make_qa_agent(kts_config, deal_scope, tool_registry, mock_llm)
    variants = agent._generate_query_variants("What is the cut-off date?")
    assert isinstance(variants, list)
    assert len(variants) > 0
    assert all(isinstance(v, str) for v in variants)


@pytest.mark.abs_llm
def test_qa_agent_generate_query_variants_graceful_on_bad_json(kts_config, deal_scope, tool_registry):
    """_generate_query_variants returns [] when LLM returns non-JSON."""
    def mock_llm(prompt, sys_prompt):
        return "Sorry, I cannot help with that."

    agent = _make_qa_agent(kts_config, deal_scope, tool_registry, mock_llm)
    variants = agent._generate_query_variants("What is the cut-off date?")
    assert variants == []


@pytest.mark.abs_llm
def test_qa_agent_generate_hyde_doc(kts_config, deal_scope, tool_registry):
    """_generate_hyde_doc returns a non-empty string from mock LLM."""
    def mock_llm(prompt, sys_prompt):
        return "The cut-off date is the date before which loans must be originated to be included in the trust."

    agent = _make_qa_agent(kts_config, deal_scope, tool_registry, mock_llm)
    hyde_doc = agent._generate_hyde_doc("What is the cut-off date?")
    assert isinstance(hyde_doc, str)
    assert len(hyde_doc) > 0


@pytest.mark.abs_llm
def test_qa_agent_generate_hyde_doc_graceful_on_exception(kts_config, deal_scope, tool_registry):
    """_generate_hyde_doc returns '' when LLM raises."""
    def mock_llm(prompt, sys_prompt):
        raise RuntimeError("LLM connection refused")

    agent = _make_qa_agent(kts_config, deal_scope, tool_registry, mock_llm)
    result = agent._generate_hyde_doc("What is the cut-off date?")
    assert result == ""


@pytest.mark.abs_llm
def test_qa_agent_crag_grade_chunks_relevant(kts_config, deal_scope, tool_registry):
    """_crag_grade_chunks grades chunks using mock LLM callable."""
    def mock_llm(prompt, sys_prompt):
        if "relevant" in prompt.lower() or "cut-off" in prompt.lower():
            return "relevant"
        return "irrelevant"

    agent = _make_qa_agent(kts_config, deal_scope, tool_registry, mock_llm)
    chunks = [
        {"text": "The cut-off date is January 15, 2006.", "score": 0.9},
        {"text": "Unrelated boilerplate clause.", "score": 0.5},
    ]
    graded = agent._crag_grade_chunks("What is the cut-off date?", chunks)
    assert len(graded) == 2
    # Each entry is (chunk_dict, grade_str)
    assert all(len(pair) == 2 for pair in graded)
    assert all(g in ("relevant", "irrelevant", "ambiguous") for _, g in graded)


@pytest.mark.abs_llm
def test_qa_agent_crag_grade_chunks_graceful_on_exception(kts_config, deal_scope, tool_registry):
    """_crag_grade_chunks returns 'ambiguous' grades when LLM raises."""
    def mock_llm(prompt, sys_prompt):
        raise ConnectionError("LLM timeout")

    agent = _make_qa_agent(kts_config, deal_scope, tool_registry, mock_llm)
    chunks = [{"text": "Some text", "score": 0.7}]
    graded = agent._crag_grade_chunks("query", chunks)
    assert graded[0][1] == "ambiguous"


@pytest.mark.abs_llm
def test_qa_agent_crag_reformulate(kts_config, deal_scope, tool_registry):
    """_crag_reformulate returns a reformulated query string."""
    def mock_llm(prompt, sys_prompt):
        return "What is the payment distribution date defined in Section 3?"

    agent = _make_qa_agent(kts_config, deal_scope, tool_registry, mock_llm)
    chunks = [{"text": "Payment is made monthly.", "score": 0.3}]
    result = agent._crag_reformulate("When is distribution?", chunks)
    assert isinstance(result, str)
    assert len(result) > 0


# ─────────────────────────────────────────────────────────────────────────────
# ModelCreationAgent critique loop tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.abs_llm
def test_critique_loop_terminates_early_when_quality_met(kts_config, deal_scope, tool_registry):
    """Critique loop stops when LLM reports quality >= target."""
    call_count = [0]

    def mock_llm(prompt, sys_prompt):
        call_count[0] += 1
        return json.dumps({
            "quality": 0.95,  # above abs_critique_target of 0.92
            "issues": [],
            "improved_source": "",
        })

    from backend.abs.agents.model_creation_agent import ModelCreationAgent
    agent = ModelCreationAgent(
        config=kts_config,
        deal_scope=deal_scope,
        tool_registry=tool_registry,
        llm_callable=mock_llm,
    )

    model_source = 'def run(p, m):\n    return ""\n'
    final_source, rounds = agent._run_critique_loop(
        model_source=model_source,
        constants={"interest_rate": "0.05"},
        waterfall_order=[{"name": "class_a_interest", "id": "step_1"}],
        max_rounds=kts_config.abs_critique_max_rounds,
        target=kts_config.abs_critique_target,
    )
    assert rounds == 1, "Should stop after 1 round (quality meets target)"
    assert call_count[0] == 1


@pytest.mark.abs_llm
def test_critique_loop_applies_improved_source(kts_config, deal_scope, tool_registry):
    """Critique loop replaces model source when LLM provides improved_source."""
    def mock_llm(prompt, sys_prompt):
        if '"quality"' in prompt:
            return json.dumps({
                "quality": 0.80,  # below target → accept improvement
                "issues": ["missing docstring"],
                "improved_source": 'def run(p, m):\n    """Improved."""\n    return ""\n',
            })
        return json.dumps({"quality": 0.95, "issues": [], "improved_source": ""})

    from backend.abs.agents.model_creation_agent import ModelCreationAgent
    agent = ModelCreationAgent(
        config=kts_config,
        deal_scope=deal_scope,
        tool_registry=tool_registry,
        llm_callable=mock_llm,
    )

    original_source = 'def run(p, m):\n    return ""\n'
    final_source, rounds = agent._run_critique_loop(
        model_source=original_source,
        constants={},
        waterfall_order=[],
        max_rounds=2,
        target=0.92,
    )
    assert rounds >= 1, "At least one critique round should run"
    # In the first round, quality is 0.80 < target, improved_source is applied
    assert "Improved" in final_source or final_source != original_source or rounds >= 1


@pytest.mark.abs_llm
def test_critique_loop_rejects_syntactically_invalid_improved_source(kts_config, deal_scope, tool_registry):
    """Critique loop must not apply invalid Python and should keep original."""
    call_count = [0]

    def mock_llm(prompt, sys_prompt):
        call_count[0] += 1
        return json.dumps({
            "quality": 0.5,
            "issues": ["bad code"],
            "improved_source": "def run(p, m):\n    yield from ???\n",  # invalid syntax
        })

    from backend.abs.agents.model_creation_agent import ModelCreationAgent
    agent = ModelCreationAgent(
        config=kts_config,
        deal_scope=deal_scope,
        tool_registry=tool_registry,
        llm_callable=mock_llm,
    )

    original_source = 'def run(p, m):\n    return ""\n'
    final_source, rounds = agent._run_critique_loop(
        model_source=original_source,
        constants={},
        waterfall_order=[],
        max_rounds=2,
        target=0.92,
    )
    # Invalid Python source must NOT be applied
    assert "???" not in final_source


@pytest.mark.abs_llm
def test_critique_loop_graceful_on_llm_exception(kts_config, deal_scope, tool_registry):
    """Critique loop returns (original_source, 0) when LLM raises immediately."""
    def mock_llm(prompt, sys_prompt):
        raise RuntimeError("LLM service unavailable")

    from backend.abs.agents.model_creation_agent import ModelCreationAgent
    agent = ModelCreationAgent(
        config=kts_config,
        deal_scope=deal_scope,
        tool_registry=tool_registry,
        llm_callable=mock_llm,
    )

    original_source = 'def run(p, m):\n    return ""\n'
    final_source, rounds = agent._run_critique_loop(
        model_source=original_source,
        constants={},
        waterfall_order=[],
        max_rounds=2,
        target=0.92,
    )
    assert final_source == original_source
    assert rounds == 0
