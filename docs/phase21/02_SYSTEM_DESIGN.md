# Phase 21: System Design
## ABS Domain Integration — Subpackage Architecture

**Document Version:** 1.0  
**Date:** February 26, 2026  
**Status:** Proposal — Pending Approval  
**Scope:** System-level architecture and data flows for ABS domain integration

---

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Current System Architecture](#current-system-architecture)
3. [Proposed System Architecture](#proposed-system-architecture)
4. [Component Mapping](#component-mapping)
5. [Data Flow](#data-flow)
6. [Integration Points](#integration-points)
7. [Scoping Architecture](#scoping-architecture)
8. [Configuration Architecture](#configuration-architecture)
9. [Error Handling Architecture](#error-handling-architecture)
10. [Backward Compatibility](#backward-compatibility)

---

## Architecture Overview

### Design Principles

1. **Subpackage Isolation** — ABS domain logic lives in `backend/abs/`, cleanly separated from KTS infrastructure
2. **Shared Infrastructure** — ABS agents use KTS's vector, graph, retrieval, and embedding modules (wired in Phase 22)
3. **Unified Agent Framework** — Single enriched AgentBase serves both KTS and ABS agents
4. **Dual Scoping** — KTS's `ScopeResolver` handles query routing; PayGen's `DealScope` handles filesystem isolation. They coexist.
5. **Config Namespace** — ABS config uses flat `abs_*` prefix on `KTSConfig` (consistent with `phase6_*`, `phase17_*`)

---

## Current System Architecture

### KTS Before Phase 21

```
┌─────────────────────────────────────────────────────────────┐
│                    VS Code Extension                         │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ @kts chat   │  │ Commands     │  │ Webview Panels   │  │
│  │ participant │  │ (13 modules) │  │                  │  │
│  └──────┬──────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                │                    │             │
│         └────────────────┼────────────────────┘             │
│                          │                                   │
│                    kts_tool.js (CLI bridge)                  │
└──────────────────────────┼──────────────────────────────────┘
                           │ subprocess
┌──────────────────────────┼──────────────────────────────────┐
│                      CLI (Click)                             │
│  crawl, ingest, search, training, impact, freshness,        │
│  describe, status, diff, enrich-vocabulary, list-deals,     │
│  ingest-onenote                                              │
└──────────────────────────┼──────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────┐
│                     Backend                                   │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ agents/ (15) │  │ retrieval/   │  │ vector/ (12)     │  │
│  │              │  │ (31 modules) │  │ dual/triple      │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │             │
│  ┌──────▼───────┐  ┌──────▼───────┐  ┌────────▼─────────┐  │
│  │ common/      │  │ graph/ (17)  │  │ ingestion/ (17)  │  │
│  │ models,      │  │ hierarchical │  │ converters       │  │
│  │ quality_gate │  │ PageRank     │  │                  │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐                         │
│  │ extraction/  │  │ data/        │                         │
│  │ items, NER   │  │ deal_catalog │                         │
│  └──────────────┘  └──────────────┘                         │
└──────────────────────────────────────────────────────────────┘
```

### Payment Generator Before Phase 21

```
┌───────────────────────────────────────────────────────────────┐
│                   AI Payment Generator                         │
│                                                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ agents/ (13) │  │ skills/ (14) │  │ generation/ (3)  │   │
│  │ rich base    │  │ cashflow,    │  │ model_runner,    │   │
│  │ 5-dim quality│  │ parsers      │  │ validator        │   │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘   │
│         │                 │                    │              │
│  ┌──────▼───────┐  ┌──────▼───────┐  ┌────────▼─────────┐   │
│  │ quality/ (6) │  │ ingestion/   │  │ config/ (6)      │   │
│  │ 800 lines    │  │ (8 modules)  │  │ PipelineConfig   │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
│                                                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ deal_scope   │  │ deal_manifest│  │ errors (464 ln)  │   │
│  │ (251 lines)  │  │ (256 lines)  │  │ 25+ error types  │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
│                                                                │
│  CLI: main.py (Click)                                         │
│  ingest, generate, compare-deals, compare-outputs, audit,     │
│  smoke-test, qa                                                │
└───────────────────────────────────────────────────────────────┘
```

---

## Proposed System Architecture

### KTS After Phase 21

```
┌──────────────────────────────────────────────────────────────────┐
│                      VS Code Extension                            │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ @kts chat   │  │ @abs chat    │  │ Commands + Panels      │  │
│  │ participant │  │ (Phase 23)   │  │                        │  │
│  └──────┬──────┘  └──────┬───────┘  └────────┬───────────────┘  │
│         └────────────────┼────────────────────┘                  │
│                          │                                        │
│                    kts_tool.js (CLI bridge)                       │
└──────────────────────────┼───────────────────────────────────────┘
                           │ subprocess
┌──────────────────────────┼───────────────────────────────────────┐
│                      CLI (Click)                                  │
│  EXISTING: crawl, ingest, search, training, ...                  │
│  NEW (Phase 23): abs-ingest, abs-generate, abs-audit, abs-qa     │
└──────────────────────────┼───────────────────────────────────────┘
                           │
┌──────────────────────────┼───────────────────────────────────────┐
│                     Backend                                       │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │                   backend/abs/  (NEW)                      │   │
│  │                                                            │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │   │
│  │  │ agents/ (13)│  │ skills/ (14)│  │ generation/ (3) │   │   │
│  │  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘   │   │
│  │         │                │                   │            │   │
│  │  ┌──────▼──────┐  ┌──────▼──────┐  ┌────────▼────────┐   │   │
│  │  │ ingestion/  │  │ config/     │  │ deal_scope.py   │   │   │
│  │  │ (8 modules) │  │ (constants, │  │ deal_manifest.py│   │   │
│  │  │             │  │  schemas)   │  │ errors.py       │   │   │
│  │  └─────────────┘  └────────────┘  └─────────────────┘   │   │
│  └───────────────────────────┬───────────────────────────────┘   │
│                              │ uses                               │
│  ┌───────────────────────────▼───────────────────────────────┐   │
│  │              Shared Infrastructure (existing)              │   │
│  │                                                            │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │   │
│  │  │ agents/  │  │retrieval/│  │ vector/  │  │ graph/   │ │   │
│  │  │ base     │  │ service  │  │ dual     │  │ builder  │ │   │
│  │  │ (merged) │  │ (31 mod) │  │ (12 mod) │  │ (17 mod) │ │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │   │
│  │                                                            │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │   │
│  │  │ common/  │  │extraction│  │ingestion/│  │ data/    │ │   │
│  │  │ quality  │  │ items    │  │converters│  │ catalog  │ │   │
│  │  │ (merged) │  │          │  │          │  │          │ │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │   │
│  └────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

---

## Component Mapping

### File-Level Mapping: PayGen → KTS

| Source (PayGen `pipeline/`) | Destination (KTS `backend/`) | Action |
|-----------------------------|------------------------------|--------|
| `agents/agent_base.py` | `agents/base_agent.py` | **MERGE** — Enrich KTS base with PayGen's 414-line version |
| `agents/agent_tools.py` | `agents/agent_tools.py` | **COPY** — New file alongside base_agent |
| `agents/cashflow_projection_agent.py` | `abs/agents/cashflow_projection_agent.py` | **COPY + REWRITE** imports |
| `agents/deal_amendment_agent.py` | `abs/agents/deal_amendment_agent.py` | **COPY + REWRITE** imports |
| `agents/deal_lifecycle_agent.py` | `abs/agents/deal_lifecycle_agent.py` | **COPY + REWRITE** imports |
| `agents/document_comparison_agent.py` | `abs/agents/document_comparison_agent.py` | **COPY + REWRITE** imports |
| `agents/document_quality_agent.py` | `abs/agents/document_quality_agent.py` | **COPY + REWRITE** imports |
| `agents/ingestion_pipeline_agent.py` | `abs/agents/ingestion_pipeline_agent.py` | **COPY + REWRITE** imports |
| `agents/investor_reporting_agent.py` | `abs/agents/investor_reporting_agent.py` | **COPY + REWRITE** imports |
| `agents/model_auditor_agent.py` | `abs/agents/model_auditor_agent.py` | **COPY + REWRITE** imports |
| `agents/model_creation_agent.py` | `abs/agents/model_creation_agent.py` | **COPY + REWRITE** imports |
| `agents/qa_agent.py` | `abs/agents/qa_agent.py` | **COPY + REWRITE** imports |
| `agents/regression_testing_agent.py` | `abs/agents/regression_testing_agent.py` | **COPY + REWRITE** imports |
| `agents/stress_testing_agent.py` | `abs/agents/stress_testing_agent.py` | **COPY + REWRITE** imports |
| `skills/*.py` (14 files) | `abs/skills/*.py` | **COPY + REWRITE** imports |
| `generation/*.py` (3 files) | `abs/generation/*.py` | **COPY + REWRITE** imports |
| `ingestion/*.py` (8 files) | `abs/ingestion/*.py` | **COPY + REWRITE** imports |
| `quality/*.py` (6 files) | `common/quality/` | **MERGE** — PayGen's quality replaces KTS's 63-line quality_gate |
| `deal_scope.py` | `abs/deal_scope.py` | **COPY + ADAPT** to KTS knowledge base pattern |
| `deal_manifest.py` | `abs/deal_manifest.py` | **COPY + ADAPT** to KTS ManifestStore |
| `errors.py` | `abs/errors.py` | **COPY** — ABS-specific error hierarchy |
| `config/pipeline_config.py` | `abs/config/abs_config.py` | **COPY + ADAPT** to `abs_*` prefix on KTSConfig |
| `config/constants.py` | `abs/config/constants.py` | **COPY** |
| `config/schemas.py` | `abs/config/schemas.py` | **COPY** |
| `config/section_maps.py` | `abs/config/section_maps.py` | **COPY** |
| `embedder.py` | ❌ NOT COPIED | Replaced by `backend/vector/embedding_provider.py` |
| `graph_builder.py` | ❌ NOT COPIED | Replaced by `backend/graph/enhanced_graph_builder.py` |
| `vector_search.py` | ❌ NOT COPIED | Replaced by `backend/retrieval/retrieval_service.py` |

### Module Count Summary

| Category | Modules Copied | Modules Merged | Modules Dropped |
|----------|---------------|---------------|-----------------|
| Agents | 13 | 1 (AgentBase) | 0 |
| Skills | 14 | 0 | 0 |
| Generation | 3 | 0 | 0 |
| Ingestion | 8 | 0 | 0 |
| Quality | 0 | 6 (into common/) | 0 |
| Config | 4 | 1 (into KTSConfig) | 0 |
| Scoping | 2 | 0 | 0 |
| Errors | 1 | 0 | 0 |
| Infra | 0 | 0 | 3 (replaced) |
| **Total** | **45** | **8** | **3** |

---

## Data Flow

### ABS Ingestion Pipeline (After Phase 21)

```
PSA/Indenture PDF
        │
        ▼
┌───────────────────┐
│ document_converter│ (abs/ingestion/)
│ PDF → text        │
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ document_         │ (abs/ingestion/)
│ intelligence      │
│ classify + dedup  │
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ section_splitter  │ (abs/ingestion/)
│ Split by Article/ │
│ Section headers   │
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ structured_       │ (abs/ingestion/)
│ extractor         │
│ Extract waterfalls│
│ definitions, rules│
└───────┬───────────┘
        │
        ▼ (Phase 22: wire to KTS vector/graph)
┌───────────────────┐
│ knowledge_store   │ → ChromaDB (KTS DualVectorStore)
│                   │ → NetworkX (KTS EnhancedGraphBuilder)
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ governing_doc_    │ (abs/ingestion/)
│ generator         │ → LLM (Phase 22: VS Code LM API)
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ DealManifest      │
│ Persist metadata  │
└───────────────────┘
```

### ABS Model Generation Pipeline (After Phase 21)

```
DealManifest (ready_for_generation = true)
        │
        ▼
┌───────────────────┐
│ data_prep         │ (abs/generation/)
│ Load deal setup,  │
│ class def, monthly│
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ model_creation_   │ (abs/agents/)
│ agent             │ → LLM (Phase 22: VS Code LM API)
│ Generate Python   │
│ payment model     │
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ model_runner      │ (abs/generation/)
│ Execute model for │
│ each payment date │
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ model_validator   │ (abs/generation/)
│ Compare outputs   │
│ to expected CSV   │
└───────────────────┘
```

---

## Integration Points

### Shared Agent Framework

After AgentBase merge, the inheritance hierarchy is:

```python
# backend/agents/base_agent.py (MERGED — 414+ lines)
class AgentBase(ABC):
    """Unified agent base for KTS + ABS agents."""
    
    def __init__(self, agent_name: str, config: KTSConfig,
                 deal_scope: Optional['DealScope'] = None,
                 tool_registry: Optional['ToolRegistry'] = None):
        self.agent_name = agent_name
        self.config = config
        self.deal_scope = deal_scope          # None for KTS agents
        self.tool_registry = tool_registry    # None for KTS agents
        self.quality_gate = QualityGate(config)

# KTS agents (unchanged interface):
class CrawlerAgent(AgentBase):
    def __init__(self, config: KTSConfig):
        super().__init__("crawler", config)    # deal_scope=None

# ABS agents (full interface):
class ModelCreationAgent(AgentBase):
    def __init__(self, deal_scope: DealScope, config: KTSConfig):
        super().__init__("model-creation", config, deal_scope=deal_scope,
                         tool_registry=get_global_registry())
```

### Shared Quality Gate

```python
# backend/common/quality_gate.py (MERGED — PayGen's 5-dimension version)
class QualityGate:
    """5-dimension quality evaluation."""
    
    DIMENSIONS = [
        QualityDimension.COMPLETENESS,
        QualityDimension.ACCURACY,
        QualityDimension.CITATION_FIDELITY,
        QualityDimension.STRUCTURAL_CONFORMANCE,
        QualityDimension.DEAL_SCOPE_COMPLIANCE,
    ]

    def apply(self, result: AgentResult) -> AgentResult:
        """Score result across 5 dimensions. 
        For KTS agents that don't override scorers, defaults return 8.0."""
        ...
```

---

## Scoping Architecture

### Dual Scoping Model

Two scoping systems coexist, serving different purposes:

```
┌──────────────────────────────────────────────────────────┐
│                   Query/Command Entry                     │
│                                                           │
│  "What waterfall rules apply to Bear Stearns 2006-HE1?"  │
└─────────────────────────┬─────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 │                 ▼
┌───────────────┐         │      ┌───────────────────┐
│ ScopeResolver │         │      │    DealScope       │
│ (KTS)         │         │      │    (PayGen/ABS)    │
│               │         │      │                    │
│ Routes query  │         │      │ Filesystem         │
│ to correct    │         │      │ isolation per deal │
│ knowledge     │         │      │                    │
│ source / deal │         │      │ deals/             │
│               │         │      │   bear_2006_he1/   │
│ "Which KB?"   │         │      │     documents/     │
│               │         │      │     vectorstore/   │
└───────┬───────┘         │      │     graph/         │
        │                 │      │     data/           │
        │    both used    │      │     escalations/   │
        │    together     │      │                    │
        └─────────────────┘      └───────────────────┘
```

**ScopeResolver** answers: "Which knowledge source should handle this query?"  
**DealScope** answers: "Where on disk are this deal's files, and can I write there?"

---

## Configuration Architecture

### `abs_*` Config Properties on KTSConfig

New properties follow the established naming convention (`phase6_*`, `phase17_*`):

```python
# Added to config/settings.py KTSConfig dataclass:

# ABS Domain (Phase 21)
abs_enabled: bool = False                          # Master toggle
abs_deals_root: str = "deals"                      # Root dir for deal folders
abs_extraction_mode: str = "hybrid"                # "template" | "llm" | "hybrid"
abs_min_quality_score: float = 8.0                 # Quality gate threshold
abs_max_retries: int = 3                           # Agent retry limit
abs_confidence_high: float = 0.90                  # High confidence tier
abs_confidence_low: float = 0.66                   # Low confidence tier
abs_vectorstore_enabled: bool = True               # Enable vector storage
abs_graph_enabled: bool = True                     # Enable graph storage
abs_embedding_dim: int = 768                       # Embedding dimensions
abs_chunk_max_chars: int = 3000                    # Max chunk size
abs_chunk_overlap: int = 500                       # Chunk overlap
abs_normalize_embeddings: bool = True              # Normalize embeds
abs_definition_resolution_enabled: bool = True     # Enable def resolution
abs_definition_resolution_depth: int = 5           # Max resolution depth
abs_definition_resolution_confidence: float = 0.80 # Min confidence
```

Environment variable overrides: `KTS_ABS_ENABLED=true`, `KTS_ABS_DEALS_ROOT=deals`, etc.

---

## Error Handling Architecture

### Merged Error Hierarchy

```
Exception
├── BaseWaterfallError (ABS)                ← from backend.abs.errors
│   ├── ScopingError
│   │   └── DealScopingViolation
│   ├── ExtractionError
│   │   ├── SectionNotFoundError
│   │   ├── ParserError
│   │   └── EmptyExtractionError
│   ├── IngestionError
│   │   ├── DocumentClassificationError
│   │   ├── DuplicateDocumentError
│   │   ├── HashMismatchError
│   │   └── SectionSplitError
│   ├── VectorError
│   │   ├── ChromaConnectionError
│   │   ├── EmbeddingError
│   │   └── CollectionNotFoundError
│   ├── GraphError
│   │   ├── GraphBuildError
│   │   └── GraphQueryError
│   ├── ValidationError
│   │   ├── CSVSchemaError
│   │   ├── OutputMismatchError
│   │   └── QualityGateError
│   ├── GenerationError
│   │   ├── ModelGenerationError
│   │   ├── GoverningDocError
│   │   └── TemplateError
│   ├── ComparisonError
│   │   └── DealNotFoundError
│   ├── EscalationError
│   │   └── EscalationRequired
│   └── ConfigurationError
│       ├── MissingConfigError
│       └── InvalidSchemaError
│
└── (KTS existing exceptions — unchanged)
```

The ABS error hierarchy is **additive** — it does not modify any existing KTS exceptions. ABS agents raise `BaseWaterfallError` subclasses; KTS agents continue raising their existing exceptions.

---

## Backward Compatibility

### Guarantees

1. **All existing KTS imports continue to work** — No existing `from backend.X import Y` changes
2. **All existing KTS tests pass** — AgentBase merge uses default no-ops for new abstract methods
3. **All existing CLI commands unchanged** — New `abs-*` commands added alongside
4. **KTSConfig backward compatible** — New `abs_*` properties all have defaults; existing configs load without modification
5. **@kts chat participant unchanged** — `@abs` added as separate participant (Phase 23)

### Migration Path for Existing KTS Agents

Existing KTS agents need **zero changes** to work with the enriched AgentBase:

```python
# BEFORE (KTS agent — still works after merge):
class CrawlerAgent(AgentBase):
    def __init__(self, config):
        super().__init__("crawler", config)  # deal_scope defaults to None
    
    def execute(self, request):
        ...  # unchanged
```

The enriched AgentBase provides **default implementations** for all new abstract methods:

| New Method | Default Behavior |
|-----------|-----------------|
| `_get_mission()` | Returns `"No mission defined"` |
| `_get_actions()` | Returns `[]` |
| `_get_output_spec()` | Returns `"No output spec"` |
| `_get_validation_rules()` | Returns `[]` |
| `_score_completeness()` | Returns `8.0` |
| `_score_accuracy()` | Returns `8.0` |
| `_score_citations()` | Returns `8.0` |
| `_score_structure()` | Returns `8.0` |
| `_score_scope()` | Returns `10.0` |
