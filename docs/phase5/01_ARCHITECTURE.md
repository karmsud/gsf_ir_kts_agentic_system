# Phase 5 — System Architecture

**Date**: 2026-02-16  
**Status**: Design — pending approval

---

## 1. Current Architecture (Phase 4)

### Pipeline Flow

```
USER QUERY
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  QUERY PRE-PROCESSING (sequential, single-pass)            │
│                                                             │
│  1. AcronymResolver.expand(query)                          │
│     └── Static dict lookup (acronyms.json, 152 entries)    │
│                                                             │
│  2. QueryExpander.expand(query)                            │
│     └── 3-tier synonym append (static + learned + NER)     │
│                                                             │
│  Result: single expanded query string                      │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  RETRIEVAL (single path, single query)                     │
│                                                             │
│  3. VectorStore.search(query, top_k=max*4)                 │
│     └── ChromaDB cosine search                             │
│     └── Embedding: MiniLM-L6-v2, 384-dim, ONNX FP32       │
│     └── Optional: doc_type_filter (caller-supplied only)   │
│                                                             │
│  Result: top_k*4 candidate chunks with scores              │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  RANKING (multi-signal, single-pass)                       │
│                                                             │
│  4. Cross-encoder rerank (optional, ONNX)                  │
│  5. Feature scoring:                                       │
│     ├── vector_similarity (base)                           │
│     ├── graph_boost (NetworkX adjacency)                   │
│     ├── error_code_exact_match (×1.5)                      │
│     ├── intent_doc_type_match (regex classifier)           │
│     ├── entity_overlap (NER Jaccard)                       │
│     ├── keyphrase_overlap (partial match)                  │
│     └── title_term_match                                   │
│  6. Deduplicate by doc_id (keep highest per doc)           │
│                                                             │
│  Result: top max_results ranked chunks                     │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  POST-PROCESSING                                           │
│                                                             │
│  7. Tool filter (graph-based, if tool_filter supplied)     │
│  8. Term resolution (if GOVERNING_DOC_LEGAL regime)        │
│  9. Freshness badges                                       │
│  10. Confidence = min(1.0, max(0.3, top_sim + 0.05*(n-1)))│
│  11. Evidence matching (if strict mode / answer provided)  │
│                                                             │
│  Result: SearchResult → JSON → extension → Copilot chat   │
└─────────────────────────────────────────────────────────────┘
```

### Limitations

| Area | Limitation |
|------|-----------|
| **Query** | Single query string, no decomposition, no metadata filter auto-extraction |
| **Embedding** | 384-dim MiniLM (lower quality than 768-dim BGE), FP32 (larger than needed) |
| **Retrieval** | Single vector search pass, no fallback strategy |
| **Confidence** | Only uses top similarity + chunk count; ignores 5+ computed signals |
| **Evidence** | One-shot check; never re-retrieves on failure |

---

## 2. Phase 5 Architecture (Target)

### Pipeline Flow

```
USER QUERY
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE A — QUERY PIPELINE                                             │
│                                                                         │
│  A1. AcronymResolver.expand(query)              [existing, unchanged]  │
│                                                                         │
│  A2. SelfQueryExtractor.extract(query)                        [NEW]    │
│      ├── doc_type filter    (regex intent → filter)                    │
│      ├── tool filter        (NER entity → filter)                      │
│      ├── error_code filter  (regex → filter)                           │
│      └── Returns: MetadataFilters + cleaned_query                      │
│                                                                         │
│  A3. QueryDecomposer.decompose(query)                         [NEW]    │
│      ├── Rule-based split (conjunctions, multi-clause)                 │
│      ├── Optional GHCP LLM decomposition (config flag)                 │
│      ├── Step-back query generation                                    │
│      └── Returns: List[SubQuery] (1-4 sub-queries)                     │
│                                                                         │
│  A4. QueryExpander.expand(sub_query)            [existing, per sub-q]  │
│                                                                         │
│  Result: N sub-queries, each with metadata filters + expanded text     │
└─────────────────────────────────────────────────────────────────────────┘
    │
    ▼ (parallel retrieval per sub-query)
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE B — MULTI-PATH RETRIEVAL                                       │
│                                                                         │
│  For each sub-query (parallel):                                        │
│                                                                         │
│  B1. VectorStore.search(sub_query, filters=extracted_filters)          │
│      └── Embedding: BGE-base-en-v1.5, 768-dim, ONNX INT8     [NEW]   │
│      └── ChromaDB where clause from SelfQueryExtractor                 │
│                                                                         │
│  B2. Fallback: if filtered search < min_results → unfiltered search    │
│                                                                         │
│  Result: N×top_k candidate sets                                        │
└─────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE C — FUSION + RANKING                                           │
│                                                                         │
│  C1. Reciprocal Rank Fusion (RRF)                             [NEW]   │
│      └── Merge N result sets using RRF formula                         │
│      └── k=60 (standard RRF constant)                                  │
│                                                                         │
│  C2. Cross-encoder rerank                       [existing, unchanged]  │
│                                                                         │
│  C3. Feature scoring                            [existing, unchanged]  │
│      └── graph_boost, error_code, intent, entity, keyphrase            │
│                                                                         │
│  C4. Deduplicate by doc_id                      [existing, unchanged]  │
│                                                                         │
│  Result: top max_results ranked chunks                                 │
└─────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE D — CONFIDENCE + POST-PROCESSING                               │
│                                                                         │
│  D1. Multi-signal confidence                                  [NEW]   │
│      └── Weighted combination of:                                      │
│          vector_sim, cross_encoder, graph_boost,                       │
│          error_code_match, intent_match, entity_overlap,               │
│          keyphrase_overlap, filter_engaged                             │
│                                                                         │
│  D2. Term resolution                            [existing, unchanged]  │
│  D3. Freshness                                  [existing, unchanged]  │
│  D4. Tool filter                                [existing, unchanged]  │
│                                                                         │
│  Result: SearchResult with calibrated confidence                       │
└─────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE E — EVIDENCE GATE + SELF-RAG RETRY                     [NEW]   │
│                                                                         │
│  E1. EvidenceMatcher.match_claims_to_chunks()   [existing]             │
│                                                                         │
│  E2. Coverage check:                                                   │
│      IF coverage ≥ threshold → PASS → return result                    │
│      IF coverage < threshold AND retry_budget > 0:                     │
│        ├── Rewrite query (rule-based or GHCP)                          │
│        ├── Re-run Stages A-D with rewritten query                      │
│        ├── Merge new results with existing                             │
│        ├── Re-check coverage                                           │
│        └── Decrement retry_budget                                      │
│      ELSE → return result with low-confidence warning                  │
│                                                                         │
│  E3. ProvenanceLedger.append()                  [existing]             │
│                                                                         │
│  Result: Final validated SearchResult                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Diagram

### New Components (shaded)

```
┌──────────────────────────────────────────────────────────────────┐
│                        config/settings.py                        │
│  KTSConfig                                                       │
│  + embed_provider: str = "bge_onnx_int8"                  [NEW] │
│  + self_query_enabled: bool = True                         [NEW] │
│  + query_decomposition_enabled: bool = True                [NEW] │
│  + query_decomposition_use_llm: bool = False               [NEW] │
│  + self_rag_retry_enabled: bool = False                    [NEW] │
│  + self_rag_max_retries: int = 1                           [NEW] │
│  + self_rag_coverage_threshold: float = 0.80               [NEW] │
│  + rrf_k: int = 60                                         [NEW] │
└──────────────────────────────────────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────────────────────────────────┐
│                    backend/vector/                                │
│                                                                  │
│  ┌────────────────────────────────────┐                          │
│  │  embedding_provider.py       [NEW] │                          │
│  │  ├── EmbeddingProvider (ABC)       │                          │
│  │  │   ├── embed_query(text)→vec     │                          │
│  │  │   ├── embed_documents(texts)    │                          │
│  │  │   ├── provider_id: str          │                          │
│  │  │   ├── dims: int                 │                          │
│  │  │   └── model_hash: str           │                          │
│  │  ├── LegacyChromaProvider          │                          │
│  │  │   └── wraps DefaultEmbedFn      │                          │
│  │  └── get_provider(config) factory  │                          │
│  └────────────────────────────────────┘                          │
│                                                                  │
│  ┌────────────────────────────────────┐                          │
│  │  bge_onnx_provider.py       [NEW] │                          │
│  │  └── BgeOnnxInt8Provider           │                          │
│  │      ├── ONNXRuntime inference     │                          │
│  │      ├── HF tokenizer (local)     │                          │
│  │      ├── Query prefix handling     │                          │
│  │      └── Batch embedding           │                          │
│  └────────────────────────────────────┘                          │
│                                                                  │
│  ┌────────────────────────────────────┐                          │
│  │  store.py                [MODIFY] │                          │
│  │  └── VectorStore                   │                          │
│  │      ├── Accept EmbeddingProvider  │                          │
│  │      ├── Pass to ChromaDB as       │                          │
│  │      │   custom EmbeddingFunction  │                          │
│  │      └── Store index metadata      │                          │
│  └────────────────────────────────────┘                          │
│                                                                  │
│  ┌────────────────────────────────────┐                          │
│  │  chunker.py            [UNCHANGED]│                          │
│  └────────────────────────────────────┘                          │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                    backend/retrieval/                             │
│                                                                  │
│  ┌────────────────────────────────────┐                          │
│  │  self_query_extractor.py    [NEW] │                          │
│  │  └── SelfQueryExtractor            │                          │
│  │      ├── extract(query) →          │                          │
│  │      │   MetadataFilters           │                          │
│  │      ├── doc_type from intent      │                          │
│  │      ├── tool from NER/regex       │                          │
│  │      ├── error_code from regex     │                          │
│  │      └── cleaned_query (filters    │                          │
│  │          stripped from text)        │                          │
│  └────────────────────────────────────┘                          │
│                                                                  │
│  ┌────────────────────────────────────┐                          │
│  │  query_decomposer.py       [NEW] │                          │
│  │  └── QueryDecomposer               │                          │
│  │      ├── decompose(query) →        │                          │
│  │      │   List[SubQuery]            │                          │
│  │      ├── Rule-based split          │                          │
│  │      ├── Step-back generation      │                          │
│  │      └── Optional GHCP LLM split  │                          │
│  └────────────────────────────────────┘                          │
│                                                                  │
│  ┌────────────────────────────────────┐                          │
│  │  rank_fusion.py             [NEW] │                          │
│  │  └── reciprocal_rank_fusion(       │                          │
│  │        result_sets, k=60)          │                          │
│  │      → merged ranked list          │                          │
│  └────────────────────────────────────┘                          │
│                                                                  │
│  ┌────────────────────────────────────────────────┐              │
│  │  query_expander.py              [UNCHANGED]    │              │
│  │  acronym_resolver.py            [UNCHANGED]    │              │
│  │  cross_encoder.py               [UNCHANGED]    │              │
│  │  evidence_matcher.py            [UNCHANGED]    │              │
│  │  term_resolver.py               [UNCHANGED]    │              │
│  │  term_registry.py               [MODIFY]       │              │
│  │  └── Use EmbeddingProvider instead of          │              │
│  │      DefaultEmbeddingFunction                   │              │
│  └────────────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                    backend/agents/                                │
│                                                                  │
│  ┌────────────────────────────────────────────────┐              │
│  │  retrieval_service.py            [MODIFY]      │              │
│  │  └── RetrievalService.execute()                │              │
│  │      ├── Insert SelfQueryExtractor (A2)        │              │
│  │      ├── Insert QueryDecomposer (A3)           │              │
│  │      ├── Loop: per-sub-query retrieval (B)     │              │
│  │      ├── Insert RRF fusion (C1)                │              │
│  │      ├── Replace confidence formula (D1)       │              │
│  │      └── Insert Self-RAG retry loop (E)        │              │
│  └────────────────────────────────────────────────┘              │
│                                                                  │
│  ┌────────────────────────────────────────────────┐              │
│  │  ingestion_agent.py              [UNCHANGED]   │              │
│  │  (embedding happens in VectorStore, not here)  │              │
│  └────────────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                    Build / Packaging                              │
│                                                                  │
│  ┌────────────────────────────────────┐                          │
│  │  scripts/model_build/        [NEW]│                          │
│  │  └── build_bge_onnx_int8.ps1      │                          │
│  │      ├── Download HF model        │                          │
│  │      ├── Export to ONNX           │                          │
│  │      ├── Quantize INT8            │                          │
│  │      ├── Smoke test               │                          │
│  │      └── Write manifest           │                          │
│  └────────────────────────────────────┘                          │
│                                                                  │
│  ┌────────────────────────────────────┐                          │
│  │  assets/models/bge-base-en-v1.5/ │                          │
│  │  └── onnx-int8/             [NEW] │                          │
│  │      ├── model.onnx (INT8)        │                          │
│  │      ├── tokenizer.json           │                          │
│  │      ├── tokenizer_config.json    │                          │
│  │      ├── vocab.txt                │                          │
│  │      ├── special_tokens_map.json  │                          │
│  │      ├── config.json              │                          │
│  │      └── model_manifest.json      │                          │
│  └────────────────────────────────────┘                          │
│                                                                  │
│  ┌────────────────────────────────────────────────┐              │
│  │  packaging/kts_backend.spec      [MODIFY]      │              │
│  │  └── Bundle BGE model instead of MiniLM        │              │
│  └────────────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────────┘
```

---

## 4. Data Flow — Ingestion Path

```
Source Files  →  CrawlerAgent  →  IngestionAgent
                                      │
                                      ├── DocConverter (extract text)
                                      ├── RegimeClassifier (doc_regime)
                                      ├── NER Extractor (entities, keyphrases)
                                      ├── Content date extraction
                                      │
                                      ▼
                               chunk_document()
                                      │
                                      ▼
                             VectorStore.upsert_chunks()
                                      │
                    ┌─────────────────┴───────────────────┐
                    │                                     │
              EmbeddingProvider                    ChromaDB Store
              .embed_documents()                   (.kts/vectors/chroma)
                    │                                     │
              BGE ONNX INT8                        Index Metadata
              768-dim vectors                      (provider_id, dims,
                                                    model_hash, created_at)
                                      │
                                      ▼
                              GraphBuilder.upsert_document()
                                      │
                              TermRegistry.register_terms()
                              .rebuild_synonyms()
                                      │
                              EmbeddingProvider._embed()  ← uses same provider
```

No changes to the ingestion pipeline itself — only the embedding layer beneath `VectorStore` changes.

---

## 5. Data Flow — Search Path (Phase 5)

```
User Query: "How do I fix AUTH401 on ToolX and what's the escalation?"
    │
    ▼
[A1] AcronymResolver
    │  "How do I fix AUTH401 on ToolX and what's the escalation?"
    ▼
[A2] SelfQueryExtractor                                          [NEW]
    │  Extracted filters:
    │    doc_type: ["TROUBLESHOOT", "SOP"]
    │    tool: "ToolX"
    │    error_code: "AUTH401"
    │  Cleaned query: "How do I fix AUTH401 and what's the escalation?"
    ▼
[A3] QueryDecomposer                                             [NEW]
    │  Sub-queries:
    │    Q1: "How do I fix AUTH401" (filters: doc_type=TROUBLESHOOT, tool=ToolX)
    │    Q2: "What is the escalation procedure" (filters: doc_type=SOP, tool=ToolX)
    │    Q3 (step-back): "What does AUTH401 mean" (filters: doc_type=REFERENCE)
    ▼
[A4] QueryExpander (per sub-query)
    │  Q1 expanded: "How do I fix AUTH401 OR authentication error 401"
    │  Q2 expanded: "escalation procedure OR incident escalation"
    │  Q3 expanded: "AUTH401 meaning OR ERR-AUTH-401 description"
    ▼
[B1-B2] Parallel Vector Search (per sub-query)                   [NEW]
    │  Q1 → 20 candidates (filtered: doc_type=TROUBLESHOOT, tool=ToolX)
    │  Q2 → 20 candidates (filtered: doc_type=SOP, tool=ToolX)
    │  Q3 → 20 candidates (filtered: doc_type=REFERENCE)
    │  + fallback unfiltered if any < min_results
    ▼
[C1] Reciprocal Rank Fusion                                      [NEW]
    │  Merge 3 candidate sets → unified ranked list
    │  RRF score = Σ 1/(k + rank_i)
    ▼
[C2-C4] Cross-encoder + Feature scoring + Dedup                 [existing]
    │  Multi-signal reranking, deduplicate by doc_id
    ▼
[D1] Multi-Signal Confidence                                     [NEW]
    │  confidence = weighted(vector_sim, ce_score, graph_boost,
    │               error_match, intent_match, entity_overlap,
    │               keyphrase_overlap, filter_engaged)
    ▼
[D2-D4] Term resolution, freshness, tool filter                 [existing]
    ▼
[E1-E3] Evidence Gate + Self-RAG Retry                           [NEW]
    │  coverage = evidence_matcher.match(answer, chunks)
    │  IF coverage < 0.80 AND retries_left > 0:
    │    → rewrite query → re-run A-D → merge → re-check
    │  ELSE → return with confidence adjusted by coverage
    ▼
FINAL RESULT → JSON → Extension → Copilot Chat
```

---

## 6. Index Metadata Schema

Stored at `.kts/vectors/index_metadata.json`:

```json
{
  "provider_id": "bge_onnx_int8",
  "dims": 768,
  "model_hash": "sha256:abc123...",
  "model_version": "BAAI/bge-base-en-v1.5",
  "created_at": "2026-02-16T10:30:00Z",
  "chunk_count": 1247,
  "doc_count": 58,
  "last_ingest": "2026-02-16T10:35:00Z"
}
```

On startup: if `provider_id` or `model_hash` mismatches active config → log warning + refuse search with clear error message requiring `kts reindex`.

---

## 7. Configuration Surface (Phase 5 additions)

All new config fields follow the existing `KTSConfig` pattern with env var overrides:

| Field | Type | Default | Env Var |
|-------|------|---------|---------|
| `embed_provider` | `str` | `"bge_onnx_int8"` | `KTS_EMBED_PROVIDER` |
| `embed_model_path` | `str` | `""` (auto-detect) | `KTS_EMBED_MODEL_PATH` |
| `self_query_enabled` | `bool` | `True` | `KTS_SELF_QUERY_ENABLED` |
| `query_decomposition_enabled` | `bool` | `True` | `KTS_QUERY_DECOMPOSITION_ENABLED` |
| `query_decomposition_use_llm` | `bool` | `False` | `KTS_QUERY_DECOMPOSITION_USE_LLM` |
| `self_rag_retry_enabled` | `bool` | `False` | `KTS_SELF_RAG_RETRY_ENABLED` |
| `self_rag_max_retries` | `int` | `1` | `KTS_SELF_RAG_MAX_RETRIES` |
| `self_rag_coverage_threshold` | `float` | `0.80` | `KTS_SELF_RAG_COVERAGE_THRESHOLD` |
| `rrf_k` | `int` | `60` | `KTS_RRF_K` |
| `min_filtered_results` | `int` | `2` | `KTS_MIN_FILTERED_RESULTS` |

### Rollback Path

Set `KTS_EMBED_PROVIDER=legacy_chroma_default` to revert to MiniLM. Requires re-index since dimensions differ.
