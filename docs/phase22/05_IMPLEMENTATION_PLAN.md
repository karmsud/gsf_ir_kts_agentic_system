# Phase 22: Implementation Plan
## Infrastructure Replacement & LLM Integration Execution Guide

**Document Version:** 1.0  
**Date:** February 26, 2026  
**Status:** Proposal — Pending Approval  
**Scope:** Step-by-step execution guide for Phase 22

---

## Table of Contents
1. [Effort Summary](#effort-summary)
2. [Prerequisites](#prerequisites)
3. [Dependency Graph](#dependency-graph)
4. [Step 1: Create ABS Config Module](#step-1)
5. [Step 2: Implement LLM Bridge](#step-2)
6. [Step 3: Replace Embedder Stub](#step-3)
7. [Step 4: Replace Graph Builder Stub](#step-4)
8. [Step 5: Replace Vector Search Stub](#step-5)
9. [Step 6: Wire LLM to All 13 ABS Agents](#step-6)
10. [Step 7: Add Phase 22 Config Properties](#step-7)
11. [Step 8: Create ABS Retrieval Profile](#step-8)
12. [Step 9: Register ABS Graph Schema](#step-9)
13. [Step 10: VS Code Extension LLM Bridge (Placeholder)](#step-10)
14. [Step 11: Integration Smoke Test](#step-11)
15. [Step 12: Validation & Rollback](#step-12)
16. [Rollback Strategy](#rollback-strategy)

---

## Effort Summary

| Step | Task | Effort | Risk | Dependencies |
|------|------|--------|------|-------------|
| 1 | ABS config module | 30 min | 🟢 Low | Phase 21 complete |
| 2 | LLM bridge | 1.5 hrs | 🟡 Medium | Step 1 |
| 3 | Embedder adapter | 45 min | 🟢 Low | Step 1 |
| 4 | Graph builder adapter | 1 hr | 🟡 Medium | Step 1 |
| 5 | Vector search adapter | 1.5 hrs | 🟡 Medium | Step 1 |
| 6 | Agent LLM wiring (13 agents) | 3–4 hrs | 🟡 Medium | Steps 2, 3, 4, 5 |
| 7 | Phase 22 config properties | 30 min | 🟢 Low | Step 1 |
| 8 | Retrieval profile | 30 min | 🟢 Low | Step 7 |
| 9 | Graph schema registration | 30 min | 🟢 Low | Step 4 |
| 10 | VS Code extension bridge | 1 hr | 🟡 Medium | Step 2 |
| 11 | Integration smoke test | 1.5 hrs | 🟡 Medium | All above |
| 12 | Validation & rollback prep | 30 min | 🟢 Low | Step 11 |
| **Total** | | **12–14 hrs** | | **3–4 work days** |

---

## Prerequisites

- [ ] Phase 21 complete and all 162 tests passing
- [ ] KTS existing 76+ test files still green
- [ ] Git branch: `feature/phase22-infra-llm`
- [ ] Python 3.13 with all dependencies installed

```powershell
# Verify Phase 21 is stable
cd "c:\Users\Karmsud\New Project\gsf_ir_kts_agentic_system"
python -m pytest tests/ -x --tb=short
```

---

## Dependency Graph

```
Phase 21 Complete
        │
        ▼
   ┌─── Step 1: ABS Config Module ───┐
   │              │                    │
   ▼              ▼                    ▼
Step 3         Step 4              Step 5
Embedder       Graph               Vector
Adapter        Adapter             Adapter
   │              │                    │
   └──────────────┼────────────────────┘
                  │
                  ▼
          Step 2: LLM Bridge
                  │
                  ▼
          Step 6: Agent LLM Wiring (13 agents)
                  │
   ┌──────────────┼──────────────┐
   ▼              ▼              ▼
Step 7         Step 8         Step 9
Config         Retrieval      Graph
Properties     Profile        Schema
   │              │              │
   └──────────────┼──────────────┘
                  ▼
          Step 10: VS Code Bridge
                  │
                  ▼
          Step 11: Integration Test
                  │
                  ▼
          Step 12: Validation
```

---

## Step 1: Create ABS Config Module

**Effort:** 30 min | **Risk:** 🟢 Low

### Actions

```powershell
# Create config subdirectory
New-Item -ItemType Directory -Path "backend\abs\config" -Force
```

### Files to Create

1. `backend/abs/config/__init__.py` (5 lines)
2. `backend/abs/config/retrieval_profile.py` (60 lines — placeholder, finished in Step 8)
3. `backend/abs/config/graph_schema.py` (100 lines — placeholder, finished in Step 9)

### `backend/abs/config/__init__.py`

```python
"""ABS-specific configuration modules."""
```

### Validation Checkpoint

```powershell
python -c "from backend.abs.config import *; print('Step 1: OK')"
```

---

## Step 2: Implement LLM Bridge

**Effort:** 1.5 hrs | **Risk:** 🟡 Medium

### Actions

Create `backend/abs/llm_bridge.py` (~200 lines) with:
- `LLMCallable` type alias
- `LLMUsageStats` dataclass
- `create_llm_callable(mode, model, temperature, max_tokens)` factory
- `_create_vscode_callable()` — IPC via stdin/stdout
- `_create_mock_callable()` — deterministic test responses
- `get_usage_stats()` — global usage tracker

### Implementation

Full code in [04_TECHNICAL_DESIGN.md §Transformation 4](04_TECHNICAL_DESIGN.md) and [03_ARCHITECTURE_UPGRADE.md §Transformation 4](03_ARCHITECTURE_UPGRADE.md).

### Key Decisions

- **Mock callable returns domain-specific responses**: Payment models, Q&A answers, governing docs — not generic text
- **Usage tracking is global**: Single `_usage` instance per process
- **IPC protocol**: JSON-per-line on stdin/stdout (same as KTS's existing extension IPC)

### Validation Checkpoint

```powershell
python -c "
from backend.abs.llm_bridge import create_llm_callable, get_usage_stats
# Test mock mode
llm = create_llm_callable(mode='mock')
assert llm is not None
result = llm('Generate payment model for waterfall')
assert 'calculate' in result.lower() or 'distribution' in result.lower()
stats = get_usage_stats()
assert stats.total_calls == 1
print('Step 2: OK')
"
```

---

## Step 3: Replace Embedder Stub

**Effort:** 45 min | **Risk:** 🟢 Low

### Actions

Replace `backend/abs/skills/embedder.py` (stub) with adapter (~120 lines).

### Key Changes

| Before (Stub) | After (Adapter) |
|---------------|----------------|
| `raise NotImplementedError` | Delegates to `EmbeddingProvider` |
| No chunking | Uses `LegalChunker` (heading-aware) |
| No storage | Uses `DualVectorStore.add_items()` |

### Implementation

Full code in [04_TECHNICAL_DESIGN.md §Adapter: embedder.py](04_TECHNICAL_DESIGN.md).

### Validation Checkpoint

```powershell
python -c "
from backend.abs.skills import embedder
from config.settings import KTSConfig
config = KTSConfig()
# Test chunking (doesn't require ONNX model)
chunks = embedder.chunk_text('Section 5.02. The Trustee shall establish...' * 50)
assert len(chunks) > 0
print(f'Step 3: OK — {len(chunks)} chunks')
"
```

---

## Step 4: Replace Graph Builder Stub

**Effort:** 1 hr | **Risk:** 🟡 Medium

### Actions

Replace `backend/abs/skills/graph_builder.py` (stub) with adapter (~150 lines).

### Key Changes

| Before (Stub) | After (Adapter) |
|---------------|----------------|
| `raise NotImplementedError` | Delegates to `EnhancedGraphBuilder` |
| No node types | 10 ABS-specific node types |
| No PageRank | PageRank computation |

### Critical API Translation

PayGen passes flat `list[dict]` sections. KTS `EnhancedGraphBuilder` expects typed sections. The `_transform_sections()` function handles this conversion:

```python
# PayGen format:
{"section_id": "5.02", "title": "...", "text": "...", "items": [...]}

# KTS format (after transformation):
{"id": "abs_section_5.02", "node_type": "abs_section", "content": "...", "children": [...]}
```

### Validation Checkpoint

```powershell
python -c "
from backend.abs.skills import graph_builder
from config.settings import KTSConfig
config = KTSConfig()
sections = [
    {'section_id': '5.02', 'title': 'Accounts', 'text': 'test', 'items': [
        {'type': 'definition', 'text': 'Distribution Account means...'}
    ]}
]
graph = graph_builder.build_graph(sections, config)
assert graph.number_of_nodes() > 0
print(f'Step 4: OK — {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges')
"
```

---

## Step 5: Replace Vector Search Stub

**Effort:** 1.5 hrs | **Risk:** 🟡 Medium

### Actions

Replace `backend/abs/skills/vector_search.py` (stub) with adapter (~160 lines).

### Key Changes

| Before (Stub) | After (Adapter) |
|---------------|----------------|
| `raise NotImplementedError` | Delegates to `RetrievalService` |
| Returns `list[dict]` | Returns `list[SearchResult]` dataclass |
| No LLM features | CRAG, critique, multi-query, HyDE when LLM available |

### LLM Feature Gating

The adapter conditionally enables advanced features based on `llm_callable`:

```python
if llm_callable is not None:
    # Enable: multi-query, HyDE, CRAG, critique
else:
    # Disable all LLM features, use hybrid search only
```

### Validation Checkpoint

```powershell
python -c "
from backend.abs.skills.vector_search import SearchResult
r = SearchResult(text='test', score=0.9, metadata={'section': '5.02'})
assert r.confidence == 0.0  # default
assert r.section == ''       # default (not from metadata)
print('Step 5: OK — SearchResult dataclass working')
"
```

---

## Step 6: Wire LLM to All 13 ABS Agents

**Effort:** 3–4 hrs | **Risk:** 🟡 Medium  
**Dependencies:** Steps 2, 3, 4, 5

### Actions

For each of the 13 ABS agents:

1. Add `llm_callable: Optional[LLMCallable] = None` parameter to `__init__`
2. Pass `llm_callable=llm_callable` to `super().__init__()`
3. Add LLM-enhanced execution path with `if self._llm:` branching
4. Add system prompt constants
5. Add template fallback for `llm_callable=None`

### Agent Modification Checklist

| # | Agent File | LLM Call Sites | System Prompts | Estimated Lines |
|---|-----------|---------------|----------------|----------------|
| 1 | `governing_doc_generator.py` | 2 (generate, consolidate) | 2 | +40 |
| 2 | `knowledge_store.py` | 2 (vocab, disambiguate) | 2 | +35 |
| 3 | `model_creation_agent.py` | 3 (generate, refine, validate) | 3 | +60 |
| 4 | `qa_agent.py` | 2 (answer, followup) | 2 | +45 |
| 5 | `structured_extractor.py` | 2 (extract, relate) | 2 | +35 |
| 6 | `audit_agent.py` | 2 (audit, discrepancy) | 2 | +40 |
| 7 | `data_prep.py` | 1 (normalize) | 1 | +20 |
| 8 | `deal_analyzer.py` | 1 (analyze) | 1 | +30 |
| 9 | `ingestion_orchestrator.py` | 1 (classify) | 1 | +25 |
| 10 | `pipeline_coordinator.py` | 1 (summarize) | 1 | +20 |
| 11 | `section_splitter.py` | 0 (no LLM needed) | 0 | +15 (param only) |
| 12 | `document_converter.py` | 0 (no LLM needed) | 0 | +10 (param only) |
| 13 | `model_validator.py` | 0 (no LLM needed) | 0 | +15 (param only) |

### Execution Order

1. Start with simplest agents (no LLM usage): `section_splitter`, `document_converter`, `model_validator` — just add parameter
2. Then agents with 1 call site: `data_prep`, `deal_analyzer`, `ingestion_orchestrator`, `pipeline_coordinator`
3. Finally complex agents with 2-3 call sites: `governing_doc_generator`, `knowledge_store`, `model_creation_agent`, `qa_agent`, `structured_extractor`, `audit_agent`

### System Prompts File

Create `backend/abs/config/prompts.py` (~200 lines) containing all system prompt constants:

```python
"""
ABS system prompts for LLM-powered agents.

All prompts follow these principles:
1. Role assignment (who the LLM should act as)
2. Domain context (ABS / structured finance)
3. Output format specification
4. Precision requirements (cite sections, use exact terms)
"""

# Governing Doc Generator
PROMPT_GOV_GENERATE = """You are an ABS payment model engineer specializing in..."""
PROMPT_GOV_CONSOLIDATE = """You are a legal document merger..."""

# Model Creation Agent
PROMPT_MODEL_GENERATE = """You are a Python financial engineer..."""
PROMPT_MODEL_REFINE = """You are a debugging assistant..."""
PROMPT_MODEL_VALIDATE = """You are a QA engineer..."""

# QA Agent
PROMPT_QA_ANSWER = """You are an ABS analyst..."""
PROMPT_QA_FOLLOWUP = """You are a Socratic questioner..."""

# ... etc for all agents
```

### Validation Checkpoint

```powershell
# Verify all agents accept llm_callable parameter
python -c "
from backend.abs.agents import (
    governing_doc_generator, knowledge_store, model_creation_agent,
    qa_agent, structured_extractor, audit_agent, data_prep,
    deal_analyzer, ingestion_orchestrator, pipeline_coordinator,
    section_splitter, document_converter, model_validator,
)
print('Step 6: OK — all 13 agents importable')
"

# Verify mock LLM works with an agent
python -c "
from backend.abs.llm_bridge import create_llm_callable
from backend.abs.agents.qa_agent import QAAgent
from backend.abs.agents.deal_scope import DealScope
from config.settings import KTSConfig

config = KTSConfig()
llm = create_llm_callable(mode='mock')
scope = DealScope(deal_id='test', config=config)
agent = QAAgent(config=config, deal_scope=scope, llm_callable=llm)
result = agent.execute(task='What is the Distribution Waterfall?')
assert result is not None
print('Step 6: OK — QA agent with mock LLM works')
"
```

---

## Step 7: Add Phase 22 Config Properties

**Effort:** 30 min | **Risk:** 🟢 Low

### Actions

Add ~25 `abs_*` properties to `KTSConfig` class in `config/settings.py`.

### Properties

See [04_TECHNICAL_DESIGN.md §KTSConfig Phase 22 Additions](04_TECHNICAL_DESIGN.md) for full list.

### Environment Variable Overrides

All properties support env-var override following KTS convention:

```
KTS_ABS_LLM_MODE=mock
KTS_ABS_LLM_MODEL=gpt-4.1
KTS_ABS_CRAG_ENABLED=false
KTS_ABS_MULTI_QUERY_ENABLED=true
```

### Validation Checkpoint

```powershell
python -c "
from config.settings import KTSConfig
config = KTSConfig()
assert config.abs_llm_mode == 'none'
assert config.abs_llm_model == 'gpt-4.1'
assert config.abs_crag_enabled == True
assert config.abs_graph_bfs_depth == 5
print('Step 7: OK — all Phase 22 config properties have defaults')
"
```

---

## Step 8: Create ABS Retrieval Profile

**Effort:** 30 min | **Risk:** 🟢 Low

### Actions

Create `backend/abs/config/retrieval_profile.py` (60 lines) with:
- `ABS_RETRIEVAL_PROFILE` dict with ABS-tuned parameters
- `apply_profile_to_config()` function

### Why ABS Needs Different Retrieval Parameters

| Parameter | KTS Default | ABS Value | Reason |
|-----------|-------------|-----------|--------|
| Chunk size | 3000 chars | 4000 chars | Legal sections are verbose |
| BM25 weight | 0.4 | 0.5 | Legal terms are precise |
| BFS depth | 4 | 5 | Cross-references run deep |
| CRAG threshold | 0.80 | 0.85 | Financial accuracy critical |
| Critique rounds | 5 | 3 | Faster for deal analysis |

### Validation Checkpoint

```powershell
python -c "
from backend.abs.config.retrieval_profile import ABS_RETRIEVAL_PROFILE, apply_profile_to_config
from config.settings import KTSConfig
config = KTSConfig()
apply_profile_to_config(config)
print('Step 8: OK — retrieval profile applied')
"
```

---

## Step 9: Register ABS Graph Schema

**Effort:** 30 min | **Risk:** 🟢 Low

### Actions

Create `backend/abs/config/graph_schema.py` (100 lines) with:
- `NodeTypeDef` and `EdgeTypeDef` dataclasses
- `ABS_NODE_TYPES` list (10 types)
- `ABS_EDGE_TYPES` list (10 types)
- `get_all_node_type_names()` and `get_all_edge_type_names()` helpers

### Validation Checkpoint

```powershell
python -c "
from backend.abs.config.graph_schema import ABS_NODE_TYPES, ABS_EDGE_TYPES
assert len(ABS_NODE_TYPES) == 10
assert len(ABS_EDGE_TYPES) == 10
assert all(n.name.startswith('abs_') for n in ABS_NODE_TYPES)
print(f'Step 9: OK — {len(ABS_NODE_TYPES)} node types, {len(ABS_EDGE_TYPES)} edge types')
"
```

---

## Step 10: VS Code Extension LLM Bridge (Placeholder)

**Effort:** 1 hr | **Risk:** 🟡 Medium

### Actions

Create `extension/src/abs/absLLMBridge.ts` (~50 lines placeholder) with:
- `handleLLMRequest()` function
- IPC protocol types (`LLMRequest`, `LLMResponse`)
- Model selection via `vscode.lm.selectChatModels()`

### Note

This is a **placeholder** for Phase 23 when the full `@abs` chat participant is built. In Phase 22, the Python-side LLM bridge can be tested with mock mode.

### Validation Checkpoint

```powershell
# TypeScript compilation check (if extension build is set up)
# Otherwise, manual review of the file
Test-Path "extension\src\abs\absLLMBridge.ts"
```

---

## Step 11: Integration Smoke Test

**Effort:** 1.5 hrs | **Risk:** 🟡 Medium

### Smoke Test Script

```python
# tests/integration/test_phase22_smoke.py

"""Phase 22 integration smoke test — verifies all infrastructure replacements."""

import pytest
from config.settings import KTSConfig
from backend.abs.llm_bridge import create_llm_callable


@pytest.fixture
def config():
    return KTSConfig()


@pytest.fixture
def mock_llm():
    return create_llm_callable(mode="mock")


class TestEmbedderAdapter:
    def test_embed_returns_vectors(self, config):
        from backend.abs.skills.embedder import embed
        vectors = embed(["test sentence"], config)
        assert len(vectors) == 1
        assert len(vectors[0]) == 768  # BGE dimensionality

    def test_chunk_text(self):
        from backend.abs.skills.embedder import chunk_text
        long_text = "Section 5.02. " * 500
        chunks = chunk_text(long_text)
        assert len(chunks) > 1


class TestGraphAdapter:
    def test_build_graph(self, config):
        from backend.abs.skills.graph_builder import build_graph
        sections = [{"section_id": "5.02", "title": "Test", "text": "test", "items": []}]
        graph = build_graph(sections, config)
        assert graph.number_of_nodes() > 0

    def test_save_load_graph(self, config, tmp_path):
        from backend.abs.skills.graph_builder import build_graph, save_graph, load_graph
        sections = [{"section_id": "1.01", "title": "Defs", "text": "...", "items": []}]
        graph = build_graph(sections, config)
        path = tmp_path / "test.graphml"
        save_graph(graph, path)
        loaded = load_graph(path)
        assert loaded is not None
        assert loaded.number_of_nodes() == graph.number_of_nodes()


class TestVectorSearchAdapter:
    def test_search_result_dataclass(self):
        from backend.abs.skills.vector_search import SearchResult
        r = SearchResult(text="test", score=0.9, metadata={})
        assert r.text == "test"
        assert r.evidence_chain == []


class TestLLMBridge:
    def test_mock_callable(self):
        llm = create_llm_callable(mode="mock")
        assert llm is not None
        result = llm("Generate payment model")
        assert len(result) > 0

    def test_none_mode(self):
        llm = create_llm_callable(mode="none")
        assert llm is None

    def test_usage_tracking(self):
        from backend.abs.llm_bridge import get_usage_stats
        llm = create_llm_callable(mode="mock")
        llm("test prompt")
        stats = get_usage_stats()
        assert stats.total_calls > 0


class TestAgentLLMWiring:
    def test_qa_agent_with_mock_llm(self, config, mock_llm):
        from backend.abs.agents.qa_agent import QAAgent
        from backend.abs.agents.deal_scope import DealScope
        scope = DealScope(deal_id="test", config=config)
        agent = QAAgent(config=config, deal_scope=scope, llm_callable=mock_llm)
        result = agent.execute(task="What is the Distribution Waterfall?")
        assert result is not None

    def test_agent_without_llm(self, config):
        from backend.abs.agents.qa_agent import QAAgent
        from backend.abs.agents.deal_scope import DealScope
        scope = DealScope(deal_id="test", config=config)
        agent = QAAgent(config=config, deal_scope=scope, llm_callable=None)
        result = agent.execute(task="What is the Distribution Waterfall?")
        assert result is not None  # Template fallback works
```

### Run Smoke Test

```powershell
python -m pytest tests/integration/test_phase22_smoke.py -v --tb=short
```

---

## Step 12: Validation & Rollback

**Effort:** 30 min | **Risk:** 🟢 Low

### Full Regression

```powershell
# Run ALL tests (KTS + ABS)
python -m pytest tests/ -x --tb=short -q

# Expected: All existing tests pass + new Phase 22 tests pass
```

### KTS Isolation Check

```powershell
# Verify KTS agents are completely unaffected
python -m pytest tests/unit/test_agents/ -v --tb=short
python -m pytest tests/unit/test_retrieval/ -v --tb=short
python -m pytest tests/unit/test_graph/ -v --tb=short
```

### Metrics to Verify

| Metric | Expected |
|--------|----------|
| Phase 21 tests | 162 pass |
| Phase 22 tests | ~50 new pass |
| KTS existing tests | No regressions |
| Import time increase | < 200ms |
| Mock LLM roundtrip | < 5ms |

---

## Rollback Strategy

### Per-Step Rollback

```powershell
# Roll back to Phase 21 state (stubs):
# Restore stub files from git
git checkout feature/phase21 -- backend/abs/skills/embedder.py
git checkout feature/phase21 -- backend/abs/skills/graph_builder.py
git checkout feature/phase21 -- backend/abs/skills/vector_search.py

# Remove new Phase 22 files
Remove-Item -Path "backend\abs\llm_bridge.py" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Path "backend\abs\config" -ErrorAction SilentlyContinue
Remove-Item -Path "extension\src\abs\absLLMBridge.ts" -ErrorAction SilentlyContinue

# Revert config changes
git checkout feature/phase21 -- config/settings.py

# Revert agent LLM additions
git checkout feature/phase21 -- backend/abs/agents/
```

### Full Phase Rollback

```powershell
# Nuclear option: discard all Phase 22 changes
git checkout feature/phase21
```
