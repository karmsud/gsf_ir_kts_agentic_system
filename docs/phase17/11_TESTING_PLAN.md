# Phase 17: Comprehensive Testing Plan
## Validation Strategy for Document-Level Isolation & Multi-Deal Analytics

**Document Version:** 1.0  
**Date:** February 22, 2026  
**Status:** Proposal — Pending Approval  
**Scope:** End-to-end testing strategy covering all Phase 17 components

---

## Table of Contents

1. [Overview](#overview)
2. [Test Categories](#test-categories)
3. [Step 1 Tests — Doc-Name-Prefix Read-Side Filtering](#step-1-tests)
4. [Step 2 Tests — Dual Graph Metadata](#step-2-tests)
5. [Step 3 Tests — Graph Partitioning](#step-3-tests)
6. [Step 4 Tests — Deal Catalog Schema](#step-4-tests)
7. [Step 5 Tests — Scope Resolution Pipeline](#step-5-tests)
8. [Step 6 Tests — Retriever Routing](#step-6-tests)
9. [Step 7 Tests — Multi-Deal Parallel Execution](#step-7-tests)
10. [Step 8 Tests — Compare / Diff / Aggregate Modes](#step-8-tests)
11. [Step 9 Tests — CLI Integration](#step-9-tests)
12. [Step 10 Tests — Extension UX](#step-10-tests)
13. [Step 11 Tests — Result Attribution](#step-11-tests)
14. [Cross-Step Integration Tests](#cross-step-integration-tests)
15. [Performance Benchmarks](#performance-benchmarks)
16. [Golden Query Validation](#golden-query-validation)
17. [Regression Tests](#regression-tests)
18. [Test Corpora](#test-corpora)
19. [Test Execution Guide](#test-execution-guide)

---

## Overview

### Testing Philosophy
- **Every step is independently testable** — each has its own test file
- **Feature flags protect production** — `phase17_*` flags toggle individual features
- **Golden query benchmarks must be maintained or improved** — no regression allowed
- **Test corpora use the `kb_test/` structure** — `Fin_deal1/` and `Fin_deal2/` with PSA + ProSupp each
- **Attribution verified end-to-end** — every result tagged with deal + doc source

### Test Summary

| Category | Test Count | Test File(s) |
|----------|-----------|--------------|
| Step 1 — Doc Filter Read-Side | 12 | `test_phase17_doc_filter.py` |
| Step 2 — Dual Graph Metadata | 10 | `test_phase17_graph_metadata.py` |
| Step 3 — Graph Partitioning | 15 | `test_phase17_graph_partition.py` |
| Step 4 — Deal Catalog | 18 | `test_phase17_deal_catalog.py` |
| Step 5 — Scope Resolution | 25 | `test_phase17_scope_resolver.py` |
| Step 6 — Retriever Routing | 14 | `test_phase17_retriever_routing.py` |
| Step 7 — Multi-Deal Parallel | 10 | `test_phase17_multi_deal.py` |
| Step 8 — Compare/Diff/Aggregate | 20 | `test_phase17_analytical_modes.py` |
| Step 9 — CLI Integration | 12 | `test_phase17_cli.py` |
| Step 10 — Extension UX | 8 | (manual + extension test runner) |
| Step 11 — Result Attribution | 8 | `test_phase17_attribution.py` |
| Cross-Step Integration | 15 | `test_phase17_integration.py` |
| Performance Benchmarks | 8 | `test_phase17_performance.py` |
| Golden Queries | 12 | `test_phase17_golden.py` |
| Regression | 10 | `test_phase17_regression.py` |
| **TOTAL** | **~197** | **14 test files** |

---

## Step 1 Tests — Doc-Name-Prefix Read-Side Filtering

### File: `tests/test_phase17_doc_filter.py`

| # | Test Name | Description | Expected Result |
|---|-----------|-------------|-----------------|
| 1 | `test_search_items_with_doc_filter_psa` | Search items with `filters={"doc_name_prefix": "PSA"}` | All returned items have `doc_name_prefix == "PSA"` |
| 2 | `test_search_items_with_doc_filter_prosupp` | Search items with `filters={"doc_name_prefix": "PROSUPP"}` | All returned items have `doc_name_prefix == "PROSUPP"` |
| 3 | `test_search_sections_with_doc_filter` | Search sections with `doc_name_prefix` filter | Only sections from filtered doc returned |
| 4 | `test_search_without_doc_filter` | Search without `doc_name_prefix` | Results from ALL docs in the deal |
| 5 | `test_combined_filters_doc_and_type` | Search with `{"doc_name_prefix": "PSA", "item_type": "Definition"}` | Only PSA definitions returned |
| 6 | `test_doc_filter_case_insensitive_input` | Pass `doc_filter="psa"` (lowercase) via CLI | Uppercased to `"PSA"` before reaching ChromaDB |
| 7 | `test_doc_filter_unknown_prefix` | Filter with `doc_name_prefix="NONEXISTENT"` | Empty result set, no crash |
| 8 | `test_retrieval_service_forwards_doc_filter` | `RetrievalService.execute({"doc_name_prefix": "PSA"})` | Filter reaches `human_like_retriever.retrieve()` |
| 9 | `test_cli_doc_filter_option` | `kts search "..." --doc-filter PSA` | CLI parses and forwards correctly |
| 10 | `test_human_like_retriever_doc_filter_in_global_fallback` | Trigger global fallback with doc filter active | Fallback search still applies doc filter |
| 11 | `test_human_like_retriever_doc_filter_in_section_scoped` | Section-scoped search with doc filter | Both section_number AND doc_name_prefix in `where` clause |
| 12 | `test_doc_filter_performance` | Compare latency: filtered vs unfiltered | Filtered ≤ unfiltered (metadata filter is free in ChromaDB) |

**Pass Criteria:** All 12 tests pass; no existing retrieval tests broken.

---

## Step 2 Tests — Dual Graph Metadata

### File: `tests/test_phase17_graph_metadata.py`

| # | Test Name | Description | Expected Result |
|---|-----------|-------------|-----------------|
| 1 | `test_enhanced_builder_stamps_doc_prefix_on_doc_node` | Build graph with `doc_name_prefix="PSA"` | Document node has `doc_name_prefix: "PSA"` |
| 2 | `test_enhanced_builder_stamps_doc_prefix_on_section_nodes` | Check all section nodes | Every section node has `doc_name_prefix: "PSA"` |
| 3 | `test_enhanced_builder_stamps_doc_prefix_on_item_nodes` | Check all item nodes | Every item node has `doc_name_prefix: "PSA"` |
| 4 | `test_enhanced_builder_stamps_doc_prefix_on_edges` | Check all edges | Every edge has `doc_name_prefix: "PSA"` |
| 5 | `test_basic_builder_stamps_doc_prefix` | `GraphBuilder.upsert_document()` with `doc_name_prefix` in metadata | Document node has attribute |
| 6 | `test_ingestion_passes_doc_prefix_to_graph` | End-to-end: ingest a PSA file | Graph nodes/edges have `doc_name_prefix: "PSA"` |
| 7 | `test_multi_doc_graph_has_both_prefixes` | Ingest PSA + ProSupp into one deal | Graph has nodes with both `"PSA"` and `"PROSUPP"` |
| 8 | `test_graph_without_prefix_backward_compatible` | Load old graph without `doc_name_prefix` | No crash; missing attribute = `""` |
| 9 | `test_definition_graph_builder_uses_prefix` | `build_definition_graph()` with prefix | TERM nodes have `doc_name_prefix` |
| 10 | `test_concept_vocabulary_uses_prefix` | ConceptVocabularyBuilder with prefix | Concept keyword nodes have `doc_name_prefix` |

**Pass Criteria:** All 10 tests pass; graph structure unchanged for existing consumers.

---

## Step 3 Tests — Graph Partitioning

### File: `tests/test_phase17_graph_partition.py`

| # | Test Name | Description | Expected Result |
|---|-----------|-------------|-----------------|
| 1 | `test_partition_creates_doc_graphs_dir` | Partition a 2-doc graph | `doc_graphs/` directory created |
| 2 | `test_partition_creates_per_doc_files` | Partition a 2-doc graph | `doc_graphs/PSA.json` and `doc_graphs/PROSUPP.json` exist |
| 3 | `test_psa_graph_contains_only_psa_nodes` | Load `PSA.json` | All nodes have `doc_name_prefix == "PSA"` |
| 4 | `test_prosupp_graph_contains_only_prosupp_nodes` | Load `PROSUPP.json` | All nodes have `doc_name_prefix == "PROSUPP"` |
| 5 | `test_doc_graph_edges_are_intra_doc_only` | Check edges in `PSA.json` | No edge references a PROSUPP node |
| 6 | `test_doc_graph_node_count_sums_to_deal_graph` | Count nodes across doc graphs | Sum ≈ deal graph node count (cross-doc nodes may differ) |
| 7 | `test_cross_doc_term_edges_added` | Check deal graph for `CROSS_DOC_TERM` edges | At least 1 edge for shared term (e.g., "Distribution Date") |
| 8 | `test_cross_doc_entity_edges_added` | Check deal graph for `CROSS_DOC_ENTITY` edges | At least 1 edge for shared entity |
| 9 | `test_cross_doc_edges_have_source_target_doc` | Inspect cross-doc edge attributes | Has `source_doc`, `target_doc`, `term`/`entity` |
| 10 | `test_partition_idempotent` | Run partition twice | Same output both times |
| 11 | `test_partition_single_doc_deal` | Deal with only 1 doc | 1 doc graph, no cross-doc edges |
| 12 | `test_partition_handles_nodes_without_prefix` | Graph with some nodes missing `doc_name_prefix` | Unprefixed nodes excluded from doc graphs, no crash |
| 13 | `test_add_cross_doc_edges_returns_count` | Call `add_cross_document_edges()` | Returns int ≥ 0 |
| 14 | `test_doc_graph_json_format` | Load doc graph JSON | Valid structure: `{"nodes": {...}, "edges": [...]}` |
| 15 | `test_partition_with_empty_graph` | Partition empty graph | No doc graphs created, no crash |

**Pass Criteria:** All 15 tests pass; deal graph unchanged for non-Phase-17 consumers.

---

## Step 4 Tests — Deal Catalog Schema

### File: `tests/test_phase17_deal_catalog.py`

| # | Test Name | Description | Expected Result |
|---|-----------|-------------|-----------------|
| 1 | `test_schema_upgrade_adds_new_columns` | Open catalog DB, check schema | `deal_name`, `vintage`, `series`, `issuer`, `doc_types`, `chunk_count`, `status` columns exist |
| 2 | `test_upsert_deal_with_full_metadata` | Insert deal with all fields | All fields persisted and retrievable |
| 3 | `test_upsert_deal_update_existing` | Upsert same scope_slug twice | Second call updates, not duplicates |
| 4 | `test_search_deals_by_pattern_wildcard` | `search_deals(pattern="bear_stearns_2006*")` | Returns matching deals |
| 5 | `test_search_deals_by_pattern_no_match` | `search_deals(pattern="nonexistent*")` | Returns empty list |
| 6 | `test_search_deals_by_deal_name` | `search_deals(deal_name="Bear Stearns")` | Returns all Bear Stearns deals |
| 7 | `test_search_deals_by_vintage` | `search_deals(vintage=2006)` | Returns all 2006 vintage deals |
| 8 | `test_search_deals_combined_filters` | `search_deals(deal_name="Bear Stearns", vintage=2006)` | AND logic: both conditions met |
| 9 | `test_get_doc_types` | `get_doc_types("fin_deal1")` | Returns `["PSA", "PROSUPP"]` |
| 10 | `test_get_doc_types_nonexistent` | `get_doc_types("nonexistent")` | Returns empty list |
| 11 | `test_list_all_deals` | `list_all_deals()` with 3 deals | Returns all 3 entries |
| 12 | `test_list_all_deals_empty_db` | `list_all_deals()` on fresh DB | Returns empty list |
| 13 | `test_parse_deal_folder_name_full` | `_parse_deal_folder_name("Bear_Stearns_2006_HE1")` | `{deal_name: "Bear Stearns", vintage: 2006, series: "HE1"}` |
| 14 | `test_parse_deal_folder_name_simple` | `_parse_deal_folder_name("Fin_deal1")` | `{deal_name: "Fin deal1", vintage: 0, series: ""}` |
| 15 | `test_parse_deal_folder_name_year_only` | `_parse_deal_folder_name("GSAA_2006")` | `{deal_name: "GSAA", vintage: 2006, series: ""}` |
| 16 | `test_catalog_backward_compatible` | Open old catalog (2-column) | Migration adds columns with defaults, old data intact |
| 17 | `test_fts5_fallback_to_like` | Simulate FTS5 unavailable | `search_deals(pattern="bear*")` still works via LIKE fallback |
| 18 | `test_ingestion_populates_catalog` | Run full ingestion → check catalog | Entry present with correct doc_types and chunk_count |

**Pass Criteria:** All 18 tests pass; existing catalog entries preserved after migration.

---

## Step 5 Tests — Scope Resolution Pipeline

### File: `tests/test_phase17_scope_resolver.py`

| # | Test Name | Description | Expected Result |
|---|-----------|-------------|-----------------|
| 1 | `test_parse_single_scope` | `/fin_deal1 What is ...` | `mode=search, scopes=[ScopeExpr("fin_deal1")]` |
| 2 | `test_parse_scope_with_doc_filter` | `/fin_deal1/PSA What is ...` | `scopes=[ScopeExpr("fin_deal1", "PSA")]` |
| 3 | `test_parse_global_doc_filter` | `//PSA What is ...` | `scopes=[ScopeExpr("*", "PSA")]` |
| 4 | `test_parse_wildcard_scope` | `/bear_stearns_2006* What is ...` | `scopes=[ScopeExpr("bear_stearns_2006", None, is_wildcard=True)]` |
| 5 | `test_parse_wildcard_with_doc_filter` | `/bear_stearns_2006*/PSA What is ...` | `scopes=[ScopeExpr("bear_stearns_2006", "PSA", is_wildcard=True)]` |
| 6 | `test_parse_compare_mode` | `/compare /fin_deal1 /fin_deal2 What is ...` | `mode=compare, scopes=[2 entries]` |
| 7 | `test_parse_diff_mode` | `/diff /fin_deal1/PSA /fin_deal2/PSA What is ...` | `mode=diff, scopes=[2 entries with PSA filter]` |
| 8 | `test_parse_aggregate_mode` | `/aggregate /bear_stearns_2006* How is ...` | `mode=aggregate, scopes=[wildcard]` |
| 9 | `test_parse_list_mode` | `/list /fin_deal1` | `mode=list, scopes=[ScopeExpr("fin_deal1")]` |
| 10 | `test_parse_define_mode` | `/fin_deal1 /define Distribution Date` | `mode=define, scopes=[fin_deal1]` |
| 11 | `test_parse_audit_mode` | `/audit /fin_deal1/PSA` | `mode=audit, scopes=[fin_deal1/PSA]` |
| 12 | `test_parse_compare_wildcard` | `/compare /bear_stearns_2006* What is ...` | `mode=compare, scopes=[wildcard]` |
| 13 | `test_parse_compare_wildcard_with_doc` | `/compare /bear_stearns_2006*/PSA What is ...` | `mode=compare, scopes=[wildcard, docFilter=PSA]` |
| 14 | `test_parse_no_scope_default` | `What is Distribution Date?` | `mode=search, scopes=[], query="What is ..."` |
| 15 | `test_parse_multiple_explicit_scopes` | `/fin_deal1 /fin_deal2 /fin_deal3 What is ...` | `scopes=[3 entries]` |
| 16 | `test_resolve_wildcard_via_catalog` | Resolve `bear_stearns_2006*` with 3 matches | Returns 3 concrete ScopeExprs |
| 17 | `test_resolve_wildcard_no_matches` | Resolve `nonexistent*` | Returns empty list |
| 18 | `test_resolve_global_doc_filter` | Resolve `//PSA` with 5 deals | Returns 5 ScopeExprs, each with `doc_filter=PSA` |
| 19 | `test_parse_strips_at_kts_prefix` | `@kts /fin_deal1 What is ...` | Same as without `@kts` prefix |
| 20 | `test_parse_query_extraction` | `/fin_deal1/PSA What is the Distribution Date?` | `query="What is the Distribution Date?"` |
| 21 | `test_parse_mode_case_insensitive` | `/Compare /fin_deal1 ...` | `mode=compare` (lowercased) |
| 22 | `test_parse_error_no_query_after_scope` | `/fin_deal1` (no query) | Returns parsed with empty query string |
| 23 | `test_parse_diff_same_deal_two_docs` | `/diff /fin_deal1/PSA /fin_deal1/PROSUPP What is ...` | `mode=diff, 2 scopes same deal different docs` |
| 24 | `test_parse_complex_command` | `/compare /bear_stearns_2006*/PSA /gs_2007*/PSA What is ...` | 2 wildcard scopes, both with PSA filter |
| 25 | `test_round_trip_parse_to_cli_args` | Parse → build CLI args → verify | CLI args match expected format |

**Pass Criteria:** All 25 tests pass; parser handles all 14 use cases correctly.

---

## Step 6 Tests — Retriever Routing

### File: `tests/test_phase17_retriever_routing.py`

| # | Test Name | Description | Expected Result |
|---|-----------|-------------|-----------------|
| 1 | `test_select_graph_path_with_doc_filter_existing` | `doc_name_prefix="PSA"`, `doc_graphs/PSA.json` exists | Returns doc graph path |
| 2 | `test_select_graph_path_with_doc_filter_missing` | `doc_name_prefix="TRUST"`, no `doc_graphs/TRUST.json` | Returns deal graph path (fallback) |
| 3 | `test_select_graph_path_without_doc_filter` | `doc_name_prefix=None` | Returns deal graph path |
| 4 | `test_human_like_retriever_uses_doc_graph` | Search with doc_filter, mock graph load | `GraphStore` path = doc graph |
| 5 | `test_human_like_retriever_uses_deal_graph` | Search without doc_filter | `GraphStore` path = deal graph |
| 6 | `test_doc_filter_propagated_to_search_items` | Inspect actual `where` clause in ChromaDB call | Contains `doc_name_prefix` |
| 7 | `test_doc_filter_propagated_to_search_sections` | Same for section search | Contains `doc_name_prefix` |
| 8 | `test_section_scoped_search_with_doc_filter` | Section + doc filter combined | `where` has both `section_number` AND `doc_name_prefix` |
| 9 | `test_retrieval_quality_psa_only` | Query "Distribution Date" with PSA filter | Top result is from PSA, not ProSupp |
| 10 | `test_retrieval_quality_deal_level` | Query "Distribution Date" without filter | Results from both PSA and ProSupp |
| 11 | `test_graph_traversal_confined_to_doc_graph` | Traverse doc graph | No cross-doc edges followed |
| 12 | `test_graph_traversal_follows_cross_doc_edges` | Traverse deal graph | Cross-doc edges available |
| 13 | `test_doc_filter_with_iterative_orchestrator` | Non-human-like retriever with doc filter | Filter still applied |
| 14 | `test_doc_filter_with_guide_retriever` | Guide strategy with doc filter | Filter still applied |

**Pass Criteria:** All 14 tests pass; doc filter consistently applied across all retriever strategies.

---

## Step 7 Tests — Multi-Deal Parallel Execution

### File: `tests/test_phase17_multi_deal.py`

| # | Test Name | Description | Expected Result |
|---|-----------|-------------|-----------------|
| 1 | `test_multi_scope_search_two_deals` | Search across `fin_deal1` + `fin_deal2` | Results from both deals returned |
| 2 | `test_multi_scope_search_result_attribution` | Check `deal_scope` field on each result | Every result tagged with source deal |
| 3 | `test_multi_scope_search_sorted_by_score` | Check result ordering | Sorted by score descending |
| 4 | `test_multi_scope_search_with_doc_filter` | Multi-deal + `doc_filter=PSA` | Only PSA results from each deal |
| 5 | `test_multi_scope_one_failure` | 1 of 3 scopes throws exception | Other 2 return results; error logged |
| 6 | `test_multi_scope_search_parallel_performance` | 5-deal query | Completes in ≤ 1.5× single-deal time (parallelism works) |
| 7 | `test_wildcard_resolution_to_multi_scope` | Wildcard `bear_stearns_2006*` → 3 deals | All 3 searched |
| 8 | `test_multi_scope_empty_results` | All scopes return empty | Empty merged result, no crash |
| 9 | `test_multi_scope_score_normalization` | Scores from different ChromaDBs | Results from different deals have comparable score ranges |
| 10 | `test_max_results_per_scope_respected` | `max_results_per_scope=3`, 2 deals | ≤ 6 total results |

**Pass Criteria:** All 10 tests pass; parallel execution provides speedup over sequential.

---

## Step 8 Tests — Compare / Diff / Aggregate Modes

### File: `tests/test_phase17_analytical_modes.py`

| # | Test Name | Description | Expected Result |
|---|-----------|-------------|-----------------|
| 1 | `test_compare_mode_returns_per_scope_results` | `/compare /fin_deal1 /fin_deal2 ...` | Result has `results_by_scope` dict |
| 2 | `test_compare_mode_contradiction_detection` | Two deals with different Distribution Date | Contradiction flagged |
| 3 | `test_compare_mode_with_doc_filter` | `/compare /fin_deal1/PSA /fin_deal2/PSA ...` | Only PSA results from each deal |
| 4 | `test_compare_mode_wildcard` | `/compare /bear_stearns_2006* ...` | All matching deals compared |
| 5 | `test_diff_mode_basic` | `/diff /fin_deal1/PSA /fin_deal2/PSA ...` | `diffs` list with field-level differences |
| 6 | `test_diff_mode_identifies_value_difference` | Different date values | `diff_type=value_difference` |
| 7 | `test_diff_mode_identifies_common_elements` | Same definition text | Appears in `common` list |
| 8 | `test_diff_mode_same_deal_two_docs` | `/diff /fin_deal1/PSA /fin_deal1/PROSUPP ...` | Cross-doc diff within same deal |
| 9 | `test_diff_mode_significance_scoring` | Date difference vs capitalization diff | Date diff has higher significance |
| 10 | `test_aggregate_mode_basic` | `/aggregate /bear_stearns_2006* ...` with 3 deals | `pattern` + `outliers` |
| 11 | `test_aggregate_mode_detects_majority_pattern` | 8/10 deals same definition | `pattern` reflects majority |
| 12 | `test_aggregate_mode_flags_outliers` | 2/10 deals different | `outliers` list has 2 entries |
| 13 | `test_aggregate_mode_confidence_score` | 10 identical definitions | `confidence ≈ 1.0` |
| 14 | `test_aggregate_mode_low_confidence` | 5/10 variant A, 5/10 variant B | `confidence < 0.7` |
| 15 | `test_aggregate_mode_deal_count` | 10 deals searched | `deal_count: 10` |
| 16 | `test_aggregate_mode_with_doc_filter` | `/aggregate /bear_stearns_2006*/PSA ...` | Only PSA results across all deals |
| 17 | `test_compare_mode_rendering_format` | Check output structure | Side-by-side format with attributions |
| 18 | `test_diff_mode_rendering_format` | Check output structure | Field-level diffs with significance |
| 19 | `test_aggregate_mode_rendering_format` | Check output structure | Pattern + outlier format |
| 20 | `test_all_modes_graceful_on_empty_results` | All modes with 0 results | Meaningful empty-state messages |

**Pass Criteria:** All 20 tests pass; comparison modes produce actionable analytical output.

---

## Step 9 Tests — CLI Integration

### File: `tests/test_phase17_cli.py`

| # | Test Name | Description | Expected Result |
|---|-----------|-------------|-----------------|
| 1 | `test_cli_doc_filter_option_parsed` | `--doc-filter PSA` | `doc_filter="PSA"` in context |
| 2 | `test_cli_mode_option_parsed` | `--mode compare` | `mode="compare"` in context |
| 3 | `test_cli_scopes_option_parsed` | `--scopes "fin_deal1,fin_deal2"` | Parsed as list of 2 slugs |
| 4 | `test_cli_scopes_wildcard` | `--scopes "bear_stearns_2006*"` | Wildcard passed to resolver |
| 5 | `test_cli_list_deals_all` | `kts list-deals` | JSON output of all deals |
| 6 | `test_cli_list_deals_filtered` | `kts list-deals --scope "bear*"` | Filtered output |
| 7 | `test_cli_search_backward_compatible` | `kts search "..." --scope-override fin_deal1` | Works as before (no new options) |
| 8 | `test_cli_mode_choice_validation` | `--mode invalid` | Click error: invalid choice |
| 9 | `test_cli_doc_filter_uppercased` | `--doc-filter psa` | Uppercased to `"PSA"` internally |
| 10 | `test_cli_combine_all_options` | `--doc-filter PSA --mode diff --scopes "fin_deal1,fin_deal2"` | All options forwarded correctly |
| 11 | `test_cli_compare_scopes_backward_compatible` | `--compare-scopes "fin_deal1,fin_deal2"` | Still works (Phase 15 option) |
| 12 | `test_cli_output_contains_attribution` | Multi-scope search | Output JSON has `deal_scope` per result |

**Pass Criteria:** All 12 tests pass; backward compatibility with Phase 12/15 CLI confirmed.

---

## Step 10 Tests — Extension UX

### Manual Testing (Extension Test Runner)

| # | Test Description | Steps | Expected Result |
|---|-----------------|-------|-----------------|
| 1 | **Scope autocomplete** | Type `@kts /` in chat | Dropdown shows discovered scopes |
| 2 | **Doc type autocomplete** | Type `@kts /fin_deal1/` in chat | Dropdown shows `PSA`, `PROSUPP` |
| 3 | **Mode autocomplete** | Type `@kts /` in chat | Dropdown includes `compare`, `diff`, `aggregate`, etc. |
| 4 | **Single-scope command** | `@kts /fin_deal1/PSA What is Distribution Date?` | Correct scoped result |
| 5 | **Compare command** | `@kts /compare /fin_deal1 /fin_deal2 What is Distribution Date?` | Side-by-side results |
| 6 | **Diff command** | `@kts /diff /fin_deal1/PSA /fin_deal2/PSA What is Distribution Date?` | Diff output |
| 7 | **List command** | `@kts /list /fin_deal1` | Shows deal metadata + doc types |
| 8 | **Error handling** | `@kts /nonexistent_deal What is ...` | Helpful error message |

**Pass Criteria:** All 8 manual tests pass in VSIX; graceful degradation when backend unavailable.

---

## Step 11 Tests — Result Attribution

### File: `tests/test_phase17_attribution.py`

| # | Test Name | Description | Expected Result |
|---|-----------|-------------|-----------------|
| 1 | `test_single_scope_result_has_deal_field` | Query single deal | Each result has `deal_scope` |
| 2 | `test_single_scope_result_has_doc_prefix` | Query with doc filter | Each result has `doc_name_prefix` |
| 3 | `test_multi_scope_results_have_attribution` | Multi-deal query | Every result has `deal_scope` identification |
| 4 | `test_compare_results_grouped_by_scope` | Compare mode output | Results organized by scope |
| 5 | `test_diff_results_reference_source_scope` | Diff mode output | Each diff value tagged to source deal |
| 6 | `test_aggregate_outliers_have_deal_id` | Aggregate mode output | Each outlier tagged with deal |
| 7 | `test_rendering_shows_deal_and_doc` | Extension rendering | "fin_deal1 / PSA" header visible |
| 8 | `test_rendering_compare_side_by_side` | Compare rendering | Parallel columns for each deal |

**Pass Criteria:** All 8 tests pass; attribution traceable from result to source deal + document.

---

## Cross-Step Integration Tests

### File: `tests/test_phase17_integration.py`

End-to-end tests using the `kb_test/` corpus with `Fin_deal1/` and `Fin_deal2/`.

| # | Test Name | Use Case | Command Simulated | Validation |
|---|-----------|----------|-------------------|------------|
| 1 | `test_uc1_single_doc_in_deal` | UC 1 | `/fin_deal1/PSA What is Distribution Date?` | Only PSA results, doc graph used |
| 2 | `test_uc2_all_docs_in_deal` | UC 2 | `/fin_deal1 What is Distribution Date?` | Results from PSA + ProSupp, deal graph used |
| 3 | `test_uc3_one_doc_type_across_deals` | UC 3 | `//PSA What is Distribution Date?` | PSA results from both deals |
| 4 | `test_uc4_wildcard_across_deals` | UC 4 | `/fin_deal* What is Distribution Date?` | Both deals searched |
| 5 | `test_uc5_wildcard_with_doc_filter` | UC 5 | `/fin_deal*/PSA What is Distribution Date?` | PSA only from both deals |
| 6 | `test_uc6_compare_wildcard` | UC 6 | `/compare /fin_deal* What is Distribution Date?` | Comparison output |
| 7 | `test_uc7_compare_specific_docs` | UC 7 | `/compare /fin_deal1/PSA /fin_deal2/PSA What is Distribution Date?` | PSA-specific comparison |
| 8 | `test_uc8_define_across_docs` | UC 8 | `/fin_deal1 /define Distribution Date` | Definition from PSA, references from ProSupp |
| 9 | `test_uc9_audit_single_doc` | UC 9 | `/audit /fin_deal1/PSA` | Anomaly detection on PSA only |
| 10 | `test_uc10_diff_two_docs_same_deal` | UC 10 | `/diff /fin_deal1/PSA /fin_deal1/PROSUPP Distribution Date` | Cross-doc diff within deal |
| 11 | `test_uc11_diff_same_doc_across_deals` | UC 11 | `/diff /fin_deal1/PSA /fin_deal2/PSA Distribution Date` | Cross-deal PSA diff |
| 12 | `test_uc13_list_docs_in_deal` | UC 13 | `/list /fin_deal1` | Returns PSA, PROSUPP |
| 13 | `test_uc14_aggregate_pattern` | UC 14 | `/aggregate /fin_deal* How is Realized Loss defined?` | Pattern + outliers |
| 14 | `test_full_pipeline_ingest_to_search` | Full pipeline | Ingest → search → verify isolation | .kts in subfolder, doc graphs created, search scoped |
| 15 | `test_scope_discovery_after_ingest` | Extension integration | Ingest → scope discovery runs → scopes available | Dynamic commands registered |

**Pass Criteria:** All 15 tests pass. This validates the entire Phase 17 feature set end-to-end.

---

## Performance Benchmarks

### File: `tests/test_phase17_performance.py`

| # | Test Name | Metric | Target | Methodology |
|---|-----------|--------|--------|-------------|
| 1 | `test_single_deal_single_doc_latency` | Wall clock | ≤ 2 sec | `/fin_deal1/PSA` query, 10 runs avg |
| 2 | `test_single_deal_all_docs_latency` | Wall clock | ≤ 2 sec | `/fin_deal1` query, 10 runs avg |
| 3 | `test_multi_deal_2_scopes_latency` | Wall clock | ≤ 3 sec | 2-deal parallel query |
| 4 | `test_multi_deal_10_scopes_latency` | Wall clock | ≤ 5 sec | 10-deal parallel query |
| 5 | `test_doc_filter_overhead` | Δ latency | ≤ 10% overhead | Filtered vs unfiltered same deal |
| 6 | `test_graph_partition_time` | Build time | ≤ 5 sec | Partition 2-doc deal graph |
| 7 | `test_catalog_wildcard_query_time` | Query time | ≤ 100 ms | Wildcard over 50-deal catalog |
| 8 | `test_scope_resolver_parse_time` | Parse time | ≤ 10 ms | Parse complex command |

**Pass Criteria:** All benchmarks meet targets on standard hardware (8GB RAM, SSD).

---

## Golden Query Validation

### File: `tests/test_phase17_golden.py`

These tests ensure Phase 17 does not degrade existing retrieval quality.

| # | Query | Expected Top Result | Scope |
|---|-------|-------------------|-------|
| 1 | "What is the Distribution Date?" | PSA §1.01 definition | `/fin_deal1` |
| 2 | "What is the Distribution Date?" | PSA §1.01 definition | `/fin_deal1/PSA` |
| 3 | "Who is the Trustee?" | PSA preamble / §8.01 | `/fin_deal1` |
| 4 | "How are losses allocated?" | PSA §5.05 | `/fin_deal1/PSA` |
| 5 | "What is a Realized Loss?" | Definition section | `/fin_deal1` |
| 6 | "Distribution Date" | PSA definition | `/fin_deal1/PSA` (doc filter) |
| 7 | "Distribution Date" across deals | Both deals' definitions | `/compare /fin_deal1 /fin_deal2` |
| 8 | "Servicer obligations" | ProSupp + PSA sections | `/fin_deal1` (both docs) |
| 9 | "Certificate holder payments" | PSA distribution waterfall | `/fin_deal1/PSA` |
| 10 | "What triggers an Event of Default?" | PSA §7 or §9 | `/fin_deal1/PSA` |
| 11 | "Who is the Depositor?" | PSA preamble / ProSupp cover | `/fin_deal1` (deal-level) |
| 12 | "Compare Distribution Date across deals" | Side-by-side | `/compare /fin_deal1/PSA /fin_deal2/PSA` |

**Pass Criteria:** All golden queries return expected top result with score ≥ 0.80.

---

## Regression Tests

### File: `tests/test_phase17_regression.py`

| # | Test Name | What It Verifies |
|---|-----------|-----------------|
| 1 | `test_no_scope_no_filter_unchanged` | Query without scope or doc filter produces same results as Phase 12 |
| 2 | `test_single_scope_no_filter_unchanged` | `/fin_deal1` query unchanged from Phase 12 |
| 3 | `test_compare_mode_backward_compatible` | Phase 15 `/compare` still works |
| 4 | `test_graph_traversal_unchanged` | Graph queries without doc filter same as before |
| 5 | `test_ingestion_output_backward_compatible` | Ingestion still creates `.kts/` with expected structure |
| 6 | `test_manifest_format_unchanged` | `manifest.json` format unchanged |
| 7 | `test_golden_queries_v2_no_regression` | All `golden_queries_v2.json` queries pass |
| 8 | `test_existing_cli_options_work` | All Phase 1–16 CLI options still function |
| 9 | `test_extension_basic_query_unchanged` | No-scope extension query works as before |
| 10 | `test_phase6_dual_store_unchanged` | DualVectorStore API unchanged for non-filtered queries |

**Pass Criteria:** All 10 regression tests pass. Zero degradation in existing functionality.

---

## Test Corpora

### Primary Test Corpus: `kb_test/`

```
kb_test/
  Fin_deal1/
    PSA_dealname1.doc         ← Pooling & Servicing Agreement
    Prosupp_dealname1.pdf     ← Prospectus Supplement
  Fin_deal2/
    PSA_dealname2.doc         ← Different deal's PSA
    Prosupp_dealname2.pdf     ← Different deal's ProSupp
```

### Extended Test Corpus (for multi-deal tests)

For performance and aggregation testing, create synthetic deals:
```
kb_test_extended/
  Bear_Stearns_2006_HE1/
    PSA_BSABS_2006HE1.doc
    Prosupp_BSABS_2006HE1.pdf
  Bear_Stearns_2006_HE2/
    PSA_BSABS_2006HE2.doc
    Prosupp_BSABS_2006HE2.pdf
  Bear_Stearns_2006_HE3/
    PSA_BSABS_2006HE3.doc
    Prosupp_BSABS_2006HE3.pdf
  ... (up to 10 deals)
```

### Corpus Requirements
- Each PSA must have a DEFINITIONS section with "Distribution Date" defined
- Each PSA must have a loss allocation section (§5.05 or equivalent)
- At least 2 deals should have slightly different Distribution Date definitions (for diff/compare testing)
- At least 1 deal should be an outlier for aggregation testing

---

## Test Execution Guide

### Quick Run (CI)

```bash
# Run all Phase 17 tests
pytest tests/test_phase17_*.py -v

# Run specific step
pytest tests/test_phase17_doc_filter.py -v

# Run integration tests
pytest tests/test_phase17_integration.py -v

# Run performance benchmarks (slower)
pytest tests/test_phase17_performance.py -v --timeout=60
```

### Full Validation

```bash
# 1. Run Phase 17 unit tests
pytest tests/test_phase17_*.py -v

# 2. Run regression tests (ensure no Phase 1-16 breakage)
pytest tests/test_phase17_regression.py -v

# 3. Run golden queries
pytest tests/test_phase17_golden.py -v

# 4. Run existing golden queries (Phase 6)
pytest tests/test_gold_standards_validation.py -v

# 5. Run all existing tests (full regression)
pytest tests/ -v --timeout=120

# 6. Build and test VSIX (manual)
# See docs/BUILD_GUIDE.md for build instructions
# Then run extension manual tests from Step 10 table
```

### Test Order (When Implementing Step by Step)

| After Step | Run These Tests |
|------------|----------------|
| Step 1 | `test_phase17_doc_filter.py` |
| Step 2 | `test_phase17_graph_metadata.py` |
| Step 3 | `test_phase17_graph_partition.py` |
| Step 4 | `test_phase17_deal_catalog.py` |
| Step 5 | `test_phase17_scope_resolver.py` |
| Step 6 | `test_phase17_retriever_routing.py` |
| Step 7 | `test_phase17_multi_deal.py` |
| Step 8 | `test_phase17_analytical_modes.py` |
| Step 9 | `test_phase17_cli.py` |
| Steps 10–11 | Manual extension tests + `test_phase17_attribution.py` |
| All done | `test_phase17_integration.py` + `test_phase17_golden.py` + `test_phase17_regression.py` |

---

*End of Document — 11_TESTING_PLAN.md*
