# Phase 2 — Test Case Matrix

## Overview
Comprehensive suite implemented across these files:
- `tests/test_phase2_common_10x.py`
- `tests/test_phase2_crawler_10x.py`
- `tests/test_phase2_ingestion_10x.py`
- `tests/test_phase2_vision_10x.py`
- `tests/test_phase2_taxonomy_version_10x.py`
- `tests/test_phase2_graph_retrieval_10x.py`
- `tests/test_phase2_advanced_agents_10x.py`
- `tests/test_phase2_cli_10x.py`

## Matrix by Domain

| Domain | 10-Way Coverage | Negative/Edge Included |
|---|---|---|
| Common utilities | 10 clean-text + 10 chunking patterns + hashing/manifest/quality gates | Yes |
| Crawler | 10 scenarios (empty/new/re-scan/modify/force/delete/dry-run/large/missing/unsupported) | Yes |
| Ingestion | 10 scenarios (md/txt/html/empty/unsupported/missing/custom-id/version/repeat) | Yes |
| Vision | 10 scenarios (initialize/status/pending/invalid-complete/valid-complete/final-state/unknown-op) | Yes |
| Taxonomy | 10 classification scenarios across labels + unknown | Yes |
| Version | 10 diff scenarios (no-change/section/image add-remove/chunk summary) | Yes |
| Graph + Retrieval | 10 scenarios including filters/no-match and query heuristics | Yes |
| Advanced agents | 10 scenarios across training/impact/freshness combinations | Yes |
| CLI | 10 end-to-end command scenarios with options/filters/status/describe | Yes |

## Legacy + Baseline Suites Also Executed
- Existing baseline tests in `tests/*.py` were retained and executed with phase2 suite.

## Total Automated Test Count
- **46 tests passing** (baseline + phase2)
