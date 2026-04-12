# Phase 8: RAG Upgrade — System Design Document

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## 1. System Context

### 1.1 Current System Overview

The KTS Agentic System is a VS Code extension that provides AI-assisted knowledge retrieval for structured finance legal documents. The system operates **entirely offline** — no cloud APIs, no external services.

```
┌─────────────────────────────────────────────────────────┐
│  VS Code Extension (JavaScript)                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ @kts Chat   │  │ Commands     │  │ Panels        │  │
│  │ Participant │  │ (Ingest,     │  │ (Graph View,  │  │
│  │             │  │  Search)     │  │  Results)     │  │
│  └──────┬──────┘  └──────┬───────┘  └───────────────┘  │
│         │ VS Code LM API │ CLI/JSON-RPC                 │
└─────────┼────────────────┼──────────────────────────────┘
          │                │
┌─────────┼────────────────┼──────────────────────────────┐
│  kts-backend (PyInstaller Binary)                       │
│         ▼                ▼                               │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Retrieval Service (retrieval_service.py)          │   │
│  │  ┌───────────────────────────────────────────┐   │   │
│  │  │ HumanLikeRetriever (11-step pipeline)     │   │   │
│  │  │  1. Filter Extraction                     │   │   │
│  │  │  2. Query Decomposition                   │   │   │
│  │  │  3. Graph-First Section Discovery         │   │   │
│  │  │  4. Section-Scoped Search                 │   │   │
│  │  │  5. Global Fallback                       │   │   │
│  │  │  6. RRF Fusion                            │   │   │
│  │  │  7. Definition Enrichment                 │   │   │
│  │  │  8. Cross-Encoder Rerank                  │   │   │
│  │  │  9. Keyword Boost                         │   │   │
│  │  │ 10. Document Drill-Down                   │   │   │
│  │  │ 11. Confidence Scoring                    │   │   │
│  │  └───────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  ┌────────────────┐  ┌─────────┐  ┌─────────────────┐  │
│  │ DualVectorStore│  │ Graph   │  │ Cross-Encoder   │  │
│  │ (ChromaDB)     │  │ (NX+JSON│  │ (ONNX)          │  │
│  │ • items coll.  │  │  DiGraph│  │                  │  │
│  │ • sections coll│  │)        │  │                  │  │
│  └────────────────┘  └─────────┘  └─────────────────┘  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Embedding Provider (BGE ONNX INT8)               │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 1.2 Key Constraints

| Constraint | Implication |
|-----------|-------------|
| **Offline-only deployment** | No cloud API calls (no OpenAI, no Cohere reranker) |
| **PyInstaller binary** | All Python dependencies must be bundleable; no dynamic installs |
| **VSIX packaging** | Total extension size ~500 MB; minimize new binary dependencies |
| **VS Code LM API** | LLM calls only via Copilot Chat; no `system()` message; only `User()`/`Assistant()` |
| **Single-user desktop** | No concurrent queries; in-memory indexes acceptable |
| **Legal document domain** | Exact terminology critical; definitions have legal force |

---

## 2. Data Flow — Current vs. Phase 8

### 2.1 Current Ingestion Flow

```
Document (PDF/DOCX/DOC)
    │
    ▼
┌──────────────────┐
│ Text Extraction   │  (textract, PyMuPDF, python-docx)
│ + Cleaning        │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ LegalChunker     │  (backend/vector/legal_chunker.py)
│ • TOC extraction │
│ • ARTICLE/SECTION│
│   parsing        │
│ • Adaptive sizing│
└────────┬─────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌────────┐ ┌──────────────┐
│Sections│ │Items per     │  (backend/extraction/legal_item_extractor.py)
│(chunks)│ │section       │
└───┬────┘ └──────┬───────┘
    │             │
    ▼             ▼
┌──────────────────────┐
│ DualVectorStore      │  (backend/vector/dual_vector_store.py)
│ ChromaDB:            │
│ • section_collection │  ← sections embedded via BGE
│ • item_collection    │  ← items embedded via BGE
└──────────────────────┘
         │
         ▼
┌──────────────────────┐
│ EnhancedGraphBuilder │  (backend/graph/enhanced_graph_builder.py)
│ NetworkX DiGraph:    │
│ • DOCUMENT nodes     │
│ • SECTION nodes      │
│ • ITEM nodes         │
│ • Typed edges        │
└──────────────────────┘
```

### 2.2 Phase 8 Ingestion Changes

```diff
  LegalChunker
      │
 ┌────┴────┐
 │         │
 ▼         ▼
Sections  Items per section
 │         │
+│    ┌────┘
+│    │ NEW: Stamp parent_section_id on each item
+│    ▼
 ▼   Items (with parent_section_id in metadata)
 │    │
 ▼    ▼
 DualVectorStore
 │
+▼
+BM25Index (NEW)
+│ Build inverted index from all items + sections
+│ Persisted alongside ChromaDB for restart efficiency
```

**Key changes:**
1. Items get `parent_section_id` metadata linking them to their containing section
2. A BM25 inverted index is built at ingestion time and persisted to disk
3. Sections and items continue to be embedded in ChromaDB (no change)

### 2.3 Phase 8 Retrieval Flow

```
Query: "What is the Closing Date"
    │
    ▼
┌──────────────────────────────────────────────────┐
│ Step 1: Filter Extraction (existing)             │
│   → item_type: "Definition" (what is X pattern)  │
│   → definition_inject: True                      │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│ Step 2: Query Decomposition (existing)           │
│   → ["What is the Closing Date",                 │
│      "definition of Closing Date"]               │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│ Step 3: Graph Section Discovery (existing)       │
│   → Injects DEFINITIONS section for def queries  │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│ Step 4: Section-Scoped Search (existing)         │
│   → Searches items within DEFINITIONS section    │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│ Step 5: Global Fallback + BM25 Hybrid  ★ NEW ★  │
│                                                  │
│  ┌────────────┐     ┌──────────────────┐         │
│  │ BM25 Search│     │ Vector Search    │         │
│  │ (keyword)  │     │ (semantic, MMR)  │ ★ NEW ★ │
│  └─────┬──────┘     └────────┬─────────┘         │
│        │                     │                   │
│        └──────┬──────────────┘                   │
│               ▼                                  │
│    ┌──────────────────┐                          │
│    │ RRF Fusion       │                          │
│    │ w_bm25=0.4       │                          │
│    │ w_vector=0.6     │                          │
│    │ c=60             │                          │
│    └──────────────────┘                          │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│ Step 5.5: Parent Expansion          ★ NEW ★      │
│   → Item results → look up parent_section_id    │
│   → Return full section text for richer context  │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│ Steps 6-11: Definition Enrichment, Cross-Encoder,│
│ Keyword Boost, Drill-Down, Confidence (existing) │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│ JS Frontend: Token-Aware Context Trim  ★ NEW ★   │
│   → Trim context blocks to token budget          │
│   → Build prompt, stream LLM answer              │
└──────────────────────────────────────────────────┘
```

---

## 3. Component Interactions

### 3.1 New Components

| Component | Type | Location | Dependencies |
|-----------|------|----------|-------------|
| `BM25Retriever` | New class | `backend/retrieval/bm25_retriever.py` | `DualVectorStore` (read-only) |
| `mmr_select()` | New function | `backend/vector/dual_vector_store.py` | Embedding provider |
| `parent_section_id` metadata | Schema change | `backend/agents/ingestion_agent.py` | Existing `add_items()` |
| `trimContextToTokenBudget()` | New JS function | `extension/chat/participant.js` | None |
| `BM25Index` persistence | New file format | `backend/retrieval/bm25_retriever.py` | JSON serialization |

### 3.2 Modified Components

| Component | File | Change |
|-----------|------|--------|
| `HumanLikeRetriever.__init__()` | `backend/retrieval/human_like_retriever.py` | Accept `BM25Retriever` dependency |
| `HumanLikeRetriever.retrieve()` | `backend/retrieval/human_like_retriever.py` | Insert BM25 + MMR + parent expansion steps |
| `RetrievalConfig` | `backend/retrieval/human_like_retriever.py` | Add Phase 8 config fields |
| `DualVectorStore.search_items()` | `backend/vector/dual_vector_store.py` | Add MMR variant method |
| `DualVectorStore.search_sections()` | `backend/vector/dual_vector_store.py` | Add MMR variant method |
| Ingestion pipeline | `backend/agents/ingestion_agent.py` | Add `parent_section_id` to item metadata |
| `generateAnswer()` | `extension/chat/participant.js` | Add token budget trimming |

### 3.3 Unchanged Components

| Component | File | Why Unchanged |
|-----------|------|---------------|
| `LegalChunker` | `backend/vector/legal_chunker.py` | Chunking logic is correct; Phase 7 fixes are sufficient |
| `LegalItemExtractor` | `backend/extraction/legal_item_extractor.py` | Classification logic unchanged |
| `EnhancedGraphBuilder` | `backend/graph/enhanced_graph_builder.py` | Graph structure unchanged |
| Cross-encoder | `backend/retrieval/cross_encoder.py` | Reranking unchanged; operates on post-fusion results |
| `ExplainabilityLogger` | `backend/common/explainability.py` | Logging interface unchanged; new steps use existing API |
| All VS Code commands | `extension/commands/` | No UI changes needed |

---

## 4. Data Model Changes

### 4.1 Item Metadata (ChromaDB)

```python
# Current metadata schema:
{
    "document_id": "abc123",
    "section_number": "I",
    "item_type": "Definition",
    "source_path": "/path/to/doc.pdf",
    "chunk_index": 5,
}

# Phase 8 addition:
{
    "document_id": "abc123",
    "section_number": "I",
    "item_type": "Definition",
    "source_path": "/path/to/doc.pdf",
    "chunk_index": 5,
    "parent_section_id": "sec_abc123_I",    # NEW — links to section collection
}
```

### 4.2 BM25 Index (New Persisted File)

```json
{
    "version": 1,
    "created": "2026-02-18T10:00:00Z",
    "params": {"k1": 1.5, "b": 0.75},
    "avgdl": 45.2,
    "N": 4500,
    "doc_lengths": {"item_001": 32, "item_002": 67, ...},
    "idf": {"closing": 3.21, "date": 1.04, ...},
    "inverted_index": {
        "closing": {"item_042": 2, "item_108": 1, ...},
        "date": {"item_042": 1, "item_203": 3, ...}
    }
}
```

**File location:** `{persist_dir}/_kts_bm25_index.json`  
**Size estimate:** ~2-5 MB for a 500-document corpus (acceptable for desktop deployment)

### 4.3 Backward Compatibility

| Scenario | Behavior |
|----------|----------|
| Old index, new code (no `parent_section_id`) | Parent expansion silently returns empty; pipeline continues |
| Old index, new code (no BM25 index) | BM25 index auto-built on first query (lazy init) |
| New index, old code | Old code ignores unknown metadata keys; no breakage |

---

## 5. Interface Contracts

### 5.1 BM25Retriever Interface

```python
class BM25Retriever:
    def __init__(self, persist_dir: str, dual_store: DualVectorStore) -> None: ...
    def build_index(self) -> None: ...
    def save_index(self) -> None: ...
    def load_index(self) -> bool: ...  # Returns False if no saved index
    def search(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]: ...
    # Returns: [{"id": str, "text": str, "bm25_score": float, "metadata": dict, "type": str}]
```

### 5.2 MMR Function Interface

```python
def mmr_select(
    query_embedding: List[float],
    candidate_embeddings: List[List[float]],
    candidate_results: List[Dict[str, Any]],
    top_k: int = 10,
    lambda_mult: float = 0.7,
) -> List[Dict[str, Any]]:
    """Select top_k diverse results using Maximal Marginal Relevance."""
```

### 5.3 Token Trimming Interface

```javascript
/**
 * Trim context blocks to fit within a token budget.
 * @param {string[]} blocks - Array of context block strings
 * @param {number} maxTokens - Maximum tokens available for context
 * @returns {string} Concatenated, trimmed context string
 */
function trimContextToTokenBudget(blocks, maxTokens) { ... }
```

---

## 6. Performance Considerations

### 6.1 Memory Impact

| Component | Estimated Memory | Notes |
|-----------|-----------------|-------|
| BM25 inverted index | 5-20 MB | For corpus of 500 documents / ~50K items |
| MMR embedding cache | 0 MB | Embeddings fetched from ChromaDB on-demand, not cached |
| Parent section cache | 0 MB | Looked up from ChromaDB per query |

**Total additional memory:** ~5-20 MB — negligible for desktop deployment.

### 6.2 Latency Impact

| Operation | Current | Phase 8 | Delta |
|-----------|---------|---------|-------|
| BM25 search (50K items) | N/A | ~5 ms | +5 ms |
| RRF fusion (40 items) | ~1 ms | ~2 ms | +1 ms |
| MMR selection (30 → 10) | N/A | ~15 ms | +15 ms |
| Parent expansion (10 items) | N/A | ~10 ms | +10 ms |
| Token trimming (JS) | N/A | <1 ms | <1 ms |
| **Total retrieval** | **~850 ms** | **~880 ms** | **+30 ms** |

**Net impact:** ~30 ms additional latency — imperceptible to users.

### 6.3 Disk Impact

| Component | Size | Notes |
|-----------|------|-------|
| BM25 index file | 2-5 MB | JSON, alongside ChromaDB |
| VSIX package size | +0 MB | No new binary dependencies |

---

## 7. Error Handling

### 7.1 Graceful Degradation

All Phase 8 features are **additive** and wrapped in try/except with fallback to existing behavior:

```python
# BM25 failure → skip hybrid, use vector-only (existing behavior)
try:
    bm25_results = self.bm25_retriever.search(query, top_k=20)
except Exception as e:
    logger.warning(f"BM25 search failed, using vector-only: {e}")
    bm25_results = []

# MMR failure → fall back to regular similarity search
try:
    results = self.dual_store.search_items_mmr(query, top_k, ...)
except Exception as e:
    logger.warning(f"MMR failed, using similarity: {e}")
    results = self.dual_store.search_items(query, top_k)

# Parent expansion failure → return items as-is
try:
    expanded = self._expand_items_to_parent_sections(item_results)
except Exception as e:
    logger.warning(f"Parent expansion failed: {e}")
    expanded = item_results
```

### 7.2 Logging

All new steps log via the existing `ExplainabilityLogger`:

```python
xlog.step("bm25_search", f"BM25 returned {len(bm25_results)} results",
          detail={"top_terms": top_3_terms}, why="Keyword matching catches exact legal terms")

xlog.step("mmr_diversity", f"MMR selected {len(mmr_results)} diverse results from {fetch_k}",
          detail={"lambda": self.config.mmr_lambda}, why="Diversity prevents redundant context")

xlog.step("parent_expansion", f"Expanded {len(items)} items to {len(parents)} sections",
          detail={"parent_ids": parent_ids[:3]}, why="Full section context for LLM")
```

---

## 8. Security Considerations

| Concern | Assessment |
|---------|-----------|
| BM25 index contains document text | Same exposure as ChromaDB — persisted locally, no network access |
| Token trimming truncates content | Truncation is safe — preserves highest-ranked content first |
| New code injection surface | All inputs are from local files; no user-controlled code paths |
| Memory exhaustion (large corpus) | BM25 index size bounded by corpus size; cap at 100K items |
