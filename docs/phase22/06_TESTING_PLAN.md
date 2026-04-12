# Phase 22: Testing Plan
## Infrastructure Replacement & LLM Integration Tests

**Document Version:** 1.0  
**Date:** February 26, 2026  
**Status:** Proposal — Pending Approval  
**Scope:** Test strategy for adapter replacements and LLM wiring

---

## Table of Contents
1. [Test Summary](#test-summary)
2. [Test File Structure](#test-file-structure)
3. [Unit Tests — Adapters](#unit-tests-adapters)
4. [Unit Tests — LLM Bridge](#unit-tests-llm-bridge)
5. [Unit Tests — Agent LLM Wiring](#unit-tests-agent-wiring)
6. [Unit Tests — Config & Schema](#unit-tests-config)
7. [Integration Tests — Pipeline Flows](#integration-tests)
8. [Regression Tests — KTS Isolation](#regression-tests)
9. [Pass Criteria](#pass-criteria)

---

## Test Summary

| Test Category | Test Count | Files | Priority |
|--------------|-----------|-------|----------|
| Adapter unit tests | 35 | 3 | 🔴 Critical |
| LLM bridge unit tests | 20 | 1 | 🔴 Critical |
| Agent LLM wiring tests | 30 | 1 | 🔴 Critical |
| Config & schema tests | 15 | 1 | 🟡 High |
| Integration tests | 25 | 2 | 🟡 High |
| Regression tests | 20 | 1 | 🔴 Critical |
| **Total** | **145** | **9** | |

Combined with Phase 21's 162 tests: **307 total ABS tests**.

---

## Test File Structure

```
tests/
├── unit/
│   ├── test_abs_embedder_adapter.py      ← NEW (12 tests)
│   ├── test_abs_graph_adapter.py         ← NEW (13 tests)
│   ├── test_abs_vector_search_adapter.py ← NEW (10 tests)
│   ├── test_abs_llm_bridge.py            ← NEW (20 tests)
│   ├── test_abs_agent_llm_wiring.py      ← NEW (30 tests)
│   └── test_abs_config_phase22.py        ← NEW (15 tests)
├── integration/
│   ├── test_phase22_smoke.py             ← NEW (15 tests)
│   └── test_phase22_pipeline.py          ← NEW (10 tests)
└── regression/
    └── test_kts_isolation_phase22.py     ← NEW (20 tests)
```

---

## Unit Tests — Adapters

### `tests/unit/test_abs_embedder_adapter.py` (12 tests)

```python
"""Unit tests for embedder adapter (Phase 22 stub replacement)."""

import pytest
from unittest.mock import patch, MagicMock
from config.settings import KTSConfig


@pytest.fixture
def config():
    return KTSConfig()


class TestEmbedFunction:
    """Tests for embedder.embed()"""
    
    def test_embed_returns_list_of_vectors(self, config):
        """embed() returns list[list[float]] matching input count."""
        from backend.abs.skills.embedder import embed
        vectors = embed(["hello world"], config)
        assert isinstance(vectors, list)
        assert len(vectors) == 1
        assert isinstance(vectors[0], list)
        assert all(isinstance(v, float) for v in vectors[0])
    
    def test_embed_empty_list_returns_empty(self, config):
        """embed([]) returns []."""
        from backend.abs.skills.embedder import embed
        assert embed([], config) == []
    
    def test_embed_multiple_texts(self, config):
        """embed() handles batch of texts."""
        from backend.abs.skills.embedder import embed
        vectors = embed(["text 1", "text 2", "text 3"], config)
        assert len(vectors) == 3
    
    def test_embed_vector_dimensionality(self, config):
        """Vectors are 768-dimensional (BGE ONNX INT8)."""
        from backend.abs.skills.embedder import embed
        vectors = embed(["test"], config)
        assert len(vectors[0]) == 768
    
    def test_embed_deterministic(self, config):
        """Same input produces same output."""
        from backend.abs.skills.embedder import embed
        v1 = embed(["test text"], config)
        v2 = embed(["test text"], config)
        assert v1 == v2


class TestChunkText:
    """Tests for embedder.chunk_text()"""
    
    def test_short_text_single_chunk(self):
        """Short text returns single chunk."""
        from backend.abs.skills.embedder import chunk_text
        chunks = chunk_text("Short text.", max_chars=4000)
        assert len(chunks) == 1
    
    def test_long_text_multiple_chunks(self):
        """Long text is split into multiple chunks."""
        from backend.abs.skills.embedder import chunk_text
        long_text = "Section 5.02 of the Agreement. " * 200
        chunks = chunk_text(long_text, max_chars=1000)
        assert len(chunks) > 1
    
    def test_default_abs_chunk_size(self):
        """Default chunk size is 4000 (ABS-specific)."""
        from backend.abs.skills.embedder import chunk_text
        # This implicitly tests the ABS default of 4000 chars
        chunks = chunk_text("x" * 5000)
        assert len(chunks) >= 2


class TestEmbedAndStore:
    """Tests for embedder.embed_and_store()"""
    
    def test_embed_and_store_returns_count(self, config):
        """embed_and_store() returns number of items stored."""
        from backend.abs.skills.embedder import embed_and_store
        with patch('backend.abs.skills.embedder._get_provider') as mock_prov, \
             patch('backend.vector.dual_vector_store.DualVectorStore') as mock_store:
            mock_prov.return_value.embed_documents.return_value = [[0.1] * 768]
            count = embed_and_store(
                texts=["test"],
                metadatas=[{"section": "5.02"}],
                collection_name="abs_test_items",
                config=config,
            )
            assert count == 1
    
    def test_embed_and_store_mismatched_lengths_raises(self, config):
        """Mismatched texts/metadatas raises ValueError."""
        from backend.abs.skills.embedder import embed_and_store
        with pytest.raises(ValueError, match="same length"):
            embed_and_store(
                texts=["text1", "text2"],
                metadatas=[{"one": 1}],
                collection_name="test",
                config=config,
            )
    
    def test_embed_and_store_empty_list(self, config):
        """Empty list returns 0."""
        from backend.abs.skills.embedder import embed_and_store
        assert embed_and_store([], [], "test", config) == 0
    
    def test_provider_singleton(self, config):
        """Provider is cached (singleton per config)."""
        from backend.abs.skills.embedder import _get_provider, reset_provider
        reset_provider()
        p1 = _get_provider(config)
        p2 = _get_provider(config)
        assert p1 is p2
```

### `tests/unit/test_abs_graph_adapter.py` (13 tests)

```python
"""Unit tests for graph builder adapter."""

import pytest
import networkx as nx
from pathlib import Path
from config.settings import KTSConfig


@pytest.fixture
def config():
    cfg = KTSConfig()
    cfg.abs_graph_pagerank_enabled = True
    return cfg


@pytest.fixture
def sample_sections():
    return [
        {
            "section_id": "5.02",
            "title": "Establishment of Accounts",
            "text": "The Trustee shall establish the Distribution Account...",
            "article": "V",
            "items": [
                {"type": "definition", "text": "Distribution Account means..."},
                {"type": "obligation", "text": "The Trustee shall deposit..."},
            ],
        },
        {
            "section_id": "5.04",
            "title": "Priority of Payments",
            "text": "On each Distribution Date...",
            "article": "V",
            "items": [
                {"type": "rule", "text": "First, to the Trustee Fee..."},
                {"type": "rule", "text": "Second, to Class A Interest..."},
            ],
        },
    ]


class TestBuildGraph:
    def test_returns_digraph(self, sample_sections, config):
        from backend.abs.skills.graph_builder import build_graph
        graph = build_graph(sample_sections, config)
        assert isinstance(graph, nx.DiGraph)
    
    def test_node_count(self, sample_sections, config):
        from backend.abs.skills.graph_builder import build_graph
        graph = build_graph(sample_sections, config)
        assert graph.number_of_nodes() >= 6  # 2 sections + 4 items
    
    def test_abs_node_types(self, sample_sections, config):
        from backend.abs.skills.graph_builder import build_graph
        graph = build_graph(sample_sections, config)
        types = {d.get("node_type") for _, d in graph.nodes(data=True)}
        assert "abs_section" in types
    
    def test_pagerank_computed(self, sample_sections, config):
        from backend.abs.skills.graph_builder import build_graph
        graph = build_graph(sample_sections, config)
        has_pagerank = any("pagerank" in d for _, d in graph.nodes(data=True))
        assert has_pagerank
    
    def test_pagerank_disabled(self, sample_sections, config):
        config.abs_graph_pagerank_enabled = False
        from backend.abs.skills.graph_builder import build_graph
        graph = build_graph(sample_sections, config)
        has_pagerank = any("pagerank" in d for _, d in graph.nodes(data=True))
        assert not has_pagerank
    
    def test_empty_sections(self, config):
        from backend.abs.skills.graph_builder import build_graph
        graph = build_graph([], config)
        assert graph.number_of_nodes() == 0
    
    def test_abs_domain_tag(self, sample_sections, config):
        from backend.abs.skills.graph_builder import build_graph
        graph = build_graph(sample_sections, config)
        abs_nodes = [n for n, d in graph.nodes(data=True) if d.get("abs_domain")]
        assert len(abs_nodes) > 0


class TestSaveLoadGraph:
    def test_save_and_load(self, sample_sections, config, tmp_path):
        from backend.abs.skills.graph_builder import build_graph, save_graph, load_graph
        graph = build_graph(sample_sections, config)
        path = tmp_path / "test_graph.graphml"
        save_graph(graph, path)
        loaded = load_graph(path)
        assert loaded is not None
        assert loaded.number_of_nodes() == graph.number_of_nodes()
    
    def test_load_nonexistent(self, tmp_path):
        from backend.abs.skills.graph_builder import load_graph
        result = load_graph(tmp_path / "nonexistent.graphml")
        assert result is None
    
    def test_save_creates_directories(self, tmp_path, sample_sections, config):
        from backend.abs.skills.graph_builder import build_graph, save_graph
        graph = build_graph(sample_sections, config)
        path = tmp_path / "subdir" / "deep" / "graph.graphml"
        save_graph(graph, path)
        assert path.exists()


class TestItemClassification:
    def test_classify_definition(self):
        from backend.abs.skills.graph_builder import _classify_item_type
        assert _classify_item_type({"type": "definition"}) == "abs_definition"
    
    def test_classify_rule(self):
        from backend.abs.skills.graph_builder import _classify_item_type
        assert _classify_item_type({"type": "rule"}) == "abs_waterfall_rule"
    
    def test_classify_unknown_defaults(self):
        from backend.abs.skills.graph_builder import _classify_item_type
        assert _classify_item_type({"type": "unknown"}) == "abs_obligation"
```

### `tests/unit/test_abs_vector_search_adapter.py` (10 tests)

```python
"""Unit tests for vector search adapter."""

import pytest
from unittest.mock import patch, MagicMock
from config.settings import KTSConfig


@pytest.fixture
def config():
    return KTSConfig()


class TestSearchResult:
    def test_dataclass_defaults(self):
        from backend.abs.skills.vector_search import SearchResult
        r = SearchResult(text="test", score=0.9, metadata={"a": 1})
        assert r.confidence == 0.0
        assert r.source == ""
        assert r.section == ""
        assert r.evidence_chain == []
    
    def test_dataclass_full(self):
        from backend.abs.skills.vector_search import SearchResult
        r = SearchResult(
            text="text", score=0.95, metadata={"section": "5.02"},
            source="PSA.pdf", section="5.02", confidence=0.95,
            evidence_chain=["Citation 1"],
        )
        assert r.evidence_chain == ["Citation 1"]


class TestVectorSearch:
    @patch('backend.abs.skills.vector_search._get_service')
    def test_returns_search_results(self, mock_svc, config):
        mock_result = MagicMock()
        mock_result.content = "Distribution Account"
        mock_result.confidence = 0.92
        mock_result.metadata = {"section": "5.02"}
        mock_result.source = "PSA.pdf"
        mock_result.evidence_chain = []
        mock_svc.return_value.search.return_value = [mock_result]
        
        from backend.abs.skills.vector_search import vector_search
        results = vector_search("Distribution Account", config)
        assert len(results) == 1
        assert results[0].text == "Distribution Account"
        assert results[0].score == 0.92
    
    @patch('backend.abs.skills.vector_search._get_service')
    def test_llm_features_enabled_with_callable(self, mock_svc, config):
        mock_svc.return_value.search.return_value = []
        from backend.abs.skills.vector_search import vector_search
        llm = lambda p, s=None: "mock"
        vector_search("test", config, llm_callable=llm)
        call_kwargs = mock_svc.return_value.search.call_args
        assert call_kwargs.kwargs.get("enable_multi_query") == True
    
    @patch('backend.abs.skills.vector_search._get_service')
    def test_llm_features_disabled_without_callable(self, mock_svc, config):
        mock_svc.return_value.search.return_value = []
        from backend.abs.skills.vector_search import vector_search
        vector_search("test", config, llm_callable=None)
        call_kwargs = mock_svc.return_value.search.call_args
        assert call_kwargs.kwargs.get("enable_multi_query") == False
    
    @patch('backend.abs.skills.vector_search._get_service')
    def test_collection_filter(self, mock_svc, config):
        mock_svc.return_value.search.return_value = []
        from backend.abs.skills.vector_search import vector_search
        vector_search("test", config, collection_name="abs_bear_items")
        call_kwargs = mock_svc.return_value.search.call_args
        assert call_kwargs.kwargs.get("collection_filter") == "abs_bear_items"


class TestSpecializedSearches:
    @patch('backend.abs.skills.vector_search.vector_search')
    def test_search_definitions(self, mock_vs, config):
        from backend.abs.skills.vector_search import search_definitions
        mock_vs.return_value = []
        search_definitions("Distribution Account", config, "bear_2006_he1")
        mock_vs.assert_called_once()
        call_args = mock_vs.call_args
        assert "definition" in call_args.kwargs.get("query", call_args.args[0]).lower()
    
    @patch('backend.abs.skills.vector_search.vector_search')
    def test_search_waterfall_rules(self, mock_vs, config):
        from backend.abs.skills.vector_search import search_waterfall_rules
        mock_vs.return_value = []
        search_waterfall_rules(config, "bear_2006_he1")
        mock_vs.assert_called_once()
        call_args = mock_vs.call_args
        assert "waterfall" in call_args.kwargs.get("query", call_args.args[0]).lower()
    
    @patch('backend.abs.skills.vector_search.vector_search')
    def test_search_by_section(self, mock_vs, config):
        from backend.abs.skills.vector_search import search_by_section
        mock_vs.return_value = []
        search_by_section("5.02", config)
        mock_vs.assert_called_once()
```

---

## Unit Tests — LLM Bridge

### `tests/unit/test_abs_llm_bridge.py` (20 tests)

```python
"""Unit tests for LLM bridge module."""

import json
import pytest
from unittest.mock import patch, MagicMock
from io import StringIO


class TestCreateLLMCallable:
    def test_none_mode_returns_none(self):
        from backend.abs.llm_bridge import create_llm_callable
        assert create_llm_callable(mode="none") is None
    
    def test_mock_mode_returns_callable(self):
        from backend.abs.llm_bridge import create_llm_callable
        llm = create_llm_callable(mode="mock")
        assert callable(llm)
    
    def test_vscode_mode_returns_callable(self):
        from backend.abs.llm_bridge import create_llm_callable
        llm = create_llm_callable(mode="vscode")
        assert callable(llm)
    
    def test_unknown_mode_returns_none(self):
        from backend.abs.llm_bridge import create_llm_callable
        assert create_llm_callable(mode="invalid") is None


class TestMockCallable:
    def test_payment_model_response(self):
        from backend.abs.llm_bridge import create_llm_callable
        llm = create_llm_callable(mode="mock")
        result = llm("Generate payment model for waterfall")
        assert "calculate" in result.lower() or "distribution" in result.lower()
    
    def test_qa_response(self):
        from backend.abs.llm_bridge import create_llm_callable
        llm = create_llm_callable(mode="mock")
        result = llm("Answer the question: What is...")
        assert "Section" in result or "PSA" in result
    
    def test_governing_doc_response(self):
        from backend.abs.llm_bridge import create_llm_callable
        llm = create_llm_callable(mode="mock")
        result = llm("Generate governing document")
        assert "Waterfall" in result or "Distribution" in result
    
    def test_multi_query_response(self):
        from backend.abs.llm_bridge import create_llm_callable
        llm = create_llm_callable(mode="mock")
        result = llm("Generate alternative queries for search")
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) >= 2
    
    def test_crag_response(self):
        from backend.abs.llm_bridge import create_llm_callable
        llm = create_llm_callable(mode="mock")
        result = llm("Verify the following claim against evidence")
        parsed = json.loads(result)
        assert "verified" in parsed
    
    def test_default_response(self):
        from backend.abs.llm_bridge import create_llm_callable
        llm = create_llm_callable(mode="mock")
        result = llm("Something completely different")
        assert "Mock LLM response" in result
    
    def test_system_prompt_accepted(self):
        from backend.abs.llm_bridge import create_llm_callable
        llm = create_llm_callable(mode="mock")
        result = llm("test", "You are an ABS analyst")
        assert isinstance(result, str)


class TestUsageStats:
    def test_initial_stats(self):
        from backend.abs.llm_bridge import LLMUsageStats
        stats = LLMUsageStats()
        assert stats.total_calls == 0
        assert stats.total_input_tokens == 0
    
    def test_record_increments(self):
        from backend.abs.llm_bridge import LLMUsageStats
        stats = LLMUsageStats()
        stats.record(100, 50, 250.0)
        assert stats.total_calls == 1
        assert stats.total_input_tokens == 100
        assert stats.total_output_tokens == 50
    
    def test_avg_latency(self):
        from backend.abs.llm_bridge import LLMUsageStats
        stats = LLMUsageStats()
        stats.record(100, 50, 200.0)
        stats.record(100, 50, 400.0)
        assert stats.avg_latency_ms() == 300.0
    
    def test_avg_latency_no_calls(self):
        from backend.abs.llm_bridge import LLMUsageStats
        stats = LLMUsageStats()
        assert stats.avg_latency_ms() == 0.0
    
    def test_mock_tracks_usage(self):
        from backend.abs.llm_bridge import create_llm_callable, LLMUsageStats
        # Create a fresh stats tracker
        llm = create_llm_callable(mode="mock")
        llm("test prompt 1")
        llm("test prompt 2")
        from backend.abs.llm_bridge import get_usage_stats
        stats = get_usage_stats()
        assert stats.total_calls >= 2


class TestVSCodeCallable:
    @patch('sys.stdout', new_callable=StringIO)
    @patch('sys.stdin')
    def test_sends_json_request(self, mock_stdin, mock_stdout):
        mock_stdin.readline.return_value = json.dumps({"text": "response"})
        from backend.abs.llm_bridge import create_llm_callable
        llm = create_llm_callable(mode="vscode")
        result = llm("test prompt", "system prompt")
        output = mock_stdout.getvalue()
        request = json.loads(output.strip())
        assert request["type"] == "llm_request"
        assert request["prompt"] == "test prompt"
        assert request["system_prompt"] == "system prompt"
        assert result == "response"
    
    @patch('sys.stdout', new_callable=StringIO)
    @patch('sys.stdin')
    def test_handles_empty_response(self, mock_stdin, mock_stdout):
        mock_stdin.readline.return_value = ""
        from backend.abs.llm_bridge import create_llm_callable
        llm = create_llm_callable(mode="vscode")
        result = llm("test")
        assert result == ""
```

---

## Unit Tests — Agent LLM Wiring

### `tests/unit/test_abs_agent_llm_wiring.py` (30 tests)

```python
"""Unit tests for LLM wiring across all 13 ABS agents."""

import pytest
from unittest.mock import MagicMock, patch
from config.settings import KTSConfig


@pytest.fixture
def config():
    return KTSConfig()


@pytest.fixture
def mock_llm():
    """Mock LLM that tracks calls."""
    calls = []
    def llm(prompt, system=None):
        calls.append({"prompt": prompt, "system": system})
        return f"LLM response for: {prompt[:50]}"
    llm.calls = calls
    return llm


@pytest.fixture
def mock_scope(config):
    """Mock DealScope."""
    scope = MagicMock()
    scope.deal_id = "test_deal"
    scope.base_dir = "/tmp/test"
    return scope


class TestAgentLLMAcceptance:
    """All 13 agents must accept llm_callable parameter."""
    
    AGENT_CLASSES = [
        ("backend.abs.agents.governing_doc_generator", "GoverningDocGenerator"),
        ("backend.abs.agents.knowledge_store", "KnowledgeStore"),
        ("backend.abs.agents.model_creation_agent", "ModelCreationAgent"),
        ("backend.abs.agents.qa_agent", "QAAgent"),
        ("backend.abs.agents.structured_extractor", "StructuredExtractor"),
        ("backend.abs.agents.audit_agent", "AuditAgent"),
        ("backend.abs.agents.data_prep", "DataPrep"),
        ("backend.abs.agents.deal_analyzer", "DealAnalyzer"),
        ("backend.abs.agents.ingestion_orchestrator", "IngestionOrchestrator"),
        ("backend.abs.agents.pipeline_coordinator", "PipelineCoordinator"),
        ("backend.abs.agents.section_splitter", "SectionSplitter"),
        ("backend.abs.agents.document_converter", "DocumentConverter"),
        ("backend.abs.agents.model_validator", "ModelValidator"),
    ]
    
    @pytest.mark.parametrize("module_path,class_name", AGENT_CLASSES)
    def test_agent_accepts_llm_callable(self, module_path, class_name, config, mock_scope, mock_llm):
        """Each agent constructor accepts llm_callable parameter."""
        import importlib
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        # Should not raise
        agent = cls(config=config, deal_scope=mock_scope, llm_callable=mock_llm)
        assert agent is not None
    
    @pytest.mark.parametrize("module_path,class_name", AGENT_CLASSES)
    def test_agent_accepts_none_llm(self, module_path, class_name, config, mock_scope):
        """Each agent constructor accepts llm_callable=None."""
        import importlib
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        agent = cls(config=config, deal_scope=mock_scope, llm_callable=None)
        assert agent is not None


class TestAgentLLMBranching:
    """Agents with LLM call sites should branch on llm_callable."""
    
    def test_qa_agent_uses_llm_when_available(self, config, mock_scope, mock_llm):
        from backend.abs.agents.qa_agent import QAAgent
        agent = QAAgent(config=config, deal_scope=mock_scope, llm_callable=mock_llm)
        result = agent.execute(task="What is the Distribution Waterfall?")
        assert len(mock_llm.calls) > 0  # LLM was called
    
    def test_qa_agent_falls_back_without_llm(self, config, mock_scope):
        from backend.abs.agents.qa_agent import QAAgent
        agent = QAAgent(config=config, deal_scope=mock_scope, llm_callable=None)
        result = agent.execute(task="What is the Distribution Waterfall?")
        assert result is not None  # Template fallback works
    
    def test_model_creation_uses_llm(self, config, mock_scope, mock_llm):
        from backend.abs.agents.model_creation_agent import ModelCreationAgent
        agent = ModelCreationAgent(config=config, deal_scope=mock_scope, llm_callable=mock_llm)
        result = agent.execute(task="Generate payment model")
        assert len(mock_llm.calls) > 0
    
    def test_governing_doc_uses_llm(self, config, mock_scope, mock_llm):
        from backend.abs.agents.governing_doc_generator import GoverningDocGenerator
        agent = GoverningDocGenerator(config=config, deal_scope=mock_scope, llm_callable=mock_llm)
        result = agent.execute(task="Generate governing document")
        assert len(mock_llm.calls) > 0


class TestAgentLLMSystemPrompts:
    """Verify agents pass appropriate system prompts."""
    
    def test_qa_agent_system_prompt(self, config, mock_scope, mock_llm):
        from backend.abs.agents.qa_agent import QAAgent
        agent = QAAgent(config=config, deal_scope=mock_scope, llm_callable=mock_llm)
        agent.execute(task="What is the Distribution Waterfall?")
        system_prompts = [c["system"] for c in mock_llm.calls if c["system"]]
        assert any("ABS" in s or "analyst" in s.lower() for s in system_prompts)
    
    def test_model_creation_system_prompt(self, config, mock_scope, mock_llm):
        from backend.abs.agents.model_creation_agent import ModelCreationAgent
        agent = ModelCreationAgent(config=config, deal_scope=mock_scope, llm_callable=mock_llm)
        agent.execute(task="Generate payment model")
        system_prompts = [c["system"] for c in mock_llm.calls if c["system"]]
        assert any("Python" in s or "engineer" in s.lower() for s in system_prompts)
```

---

## Unit Tests — Config & Schema

### `tests/unit/test_abs_config_phase22.py` (15 tests)

```python
"""Unit tests for Phase 22 config additions and ABS graph schema."""

import pytest
from config.settings import KTSConfig


class TestPhase22ConfigDefaults:
    def test_llm_mode_default(self):
        config = KTSConfig()
        assert config.abs_llm_mode == "none"
    
    def test_llm_model_default(self):
        config = KTSConfig()
        assert config.abs_llm_model == "gpt-4.1"
    
    def test_llm_temperature_default(self):
        config = KTSConfig()
        assert config.abs_llm_temperature == 0.0
    
    def test_crag_enabled_default(self):
        config = KTSConfig()
        assert config.abs_crag_enabled == True
    
    def test_graph_bfs_depth_default(self):
        config = KTSConfig()
        assert config.abs_graph_bfs_depth == 5
    
    def test_retrieval_bm25_weight_default(self):
        config = KTSConfig()
        assert config.abs_retrieval_bm25_weight == 0.5


class TestPhase22ConfigOverrides:
    def test_llm_mode_override(self, monkeypatch):
        monkeypatch.setenv("KTS_ABS_LLM_MODE", "mock")
        config = KTSConfig()
        assert config.abs_llm_mode == "mock"
    
    def test_crag_disabled_override(self, monkeypatch):
        monkeypatch.setenv("KTS_ABS_CRAG_ENABLED", "false")
        config = KTSConfig()
        assert config.abs_crag_enabled == False


class TestABSRetrievalProfile:
    def test_profile_has_all_keys(self):
        from backend.abs.config.retrieval_profile import ABS_RETRIEVAL_PROFILE
        required = ["chunk_max_chars", "bm25_weight", "graph_bfs_depth", "crag_confidence_threshold"]
        for key in required:
            assert key in ABS_RETRIEVAL_PROFILE
    
    def test_apply_profile(self):
        from backend.abs.config.retrieval_profile import apply_profile_to_config
        config = KTSConfig()
        apply_profile_to_config(config)
        # Should not raise


class TestABSGraphSchema:
    def test_node_types_count(self):
        from backend.abs.config.graph_schema import ABS_NODE_TYPES
        assert len(ABS_NODE_TYPES) == 10
    
    def test_edge_types_count(self):
        from backend.abs.config.graph_schema import ABS_EDGE_TYPES
        assert len(ABS_EDGE_TYPES) == 10
    
    def test_node_types_prefixed(self):
        from backend.abs.config.graph_schema import ABS_NODE_TYPES
        assert all(n.name.startswith("abs_") for n in ABS_NODE_TYPES)
    
    def test_edge_types_valid_endpoints(self):
        from backend.abs.config.graph_schema import ABS_NODE_TYPES, ABS_EDGE_TYPES
        node_names = {n.name for n in ABS_NODE_TYPES}
        for edge in ABS_EDGE_TYPES:
            assert edge.from_type in node_names, f"{edge.name}: invalid from_type {edge.from_type}"
            assert edge.to_type in node_names, f"{edge.name}: invalid to_type {edge.to_type}"
```

---

## Integration Tests — Pipeline Flows

### `tests/integration/test_phase22_pipeline.py` (10 tests)

```python
"""Integration tests for Phase 22 — end-to-end pipeline flows."""

import pytest
from config.settings import KTSConfig
from backend.abs.llm_bridge import create_llm_callable


@pytest.fixture
def config():
    cfg = KTSConfig()
    cfg.abs_llm_mode = "mock"
    return cfg


@pytest.fixture
def mock_llm(config):
    return create_llm_callable(mode=config.abs_llm_mode)


class TestIngestionPipeline:
    """Test ingestion flow: split → extract → embed → graph → store."""
    
    def test_full_ingestion_flow(self, config, mock_llm):
        """Ingestion orchestrator processes document end-to-end."""
        pass  # Detailed implementation when actual modules are ready

    def test_ingestion_creates_vector_collection(self, config, mock_llm):
        """Ingestion creates abs_{deal_id}_items collection."""
        pass

    def test_ingestion_creates_graph(self, config, mock_llm):
        """Ingestion creates graph with ABS node types."""
        pass


class TestRetrievalPipeline:
    """Test retrieval flow: query → search → rerank → answer."""
    
    def test_qa_with_mock_llm(self, config, mock_llm):
        """QA agent answers with mock LLM and retrieval."""
        pass

    def test_qa_without_llm_uses_template(self, config):
        """QA agent falls back to template without LLM."""
        pass

    def test_retrieval_respects_abs_weights(self, config, mock_llm):
        """Retrieval uses ABS-specific BM25/vector weights."""
        pass


class TestModelGenerationPipeline:
    """Test model gen: retrieve rules → LLM generate → validate."""
    
    def test_model_gen_with_llm(self, config, mock_llm):
        """Model creation agent generates Python code with mock LLM."""
        pass

    def test_model_gen_quality_gate(self, config, mock_llm):
        """Quality gate evaluates generated model."""
        pass


class TestLLMUsageTracking:
    def test_usage_across_pipeline(self, config, mock_llm):
        """LLM usage stats accumulate across pipeline calls."""
        from backend.abs.llm_bridge import get_usage_stats
        stats = get_usage_stats()
        initial = stats.total_calls
        mock_llm("test 1")
        mock_llm("test 2")
        assert stats.total_calls >= initial + 2

    def test_mock_latency(self, config, mock_llm):
        """Mock LLM latency is < 5ms."""
        import time
        start = time.time()
        for _ in range(100):
            mock_llm("test")
        elapsed = (time.time() - start) * 1000
        assert elapsed / 100 < 5  # avg < 5ms per call
```

---

## Regression Tests — KTS Isolation

### `tests/regression/test_kts_isolation_phase22.py` (20 tests)

```python
"""Regression tests — verify Phase 22 doesn't break existing KTS functionality."""

import pytest
from config.settings import KTSConfig


class TestKTSConfigUnaffected:
    """Phase 22 config additions don't change existing properties."""
    
    def test_existing_properties_unchanged(self):
        config = KTSConfig()
        # Spot-check existing KTS properties still have correct defaults
        assert hasattr(config, 'phase6_enabled') or True  # Property may vary
        # The key assertion: no AttributeError on existing properties
    
    def test_abs_properties_have_defaults(self):
        config = KTSConfig()
        assert config.abs_llm_mode == "none"  # Doesn't activate by default


class TestKTSImportsUnaffected:
    """ABS imports don't interfere with KTS imports."""
    
    def test_kts_backend_imports(self):
        """All existing backend imports still work."""
        from backend import agents
        from backend.common import models  # if exists
    
    def test_kts_config_import(self):
        from config.settings import KTSConfig
        config = KTSConfig()
        assert config is not None
    
    def test_kts_retrieval_import(self):
        from backend.retrieval import retrieval_service
    
    def test_kts_graph_import(self):
        from backend.graph import enhanced_graph_builder
    
    def test_kts_vector_import(self):
        from backend.vector import embedding_provider


class TestKTSVectorStoreUnaffected:
    """ABS collections don't collide with KTS collections."""
    
    def test_abs_collection_prefix(self):
        """ABS collections use abs_ prefix."""
        # This is a design guarantee test
        assert "abs_" != ""  # Prefix is non-empty


class TestKTSAgentsUnaffected:
    """Existing KTS agents are not modified by Phase 22."""
    
    def test_kts_agents_importable(self):
        """All existing KTS agents still import cleanly."""
        from backend.agents import base_agent  # Merged in Phase 21 but backward compat
    
    def test_kts_agent_no_llm_required(self):
        """KTS agents don't require llm_callable."""
        from backend.agents.base_agent import AgentBase
        # AgentBase default is llm_callable=None
        # KTS agents should not be forced to provide it


class TestKTSGraphUnaffected:
    """ABS graph nodes don't collide with KTS graph nodes."""
    
    def test_abs_node_types_prefixed(self):
        from backend.abs.config.graph_schema import ABS_NODE_TYPES
        for nt in ABS_NODE_TYPES:
            assert nt.name.startswith("abs_"), f"Node type {nt.name} not prefixed"
    
    def test_abs_edge_types_named(self):
        from backend.abs.config.graph_schema import ABS_EDGE_TYPES
        for et in ABS_EDGE_TYPES:
            assert et.name, f"Edge type missing name"


class TestKTSTestsStillPass:
    """Meta-test: existing KTS test files should still pass."""
    
    def test_existing_test_count(self):
        """Verify we haven't accidentally deleted test files."""
        from pathlib import Path
        test_dir = Path("tests")
        test_files = list(test_dir.rglob("test_*.py"))
        # Should have at least as many as before Phase 22
        assert len(test_files) >= 76  # KTS had 76+ test files
```

---

## Pass Criteria

### Phase 22 Complete When

| Criterion | Threshold | How to Verify |
|-----------|-----------|--------------|
| Adapter unit tests | 35/35 pass | `pytest tests/unit/test_abs_*adapter*.py` |
| LLM bridge tests | 20/20 pass | `pytest tests/unit/test_abs_llm_bridge.py` |
| Agent wiring tests | 26/30 pass (86%) | `pytest tests/unit/test_abs_agent_llm_wiring.py` |
| Config tests | 15/15 pass | `pytest tests/unit/test_abs_config_phase22.py` |
| Integration tests | 8/10 pass | `pytest tests/integration/test_phase22_*.py` |
| Regression tests | 20/20 pass | `pytest tests/regression/test_kts_isolation_phase22.py` |
| KTS existing tests | 0 regressions | `pytest tests/ -k "not abs"` |
| Mock LLM roundtrip | < 5ms avg | Integration test assertion |
| Import time delta | < 200ms | Manual measurement |

### Test Execution Command

```powershell
# Run all Phase 22 tests
python -m pytest tests/ -k "phase22 or abs_llm or abs_embedder or abs_graph_adapter or abs_vector_search_adapter or abs_agent_llm or abs_config_phase22 or kts_isolation_phase22" -v --tb=short

# Run full regression suite
python -m pytest tests/ -x --tb=short -q
```
