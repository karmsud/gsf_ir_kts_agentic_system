# Phase 21: Executive Summary
## ABS Domain Integration — Port Payment Generator into KTS

**Document Version:** 1.0  
**Date:** February 26, 2026  
**Status:** Proposal — Pending Approval  
**Business Impact:** STRATEGIC — Unifies two codebases into a single enterprise platform  
**Estimated Effort:** 12–16 hours (Phase 21 only)

---

## Table of Contents
1. [Executive Overview](#executive-overview)
2. [Strategic Rationale](#strategic-rationale)
3. [What Is Being Ported](#what-is-being-ported)
4. [What Is NOT Being Ported](#what-is-not-being-ported)
5. [Architecture Decision](#architecture-decision)
6. [Value Proposition](#value-proposition)
7. [Risk Assessment](#risk-assessment)
8. [Success Metrics](#success-metrics)
9. [Relationship to Phases 22 & 23](#relationship-to-phases-22--23)

---

## Executive Overview

### The Opportunity

Two parallel projects exist today:

| Project | Lines of Code | Agents | Vector Store | Graph | LLM | Tests |
|---------|--------------|--------|-------------|-------|-----|-------|
| **AI Payment Generator** | ~5,500 domain logic | 13 (7 functional, 4 skeleton) | ChromaDB (basic) | NetworkX (flat) | **Zero** | 479 |
| **KTS Agentic System** | ~15,000+ infrastructure | 15 | ChromaDB (dual/triple) | NetworkX (hierarchical) | 27 call sites | 76+ files |

**Key insight:** Payment Generator's unique value is ~5,500 lines of **self-contained ABS domain logic** (cashflow engine, waterfall parsers, model generation). KTS's unique value is ~15,000+ lines of **deeply interconnected infrastructure** (31 retrieval modules, 17 graph modules, 12 vector modules, VS Code extension).

**Decision:** Port Payment Generator's domain logic INTO KTS as `backend/abs/`, rather than rebuilding KTS's infrastructure inside Payment Generator. This is **3–4× less work**.

### What Phase 21 Delivers

Phase 21 (this phase) handles the **structural integration** — moving files, rewriting imports, merging the agent framework, and establishing the `backend/abs/` subpackage. No LLM wiring, no CLI, no extension work — those come in Phases 22 and 23.

**After Phase 21, the ABS domain code lives inside KTS and compiles cleanly, but does not yet use KTS's retrieval/embedding/graph infrastructure.**

---

## Strategic Rationale

### Why Direction B (PayGen → KTS) Instead of Direction A (KTS → PayGen)

| Criterion | Direction A (KTS → PayGen) | Direction B (PayGen → KTS) |
|-----------|---------------------------|---------------------------|
| Lines to move | ~15,000+ interconnected | ~5,500 self-contained |
| Import rewrites | 200+ cross-module refs | ~50 internal refs |
| Infrastructure duplication | Must rebuild retrieval, graph, embedding | Reuse existing |
| Extension work | Must rebuild VS Code agent | Add `@abs` participant alongside `@kts` |
| AgentBase conflict | Downgrade to 24-line stub | Upgrade stub with 414-line rich base |
| Estimated effort | 80–120 hours | 25–35 hours (all 3 phases) |

### Three Phases Overview

| Phase | Name | Scope | Effort |
|-------|------|-------|--------|
| **21** | ABS Domain Integration | Scaffold, copy, merge AgentBase, merge quality | 12–16 hours |
| **22** | Infrastructure Replacement + LLM Wiring | Swap vector/graph/embed, add LLM via VS Code LM API | 10–14 hours |
| **23** | CLI + Extension + Packaging | `@abs` chat participant, CLI commands, VSIX | 8–12 hours |

---

## What Is Being Ported

### Domain Logic (~5,500 lines, 26 modules)

**Agents (13 modules, ~3,200 lines):**
- `agent_base.py` — 414-line rich AgentBase with 5-dimension quality gate, retry loop, state persistence, tool registry, prompt structure
- `agent_tools.py` — ToolRegistry with `@agent_tool` decorator (168 lines)
- `cashflow_projection_agent.py` — CashflowProjectionAgent
- `deal_amendment_agent.py` — DealAmendmentAgent
- `deal_lifecycle_agent.py` — DealLifecycleAgent
- `document_comparison_agent.py` — DocumentComparisonAgent
- `document_quality_agent.py` — DocumentQualityAgent
- `ingestion_pipeline_agent.py` — IngestionPipelineAgent
- `investor_reporting_agent.py` — InvestorReportingAgent
- `model_auditor_agent.py` — ModelAuditorAgent
- `model_creation_agent.py` — ModelCreationAgent (401 lines)
- `qa_agent.py` — QAAgent
- `regression_testing_agent.py` — RegressionTestingAgent
- `stress_testing_agent.py` — StressTestingAgent

**Skills (14 modules, ~1,800 lines):**
- `cashflow_engine.py` — 557 lines, waterfall projection engine
- `amendment_manager.py` — Version-controlled deal amendments
- `csv_validator.py` — CSV schema validation
- `deal_comparator.py` — Cross-deal similarity scoring
- `deal_setup_extractor.py` — Deal setup field extraction
- `document_classifier.py` — Document type classification
- `document_hasher.py` — Content hashing and duplicate detection
- `document_tools.py` — Document manipulation utilities
- `output_comparator.py` — Model output comparison
- `parsers.py` — Section parsing and splitting
- `report_generator.py` — Report and governing doc generation

**Generation (3 modules):**
- `data_prep.py` — Monthly cashflow data preparation
- `model_runner.py` — Payment model execution engine
- `model_validator.py` — Output validation and comparison

**Ingestion (8 modules):**
- `governing_doc_generator.py` — 931 lines, governing document generation
- `knowledge_store.py` — Knowledge store builder
- `pipeline_runner.py` — Ingestion pipeline orchestration
- `section_splitter.py` — Document section splitting
- `structured_extractor.py` — Structured data extraction
- `definition_resolution.py` — Term definition resolution
- `document_converter.py` — Document format conversion
- `document_intelligence.py` — Classification and duplicate detection

**Quality (6 modules, ~800 lines):**
- `quality_gate.py` — 5-dimension quality evaluation
- `confidence.py` — Confidence scoring and tier classification
- `escalation.py` — Escalation logic and reporting
- `output_contracts.py` — Output contract validation
- `pre_mortem.py` — Pre-mortem risk analysis
- `refine_loop.py` — Quality-driven refinement loop

**Config & Scoping (4 modules):**
- `deal_scope.py` — 251 lines, filesystem isolation per deal
- `deal_manifest.py` — 256 lines, deal metadata and document tracking
- `errors.py` — 464 lines, 25+ error classes with structured logging
- `pipeline_config.py` — 300 lines, configuration dataclasses

---

## What Is NOT Being Ported

These modules are **replaced** by existing KTS infrastructure:

| PayGen Module | Replaced By (KTS) | Reason |
|---------------|-------------------|--------|
| `embedder.py` (136 lines) | `backend/vector/embedding_provider.py` | KTS provider is more mature (query prefix, ChromaDB adapter, model hash) |
| `graph_builder.py` (294 lines) | `backend/graph/enhanced_graph_builder.py` | KTS graph has 14 node types, PageRank, resolution trees vs PayGen's 7 flat types |
| `vector_search.py` (179 lines) | `backend/retrieval/retrieval_service.py` (2,714 lines) | KTS has 31 retrieval modules vs PayGen's basic search |

---

## Architecture Decision

### Subpackage Pattern: `backend/abs/`

ABS domain logic will live in a new `backend/abs/` subpackage, parallel to existing modules:

```
backend/
├── abs/                          ← NEW: ABS domain logic
│   ├── __init__.py
│   ├── agents/                   ← 13 ABS-specific agents
│   ├── skills/                   ← 14 domain skills
│   ├── generation/               ← 3 model generation modules
│   ├── ingestion/                ← 8 ingestion modules
│   └── config/                   ← ABS-specific config
├── agents/                       ← Existing KTS agents (enriched AgentBase)
├── common/                       ← Shared: quality, models, errors
├── graph/                        ← Shared: graph builder
├── retrieval/                    ← Shared: retrieval service
└── vector/                       ← Shared: vector stores
```

### AgentBase Merge Strategy

KTS's 24-line `AgentBase` is replaced by PayGen's 414-line version, with backward-compatible adaptations:

```python
# PayGen's AgentBase gains:
# - KTSConfig as constructor parameter (alongside DealScope)
# - Default no-op implementations for abstract methods
#   so existing KTS agents don't break
# - DealScope becomes optional (None for non-ABS agents)

class AgentBase(ABC):
    def __init__(self, agent_name, config: KTSConfig, 
                 deal_scope: Optional[DealScope] = None,
                 tool_registry: Optional[ToolRegistry] = None):
        ...
```

### Quality Infrastructure Merge

PayGen's 6 quality modules (~800 lines) move into `backend/common/` alongside KTS's existing `quality_gate.py` (63 lines):

- PayGen's `quality_gate.py` **replaces** KTS's — it's a strict superset (5-dimension scoring vs simple threshold)
- PayGen's `confidence.py`, `escalation.py`, `output_contracts.py`, `pre_mortem.py`, `refine_loop.py` are **new additions**
- KTS's existing `QualityGate` interface is preserved via an adapter

---

## Value Proposition

### Before Phase 21
- Two separate, incompatible projects
- Payment Generator has no LLM, no retrieval depth, no extension
- KTS has no ABS domain knowledge
- Maintaining two codebases doubles effort

### After Phase 21
- Single unified codebase
- ABS domain logic compiles inside KTS
- Enriched AgentBase available to ALL agents (KTS + ABS)
- 5-dimension quality gate available to ALL agents
- Foundation ready for LLM wiring (Phase 22) and extension integration (Phase 23)

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Import conflicts during rewrite | 🟡 Medium | 🟡 Medium | Systematic grep-and-replace; full test suite validation |
| AgentBase merge breaks existing KTS agents | 🟡 Medium | 🟠 High | Default no-op abstract methods; backward-compat adapter |
| DealScope conflicts with KTS ScopeResolver | ⚪ Low | 🟡 Medium | Coexistence: ScopeResolver for query routing, DealScope for filesystem isolation |
| Config namespace collision | ⚪ Low | ⚪ Low | Flat `abs_*` prefix on KTSConfig (consistent with existing `phase6_*`, `phase17_*` pattern) |
| Test failures after import rewrite | 🟡 Medium | 🟡 Medium | Run PayGen's 479 tests after each module migration |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| All PayGen modules importable from `backend.abs.*` | ✅ |
| All 479 PayGen tests pass after import rewrite | ✅ |
| All existing KTS tests pass (no regression) | ✅ |
| AgentBase merge: both KTS and ABS agents instantiate correctly | ✅ |
| Quality gate: 5-dimension scoring works for both KTS and ABS agents | ✅ |
| `backend/abs/` folder structure matches spec | ✅ |
| Zero duplicate code between `backend/abs/` and `backend/` | ✅ |

---

## Relationship to Phases 22 & 23

```
Phase 21 (THIS)              Phase 22                    Phase 23
┌──────────────────┐    ┌──────────────────────┐    ┌──────────────────┐
│ Scaffold backend/│    │ Replace embedder,    │    │ @abs chat        │
│ abs/, copy code, │───►│ graph, vector with   │───►│ participant,     │
│ merge AgentBase, │    │ KTS infrastructure,  │    │ CLI commands,    │
│ merge quality    │    │ wire LLM via VS Code │    │ VSIX packaging,  │
│                  │    │ LM API (GPT-4.1)    │    │ integration tests│
└──────────────────┘    └──────────────────────┘    └──────────────────┘
   Structural               Functional                 User-Facing
```

**Phase 21 is a prerequisite for Phase 22.** Phase 22 is a prerequisite for Phase 23. They must execute in order.
