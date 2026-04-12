# Phase 6: Comprehensive Testing Plan
## Validation Strategy for Unified Hierarchical GraphRAG

**Document Version:** 1.0  
**Date:** February 2026  
**Status:** Active  
**Scope:** End-to-end testing strategy covering all Phase 6 components

---

## Table of Contents
1. [Overview](#overview)
2. [Test Categories](#test-categories)
3. [Phase 0 Tests — Multi-Level Section Regex](#phase-0-tests)
4. [Phase 1 Tests — ItemExtractor Framework](#phase-1-tests)
5. [Phase 2 Tests — Dual Vector Stores & Section Nodes](#phase-2-tests)
6. [Phase 3 Tests — REFERENCES Edges](#phase-3-tests)
7. [Phase 4 Tests — PageRank Boost](#phase-4-tests)
8. [Phase 5 Tests — Iterative Multi-Hop Retrieval](#phase-5-tests)
9. [Phase 6 Tests — Section-Specific Queries](#phase-6-tests)
10. [Cross-Domain Validation](#cross-domain-validation)
11. [Performance Benchmarks](#performance-benchmarks)
12. [Golden Query Validation](#golden-query-validation)
13. [Regression Tests](#regression-tests)
14. [AI Explainability Logging Validation](#ai-explainability-logging)
15. [VSIX Integration Tests](#vsix-integration-tests)
16. [Knowledge Source Test Corpora](#knowledge-source-test-corpora)
17. [Test Execution Guide](#test-execution-guide)

---

## Overview

### Testing Philosophy
- **Every phase is independently testable** — each has its own test file
- **Feature flags protect production** — `phase6_enabled` toggles entire Phase 6 pipeline
- **Golden query benchmarks must be maintained or improved** — no regression allowed
- **Three existing knowledge sources used for all testing** — `kts_synthetic_corpus_v2`, `kts_test_corpus`, and workspace source documents
- **AI explainability logging verified** — VS Code output channel shows detailed step-by-step reasoning

### Test Summary

| Category | Test Count | Test File(s) |
|----------|-----------|--------------|
| Phase 0 — Regex Fix | 7 | `test_phase6_regex.py` |
| Phase 1 — ItemExtractor | 60+ | `test_item_extractors.py` |
| Phase 2 — Dual Stores | 15 | `test_phase6_ingestion.py` |
| Phase 3 — REFERENCES | 10 | `test_reference_edges.py` |
| Phase 4 — PageRank | 12 | `test_pagerank.py` |
| Phase 5 — Iterative | 20 | `test_iterative_retrieval.py` |
| Phase 6 — Section Queries | 10 | `test_section_queries.py` |
| Cross-Domain | 9 | `test_cross_domain.py` |
| Performance | 5 | `test_performance_benchmarks.py` |
| Golden Queries | 10 | `test_golden_queries_phase6.py` |
| Regression | 20 | `test_regression_phase6.py` |
| AI Explainability | 8 | `test_explainability_logging.py` |
| VSIX Integration | 10 | `test_vsix_phase6.py` |
| **TOTAL** | **~196** | **13 test files** |

---

## Phase 0 Tests — Multi-Level Section Regex

### File: `tests/test_phase6_regex.py`

| # | Test Name | Description | Expected Result |
|---|-----------|-------------|-----------------|
| 1 | `test_section_single_level` | Match "Section 5" | Group(1) = "5" |
| 2 | `test_section_two_level` | Match "Section 5.02" | Group(1) = "5.02" |
| 3 | `test_section_three_level` | Match "Section 5.02.03" | Group(1) = "5.02.03" |
| 4 | `test_section_four_level` | Match "Section 5.02.03.04" | Group(1) = "5.02.03.04" |
| 5 | `test_section_with_paren_lower` | Match "Section 5.02(a)" | Group(1) = "5.02(a)" |
| 6 | `test_section_with_paren_upper` | Match "Section 5.02(III)" | Group(1) = "5.02(III)" |
| 7 | `test_section_no_false_positives` | "Random text" should NOT match | No match |

**Pass Criteria:** All 7 tests pass, no existing chunker tests broken.

---

## Phase 1 Tests — ItemExtractor Framework

### File: `tests/test_item_extractors.py`

#### Base Class Tests (10)
| # | Test Name | Description |
|---|-----------|-------------|
| 1 | `test_generate_item_id_format` | ID format: `doc-sec042-type-0-hash` |
| 2 | `test_generate_item_id_uniqueness` | Different text → different IDs |
| 3 | `test_split_into_sentences_basic` | "First. Second." → 2 sentences |
| 4 | `test_split_into_sentences_abbreviations` | "U.S. law applies." → 1 sentence |
| 5 | `test_split_into_sentences_decimals` | "Section 5.02 defines." → 1 sentence |
| 6 | `test_extract_section_references` | "Section 5.02 and § 6.03" → ["5.02","6.03"] |
| 7 | `test_factory_routing_legal` | GOVERNING_DOC_LEGAL → LegalItemExtractor |
| 8 | `test_factory_routing_technical` | TECHNICAL_SPEC → TechnicalItemExtractor |
| 9 | `test_factory_routing_research` | RESEARCH_PAPER → ResearchItemExtractor |
| 10 | `test_factory_fallback_generic` | UNKNOWN → GenericItemExtractor |

#### Legal Extractor Tests (20)
| # | Test Name | Description |
|---|-----------|-------------|
| 11 | `test_legal_classify_obligation` | "Trustee shall establish..." → Obligation |
| 12 | `test_legal_classify_prohibition` | "Servicer shall not transfer..." → Prohibition |
| 13 | `test_legal_classify_right` | "Issuer may redeem..." → Right |
| 14 | `test_legal_classify_definition` | "Distribution Account means..." → Definition |
| 15 | `test_legal_classify_condition` | "If Closing Date occurs..." → Condition |
| 16 | `test_legal_classify_statement` | "The agreement is..." → Statement |
| 17 | `test_legal_prohibition_priority` | "shall not" beats "shall" → Prohibition |
| 18 | `test_legal_extract_actors_trustee` | Finds "Trustee" in actors |
| 19 | `test_legal_extract_actors_servicer` | Finds "Servicer" in actors |
| 20 | `test_legal_extract_actors_multiple` | Finds all mentioned actors |
| 21 | `test_legal_extract_modal_verbs` | Extracts shall, must, may |
| 22 | `test_legal_extract_defined_terms` | Extracts "Distribution Account" |
| 23 | `test_legal_extract_section_refs` | Extracts Section 5.02 |
| 24 | `test_legal_extract_items_full` | Full section → list of Items |
| 25 | `test_legal_empty_section` | Empty text → empty list |
| 26 | `test_legal_item_id_generated` | Each item has valid ID |
| 27 | `test_legal_item_metadata_shape` | Metadata has actors, verbs, defined_terms, section_refs |
| 28 | `test_legal_supported_types` | 6 types returned |
| 29 | `test_legal_required_to_obligation` | "is required to" → Obligation |
| 30 | `test_legal_subject_to_condition` | "subject to" → Condition |

#### Technical Extractor Tests (15)
| # | Test Name | Description |
|---|-----------|-------------|
| 31 | `test_tech_classify_requirement` | "System MUST validate..." → Requirement |
| 32 | `test_tech_classify_procedure` | "Step 1. Configure..." → Procedure |
| 33 | `test_tech_classify_configuration` | "Set timeout: 30s" → Configuration |
| 34 | `test_tech_classify_warning` | "WARNING: Do not..." → Warning |
| 35 | `test_tech_classify_note` | "Note: This feature..." → Note |
| 36 | `test_tech_classify_example` | "Example: code block" → Example |
| 37 | `test_tech_extract_parameters` | Extracts key:value pairs |
| 38 | `test_tech_extract_commands` | Extracts `$ command` |
| 39 | `test_tech_extract_files` | Extracts /path/to/file |
| 40 | `test_tech_extract_urls` | Extracts https://... |
| 41 | `test_tech_empty_section` | Empty text → empty list |
| 42 | `test_tech_supported_types` | 6 types returned |
| 43 | `test_tech_warning_priority` | WARNING overrides MUST → Warning |
| 44 | `test_tech_imperative_fallback` | "should configure" → Requirement |
| 45 | `test_tech_metadata_shape` | Metadata has parameters, commands, files, urls |

#### Research Extractor Tests (15)
| # | Test Name | Description |
|---|-----------|-------------|
| 46 | `test_research_classify_theorem` | "Theorem 1. Let..." → Theorem |
| 47 | `test_research_classify_proof` | "Proof. We show..." → Proof |
| 48 | `test_research_classify_lemma` | "Lemma 2. Supporting..." → Lemma |
| 49 | `test_research_classify_algorithm` | "Algorithm: Input..." → Algorithm |
| 50 | `test_research_classify_observation` | "We observe that..." → Observation |
| 51 | `test_research_classify_hypothesis` | "We hypothesize..." → Hypothesis |
| 52 | `test_research_extract_numbers` | Extracts "Theorem 5" → "5" |
| 53 | `test_research_extract_citations` | Extracts [Smith et al., 2020] |
| 54 | `test_research_extract_variables` | Extracts single letters |
| 55 | `test_research_extract_equations` | Extracts $$...$$ |
| 56 | `test_research_empty_section` | Empty text → empty list |
| 57 | `test_research_supported_types` | 6 types returned |
| 58 | `test_research_metadata_shape` | Metadata has equations, citations, variables, numbers |
| 59 | `test_research_proposition` | "Proposition 3." → Theorem |
| 60 | `test_research_conjecture` | "Conjecture 1." → Hypothesis |

**Pass Criteria:** All 60+ tests pass. Factory routing correct. All extractors produce valid Item objects.

---

## Phase 2 Tests — Dual Vector Stores & Section Nodes

### File: `tests/test_phase6_ingestion.py`

| # | Test Name | Description |
|---|-----------|-------------|
| 1 | `test_dual_store_initialization` | DualVectorStore creates both collections |
| 2 | `test_add_items_to_store` | Items added to items collection |
| 3 | `test_add_sections_to_store` | Sections added to sections collection |
| 4 | `test_search_items` | Item search returns ranked results |
| 5 | `test_search_sections` | Section search returns ranked results |
| 6 | `test_unified_search_interface` | `search(store="items")` routes correctly |
| 7 | `test_get_by_id_item` | Retrieve item by ID |
| 8 | `test_get_by_id_section` | Retrieve section by ID |
| 9 | `test_enhanced_graph_document_node` | Document node created in graph |
| 10 | `test_enhanced_graph_section_nodes` | Section nodes created |
| 11 | `test_enhanced_graph_item_nodes` | Item nodes created |
| 12 | `test_enhanced_graph_contains_edges` | CONTAINS edges: Doc→Section |
| 13 | `test_enhanced_graph_next_edges` | NEXT edges: Section→Section |
| 14 | `test_enhanced_graph_typed_edges` | HAS_RULE, HAS_DEFINITION edges |
| 15 | `test_full_ingestion_pipeline` | End-to-end Phase 6 ingestion |

**Pass Criteria:** All 15 tests pass. Dual stores hold items and sections. Graph has hierarchical structure.

---

## Phase 3 Tests — REFERENCES Edges

### File: `tests/test_reference_edges.py`

| # | Test Name | Description |
|---|-----------|-------------|
| 1 | `test_extract_defined_term_quoted` | `"Distribution Account" means...` → "Distribution Account" |
| 2 | `test_extract_defined_term_capitalized` | `Distribution Account means...` → "Distribution Account" |
| 3 | `test_extract_defined_term_no_match` | No definition pattern → None |
| 4 | `test_references_edge_created` | Item mentions defined term → edge created |
| 5 | `test_references_edge_not_created` | No mention → no edge |
| 6 | `test_references_multiple_defs` | Item references 2+ defs → 2+ edges |
| 7 | `test_definitions_only_no_edges` | All definitions, no rules → 0 edges |
| 8 | `test_graph_traversal_references` | Query via REFERENCES edge |
| 9 | `test_reference_edge_weight` | Edge weight = 0.4 |
| 10 | `test_case_insensitive_matching` | Lowercase text matches capitalized term |

**Pass Criteria:** All 10 tests pass. REFERENCES edges correctly link items to definitions.

---

## Phase 4 Tests — PageRank Boost

### File: `tests/test_pagerank.py`

| # | Test Name | Description |
|---|-----------|-------------|
| 1 | `test_pagerank_single_seed` | Single seed node → scores computed |
| 2 | `test_pagerank_multiple_seeds` | Multiple seeds → all scored |
| 3 | `test_pagerank_scaled_range` | Scores in [0, 0.3] |
| 4 | `test_pagerank_empty_graph` | No nodes → empty dict returned |
| 5 | `test_pagerank_subgraph_limit` | Subgraph limited to max_nodes |
| 6 | `test_pagerank_connected_higher` | Well-connected node scores higher |
| 7 | `test_hybrid_reranker_basic` | Content + PageRank combined |
| 8 | `test_hybrid_reranker_weights` | 0.7 content + 0.3 pagerank verified |
| 9 | `test_hybrid_reranker_sorting` | Results sorted by confidence desc |
| 10 | `test_hybrid_reranker_dedup` | Duplicate IDs merged |
| 11 | `test_hybrid_reranker_empty` | Empty results → empty list |
| 12 | `test_pagerank_personalization` | Seed nodes get non-zero personalization |

**Pass Criteria:** All 12 tests pass. PageRank scores scaled correctly. Hybrid reranker combines signals.

---

## Phase 5 Tests — Iterative Multi-Hop Retrieval

### File: `tests/test_iterative_retrieval.py`

| # | Test Name | Description |
|---|-----------|-------------|
| 1 | `test_orchestrator_init` | All components initialized |
| 2 | `test_single_iteration` | 1 iteration runs and returns results |
| 3 | `test_multiple_iterations` | 2-3 iterations progressively improve |
| 4 | `test_alternating_stores` | iter0→items, iter1→sections, iter2→items |
| 5 | `test_max_iterations_exit` | Stops at max_iterations |
| 6 | `test_high_confidence_exit` | confidence > 0.90 → exits early |
| 7 | `test_diminishing_returns_exit` | improvement < 0.05 → exits early |
| 8 | `test_confidence_increases` | Confidence improves per iteration |
| 9 | `test_visited_nodes_dedup` | No duplicate node visits |
| 10 | `test_bfs_expansion_depth2` | 2-hop neighbors discovered |
| 11 | `test_expansion_avoids_visited` | Skips already-visited nodes |
| 12 | `test_expansion_edge_types` | Follows CONTAINS, NEXT, REFERENCES |
| 13 | `test_expansion_max_neighbors` | Limits to 20 neighbors per node |
| 14 | `test_empty_expansion` | Node with no neighbors returns [] |
| 15 | `test_reranking_combines` | Vector + expanded results merged |
| 16 | `test_reranking_dedup` | Duplicate IDs removed |
| 17 | `test_reranking_sorts` | Descending confidence order |
| 18 | `test_top_k_respected` | Final results limited to top_k |
| 19 | `test_pagerank_boost_applied` | PageRank boosts reranked scores |
| 20 | `test_phase6_flag_routing` | phase6_enabled=False → legacy path |

**Pass Criteria:** All 20 tests pass. Iterative loop functions end-to-end. Exit criteria enforced.

---

## Phase 6 Tests — Section-Specific Queries

### File: `tests/test_section_queries.py`

| # | Test Name | Description |
|---|-----------|-------------|
| 1 | `test_query_section_exists` | Section 5.02 returns items |
| 2 | `test_query_section_not_found` | Non-existent section → error |
| 3 | `test_query_section_item_order` | Items in item_index order |
| 4 | `test_query_section_metadata` | Section heading, item_count present |
| 5 | `test_get_next_section` | Section 5.02 → Section 5.03 |
| 6 | `test_get_next_section_last` | Last section → None |
| 7 | `test_get_item_dependencies` | Item references 2 definitions |
| 8 | `test_get_item_no_dependencies` | No references → empty list |
| 9 | `test_phase6_required` | phase6_enabled=False → NotImplementedError |
| 10 | `test_cli_section_command` | CLI `section 5.02 --doc-id ...` works |

**Pass Criteria:** All 10 tests pass. Section navigation and dependency tracing functional.

---

## Cross-Domain Validation

### File: `tests/test_cross_domain.py`

Tests using the 3 knowledge sources:

| # | Test Name | Domain | Corpus |
|---|-----------|--------|--------|
| 1 | `test_legal_governing_doc` | Legal | kts_test_corpus/governing_docs |
| 2 | `test_legal_psa_structure` | Legal | kts_synthetic_corpus_v2/governing_docs |
| 3 | `test_legal_item_extraction` | Legal | kts_test_corpus/governing_docs |
| 4 | `test_technical_sop` | Technical | kts_test_corpus/sops |
| 5 | `test_technical_user_guide` | Technical | kts_synthetic_corpus_v2/user_guides |
| 6 | `test_technical_troubleshoot` | Technical | kts_test_corpus/troubleshooting |
| 7 | `test_reference_catalog` | Generic | kts_synthetic_corpus_v2/reference |
| 8 | `test_training_material` | Generic | kts_test_corpus/training |
| 9 | `test_mixed_corpus_ingestion` | All | All corpora combined |

**Pass Criteria:** Each domain produces correct item types. No cross-domain contamination.

---

## Performance Benchmarks

### File: `tests/test_performance_benchmarks.py`

| # | Test Name | Target |
|---|-----------|--------|
| 1 | `test_query_latency_p50` | Median latency < 250ms |
| 2 | `test_query_latency_p95` | P95 latency < 500ms |
| 3 | `test_query_latency_p99` | P99 latency < 750ms |
| 4 | `test_ingestion_throughput` | Single doc ingestion < 30s |
| 5 | `test_pagerank_computation` | PageRank < 100ms |

**Pass Criteria:** All 5 benchmarks met on standard hardware.

---

## Golden Query Validation

### File: `tests/test_golden_queries_phase6.py`

Uses existing golden queries from `tests/golden_queries_v2.json`:

| # | Query | Expected Confidence |
|---|-------|-------------------|
| 1 | "What is Distribution Account?" | > 0.85 |
| 2 | "What must Trustee establish?" | > 0.85 |
| 3 | "What are Servicer obligations?" | > 0.80 |
| 4 | "What are sub-account requirements?" | > 0.80 |
| 5 | "What is Closing Date?" | > 0.90 |
| 6 | "What's in Section 5.02?" | Returns items |
| 7 | "Compare Trustee vs Servicer" | Retrieves both |
| 8 | "What definitions does this obligation reference?" | REFERENCES edges |
| 9 | "What happens after Closing Date?" | Multi-hop results |
| 10 | "List all obligations in Article V" | Section-scoped query |

**Pass Criteria:** All golden queries meet minimum confidence thresholds. No regression from Phase 5 scores.

---

## Regression Tests

### File: `tests/test_regression_phase6.py`

| # | Test Name | Description |
|---|-----------|-------------|
| 1 | `test_phase5_query_works` | Legacy query with phase6_enabled=False |
| 2 | `test_phase5_confidence_maintained` | Phase 5 confidence scores unchanged |
| 3 | `test_phase5_ingestion_compatible` | Old ingest format still works |
| 4 | `test_phase5_cli_crawl` | CLI `crawl` still works |
| 5 | `test_phase5_cli_ingest` | CLI `ingest` still works |
| 6 | `test_phase5_cli_search` | CLI `search` still works |
| 7 | `test_phase5_cli_status` | CLI `status` still works |
| 8 | `test_phase5_graph_builder` | GraphBuilder still creates nodes |
| 9 | `test_phase5_vector_store` | VectorStore add/search works |
| 10 | `test_phase5_regime_classifier` | RegimeClassifier unchanged |
| 11 | `test_phase5_legal_chunker` | LegalChunker still works |
| 12 | `test_phase5_term_extraction` | DefinedTermExtractor unchanged |
| 13 | `test_phase5_evidence_matcher` | EvidenceMatcher unchanged |
| 14 | `test_phase5_provenance` | Provenance validation unchanged |
| 15 | `test_phase5_freshness` | FreshnessAgent unchanged |
| 16 | `test_phase5_training_path` | TrainingPathAgent unchanged |
| 17 | `test_phase5_change_impact` | ChangeImpactAgent unchanged |
| 18 | `test_phase5_vision_agent` | VisionAgent unchanged |
| 19 | `test_config_backward_compat` | KTSConfig field defaults unchanged |
| 20 | `test_feature_flag_default_off` | phase6_enabled defaults to False |

**Pass Criteria:** All 20 regression tests pass. Zero changes to Phase 5 behavior when flag is off.

---

## AI Explainability Logging Validation

### File: `tests/test_explainability_logging.py`

| # | Test Name | Description |
|---|-----------|-------------|
| 1 | `test_ingestion_logs_regime` | Logs regime classification result and score |
| 2 | `test_ingestion_logs_section_parsing` | Logs each section parsed with number/heading |
| 3 | `test_ingestion_logs_item_extraction` | Logs item count per section with types |
| 4 | `test_ingestion_logs_vector_upsert` | Logs chunk/item count upserted |
| 5 | `test_retrieval_logs_query_augment` | Logs query expansion/augmentation |
| 6 | `test_retrieval_logs_top_k_chunks` | Logs top-K chunks retrieved with scores |
| 7 | `test_retrieval_logs_iteration_loop` | Logs each iteration: store used, expansion, confidence |
| 8 | `test_retrieval_logs_final_send` | Logs final context sent to LLM |

**Pass Criteria:** All 8 tests verify appropriate log messages appear in the logging output.

---

## VSIX Integration Tests

### File: `tests/test_vsix_phase6.py`

| # | Test Name | Description |
|---|-----------|-------------|
| 1 | `test_backend_exe_discovery` | Extension finds kts-backend.exe |
| 2 | `test_backend_cli_json_output` | CLI returns valid JSON |
| 3 | `test_search_command_phase6` | `/search` routes through Phase 6 pipeline |
| 4 | `test_deep_command_phase6` | `/deep` with Phase 6 enabled |
| 5 | `test_output_channel_logging` | KTS output channel shows logs |
| 6 | `test_crawl_ingest_command` | Crawl+Ingest command completes |
| 7 | `test_status_command` | Status shows Phase 6 info |
| 8 | `test_error_handling` | Backend errors shown in VS Code |
| 9 | `test_bundled_model_path` | ONNX model found in bundled exe |
| 10 | `test_pyinstaller_hidden_imports` | Phase 6 modules included in bundle |

**Pass Criteria:** All 10 tests pass. VSIX correctly dispatches to Phase 6 pipeline.

---

## Knowledge Source Test Corpora

### Corpus 1: `Knowledge Base test/kts_synthetic_corpus_v2`
- 9 categories of synthetic documents
- Used for: cross-domain validation, ingestion pipeline testing

### Corpus 2: `Knowledge Base test/kts_test_corpus`
- 5 categories of test documents  
- Used for: golden query validation, regression testing

### Corpus 3: Workspace source documents (`source_1/`, `source_2/`)
- Actual project source documents
- Used for: real-world integration testing, VSIX end-to-end testing

---

## Test Execution Guide

### Quick Smoke Test
```bash
pytest tests/test_phase6_regex.py -v
```

### Phase-by-Phase Validation
```bash
# Phase 0
pytest tests/test_phase6_regex.py -v

# Phase 1
pytest tests/test_item_extractors.py -v

# Phase 2
pytest tests/test_phase6_ingestion.py -v

# Phase 3
pytest tests/test_reference_edges.py -v

# Phase 4
pytest tests/test_pagerank.py -v

# Phase 5
pytest tests/test_iterative_retrieval.py -v

# Phase 6
pytest tests/test_section_queries.py -v
```

### Full Suite
```bash
pytest tests/ -v --tb=short -q
```

### With Coverage
```bash
pytest tests/ --cov=backend --cov-report=html -v
```

### Specific Knowledge Source Testing
```bash
# Test with synthetic corpus
pytest tests/test_cross_domain.py -v -k "synthetic"

# Test with test corpus
pytest tests/test_cross_domain.py -v -k "test_corpus"
```

---

## Related Documents

- [Executive Summary](01_EXECUTIVE_SUMMARY.md)
- [System Design](02_SYSTEM_DESIGN.md)
- [Architecture Upgrade](03_ARCHITECTURE_UPGRADE.md)
- [Technical Design](04_TECHNICAL_DESIGN.md)
- [Implementation Plan](05_IMPLEMENTATION_PLAN.md)

---

*This testing plan ensures comprehensive validation of all Phase 6 components before production deployment.*
