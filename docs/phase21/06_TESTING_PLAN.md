# Phase 21: Testing Plan
## Validation Strategy for ABS Domain Integration

**Document Version:** 1.0  
**Date:** February 26, 2026  
**Status:** Proposal — Pending Approval  
**Scope:** End-to-end testing strategy covering all Phase 21 components

---

## Table of Contents
1. [Overview](#overview)
2. [Test Categories](#test-categories)
3. [Step 1 Tests — Directory Scaffold](#step-1-tests)
4. [Step 2 Tests — File Copy Verification](#step-2-tests)
5. [Step 3 Tests — Temporary Stubs](#step-3-tests)
6. [Step 4 Tests — Import Resolution](#step-4-tests)
7. [Step 5 Tests — AgentBase Merge](#step-5-tests)
8. [Step 6 Tests — Quality Infrastructure](#step-6-tests)
9. [Step 7 Tests — KTSConfig Properties](#step-7-tests)
10. [Regression Tests](#regression-tests)
11. [Integration Tests](#integration-tests)
12. [Test Execution Guide](#test-execution-guide)

---

## Overview

### Testing Philosophy
- **Every step is independently testable** — each has its own test set
- **Existing KTS tests must pass throughout** — no regression allowed
- **Import resolution verified for every module** — no `ModuleNotFoundError`
- **Agent instantiation verified** — both KTS and ABS agents must work

### Test Summary

| Category | Test Count | Test File(s) |
|----------|-----------|--------------|
| Step 1 — Scaffold | 6 | `test_phase21_scaffold.py` |
| Step 2 — File Copy | 12 | `test_phase21_file_copy.py` |
| Step 3 — Stubs | 9 | `test_phase21_stubs.py` |
| Step 4 — Imports | 45 | `test_phase21_imports.py` |
| Step 5 — AgentBase | 25 | `test_phase21_agent_base.py` |
| Step 6 — Quality | 20 | `test_phase21_quality.py` |
| Step 7 — Config | 15 | `test_phase21_config.py` |
| Regression | 20 | `test_phase21_regression.py` |
| Integration | 10 | `test_phase21_integration.py` |
| **TOTAL** | **~162** | **9 test files** |

---

## Step 1 Tests — Directory Scaffold

### File: `tests/test_phase21_scaffold.py`

| # | Test Name | Description | Expected Result |
|---|-----------|-------------|-----------------|
| 1 | `test_abs_root_exists` | `backend/abs/` directory exists | `True` |
| 2 | `test_abs_agents_dir_exists` | `backend/abs/agents/` exists | `True` |
| 3 | `test_abs_skills_dir_exists` | `backend/abs/skills/` exists | `True` |
| 4 | `test_abs_generation_dir_exists` | `backend/abs/generation/` exists | `True` |
| 5 | `test_abs_ingestion_dir_exists` | `backend/abs/ingestion/` exists | `True` |
| 6 | `test_abs_config_dir_exists` | `backend/abs/config/` exists | `True` |

**Pass Criteria:** All 6 directories exist with `__init__.py` files.

---

## Step 2 Tests — File Copy Verification

### File: `tests/test_phase21_file_copy.py`

| # | Test Name | Description | Expected Result |
|---|-----------|-------------|-----------------|
| 1 | `test_abs_agent_count` | 12 agent files in `abs/agents/` | Count = 12 |
| 2 | `test_abs_skill_count` | 14 files in `abs/skills/` (11 real + 3 stubs) | Count = 14 |
| 3 | `test_abs_generation_count` | 3 files in `abs/generation/` | Count = 3 |
| 4 | `test_abs_ingestion_count` | 9 files in `abs/ingestion/` | Count = 9 |
| 5 | `test_abs_config_count` | 3 domain config files in `abs/config/` | Count = 3 |
| 6 | `test_deal_scope_exists` | `abs/deal_scope.py` exists | `True` |
| 7 | `test_deal_manifest_exists` | `abs/deal_manifest.py` exists | `True` |
| 8 | `test_errors_exists` | `abs/errors.py` exists | `True` |
| 9 | `test_agent_tools_in_agents` | `backend/agents/agent_tools.py` exists | `True` |
| 10 | `test_confidence_in_common` | `backend/common/confidence.py` exists | `True` |
| 11 | `test_pre_mortem_in_common` | `backend/common/pre_mortem.py` exists | `True` |
| 12 | `test_cashflow_engine_nonzero` | `abs/skills/cashflow_engine.py` > 500 lines | `True` |

**Pass Criteria:** All files present, key files non-empty.

---

## Step 3 Tests — Temporary Stubs

### File: `tests/test_phase21_stubs.py`

| # | Test Name | Description | Expected Result |
|---|-----------|-------------|-----------------|
| 1 | `test_embedder_stub_import` | `from backend.abs.skills.embedder import embed_and_store` | No ImportError |
| 2 | `test_embedder_stub_raises` | `embed_and_store()` raises `NotImplementedError` | "Phase 22" in message |
| 3 | `test_embedder_stub_all_functions` | `chunk_text`, `embed`, `upsert_to_chroma` all raise | All raise NotImplementedError |
| 4 | `test_graph_stub_import` | `from backend.abs.skills.graph_builder import build_graph` | No ImportError |
| 5 | `test_graph_stub_raises` | `build_graph()` raises `NotImplementedError` | "Phase 22" in message |
| 6 | `test_graph_stub_all_functions` | `save_graph`, `load_graph`, `query_graph` all raise | All raise NotImplementedError |
| 7 | `test_vector_stub_import` | `from backend.abs.skills.vector_search import vector_search` | No ImportError |
| 8 | `test_vector_stub_raises` | `vector_search()` raises `NotImplementedError` | "Phase 22" in message |
| 9 | `test_search_result_dataclass` | `SearchResult` dataclass importable and constructable | `SearchResult()` works |

**Pass Criteria:** All stubs import cleanly and raise `NotImplementedError` with "Phase 22" in message.

---

## Step 4 Tests — Import Resolution

### File: `tests/test_phase21_imports.py`

This is the largest test file — it verifies every ABS module can be imported.

```python
import pytest
import importlib


ABS_MODULES = [
    # Root
    "backend.abs",
    "backend.abs.deal_scope",
    "backend.abs.deal_manifest",
    "backend.abs.errors",
    # Agents
    "backend.abs.agents",
    "backend.abs.agents.cashflow_projection_agent",
    "backend.abs.agents.deal_amendment_agent",
    "backend.abs.agents.deal_lifecycle_agent",
    "backend.abs.agents.document_comparison_agent",
    "backend.abs.agents.document_quality_agent",
    "backend.abs.agents.ingestion_pipeline_agent",
    "backend.abs.agents.investor_reporting_agent",
    "backend.abs.agents.model_auditor_agent",
    "backend.abs.agents.model_creation_agent",
    "backend.abs.agents.qa_agent",
    "backend.abs.agents.regression_testing_agent",
    "backend.abs.agents.stress_testing_agent",
    # Skills
    "backend.abs.skills",
    "backend.abs.skills.amendment_manager",
    "backend.abs.skills.cashflow_engine",
    "backend.abs.skills.csv_validator",
    "backend.abs.skills.deal_comparator",
    "backend.abs.skills.deal_setup_extractor",
    "backend.abs.skills.document_classifier",
    "backend.abs.skills.document_hasher",
    "backend.abs.skills.document_tools",
    "backend.abs.skills.embedder",
    "backend.abs.skills.graph_builder",
    "backend.abs.skills.output_comparator",
    "backend.abs.skills.parsers",
    "backend.abs.skills.report_generator",
    "backend.abs.skills.vector_search",
    # Generation
    "backend.abs.generation",
    "backend.abs.generation.data_prep",
    "backend.abs.generation.model_runner",
    "backend.abs.generation.model_validator",
    # Ingestion
    "backend.abs.ingestion",
    "backend.abs.ingestion.definition_resolution",
    "backend.abs.ingestion.document_converter",
    "backend.abs.ingestion.document_intelligence",
    "backend.abs.ingestion.governing_doc_generator",
    "backend.abs.ingestion.ingestion_validator",
    "backend.abs.ingestion.knowledge_store",
    "backend.abs.ingestion.pipeline_runner",
    "backend.abs.ingestion.section_splitter",
    "backend.abs.ingestion.structured_extractor",
    # Config
    "backend.abs.config",
    "backend.abs.config.constants",
    "backend.abs.config.schemas",
    "backend.abs.config.section_maps",
]


@pytest.mark.parametrize("module_path", ABS_MODULES)
def test_import_abs_module(module_path):
    """Every ABS module must import without error."""
    mod = importlib.import_module(module_path)
    assert mod is not None
```

Additional import tests:

| # | Test Name | Description |
|---|-----------|-------------|
| 46 | `test_no_pipeline_imports_remain` | grep `from pipeline.` in `backend/abs/` → 0 matches |
| 47 | `test_agent_tools_importable` | `from backend.agents.agent_tools import ToolRegistry` works |
| 48 | `test_quality_modules_importable` | All 6 quality modules in `backend/common/` import |

**Pass Criteria:** All 45+ modules import without `ModuleNotFoundError` or `ImportError`.

---

## Step 5 Tests — AgentBase Merge

### File: `tests/test_phase21_agent_base.py`

| # | Test Name | Description | Expected Result |
|---|-----------|-------------|-----------------|
| 1 | `test_agent_base_has_max_retries` | `AgentBase.MAX_RETRIES == 3` | `True` |
| 2 | `test_agent_base_has_min_quality` | `AgentBase.MIN_QUALITY_SCORE == 8.0` | `True` |
| 3 | `test_kts_agent_init_no_scope` | KTS agent: `deal_scope is None` | `True` |
| 4 | `test_kts_agent_init_no_tools` | KTS agent: `tool_registry is None` | `True` |
| 5 | `test_abs_agent_init_with_scope` | ABS agent: `deal_scope is not None` | `True` |
| 6 | `test_abs_agent_init_with_tools` | ABS agent: `tool_registry is not None` | `True` |
| 7 | `test_default_mission` | Default `_get_mission()` returns string | `"No mission defined"` |
| 8 | `test_default_actions` | Default `_get_actions()` returns `[]` | `[]` |
| 9 | `test_default_output_spec` | Default `_get_output_spec()` returns string | Non-empty string |
| 10 | `test_default_validation_rules` | Default `_get_validation_rules()` returns `[]` | `[]` |
| 11 | `test_system_prompt_property` | `system_prompt` builds from mission/actions/output/rules | Contains "MISSION:" |
| 12 | `test_execute_returns_agent_output` | `execute()` returns `AgentOutput` | isinstance check |
| 13 | `test_execute_calls_run` | `execute()` calls `_run()` | Mock verification |
| 14 | `test_execute_retry_on_quality_fail` | Failed quality → retry up to MAX_RETRIES | 3 `_run()` calls |
| 15 | `test_evaluate_quality_5_dimensions` | `_evaluate_quality()` scores 5 dimensions | 5 keys in scores |
| 16 | `test_default_scores_are_8` | Default dimension scores are 8.0 | All 8.0 |
| 17 | `test_quality_pass_at_8` | Average ≥ 8.0 → passed=True | `True` |
| 18 | `test_quality_fail_below_8` | Average < 8.0 → passed=False | `False` |
| 19 | `test_confidence_high` | Score ≥ 0.90 → ConfidenceTier.HIGH | `HIGH` |
| 20 | `test_confidence_medium` | 0.66 ≤ score < 0.90 → MEDIUM | `MEDIUM` |
| 21 | `test_confidence_low` | Score < 0.66 → LOW | `LOW` |
| 22 | `test_state_persistence_with_scope` | `_save_state()` + `_load_state()` round-trip | State preserved |
| 23 | `test_state_persistence_no_scope` | `_load_state()` without scope → `{}` | `{}` |
| 24 | `test_quality_check_legacy` | `quality_check()` still works for AgentResult | Returns AgentResult |
| 25 | `test_all_kts_agents_instantiate` | All 15 KTS agents create with merged base | All succeed |

**Pass Criteria:** All 25 tests pass. KTS + ABS agents coexist.

---

## Step 6 Tests — Quality Infrastructure

### File: `tests/test_phase21_quality.py`

| # | Test Name | Description | Expected Result |
|---|-----------|-------------|-----------------|
| 1 | `test_quality_gate_init` | `QualityGate(config)` creates successfully | No error |
| 2 | `test_legacy_apply_high` | `apply()` with confidence 0.95 → `quality_tier = "high"` | `"high"` |
| 3 | `test_legacy_apply_medium` | `apply()` with confidence 0.75 → `quality_tier = "medium"` | `"medium"` |
| 4 | `test_legacy_apply_low` | `apply()` with confidence 0.40 → `quality_tier = "low"` | `"low"` |
| 5 | `test_evaluate_5_dims` | `evaluate()` returns QualityResult with 5 scores | 5 dimension keys |
| 6 | `test_evaluate_default_pass` | `evaluate()` with defaults → passed=True | `True` |
| 7 | `test_evaluate_custom_scorers` | Custom scorer returning 5.0 → passed=False | `False` |
| 8 | `test_evaluate_feedback_on_fail` | Failed result has feedback with low dimensions | Non-empty feedback |
| 9 | `test_confidence_import` | `from backend.common.confidence import *` | No error |
| 10 | `test_confidence_tier_classification` | `categorize_confidence()` works | Correct tiers |
| 11 | `test_escalation_import` | `from backend.common.escalation import *` | No error |
| 12 | `test_escalation_report_dataclass` | `EscalationReport` constructable | No error |
| 13 | `test_output_contracts_import` | `from backend.common.output_contracts import *` | No error |
| 14 | `test_pre_mortem_import` | `from backend.common.pre_mortem import *` | No error |
| 15 | `test_refine_loop_import` | `from backend.common.refine_loop import *` | No error |
| 16 | `test_quality_dimension_enum` | `QualityDimension` has 5 values | 5 members |
| 17 | `test_quality_result_dataclass` | `QualityResult` fields correct | `passed, scores, retry_count, feedback` |
| 18 | `test_quality_gate_uses_abs_threshold` | Gate reads `abs_min_quality_score` from config | Uses 8.0 |
| 19 | `test_quality_gate_uses_kts_confidence` | Gate reads `confidence_high` from config | Uses 0.90 |
| 20 | `test_both_interfaces_coexist` | `apply()` and `evaluate()` callable on same instance | Both work |

**Pass Criteria:** All 20 tests pass. Both legacy and 5-dimension interfaces work.

---

## Step 7 Tests — KTSConfig Properties

### File: `tests/test_phase21_config.py`

| # | Test Name | Description | Expected Result |
|---|-----------|-------------|-----------------|
| 1 | `test_abs_enabled_default` | `config.abs_enabled` default | `False` |
| 2 | `test_abs_deals_root_default` | `config.abs_deals_root` default | `"deals"` |
| 3 | `test_abs_extraction_mode_default` | `config.abs_extraction_mode` default | `"hybrid"` |
| 4 | `test_abs_min_quality_score_default` | `config.abs_min_quality_score` default | `8.0` |
| 5 | `test_abs_max_retries_default` | `config.abs_max_retries` default | `3` |
| 6 | `test_abs_confidence_high_default` | `config.abs_confidence_high` default | `0.90` |
| 7 | `test_abs_confidence_low_default` | `config.abs_confidence_low` default | `0.66` |
| 8 | `test_abs_vectorstore_enabled_default` | `config.abs_vectorstore_enabled` default | `True` |
| 9 | `test_abs_embedding_dim_default` | `config.abs_embedding_dim` default | `768` |
| 10 | `test_abs_chunk_max_chars_default` | `config.abs_chunk_max_chars` default | `3000` |
| 11 | `test_abs_definition_resolution_defaults` | All resolution defaults correct | Correct values |
| 12 | `test_env_var_override_abs_enabled` | `KTS_ABS_ENABLED=true` → `True` | `True` |
| 13 | `test_env_var_override_abs_deals_root` | `KTS_ABS_DEALS_ROOT=my_deals` → `"my_deals"` | `"my_deals"` |
| 14 | `test_existing_config_loads` | Loading existing config (no abs_ keys) → defaults | No error |
| 15 | `test_abs_config_serialization` | Config with abs_ fields → dict → config round-trip | All values preserved |

**Pass Criteria:** All 15 tests pass. Existing configs load without modification.

---

## Regression Tests

### File: `tests/test_phase21_regression.py`

| # | Test Name | Description |
|---|-----------|-------------|
| 1 | `test_crawler_agent_still_works` | CrawlerAgent executes on test corpus |
| 2 | `test_ingestion_agent_still_works` | IngestionAgent processes test document |
| 3 | `test_taxonomy_agent_still_works` | TaxonomyAgent classifies test document |
| 4 | `test_retrieval_service_still_works` | RetrievalService searches test query |
| 5 | `test_graph_builder_agent_still_works` | GraphBuilderAgent builds graph |
| 6 | `test_training_path_agent_still_works` | TrainingPathAgent generates paths |
| 7 | `test_change_impact_agent_still_works` | ChangeImpactAgent analyzes entity |
| 8 | `test_freshness_agent_still_works` | FreshnessAgent checks staleness |
| 9 | `test_diff_agent_still_works` | DiffAgent compares documents |
| 10 | `test_describe_agent_still_works` | DescribeAgent generates description |
| 11 | `test_cli_search_command` | `cli search "test query"` returns results |
| 12 | `test_cli_status_command` | `cli status` shows knowledge base info |
| 13 | `test_cli_crawl_command` | `cli crawl --dry-run` lists files |
| 14 | `test_existing_golden_queries` | Golden query tests all pass |
| 15 | `test_config_loads_without_abs` | Existing config files load cleanly |
| 16 | `test_quality_gate_backward_compat` | Old-style `quality_check()` works |
| 17 | `test_agent_result_model_unchanged` | `AgentResult` dataclass still has all fields |
| 18 | `test_scope_resolver_unchanged` | ScopeResolver works with existing scopes |
| 19 | `test_deal_catalog_unchanged` | DealCatalog queries still work |
| 20 | `test_manifest_store_unchanged` | ManifestStore read/write unchanged |

**Pass Criteria:** All 20 regression tests pass. Zero regressions from Phase 21 changes.

---

## Integration Tests

### File: `tests/test_phase21_integration.py`

| # | Test Name | Description |
|---|-----------|-------------|
| 1 | `test_abs_agent_uses_kts_quality_gate` | ABS agent's QualityGate reads KTSConfig |
| 2 | `test_abs_deal_scope_creates_dirs` | DealScope.create() builds directory tree |
| 3 | `test_abs_deal_scope_prevents_escape` | DealScope.resolve("../../etc") → DealScopingViolation |
| 4 | `test_abs_deal_manifest_save_load` | DealManifest save → load round-trip |
| 5 | `test_abs_errors_structured_logging` | StructuredErrorLogger writes JSON-lines |
| 6 | `test_kts_and_abs_agents_coexist` | KTS CrawlerAgent + ABS ModelCreationAgent both instantiate |
| 7 | `test_tool_registry_for_abs_agent` | ABS agent accesses tools via ToolRegistry |
| 8 | `test_abs_cashflow_engine_runs` | CashflowEngine processes synthetic deal data |
| 9 | `test_abs_parsers_run` | Section parser splits test PSA text |
| 10 | `test_abs_config_from_ktsconfig` | ABS modules read `abs_*` properties from KTSConfig |

**Pass Criteria:** All 10 integration tests pass. KTS + ABS modules interoperate.

---

## Test Execution Guide

### Quick Validation (After Each Step)

```powershell
# Run only Phase 21 tests
pytest tests/test_phase21_*.py -v --tb=short
```

### Full Suite (After Step 7)

```powershell
# Run everything — KTS + Phase 21
pytest tests/ -v --tb=short -x  # Stop on first failure
```

### CI Command

```powershell
pytest tests/ -v --tb=long --junitxml=test-results/phase21.xml
```

### Expected Test Duration

| Test Suite | Duration |
|-----------|----------|
| Phase 21 tests (162 tests) | ~30 seconds |
| Full KTS suite + Phase 21 | ~3 minutes |
