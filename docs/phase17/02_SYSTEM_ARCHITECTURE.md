# Phase 17: System Architecture
## Deal-Scoped Storage, Dual Graph, and Unified Retrieval Pipeline

**Document Version:** 1.0  
**Date:** February 22, 2026  
**Status:** Proposal — Pending Approval  
**Scope:** System-level architecture, storage layout, data flow, and integration points

---

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Storage Layout](#storage-layout)
3. [Ingestion Data Flow](#ingestion-data-flow)
4. [Retrieval Data Flow](#retrieval-data-flow)
5. [Component Interaction Map](#component-interaction-map)
6. [Configuration System](#configuration-system)
7. [Backward Compatibility](#backward-compatibility)

---

## Architecture Overview

### Design Principles

1. **Single ChromaDB per deal** — document isolation via metadata filtering, not collection splitting
2. **Dual graph per deal** — doc-specific graphs for precision, deal graph for cross-doc reasoning
3. **Unified scope resolution** — single code path resolves all scope expressions (slug, wildcard, structured)
4. **Parallel multi-scope execution** — embarrassingly parallel search across independent deal stores
5. **Composable command syntax** — modes, scopes, doc filters combine orthogonally

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USER INTERFACE LAYER                               │
│                                                                              │
│  VS Code Chat:  @kts /fin_deal1/PSA What is the Distribution Date?          │
│                                                                              │
│  CLI:  kts search "What is ..." --scope-override fin_deal1 --doc-filter PSA │
│                                                                              │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SCOPE RESOLUTION PIPELINE                             │
│                                                                              │
│  Input Tokens → Mode Detection → Scope Resolution → Doc Filter Extraction  │
│                                                                              │
│  Components:                                                                 │
│    TokenParser  →  CatalogResolver  →  ScopeConfig  →  GraphSelector       │
│                                                                              │
│  Output: List[ResolvedScope]                                                 │
│    {scope_slug, kb_path, doc_filter, graph_path, vector_store_path}         │
│                                                                              │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
              Single Scope    Multi-Scope    Wildcard/Catalog
                    │              │              │
                    ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        RETRIEVAL SERVICE (per scope)                          │
│                                                                              │
│  For EACH resolved scope:                                                    │
│    1. Load scoped config → ChromaDB path, graph path                        │
│    2. Select graph: doc_filter ? doc_graphs/X.json : knowledge_graph.json   │
│    3. Build vector filter: doc_filter ? {doc_name_prefix: X} : None         │
│    4. Run HumanLikeRetriever / IterativeOrchestrator                        │
│    5. Tag results with {deal, doc_type, scope_slug}                         │
│                                                                              │
│  Multi-scope: asyncio.gather() for parallel execution                       │
│                                                                              │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RESULT AGGREGATION LAYER                             │
│                                                                              │
│  Mode-specific post-processing:                                              │
│    search    → Merge + deduplicate + re-rank                                │
│    compare   → Side-by-side alignment                                        │
│    diff      → Semantic delta detection + highlighting                       │
│    aggregate → Pattern extraction + outlier detection                        │
│    audit     → Anomaly scoring + completeness check                         │
│    define    → Cross-doc definition resolution                              │
│    list      → Catalog entry display                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Storage Layout

### Directory Structure

```
kb_test/                                    ← Knowledge source root
├── deal_catalog.db                         ← SQLite deal catalog (shared)
│
├── Fin_deal1/                              ← Deal folder
│   ├── PSA_BearStearns_2006HE1.doc        ← Source document
│   ├── Prosupp_BearStearns_2006HE1.pdf    ← Source document
│   └── .kts/                               ← Deal-scoped KTS data
│       ├── manifest.json                   ← Ingested file manifest
│       ├── vectors/
│       │   ├── chroma/                     ← Phase 5 legacy vector store
│       │   └── phase6/                     ← Phase 6 dual vector store
│       │       ├── chroma.sqlite3          ← ChromaDB (ALL docs in deal)
│       │       └── ...                     ← HNSW indices
│       └── graph/
│           ├── knowledge_graph.json        ← DEAL graph (all docs, cross-doc edges)
│           └── doc_graphs/                 ← NEW: Per-document graphs
│               ├── PSA.json               ← PSA-only nodes and edges
│               └── PROSUPP.json           ← PROSUPP-only nodes and edges
│
├── Fin_deal2/                              ← Another deal folder
│   ├── PSA_BearStearns_2006HE2.doc
│   ├── Prosupp_BearStearns_2006HE2.pdf
│   └── .kts/
│       ├── manifest.json
│       ├── vectors/
│       │   └── phase6/
│       └── graph/
│           ├── knowledge_graph.json
│           └── doc_graphs/
│               ├── PSA.json
│               └── PROSUPP.json
│
└── ... (more deal folders)
```

### ChromaDB Collection Schema

**Single collection per deal** (`kts_items` / `kts_sections`):

```
┌───────────────────────────────────────────────────────────────┐
│  ChromaDB Collection: kts_items                                │
│                                                                │
│  Document 1 chunks:                                           │
│    id: "doc-sec0001-DEF-0-abc123"                             │
│    text: "Distribution Date means the 25th day..."            │
│    metadata: {                                                 │
│      "section_number": "1.01",                                │
│      "section_heading": "Definitions",                        │
│      "item_type": "Definition",                               │
│      "document_id": "PSA_BearStearns_2006HE1",               │
│      "doc_name_prefix": "PSA",          ← FILTER KEY          │
│      "doc_type": "GOVERNING_DOC_LEGAL",                       │
│    }                                                           │
│                                                                │
│  Document 2 chunks:                                           │
│    id: "doc-sec0015-STMT-0-def456"                            │
│    text: "The Distribution Date for each period..."           │
│    metadata: {                                                 │
│      "section_number": "4.01",                                │
│      "item_type": "Statement",                                │
│      "document_id": "Prosupp_BearStearns_2006HE1",           │
│      "doc_name_prefix": "PROSUPP",      ← FILTER KEY          │
│      "doc_type": "GOVERNING_DOC_LEGAL",                       │
│    }                                                           │
│                                                                │
│  Query with doc filter:                                        │
│    collection.query(                                           │
│      query_texts=["Distribution Date"],                       │
│      where={"doc_name_prefix": "PSA"},   ← Only PSA chunks    │
│      n_results=10,                                            │
│    )                                                           │
│                                                                │
│  Query without doc filter:                                     │
│    collection.query(                                           │
│      query_texts=["Distribution Date"],                       │
│      n_results=10,                       ← All docs in deal   │
│    )                                                           │
│                                                                │
└───────────────────────────────────────────────────────────────┘
```

---

## Ingestion Data Flow

### Phase 17 Ingestion Pipeline

```
User selects source folder: kb_test/
                    │
                    ▼
┌──────────────────────────────────────────────────────┐
│  CLI: kts ingest kb_test/                             │
│                                                       │
│  Step 1: Discover subfolders                          │
│    → Fin_deal1/, Fin_deal2/, ...                     │
│                                                       │
│  Step 2: Group files by parent subfolder              │
│    → Fin_deal1: [PSA_*.doc, Prosupp_*.pdf]           │
│    → Fin_deal2: [PSA_*.doc, Prosupp_*.pdf]           │
│                                                       │
│  Step 3: For EACH deal folder:                        │
│    3a. Create scoped config via scope_config()        │
│        → kb_path = Fin_deal1/.kts/                   │
│    3b. Ingest all files into SINGLE ChromaDB          │
│        → Each chunk gets doc_name_prefix metadata     │
│    3c. Build deal-level graph (all docs)              │
│        → Add cross-doc edges                         │
│    3d. Partition deal graph → doc-specific graphs     │  ← NEW
│        → PSA.json, PROSUPP.json                      │
│    3e. Upsert deal catalog entry                      │
│        → doc_types: ["PSA", "PROSUPP"]               │
│                                                       │
└──────────────────────────────────────────────────────┘
```

### Graph Build + Partition Detail

```
Step 3c: Build deal-level graph
─────────────────────────────────
For each document in the deal folder:
  → Run EnhancedGraphBuilder.build_hierarchical_graph()
  → Creates: doc node, section nodes, item nodes
  → All nodes get doc_name_prefix attribute         ← NEW
  → Creates: CONTAINS, NEXT, HAS_RULE, HAS_DEFINITION, REFERENCES edges

After all docs are processed:
  → Run cross-doc edge builder (NEW):              ← NEW
    • TERM_DEFINED_IN → TERM_REFERENCED_IN
      (same term text appears in definition of Doc A and body of Doc B)
    • ENTITY_SHARED
      (same NER entity appears in both Doc A and Doc B)
    • CONCEPT_COOCCURRENCE
      (same concept_keyword in sections of different docs)
    • SECTION_CROSS_REF
      (explicit "as described in the PSA, Section X.XX" references)
  → Save as knowledge_graph.json

Step 3d: Partition into doc-specific graphs          ← NEW
─────────────────────────────────────────
For each unique doc_name_prefix found in the deal graph:
  → Create subgraph: all nodes where doc_name_prefix == X
  → Include edges where BOTH endpoints have doc_name_prefix == X
  → Exclude cross-doc edges (those live only in deal graph)
  → Save as doc_graphs/{PREFIX}.json
```

---

## Retrieval Data Flow

### Single-Scope Search

```
@kts /fin_deal1/PSA What is the Distribution Date?
                    │
                    ▼
Token Parser:
  mode = "search" (default)
  scopes = ["fin_deal1"]
  doc_filter = "PSA"
  query = "What is the Distribution Date?"
                    │
                    ▼
Scope Config:
  kb_path = "kb_test/Fin_deal1/.kts/"
  chroma_dir = "kb_test/Fin_deal1/.kts/vectors/phase6/"
  graph_path = "kb_test/Fin_deal1/.kts/graph/doc_graphs/PSA.json"   ← doc graph
  vector_filter = {"doc_name_prefix": "PSA"}
                    │
                    ▼
HumanLikeRetriever:
  graph_section_lookup() → uses PSA.json only
  search_items(filters={"doc_name_prefix": "PSA"}) → only PSA chunks
  search_sections(filters={"doc_name_prefix": "PSA"}) → only PSA sections
                    │
                    ▼
Result:
  [{text: "Distribution Date means the 25th day...",
    deal: "fin_deal1", doc: "PSA", section: "1.01", score: 0.96}]
```

### Multi-Scope Parallel Search

```
@kts /compare /bear_stearns_2006*/PSA What is the Distribution Date?
                    │
                    ▼
Token Parser:
  mode = "compare"
  scope_pattern = "bear_stearns_2006*"
  doc_filter = "PSA"
  query = "What is the Distribution Date?"
                    │
                    ▼
Catalog Resolution:
  catalog.search("bear_stearns_2006") → [deal1, deal2, deal3, ...]
  OR catalog.search with slug GLOB match
                    │
                    ▼
Parallel Execution (asyncio.gather):
  ┌──────────────┬──────────────┬──────────────────────┐
  │ Scope: deal1 │ Scope: deal2 │ Scope: deal3  ...    │
  │ Graph: PSA   │ Graph: PSA   │ Graph: PSA           │
  │ Filter: PSA  │ Filter: PSA  │ Filter: PSA          │
  │ Result: [...]│ Result: [...]│ Result: [...]         │
  └──────┬───────┴──────┬───────┴──────────┬───────────┘
         │              │                  │
         ▼              ▼                  ▼
Comparison Engine:
  Align results by semantic similarity
  Output: Side-by-side table with differences highlighted
```

---

## Component Interaction Map

### Modified Files (from existing codebase)

| Component | File | Change Type | Description |
|-----------|------|------------|-------------|
| **Config** | `config/settings.py` | MODIFY | Add `doc_filter` param support |
| **CLI** | `cli/main.py` | MODIFY | Add `--doc-filter` option, wire modes |
| **Ingestion Agent** | `backend/agents/ingestion_agent.py` | MODIFY | Add `doc_name_prefix` to graph nodes |
| **Enhanced Graph Builder** | `backend/graph/enhanced_graph_builder.py` | MODIFY | Accept `doc_name_prefix`, partition output |
| **Graph Schema** | `backend/graph/schema.py` | MODIFY | Add cross-doc edge types |
| **Graph Persistence** | `backend/graph/persistence.py` | MODIFY | Support doc_graphs/ subdirectory |
| **Retrieval Service** | `backend/agents/retrieval_service.py` | MODIFY | Wire doc_filter through pipeline |
| **Human-Like Retriever** | `backend/retrieval/human_like_retriever.py` | MODIFY | Pass doc_filter to all search calls |
| **Dual Vector Store** | `backend/vector/dual_vector_store.py` | NO CHANGE | Already accepts `filters` dict |
| **Deal Catalog** | `backend/vector/deal_catalog.py` | MODIFY | Add wildcard/glob + structured query |
| **Scope Discovery** | `extension/lib/scope_discovery.js` | MODIFY | Return doc_types per scope |
| **Chat Participant** | `extension/chat/participant.js` | MODIFY | New token parser |
| **KTS Tool** | `extension/copilot/kts_tool.js` | MODIFY | Forward doc_filter + mode |
| **Select Source** | `extension/commands/select_source.js` | NO CHANGE | Already sets knowledgeSourceRoot |
| **Package.json** | `extension/package.json` | MODIFY | New settings if needed |

### New Files

| Component | File | Description |
|-----------|------|-------------|
| **Scope Resolver** | `backend/retrieval/scope_resolver.py` | NEW — Unified scope resolution pipeline |
| **Token Parser** | `backend/retrieval/token_parser.py` | NEW — Parse command tokens from user input |
| **Cross-Doc Edge Builder** | `backend/graph/cross_doc_edges.py` | NEW — Build edges between documents in same deal |
| **Graph Partitioner** | `backend/graph/graph_partitioner.py` | NEW — Split deal graph into doc-specific graphs |
| **Diff Engine** | `backend/retrieval/diff_engine.py` | NEW — Semantic diff between retrieval results |
| **Aggregation Engine** | `backend/retrieval/aggregation_engine.py` | NEW — Portfolio-level pattern + outlier detection |

---

## Configuration System

### New Config Fields in `KTSConfig`

```python
@dataclass
class KTSConfig:
    # ... existing fields ...

    # Phase 17: Document-level isolation
    doc_filter_enabled: bool = True           # Enable doc_name_prefix filtering
    doc_graphs_enabled: bool = True           # Build per-doc graph partitions
    cross_doc_edges_enabled: bool = True      # Build cross-doc edges in deal graph
    doc_graphs_dir: str = "graph/doc_graphs"  # Subdirectory for doc graphs

    # Phase 17: Multi-deal queries
    max_parallel_scopes: int = 20             # Max concurrent scope searches
    wildcard_max_matches: int = 50            # Max deals matched by wildcard
    multi_scope_timeout_ms: int = 30000       # Timeout for multi-scope queries

    # Phase 17: Comparison modes
    diff_mode_enabled: bool = True            # Enable /diff command
    aggregate_mode_enabled: bool = True       # Enable /aggregate command
    diff_similarity_threshold: float = 0.85   # Below this = "different"
    aggregate_outlier_threshold: float = 0.70 # Below this = "outlier"
```

### Feature Flags

All Phase 17 features are gated behind flags:
- `doc_filter_enabled` — controls whether `doc_name_prefix` filter is applied at search time
- `doc_graphs_enabled` — controls whether doc-specific graphs are built during ingestion
- `cross_doc_edges_enabled` — controls whether cross-doc edges are added to deal graph
- `diff_mode_enabled` / `aggregate_mode_enabled` — control new comparison modes

Flags default to `True` but can be overridden via config file or environment variables for gradual rollout or debugging.

---

## Backward Compatibility

### Existing Behavior Preserved

| Scenario | Pre-Phase 17 | Post-Phase 17 |
|----------|-------------|---------------|
| `@kts /fin_deal1 What is ...?` | Searches deal ChromaDB, deal graph | **Identical** — no doc filter → same behavior |
| `@kts /compare /fin_deal1 /fin_deal2 ...` | Comparison mode | **Identical** — no doc filter changes |
| `kts ingest kb_test/` | Per-deal .kts/, single graph | **Same + additional** doc graphs built |
| Single-deal, single-doc workspace | Global .kts/ | **Identical** — falls back to global when no subfolders |

### Migration Path

No migration required. Phase 17 is purely additive:
- New metadata key (`doc_name_prefix`) already written by Phase 12.1 ingestion
- New graph files (`doc_graphs/`) are created alongside existing `knowledge_graph.json`
- New CLI options (`--doc-filter`, `--mode`) are optional with backward-compatible defaults
- New extension syntax (`/scope/DOC`) is a superset of existing `/scope` syntax

---

*End of Document — 02_SYSTEM_ARCHITECTURE.md*
