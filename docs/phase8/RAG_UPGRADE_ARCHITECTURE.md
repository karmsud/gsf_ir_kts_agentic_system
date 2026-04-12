# Phase 8: RAG Upgrade — Architecture Document

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## 1. Architectural Principles

### 1.1 Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Graft, don't replace** | 6 months of domain-specific engineering (legal chunker, graph retrieval, item classification) exceeds what any framework provides. Add techniques, don't rewrite. |
| **No LangChain dependency** | LangChain adds ~50 MB of dependencies, complex import chains, and version coupling. Adopt their *algorithms*, not their library. |
| **Feature-flagged** | Every Phase 8 technique is behind a config flag. Disabled = exact current behavior. |
| **Backward-compatible storage** | New indexes coexist with old. Missing metadata fields are handled gracefully. |
| **Pure Python, no new binaries** | BM25 and MMR are implemented in-house (~150 lines each). Zero new pip dependencies. |
| **LLM-at-ingestion is acceptable** | HyPE targets only ~100-180 high-value chunks (definitions + triggers). Same VS Code LM API pattern as `image_describer.js`. Time-bounded and gracefully rate-limited. |
| **LLM-at-query-time is opt-in** | Multi-Query expansion adds ~750ms overhead. Feature-flagged off by default until validated. |

### 1.2 Architectural Goals

1. **Precision:** BM25 hybrid search captures exact legal terminology
2. **Diversity:** MMR prevents redundant chunks from dominating context
3. **Context richness:** Parent expansion provides full section text from item-level matches
4. **Robustness:** Token trimming prevents LLM context overflow
5. **Embedding quality:** CCH anchors doc/section provenance in the embedding space
6. **Query-document gap closure:** HyPE generates query-style questions for definition/trigger chunks
7. **Phrasing resilience:** Multi-Query RAG Fusion resolves alternate query formulations
8. **Observability:** All new steps logged through ExplainabilityLogger
9. **Zero regression:** Comprehensive test gates at every implementation step

---

## 2. Layer Architecture

### 2.1 Current Layer Stack

```
┌─────────────────────────────────────────────────────┐
│                  PRESENTATION LAYER                  │
│  extension/chat/participant.js                       │
│  • Prompt selection (Legal vs KTS)                   │
│  • Context block construction                        │
│  • LLM streaming via VS Code LM API                  │
│  • Citation + trace rendering                        │
├─────────────────────────────────────────────────────┤
│                  ORCHESTRATION LAYER                  │
│  backend/agents/retrieval_service.py                 │
│  • Intent detection (15+ patterns)                   │
│  • Feature scoring (error codes, NER, keyphrases)    │
│  • Context window expansion                          │
│  • Evidence provenance enforcement                   │
├─────────────────────────────────────────────────────┤
│                  RETRIEVAL LAYER                      │
│  backend/retrieval/human_like_retriever.py           │
│  • 11-step pipeline (filter → decompose → graph →    │
│    scope → fallback → fuse → enrich → rerank →       │
│    boost → drill-down → confidence)                  │
│  backend/retrieval/cross_encoder.py                  │
│  • ONNX cross-encoder reranking                      │
├─────────────────────────────────────────────────────┤
│                  STORAGE LAYER                        │
│  backend/vector/dual_vector_store.py (ChromaDB)      │
│  backend/graph/persistence.py (NetworkX + JSON)      │
│  backend/vector/embedding_provider.py (BGE ONNX)     │
├─────────────────────────────────────────────────────┤
│                  INGESTION LAYER                      │
│  backend/agents/ingestion_agent.py                   │
│  backend/vector/legal_chunker.py                     │
│  backend/extraction/legal_item_extractor.py          │
│  backend/graph/enhanced_graph_builder.py             │
└─────────────────────────────────────────────────────┘
```

### 2.2 Phase 8 Layer Changes

```
┌─────────────────────────────────────────────────────┐
│                  PRESENTATION LAYER                  │
│  + trimContextToTokenBudget()     ← TOKEN TRIMMING   │
│  + expandQueryWithLLM()           ← MULTI-QUERY      │
│  + hype_enricher.js               ← HYPE ENRICHMENT  │
│  + gap_analyzer.js                ← SELF-RAG         │
│  + iterative_generator.js         ← SELF-RAG         │
├─────────────────────────────────────────────────────┤
│                  ORCHESTRATION LAYER                  │
│  (no changes)                                        │
├─────────────────────────────────────────────────────┤
│                  RETRIEVAL LAYER                      │
│  + BM25Retriever (new class)      ← BM25 HYBRID     │
│  + RRF fusion of BM25 + vector    ← BM25 HYBRID     │
│  + Parent section expansion       ← PARENT-CHILD    │
│  + MMR selection in global search ← MMR DIVERSITY    │
│  + _multi_query_retrieve()        ← MULTI-QUERY      │
│  + _rrf_merge() across query lists ← MULTI-QUERY    │
│  + search_item_questions()        ← HYPE             │
│  + TermResolver wiring in Step 5  ← DEF TRAVERSAL   │
│  + _resolve_term_from_vector()    ← DEF TRAVERSAL   │
│  exclude_chunk_ids param support  ← SELF-RAG         │
├─────────────────────────────────────────────────────┤
│                  STORAGE LAYER                        │
│  + search_items_mmr()             ← MMR DIVERSITY    │
│  + search_sections_mmr()          ← MMR DIVERSITY    │
│  + BM25 index file persistence    ← BM25 HYBRID     │
│  + item_questions collection      ← HYPE             │
│  + store_item_questions()         ← HYPE             │
│  + search_item_questions()        ← HYPE             │
│  + mark_questions_pending()       ← HYPE             │
├─────────────────────────────────────────────────────┤
│                  INGESTION LAYER                      │
│  + parent_section_id in metadata  ← PARENT-CHILD    │
│  + BM25 index building            ← BM25 HYBRID     │
│  + build_cch_header()             ← CCH              │
│  + _create_chunk_for_embedding()  ← CCH              │
│  + HyPE enrichment post-ingest    ← HYPE             │
│  + plain-colon PSA pattern fix    ← DEF TRAVERSAL   │
└─────────────────────────────────────────────────────┘
```

---

## 3. Component Architecture

### 3.1 BM25Retriever Component

```
┌──────────────────────────────────────────┐
│             BM25Retriever                │
│                                          │
│  Responsibilities:                       │
│  • Build inverted index from corpus      │
│  • Persist/load index to/from JSON       │
│  • Score documents via BM25 formula      │
│  • Return ranked results                 │
│                                          │
│  Dependencies:                           │
│  • DualVectorStore (read all docs)       │
│  • File system (persist index)           │
│                                          │
│  Interface:                              │
│  __init__(persist_dir, dual_store)       │
│  build_index() → None                   │
│  search(query, top_k) → List[Dict]      │
│  save_index() → None                    │
│  load_index() → bool                    │
│                                          │
│  Internal State:                         │
│  _inverted_index: Dict[str, Dict[str,int]]│
│  _doc_lengths: Dict[str, int]            │
│  _idf_cache: Dict[str, float]           │
│  _avgdl: float                           │
│  _N: int (total document count)          │
│                                          │
│  File: backend/retrieval/bm25_retriever.py│
└──────────────────────────────────────────┘
```

### 3.2 MMR Selection Module

```
┌──────────────────────────────────────────┐
│          MMR Selection (function)        │
│                                          │
│  Responsibilities:                       │
│  • Select diverse subset from candidates │
│  • Balance relevance vs. diversity       │
│                                          │
│  Dependencies:                           │
│  • numpy (already in bundle)             │
│                                          │
│  Interface:                              │
│  mmr_select(                             │
│    query_embedding,                      │
│    candidate_embeddings,                 │
│    candidate_results,                    │
│    top_k, lambda_mult                    │
│  ) → List[Dict]                          │
│                                          │
│  Algorithm: O(k × n) where              │
│    k = top_k, n = candidates             │
│                                          │
│  File: backend/vector/dual_vector_store.py│
└──────────────────────────────────────────┘
```

### 3.3 Parent-Child Expansion

```
┌──────────────────────────────────────────┐
│     Parent-Child Expansion (method)      │
│                                          │
│  Responsibilities:                       │
│  • Map item IDs to parent section IDs    │
│  • Fetch full section text from store    │
│  • Deduplicate by section ID             │
│  • Preserve item-level match metadata    │
│                                          │
│  Dependencies:                           │
│  • DualVectorStore.get_by_id()           │
│                                          │
│  Interface:                              │
│  _expand_items_to_parent_sections(       │
│    item_results,                         │
│    max_parents                           │
│  ) → List[Dict]                          │
│                                          │
│  File: backend/retrieval/                │
│        human_like_retriever.py           │
└──────────────────────────────────────────┘
```

### 3.4 Token Trimming (JS)

```
┌──────────────────────────────────────────┐
│     Token Budget Trimmer (function)      │
│                                          │
│  Responsibilities:                       │
│  • Estimate token count from chars       │
│  • Trim context blocks to budget         │
│  • Preserve highest-priority blocks      │
│  • Add truncation indicator              │
│                                          │
│  Dependencies: None                      │
│                                          │
│  Interface:                              │
│  trimContextToTokenBudget(               │
│    blocks: string[],                     │
│    maxTokens: number                     │
│  ) → string                              │
│                                          │
│  Constants:                              │
│  TOKEN_RATIO = 4 (chars per token)       │
│  RESERVED_TOKENS = 2900                  │
│    (system prompt + query + answer)      │
│                                          │
│  File: extension/chat/participant.js     │
└──────────────────────────────────────────┘
```

---

## 4. Retrieval Pipeline — Detailed Step Mapping

### 4.1 Full Pipeline (Post-Phase 8)

```
Step  Name                        Source                  Phase 8?   Config Flag
──── ─────────────────────────── ─────────────────────── ────────── ─────────────────────
 1   Filter Extraction            human_like_retriever.py  Existing   enable_self_query_filters
 2   Query Decomposition          human_like_retriever.py  Existing   enable_query_decomposition
 3   Graph Section Discovery      human_like_retriever.py  Existing   graph_keyword_search
 4   Section-Scoped Search        human_like_retriever.py  Existing   section_scoped_search
 5   Global Fallback              human_like_retriever.py  Existing   fallback_to_global
 5a  ★ BM25 Hybrid Search        bm25_retriever.py        NEW        enable_bm25_hybrid
 5b  Routing Supplemental         human_like_retriever.py  Existing   (always on)
 6   RRF Fusion (vector + BM25)   human_like_retriever.py  MODIFIED   enable_bm25_hybrid
 6a  ★ Parent Section Expansion  human_like_retriever.py  NEW        enable_parent_expansion
 7   Definition Enrichment        human_like_retriever.py  Existing   inject_definitions
 8   Cross-Encoder Rerank         cross_encoder.py         Existing   use_cross_encoder
 9   Keyword Boost                human_like_retriever.py  Existing   (always on)
10   Document Drill-Down          human_like_retriever.py  Existing   (conditional)
11   Confidence Scoring           human_like_retriever.py  Existing   (always on)
──── ─────────────────────────── ─────────────────────── ────────── ─────────────────────
JS   ★ Token-Aware Trimming      participant.js           NEW        (always on, safe)
```

### 4.2 Step Insertion Points

The new steps are inserted at precise points to maximize impact with minimal disruption:

**Step 5a (BM25):** Runs in parallel with Step 5 (global vector search). Both produce result sets that merge in Step 6.

**Step 6 (Modified RRF):** Currently fuses sub-query result sets. Extended to also fuse BM25 results with vector results using weighted RRF.

**Step 6a (Parent Expansion):** After RRF fusion but before definition enrichment. Items in the fused set that have `parent_section_id` get their parent section text attached. The enriched section text flows into the cross-encoder for more accurate reranking.

**JS Token Trimming:** After all Python-side processing, in `generateAnswer()`, right before constructing the LLM message.

---

## 5. Configuration Architecture

### 5.1 Feature Flags

All Phase 8 features default to **enabled** but can be disabled independently:

```python
@dataclass
class RetrievalConfig:
    # ── Existing Phase 6-7 ──
    graph_keyword_search: bool = True
    max_section_candidates: int = 5
    section_scoped_search: bool = True
    items_per_section: int = 20
    fallback_to_global: bool = True
    inject_definitions: bool = True
    max_definitions_per_chunk: int = 3
    use_cross_encoder: bool = True
    min_confidence: float = 0.7
    enable_query_decomposition: bool = True
    enable_self_query_filters: bool = True
    
    # ── Phase 8: BM25 Hybrid Search ──
    enable_bm25_hybrid: bool = True
    bm25_weight: float = 0.4
    vector_weight: float = 0.6
    rrf_constant: int = 60
    bm25_k1: float = 1.5
    bm25_b: float = 0.75
    
    # ── Phase 8: MMR Diversity ──
    enable_mmr: bool = True
    mmr_lambda: float = 0.7
    mmr_fetch_multiplier: int = 3
    
    # ── Phase 8: Parent-Child ──
    enable_parent_expansion: bool = True
    max_parent_sections: int = 10
```

### 5.2 Configuration Override

Settings can be overridden via environment variables for testing:

```
KTS_BM25_ENABLED=false         → disable BM25 hybrid
KTS_MMR_ENABLED=false          → disable MMR diversity
KTS_PARENT_EXPAND=false        → disable parent expansion
KTS_BM25_WEIGHT=0.5            → adjust BM25 weight
KTS_MMR_LAMBDA=0.8             → adjust MMR diversity
```

---

## 6. File Structure — Phase 8 Changes

```
backend/
├── retrieval/
│   ├── human_like_retriever.py    ← MODIFIED (BM25, MMR, parent expansion, multi-query)
│   ├── bm25_retriever.py          ← NEW (BM25 index + search)
│   ├── cross_encoder.py           ← UNCHANGED
│   └── iterative_orchestrator.py  ← UNCHANGED
├── vector/
│   ├── dual_vector_store.py       ← MODIFIED (MMR methods, item_questions collection)
│   ├── legal_chunker.py           ← MODIFIED (build_cch_header, _create_chunk_for_embedding)
│   └── embedding_provider.py      ← UNCHANGED
├── agents/
│   ├── ingestion_agent.py         ← MODIFIED (parent_section_id, HyPE trigger)
│   └── retrieval_service.py       ← MODIFIED (pass BM25Retriever to HumanLikeRetriever)
├── extraction/
│   └── legal_item_extractor.py    ← UNCHANGED
├── graph/
│   ├── enhanced_graph_builder.py  ← UNCHANGED
│   └── persistence.py             ← UNCHANGED
└── common/
    ├── models.py                  ← UNCHANGED
    └── explainability.py          ← UNCHANGED

extension/
├── chat/
│   └── participant.js             ← MODIFIED (token trimming, multi-query expansion call, Self-RAG loop)
├── lib/
│   ├── hype_enricher.js           ← NEW (HyPE: LLM question generation at ingestion time)
│   ├── query_expander.js          ← NEW (Multi-Query: LLM query variant generation)
│   ├── gap_analyzer.js            ← NEW (Self-RAG: LLM gap identification between rounds)
│   └── iterative_generator.js    ← NEW (Self-RAG: round loop orchestration + synthesis)
└── ...                            ← UNCHANGED

config/
└── settings.py                    ← MODIFIED (ENABLE_CCH, ENABLE_HYPE, MULTI_QUERY_ENABLED, etc.)

tests/
├── test_phase8_cch.py             ← NEW
├── test_phase8_bm25.py            ← NEW
├── test_phase8_mmr.py             ← NEW
├── test_phase8_parent_child.py    ← NEW
├── test_phase8_hype.py            ← NEW
├── test_phase8_multi_query.py     ← NEW
├── test_phase8_token_trim.js      ← NEW
├── test_phase8_hype.js            ← NEW
├── test_phase8_expansion.js       ← NEW
├── test_phase8_integration.py     ← NEW
├── test_phase8_def_traversal.py   ← NEW (Inc 7: TermResolver wiring, plain-colon fix, fallback)
├── test_phase8_self_rag.js        ← NEW (Inc 8: gap_analyzer, iterative_generator)
├── test_phase8_self_rag.py        ← NEW (Inc 8: integration, confidence penalty, latency)
└── ...                            ← UNCHANGED (regression suite)
```

---

## 7. Deployment Architecture

### 7.1 Build Pipeline (Unchanged)

```
Python source → PyInstaller → kts-backend binary → extension/bin/
Extension source + bin/ → vsce package → .vsix
.vsix → VS Code Extension Install
```

### 7.2 Runtime Initialization Sequence

```
Extension activates
    │
    ├── kts-backend process starts
    │   ├── Load ChromaDB (existing)
    │   ├── Load NetworkX graph (existing)
    │   ├── Load embedding provider (existing)
    │   ├── Load cross-encoder (existing, lazy)
    │   ├── ★ Load/build BM25 index (NEW)
    │   │   ├── Try load from _kts_bm25_index.json
    │   │   └── If missing → build from ChromaDB collections → save
    │   ├── ★ HyPE: check for questions_pending chunks (NEW)
    │   │   └── If any found → notify extension to offer /enrich_questions
    │   └── Initialize HumanLikeRetriever with all components
    │
    └── Chat participant registers (@kts)
```

### 7.3 Re-Ingestion Trigger

Parent-child linking requires re-ingestion. The system detects this automatically:

```python
def _needs_reingestion(self) -> bool:
    """Check if items have parent_section_id metadata."""
    sample = self.item_collection.peek(limit=5)
    if not sample["metadatas"]:
        return False
    return "parent_section_id" not in sample["metadatas"][0]
```

When detected, the extension shows a notification: *"Phase 8 upgrade detected. Re-ingest documents for improved retrieval. Current functionality is preserved."*

---

## 8. Technique Source Mapping

Each Phase 8 technique traces to specific LangChain source code:

| KTS Implementation | Source | Algorithm Adopted |
|-------------------|--------|-------------------|
| `BM25Retriever.search()` | `langchain_classic/retrievers/bm25.py` | BM25 scoring with k1/b parameters |
| RRF fusion weights | `langchain_classic/retrievers/ensemble.py` L303-L353 | `weighted_reciprocal_rank()` with constant c=60 |
| `mmr_select()` | `langchain_core/vectorstores/base.py` L661-L686 | MMR with lambda balancing |
| Parent expansion | `langchain_classic/retrievers/parent_document_retriever.py` L107-L150 | Child-search → parent-return pattern |
| Token trimming | `langchain_classic/chains/combine_documents/stuff.py` L98 | Context-fits-window enforcement |
| `build_cch_header()` | `RAG_Techniques-main/contextual_chunk_headers.py` | Prepend `[DOC: \| TYPE: \| SECTION:]` header before embedding |
| `hype_enricher.js` + `item_questions` | `RAG_Techniques-main/HyDE.py` (adapted) | LLM-at-ingestion question generation for definitions/triggers |
| `expandQueryWithLLM()` + `_rrf_merge()` | RAG Fusion (Shi et al., 2023) | Multi-query generation + RRF merge across retrieval results |
| `TermResolver.resolve_term()` + `_resolve_term_from_vector()` | Recursive RAG / TermResolver (in-house, `term_resolver.py`) | BFS over graph REFERS_TO edges to depth N; ChromaDB fallback on graph miss |
| `gap_analyzer.js` + `iterative_generator.js` | FLARE (Jiang et al. 2023) / Self-RAG (Asai et al. 2023) | LLM-as-judge generation loop: gap analysis → targeted retrieval → synthesis |

**None of these adopt LangChain or any third-party library as a dependency.** All algorithms are implemented directly in the KTS codebase, adapted to our data structures and offline VSIX constraints.
