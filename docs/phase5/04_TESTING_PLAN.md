# Phase 5 — Testing Plan

**Date**: 2026-02-16  
**Status**: Design — pending approval

---

## 1. Test Strategy Overview

```
                     ┌──────────────────────────────────┐
                     │     FINAL VALIDATION             │
                     │  VSIX offline smoke test          │
                     │  3-folder golden regression       │
                     │  Confidence distribution audit    │
                     └──────────────────────────────────┘
                                    ▲
                     ┌──────────────────────────────────┐
                     │     INTEGRATION TESTS            │
                     │  Full pipeline: ingest → search   │
                     │  Golden query regression          │
                     │  Cross-sprint compatibility       │
                     └──────────────────────────────────┘
                                    ▲
                     ┌──────────────────────────────────┐
                     │     COMPONENT TESTS              │
                     │  Provider ↔ VectorStore           │
                     │  Extractor ↔ RetrievalService     │
                     │  Decomposer ↔ RRF ↔ Ranking      │
                     └──────────────────────────────────┘
                                    ▲
                     ┌──────────────────────────────────┐
                     │     UNIT TESTS                   │
                     │  Per-module isolated tests        │
                     │  Mock dependencies               │
                     └──────────────────────────────────┘
```

All tests run offline. No network access. No LLM calls (unless `query_decomposition_use_llm` is explicitly tested with a mock).

---

## 2. Sprint 1 Tests — WS-1: Embedding Provider

### 2.1 Unit Tests

**File: `tests/test_embedding_provider.py`**

| Test ID | Test Name | Description | Pass Criteria |
|---------|-----------|-------------|---------------|
| EP-01 | `test_bge_embed_query_returns_768_dims` | Call `embed_query("hello world")`, check shape | `len(result) == 768` |
| EP-02 | `test_bge_embed_documents_batch` | Embed 10 documents, check all 768-dim | All vectors have `len == 768` |
| EP-03 | `test_bge_query_prefix_applied` | Verify `embed_query()` internally prepends prefix | Mock tokenizer, assert input starts with `"Represent this sentence: "` |
| EP-04 | `test_bge_embed_documents_no_prefix` | Verify `embed_documents()` does NOT prepend prefix | Mock tokenizer, assert no prefix |
| EP-05 | `test_bge_l2_normalized` | Verify output vectors are L2-normalized | `np.linalg.norm(vec) ≈ 1.0` (±1e-5) |
| EP-06 | `test_bge_deterministic` | Same input → same output | Two calls with same text → identical vectors |
| EP-07 | `test_legacy_provider_returns_384_dims` | `LegacyChromaProvider.embed_query()` → 384 | `len(result) == 384` |
| EP-08 | `test_chroma_adapter_callable` | `as_chroma_ef()` returns callable that ChromaDB accepts | `callable(adapter)` and `adapter(["text"])` returns list of lists |
| EP-09 | `test_provider_factory_bge` | `get_provider("bge_onnx_int8")` returns `BgeOnnxInt8Provider` | `isinstance(result, BgeOnnxInt8Provider)` |
| EP-10 | `test_provider_factory_legacy` | `get_provider("legacy_chroma_default")` returns `LegacyChromaProvider` | `isinstance(result, LegacyChromaProvider)` |
| EP-11 | `test_provider_factory_invalid` | `get_provider("nonexistent")` raises `ValueError` | `pytest.raises(ValueError)` |
| EP-12 | `test_model_hash_stable` | Same model file → same hash | Two instantiations → same `model_hash` |
| EP-13 | `test_bge_max_seq_len_truncation` | Embed a 1000-token input → no crash | Completes without error |
| EP-14 | `test_bge_empty_input` | `embed_documents([])` → empty list | `result == []` |
| EP-15 | `test_bge_unicode_input` | Embed text with CJK/emoji → no crash | Returns valid 768-dim vector |

### 2.2 Component Tests

**File: `tests/test_vectorstore_provider.py`**

| Test ID | Test Name | Description | Pass Criteria |
|---------|-----------|-------------|---------------|
| VS-01 | `test_vectorstore_accepts_provider` | Construct `VectorStore` with `BgeOnnxInt8Provider` | No exception |
| VS-02 | `test_ingest_and_search_bge` | Ingest 3 chunks, search, verify results returned | ≥1 result with score > 0 |
| VS-03 | `test_search_uses_embed_query` | Verify `search()` calls `provider.embed_query()` (not `embed_documents()`) | Mock provider, assert `embed_query` called |
| VS-04 | `test_ingest_uses_embed_documents` | Verify upsert calls `embed_documents()` via ChromaDB adapter | Mock provider, assert `embed_documents` called |
| VS-05 | `test_index_metadata_written` | After init, check `index_metadata.json` exists | File exists with correct `provider_id` and `dims` |
| VS-06 | `test_index_metadata_mismatch_detected` | Write metadata for MiniLM, then init with BGE → error | Appropriate error raised or logged |

### 2.3 Integration Test

**File: `tests/test_embedding_integration.py`**

| Test ID | Test Name | Description | Pass Criteria |
|---------|-----------|-------------|---------------|
| EI-01 | `test_full_ingest_search_bge` | Ingest a real Troubleshooting doc, search for its error code | Hit rate 100% for the ingested doc |
| EI-02 | `test_term_registry_with_bge` | Register terms using BGE provider, verify synonym clustering | Synonyms group correctly (cosine > 0.7 within cluster) |
| EI-03 | `test_legacy_roundtrip` | Set `embed_provider=legacy_chroma_default`, ingest + search | Results identical to Phase 4 baseline |

### 2.4 Performance Benchmarks

| Metric | Baseline (MiniLM) | Target (BGE INT8) | Measurement Method |
|--------|-------------------|--------------------|--------------------|
| Query embed latency | ~5ms | <50ms | `time.perf_counter()` over 100 queries |
| Document batch embed (32 chunks) | ~20ms | <200ms | Same |
| VSIX size | 222.6 MB | ≤255 MB | `(Get-Item *.vsix).Length` |
| Memory at startup | ~180 MB | <250 MB | `psutil.Process().memory_info().rss` |

---

## 3. Sprint 2 Tests — WS-2: Self-Query + WS-3: Confidence

### 3.1 WS-2 Unit Tests

**File: `tests/test_self_query_extractor.py`**

| Test ID | Test Name | Input Query | Expected Filters |
|---------|-----------|-------------|-----------------|
| SQ-01 | `test_error_code_extraction` | `"How to fix ERR-TLS-014?"` | `error_code="ERR-TLS-014"` |
| SQ-02 | `test_error_code_pattern_alt` | `"AUTH401 in BatchBridge"` | `error_code="AUTH401"` |
| SQ-03 | `test_tool_extraction` | `"BatchBridge connection fails"` | `tool="BatchBridge"` |
| SQ-04 | `test_intent_troubleshoot_filter` | `"How to troubleshoot timeout"` | `doc_type=["TROUBLESHOOT"]` |
| SQ-05 | `test_intent_howto_filter` | `"How do I configure SSL?"` | `doc_type=["SOP", "USER_GUIDE"]` |
| SQ-06 | `test_intent_general_no_filter` | `"Tell me about the system"` | `doc_type=None` |
| SQ-07 | `test_query_cleaning` | `"Fix ERR-TLS-014 in BatchBridge"` | `cleaned_query` has error code and tool removed |
| SQ-08 | `test_multiple_filters` | `"ERR-RATE-429 in OpsFlow troubleshoot"` | `error_code`, `tool`, and `doc_type` all set |
| SQ-09 | `test_no_filters_extracted` | `"general question about things"` | All filter fields `None` |

### 3.2 WS-2 Component Tests

**File: `tests/test_self_query_integration.py`**

| Test ID | Test Name | Description | Pass Criteria |
|---------|-----------|-------------|---------------|
| SQI-01 | `test_filtered_search_narrows_results` | Search with doc_type filter vs without | Filtered results all match doc_type |
| SQI-02 | `test_fallback_on_empty_filtered_results` | Filter returns 0 results → fallback triggers | Results returned despite filter |
| SQI-03 | `test_where_clause_composition` | Multiple filters → `$and` clause constructed | ChromaDB query executes without error |
| SQI-04 | `test_in_filter_multiple_doc_types` | `doc_type=["SOP", "USER_GUIDE"]` → `$in` clause | Both doc types appear in results |

### 3.3 WS-3 Unit Tests

**File: `tests/test_confidence_overhaul.py`**

| Test ID | Test Name | Scenario | Expected Confidence Range |
|---------|-----------|----------|--------------------------|
| CO-01 | `test_high_confidence_all_signals` | All signals high (sim=0.95, CE=0.9, graph=0.5, error match, intent match) | 0.85-0.98 |
| CO-02 | `test_medium_confidence_partial` | Decent similarity (0.7), no error match, some entity overlap | 0.50-0.70 |
| CO-03 | `test_low_confidence_vague_query` | Low similarity (0.3), no matches on any feature | 0.10-0.30 |
| CO-04 | `test_zero_confidence_no_results` | Empty rows | 0.0 |
| CO-05 | `test_coverage_penalty` | Good signals but coverage=0.5 | Confidence reduced by ~25% vs no penalty |
| CO-06 | `test_chunk_bonus` | 5 chunks vs 1 chunk, same top score | 5-chunk version ~0.08 higher |
| CO-07 | `test_filter_engaged_bonus` | Same signals, filter on vs off | Filter version ~0.05 higher |
| CO-08 | `test_weights_sum_to_one` | Verify weight constants | `sum(weights) == 1.0` |

### 3.4 Confidence Distribution Test

**File: `tests/test_confidence_distribution.py`**

Run all golden queries and produce a histogram:

```python
def test_confidence_distribution():
    """Verify confidence scores are well-distributed, not clustered."""
    golden = load_golden_queries()  # tests/golden_queries_v2.json
    confidences = []

    for gq in golden:
        result = search(gq["query"])
        confidences.append(result.confidence)

    # No more than 30% of queries should have confidence > 0.9
    # (Phase 4 problem: most queries clustered around 0.85-0.95)
    high_conf = sum(1 for c in confidences if c > 0.9) / len(confidences)
    assert high_conf < 0.30, f"Too many high-confidence results: {high_conf:.0%}"

    # At least 10% should be below 0.5 (negative/vague queries)
    low_conf = sum(1 for c in confidences if c < 0.5) / len(confidences)
    assert low_conf > 0.05, f"Too few low-confidence results: {low_conf:.0%}"
```

---

## 4. Sprint 3 Tests — WS-4: Query Decomposition + RRF

### 4.1 Unit Tests

**File: `tests/test_query_decomposer.py`**

| Test ID | Test Name | Input Query | Expected Sub-queries |
|---------|-----------|-------------|---------------------|
| QD-01 | `test_simple_query_no_split` | `"How to fix timeout?"` | 1 sub-query (original only) + optional step-back |
| QD-02 | `test_conjunction_split` | `"Fix AUTH401 and what is escalation?"` | 2-3 sub-queries (original + 2 parts) |
| QD-03 | `test_semicolon_split` | `"Check logs; restart service"` | 2-3 sub-queries |
| QD-04 | `test_question_sequence_split` | `"What is TLS? How to renew certs?"` | 2-3 sub-queries |
| QD-05 | `test_step_back_generated` | `"Fix ERR-TLS-014 v2.3 timeout"` | Step-back query without error code/version |
| QD-06 | `test_max_four_sub_queries` | Complex 5-clause query | ≤4 sub-queries returned |
| QD-07 | `test_deduplication` | Query where split produces near-duplicate | Duplicates removed |
| QD-08 | `test_short_parts_filtered` | `"Fix X and Y"` (Y too short) | Short parts (<10 chars) excluded |

**File: `tests/test_rank_fusion.py`**

| Test ID | Test Name | Description | Pass Criteria |
|---------|-----------|-------------|---------------|
| RF-01 | `test_rrf_single_set` | Single result set → passthrough | Order preserved |
| RF-02 | `test_rrf_two_sets_overlap` | 2 sets with 50% overlap | Overlapping docs ranked higher |
| RF-03 | `test_rrf_two_sets_disjoint` | 2 sets with no overlap | All docs present in output |
| RF-04 | `test_rrf_score_formula` | Known ranks → verify RRF score | `score == 1/(60+1) + 1/(60+2)` for doc in both sets at rank 1 and 2 |
| RF-05 | `test_rrf_preserves_best_metadata` | Same doc in 2 sets with different scores | Higher-scored version's metadata kept |
| RF-06 | `test_rrf_empty_sets` | Empty input → empty output | `result == []` |

### 4.2 Component Tests

**File: `tests/test_decomposition_integration.py`**

| Test ID | Test Name | Description | Pass Criteria |
|---------|-----------|-------------|---------------|
| DI-01 | `test_decomposed_search_multi_topic` | Query about 2 different error codes → both found in results | Both error codes appear in returned chunks |
| DI-02 | `test_decomposed_vs_single_recall` | Compare recall for multi-topic query: single vs decomposed | Decomposed recall ≥ single recall |
| DI-03 | `test_latency_within_budget` | Complex decomposed query (3 sub-queries) | Total latency < 2× baseline |

---

## 5. Sprint 4 Tests — WS-5: Self-RAG Retry

### 5.1 Unit Tests

**File: `tests/test_self_rag_retry.py`**

| Test ID | Test Name | Description | Pass Criteria |
|---------|-----------|-------------|---------------|
| SR-01 | `test_retry_triggers_on_low_coverage` | Coverage 0.5 < threshold 0.8 → retry fires | Retry query constructed |
| SR-02 | `test_no_retry_on_good_coverage` | Coverage 0.9 ≥ threshold 0.8 → no retry | Retry loop NOT entered |
| SR-03 | `test_retry_budget_enforced` | Force 3 retries with max=1 | Only 1 retry executed |
| SR-04 | `test_same_query_skips_retry` | Uncited claims produce same query → skip | Loop exits early |
| SR-05 | `test_retry_query_uses_novel_terms` | Verify retry query contains terms not in existing chunks | Novel terms present in retry query |
| SR-06 | `test_chunk_merge_deduplicates` | Retry returns overlapping chunks | No duplicate chunk_ids in final set |
| SR-07 | `test_coverage_improves_after_retry` | Mock: retry returns missing chunks | Final coverage > initial coverage |
| SR-08 | `test_disabled_by_default` | `self_rag_retry_enabled=False` → no retry | Retry loop never entered |

### 5.2 Integration Test

| Test ID | Test Name | Description | Pass Criteria |
|---------|-----------|-------------|---------------|
| SRI-01 | `test_self_rag_end_to_end` | Ingest partial corpus, query, verify retry improves results | Coverage improves or confidence adjusts |

---

## 6. Golden Query Regression

### 6.1 Existing Test Assets

| Asset | Location | Count |
|-------|----------|-------|
| Golden queries v2 | `tests/golden_queries_v2.json` | ~40 queries |
| Golden queries v1 | `tests/golden_queries.json` | ~20 queries |
| PSA test queries | `tests/psa_test_queries.json` | ~10 queries |
| PSA golden standard | `tests/golden_psa_2006he1.json` | 1 comprehensive test |
| Score queries | `tests/score_queries.py` | Scoring harness |

### 6.2 Regression Test Protocol

Run at each sprint boundary:

```python
def test_golden_regression():
    """
    Run all golden queries. Compare results to Phase 4 baseline.
    
    Pass criteria:
    - Hit rate ≥ Phase 4 hit rate (no regression)
    - Mean confidence within ±0.15 of baseline (calibration change expected)
    - No query that previously returned results now returns empty
    - Latency within 2× of baseline per query
    """
    baseline = load_baseline("tests/phase4_baseline.json")
    golden = load_golden_queries()

    regressions = []
    for gq in golden:
        result = search(gq["query"])
        b = baseline[gq["id"]]

        # Hit rate check
        if b["hit"] and not result.context_chunks:
            regressions.append(f"{gq['id']}: was hit, now miss")

        # Confidence delta check
        delta = abs(result.confidence - b["confidence"])
        if delta > 0.15:
            regressions.append(f"{gq['id']}: confidence delta {delta:.2f}")

    assert not regressions, f"Regressions:\n" + "\n".join(regressions)
```

### 6.3 Baseline Capture

Before starting Sprint 1, capture Phase 4 baselines:

```powershell
# Capture baseline for all golden queries
python -m pytest tests/score_queries.py --json-report --json-report-file=tests/phase4_baseline.json
```

This baseline is used for all subsequent regression comparisons.

---

## 7. Performance Test Suite

### 7.1 Latency Benchmarks

**File: `tests/test_performance.py`**

| Metric | Phase 4 Baseline | Phase 5 Target | Max Allowed |
|--------|-----------------|----------------|-------------|
| Single query (no decomposition) | ~200ms | ~250ms | 500ms |
| Decomposed query (2 sub-queries) | N/A | ~400ms | 800ms |
| Decomposed query (3 sub-queries) | N/A | ~500ms | 1000ms |
| Self-RAG retry (1 retry) | N/A | ~700ms | 1500ms |
| Ingestion: 1 document (10 chunks) | ~2s | ~3s | 5s |
| Full corpus ingestion (3 folders) | ~30s | ~45s | 90s |

### 7.2 Memory Benchmarks

| Metric | Phase 4 | Phase 5 Target | Max |
|--------|---------|----------------|-----|
| Backend startup RSS | ~180 MB | <250 MB | 350 MB |
| Per-query allocation | ~5 MB | <10 MB | 20 MB |
| Peak during ingestion | ~300 MB | <400 MB | 500 MB |

---

## 8. VSIX Offline Validation

**File: `tests/test_vsix_offline.py`** (extends existing `test_vsix_full_retest.py`)

| Test ID | Test Name | Description |
|---------|-----------|-------------|
| VO-01 | `test_no_network_during_ingest` | Ingest with network adapter disabled → success |
| VO-02 | `test_no_network_during_search` | Search with network adapter disabled → success |
| VO-03 | `test_model_files_bundled` | Check `sys._MEIPASS/models/bge-base-en-v1.5/onnx-int8/` contains `model.onnx`, `tokenizer.json`, `vocab.txt` |
| VO-04 | `test_no_download_attempt` | Monitor stdout/stderr during startup → no download messages |
| VO-05 | `test_onnxruntime_cpu_only` | Verify only CPUExecutionProvider used → no CUDA/GPU fallback |

---

## 9. Negative / Edge Case Tests

**File: `tests/test_phase5_edge_cases.py`**

| Test ID | Test Name | Description |
|---------|-----------|-------------|
| EC-01 | `test_empty_corpus_search` | Search on empty vector store → graceful empty result |
| EC-02 | `test_single_chunk_corpus` | Only 1 chunk ingested → search returns it with appropriate confidence |
| EC-03 | `test_unicode_query` | Query with CJK/emoji characters → no crash |
| EC-04 | `test_very_long_query` | 500-word query → truncated gracefully, results returned |
| EC-05 | `test_all_features_disabled` | All new features off (`self_query_enabled=False`, etc.) → Phase 4 behavior |
| EC-06 | `test_config_env_var_overrides` | Set `KTS_EMBED_PROVIDER=legacy_chroma_default` → uses legacy |
| EC-07 | `test_index_metadata_corruption` | Malformed `index_metadata.json` → clear error, not crash |
| EC-08 | `test_concurrent_ingest_and_search` | Ingest while searching → no data corruption |

---

## 10. Test File Index

| File | Sprint | Tests | Focus |
|------|--------|-------|-------|
| `tests/test_embedding_provider.py` | 1 | 15 | BGE provider unit tests |
| `tests/test_vectorstore_provider.py` | 1 | 6 | VectorStore + provider integration |
| `tests/test_embedding_integration.py` | 1 | 3 | Full ingest→search with BGE |
| `tests/test_self_query_extractor.py` | 2 | 9 | Filter extraction unit tests |
| `tests/test_self_query_integration.py` | 2 | 4 | Filtered search component tests |
| `tests/test_confidence_overhaul.py` | 2 | 8 | Confidence formula unit tests |
| `tests/test_confidence_distribution.py` | 2 | 1 | Distribution analysis |
| `tests/test_query_decomposer.py` | 3 | 8 | Decomposition unit tests |
| `tests/test_rank_fusion.py` | 3 | 6 | RRF unit tests |
| `tests/test_decomposition_integration.py` | 3 | 3 | Multi-query retrieval component tests |
| `tests/test_self_rag_retry.py` | 4 | 8 | Self-RAG unit tests |
| `tests/test_performance.py` | All | 6 | Latency + memory benchmarks |
| `tests/test_vsix_offline.py` | Final | 5 | Offline + bundling validation |
| `tests/test_phase5_edge_cases.py` | Final | 8 | Negative / edge cases |
| **Total** | | **~90** | |

---

## 11. Test Dependencies

| Package | Purpose | Already Available |
|---------|---------|-------------------|
| `pytest` | Test runner | Yes |
| `pytest-json-report` | Baseline capture | Check (may need install) |
| `psutil` | Memory benchmarks | Check (may need install) |

No additional test dependencies beyond existing test infrastructure.
