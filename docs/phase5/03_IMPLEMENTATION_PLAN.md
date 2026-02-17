# Phase 5 — Implementation Plan

**Date**: 2026-02-16  
**Status**: Design — pending approval

---

## 1. Implementation Order

```
Sprint 1 (WS-1)      Sprint 2 (WS-2 + WS-3)      Sprint 3 (WS-4)      Sprint 4 (WS-5)
──────────────────    ─────────────────────────    ──────────────────    ──────────────────
Embedding Provider    Self-Query Extraction        Query Decomposition   Self-RAG Retry Loop
BGE ONNX INT8         Confidence Overhaul          RRF Fusion
Build Pipeline        (parallel — no dependency)
Index Metadata
────────────────────────────────────────────────────────────────────────────────────────────
                                    ▲ Full regression test between each sprint
```

**Rationale:**
- WS-1 first: everything depends on the embedding provider abstraction
- WS-2 + WS-3 parallel: both only touch `retrieval_service.py` and are independent of each other
- WS-4 after WS-2: decomposer produces sub-queries with `MetadataFilters` from WS-2
- WS-5 after WS-4: retry loop re-runs the full pipeline (needs decomposition in place)

---

## 2. Sprint 1 — WS-1: Embedding Provider Swap

### 2.1 Pre-requisites

- [ ] Build BGE ONNX INT8 model artifacts (one-time developer task)
- [ ] Validate `tokenizers` package works in PyInstaller frozen environment
- [ ] Benchmark BGE INT8 inference latency (target: <50ms per query embed)

### 2.2 File Change Matrix

| File | Action | Description |
|------|--------|-------------|
| `backend/vector/embedding_provider.py` | **CREATE** | `EmbeddingProvider` ABC, `LegacyChromaProvider`, `ChromaEmbeddingAdapter`, `get_provider()` factory |
| `backend/vector/bge_onnx_provider.py` | **CREATE** | `BgeOnnxInt8Provider` — ONNX inference, tokenization, mean pooling, L2 norm |
| `backend/vector/store.py` | **MODIFY** | Accept `EmbeddingProvider` in constructor; use `embed_query()` for search; write index metadata |
| `backend/retrieval/term_registry.py` | **MODIFY** | Accept `EmbeddingProvider` instead of `DefaultEmbeddingFunction()` |
| `config/settings.py` | **MODIFY** | Add `embed_provider`, `embed_model_path` fields to `KTSConfig` |
| `backend/agents/retrieval_service.py` | **MODIFY** | Instantiate provider via factory; pass to VectorStore and TermRegistry |
| `backend/agents/ingestion_agent.py` | **MODIFY** | Instantiate provider via factory; pass to VectorStore |
| `cli/main.py` | **MODIFY** | Instantiate provider; wire to ingestion and search commands |
| `packaging/kts_backend.spec` | **MODIFY** | Replace MiniLM model bundling with BGE INT8; add tokenizer files; remove monkey-patch |
| `scripts/model_build/build_bge_onnx_int8.ps1` | **CREATE** | One-time model export, quantization, validation script |
| `assets/models/bge-base-en-v1.5/onnx-int8/` | **CREATE** | Model artifacts (model.onnx, tokenizer.json, vocab.txt, config.json, etc.) |
| `requirements.txt` | **MODIFY** | Add `tokenizers>=0.19.0` |

### 2.3 Implementation Steps

1. **Create `embedding_provider.py`** — ABC + `LegacyChromaProvider` + `ChromaEmbeddingAdapter` + factory
2. **Create `bge_onnx_provider.py`** — ONNX session, tokenizer loading, batch inference, pooling
3. **Run model build script** — Generate INT8 artifacts, place in `assets/models/`
4. **Modify `config/settings.py`** — Add 2 new fields (`embed_provider`, `embed_model_path`)
5. **Modify `store.py`** — New constructor signature, `embed_query()` in `search()`, index metadata write/check
6. **Modify `term_registry.py`** — Use provider's `embed_documents()` instead of `DefaultEmbeddingFunction`
7. **Modify `retrieval_service.py`** — Provider factory in `__init__()`, pass through
8. **Modify `ingestion_agent.py`** — Provider factory, pass to VectorStore
9. **Modify `cli/main.py`** — Provider wiring for both `ingest` and `search` commands
10. **Modify `kts_backend.spec`** — Remove MiniLM bundling, add BGE INT8 bundling, remove monkey-patch
11. **Modify `requirements.txt`** — Add `tokenizers`
12. **Write unit tests** — Provider interface, BGE inference, VectorStore integration
13. **Rebuild VSIX** — Verify size ≤250 MB, verify offline operation

### 2.4 Rollback Checkpoint

After step 6, verify:
- `KTS_EMBED_PROVIDER=legacy_chroma_default` falls back to MiniLM
- `KTS_EMBED_PROVIDER=bge_onnx_int8` uses BGE
- Index metadata mismatch is detected and reported

### 2.5 Estimated Effort

| Task | Effort |
|------|--------|
| Provider abstraction (ABC + Legacy + Adapter) | 2 hours |
| BGE ONNX provider (inference + tokenizer) | 3 hours |
| Model build script | 2 hours |
| VectorStore + TermRegistry refactor | 2 hours |
| Config + wiring (retrieval_service, ingestion, CLI) | 2 hours |
| PyInstaller spec + VSIX rebuild | 2 hours |
| Unit tests | 2 hours |
| Integration test + golden query regression | 2 hours |
| **Total** | **~17 hours** |

---

## 3. Sprint 2 — WS-2 + WS-3 (Parallel)

### 3.1 WS-2: Self-Query Filter Extraction

#### File Change Matrix

| File | Action | Description |
|------|--------|-------------|
| `backend/retrieval/self_query_extractor.py` | **CREATE** | `SelfQueryExtractor` class, `MetadataFilters` dataclass |
| `backend/vector/store.py` | **MODIFY** | Enhanced `search()` with `MetadataFilters` support, `$in` / `$and` where clauses, fallback |
| `backend/agents/retrieval_service.py` | **MODIFY** | Integrate extractor between acronym resolution and vector search |
| `config/settings.py` | **MODIFY** | Add `self_query_enabled`, `min_filtered_results` |
| `backend/common/models.py` | **MODIFY** | Add `MetadataFilters` dataclass (or keep in self_query_extractor.py) |

#### Implementation Steps

1. **Create `self_query_extractor.py`** — `MetadataFilters` dataclass, `SelfQueryExtractor` with intent→filter map, error code regex, tool name lookup, query cleaning
2. **Modify `store.py`** — Add `filters: MetadataFilters | None` param to `search()`, build composite where clause, implement fallback
3. **Modify `config/settings.py`** — 2 new fields
4. **Modify `retrieval_service.py`** — Wire extractor after acronym resolution
5. **Write tests** — Filter extraction accuracy, where clause construction, fallback behavior

#### Effort: ~8 hours

### 3.2 WS-3: Confidence Score Overhaul

#### File Change Matrix

| File | Action | Description |
|------|--------|-------------|
| `backend/agents/retrieval_service.py` | **MODIFY** | Replace confidence formula, store features on rows, add `_compute_confidence()` method |

#### Implementation Steps

1. **Add `_compute_confidence()` method** — Multi-signal weighted formula
2. **Modify `rerank_scorer()`** — Persist `features` and `graph_boost` on each row dict
3. **Replace inline confidence calculation** — Call `_compute_confidence()` at step 12
4. **Write tests** — Confidence distribution tests across query types, calibration validation

#### Effort: ~4 hours

### 3.3 Sprint 2 Total: ~12 hours

---

## 4. Sprint 3 — WS-4: Query Decomposition + RRF

### File Change Matrix

| File | Action | Description |
|------|--------|-------------|
| `backend/retrieval/query_decomposer.py` | **CREATE** | `QueryDecomposer` class, `SubQuery` dataclass, rule-based splitting, step-back generation |
| `backend/retrieval/rank_fusion.py` | **CREATE** | `reciprocal_rank_fusion()` function |
| `backend/agents/retrieval_service.py` | **MODIFY** | Loop over sub-queries, call RRF, restructure execute() into stages |
| `config/settings.py` | **MODIFY** | Add `query_decomposition_enabled`, `query_decomposition_use_llm`, `rrf_k` |

### Implementation Steps

1. **Create `query_decomposer.py`** — Split patterns, step-back logic, deduplication, LLM stub
2. **Create `rank_fusion.py`** — RRF implementation, id-based merging
3. **Refactor `retrieval_service.py`** — Extract `_retrieve_and_rank()` helper for re-use by both main pipeline and retry loop; replace single search call with sub-query loop + RRF
4. **Modify `config/settings.py`** — 3 new fields
5. **Write tests** — Decomposition accuracy, RRF correctness, latency benchmarks

### Effort: ~10 hours

---

## 5. Sprint 4 — WS-5: Self-RAG Retry Loop

### File Change Matrix

| File | Action | Description |
|------|--------|-------------|
| `backend/agents/retrieval_service.py` | **MODIFY** | Add retry loop around evidence matching, query rewriting from uncited claims, chunk merging |
| `config/settings.py` | **MODIFY** | Add `self_rag_retry_enabled`, `self_rag_max_retries`, `self_rag_coverage_threshold` |

### Implementation Steps

1. **Implement `_build_retry_query()`** — Extract novel terms from uncited claims
2. **Add retry loop** — After evidence matching, check coverage, rewrite, re-retrieve, merge, re-check
3. **Integrate with `_compute_confidence()`** — Pass final coverage to confidence formula
4. **Modify `config/settings.py`** — 3 new fields
5. **Write tests** — Retry trigger conditions, query rewriting, coverage improvement, retry budget enforcement

### Effort: ~8 hours

---

## 6. Config Additions Summary

All fields added to `KTSConfig` in `config/settings.py`:

| Sprint | Field | Type | Default | Env Var |
|--------|-------|------|---------|---------|
| 1 | `embed_provider` | `str` | `"bge_onnx_int8"` | `KTS_EMBED_PROVIDER` |
| 1 | `embed_model_path` | `str` | `""` | `KTS_EMBED_MODEL_PATH` |
| 2 | `self_query_enabled` | `bool` | `True` | `KTS_SELF_QUERY_ENABLED` |
| 2 | `min_filtered_results` | `int` | `2` | `KTS_MIN_FILTERED_RESULTS` |
| 3 | *(no config — formula lives in code)* | — | — | — |
| 4 | `query_decomposition_enabled` | `bool` | `True` | `KTS_QUERY_DECOMPOSITION_ENABLED` |
| 4 | `query_decomposition_use_llm` | `bool` | `False` | `KTS_QUERY_DECOMPOSITION_USE_LLM` |
| 4 | `rrf_k` | `int` | `60` | `KTS_RRF_K` |
| 5 | `self_rag_retry_enabled` | `bool` | `False` | `KTS_SELF_RAG_RETRY_ENABLED` |
| 5 | `self_rag_max_retries` | `int` | `1` | `KTS_SELF_RAG_MAX_RETRIES` |
| 5 | `self_rag_coverage_threshold` | `float` | `0.80` | `KTS_SELF_RAG_COVERAGE_THRESHOLD` |

**Total new config fields:** 11

---

## 7. New Files Summary

| File | Sprint | Component |
|------|--------|-----------|
| `backend/vector/embedding_provider.py` | 1 | ABC + Legacy + Adapter + factory |
| `backend/vector/bge_onnx_provider.py` | 1 | BGE ONNX INT8 provider |
| `scripts/model_build/build_bge_onnx_int8.ps1` | 1 | Model build script (dev only) |
| `assets/models/bge-base-en-v1.5/onnx-int8/*` | 1 | Model artifacts |
| `backend/retrieval/self_query_extractor.py` | 2 | Filter extraction |
| `backend/retrieval/query_decomposer.py` | 3 | Query splitting + step-back |
| `backend/retrieval/rank_fusion.py` | 3 | RRF implementation |

**Total new Python files:** 5  
**Total new files (incl. model artifacts + script):** ~12

---

## 8. Modified Files Summary

| File | Sprints | Changes |
|------|---------|---------|
| `backend/vector/store.py` | 1, 2 | Provider injection, query embedding, filter support, fallback, index metadata |
| `backend/agents/retrieval_service.py` | 1, 2, 3, 4, 5 | Provider wiring, self-query, confidence, decomposition, retry loop |
| `backend/agents/ingestion_agent.py` | 1 | Provider wiring |
| `backend/retrieval/term_registry.py` | 1 | Provider injection |
| `config/settings.py` | 1, 2, 4, 5 | 11 new config fields |
| `cli/main.py` | 1 | Provider instantiation |
| `packaging/kts_backend.spec` | 1 | Model bundling swap |
| `requirements.txt` | 1 | Add `tokenizers` |
| `backend/common/models.py` | 2 (optional) | `MetadataFilters` dataclass |

---

## 9. VSIX Build Impact

| Component | Phase 4 Size | Phase 5 Size | Delta |
|-----------|-------------|-------------|-------|
| MiniLM-L6-v2 ONNX FP32 | 86.2 MB | 0 MB (removed) | -86.2 MB |
| BGE-base-en-v1.5 ONNX INT8 | 0 MB | ~110 MB | +110 MB |
| tokenizers wheel | 0 MB | ~5 MB | +5 MB |
| New Python files | 0 MB | <0.1 MB | +0.1 MB |
| **Net delta** | — | — | **+28.9 MB** |
| **Total VSIX** | 222.6 MB | **~251.5 MB** | — |

**Risk:** Slightly over 250 MB budget. Mitigations:
1. ONNX INT8 model may compress better in 7z (VSIX format) — need to measure
2. Can strip unused ONNX runtime providers from PyInstaller bundle (~10 MB savings)
3. If needed, pruning unused chromadb model cache will reclaim space

---

## 10. Risk Mitigation Checkpoints

| After Sprint | Checkpoint |
|---|---|
| **Sprint 1** | Golden query regression (all 3 source folders). Compare BGE vs MiniLM hit rates. If BGE is worse on >10% of queries → investigate before proceeding. |
| **Sprint 2** | Verify self-query filters improve precision without hurting recall. Check fallback engages correctly. Confidence distribution analysis — no query type should be miscalibrated by >0.2. |
| **Sprint 3** | Latency benchmark: decomposed queries must stay under 2× baseline latency. RRF must not introduce duplicate results. |
| **Sprint 4** | Self-RAG retry must not cause infinite loops (budget enforcement). Coverage improvement must be measurable on at least 2 golden queries. |

---

## 11. Integration Sequence Diagram

```
Sprint 1 complete → FULL RETEST → Sprint 2 starts
    │
    ├── Branch: WS-2 (self-query)     ─┐
    ├── Branch: WS-3 (confidence)     ─┤ parallel
    │                                   │
    └── Merge both → FULL RETEST ──────┘
                │
                ▼
        Sprint 3 starts (decomposition + RRF)
                │
                ▼
        Sprint 3 complete → FULL RETEST
                │
                ▼
        Sprint 4 starts (self-RAG)
                │
                ▼
        Sprint 4 complete → FINAL VALIDATION
                │
                ▼
        Phase 5 complete → VSIX build → smoke test
```

Each sprint boundary includes a full golden query regression using `tests/golden_queries_v2.json` and the 3 source folders.
