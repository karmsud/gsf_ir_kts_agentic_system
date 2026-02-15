# TRIAGE TABLE - Autopilot Run 20260214_131137

**Date:** 2026-02-14 13:11:37  
**Overall Result:** FAIL (exit code 1)  
**Pytest:** 46/46 PASSED ✓  
**End-to-End Pipeline:** FAILED ✗

## Exit Criteria Evaluation

| Criterion | Status | Notes |
|-----------|--------|-------|
| Ingestion pipeline completed | ❌ FAIL | Crawl command syntax error |
| All queries returned citations | ⚠️ PASS* | *No queries ran (query pack load failed) |
| Query accuracy >= 90% | ❌ FAIL | No queries ran |
| No idempotency duplicates | ✅ PASS | Count stable at 0 |
| Advanced agents succeeded | ❌ FAIL | Training and Impact CLI errors |
| Pytest suite passed | ✅ PASS | 46/46 tests passed |
| **OVERALL** | ❌ FAIL | 3/6 criteria failed |

## Failure Triage

### P0 Failures (Critical - Block all testing)

| ID | Layer | Root Cause | Evidence | Fix Plan |
|----|-------|------------|----------|----------|
| **P0-1** | CLI / Crawl | **Crawl command syntax error**<br>Script passes positional arg but CLI expects `--paths` flag | `Error: Got unexpected extra argument (.\kts_test_corpus)`<br>Exit code: 2 | Change `crawl .\kts_test_corpus` to `crawl --paths ".\kts_test_corpus"` in autopilot script |
| **P0-2** | Test Harness | **Query pack parsing failure**<br>Script looks for `$QueryPack.queries` but JSON structure is `categories[].queries[]` | `Query pack: 0 queries loaded`<br>Expected: 50 queries | Fix query pack parsing logic to iterate through categories array |

### P1 Failures (High - Partial functionality loss)

| ID | Layer | Root Cause | Evidence | Fix Plan |
|----|-------|------------|----------|----------|
| **P1-1** | CLI / Training | **Training command missing required flag**<br>CLI expects `--topic` flag but script passes positional arg | `Error: Missing option '--topic'`<br>Exit code: 2 | Change `training "How do I..."` to `training --topic "ToolX authentication"` |
| **P1-2** | CLI / Impact | **Impact command missing required flag**<br>CLI expects `--entity` flag but script passes positional arg | `Error: Missing option '--entity'`<br>Exit code: 2 | Change `impact "What changed..."` to `impact --entity "ToolX"` |

### P2 Failures (Low - Quality issues)

| ID | Layer | Root Cause | Evidence | Fix Plan |
|----|-------|------------|----------|----------|
| *None* | N/A | N/A | N/A | N/A |

## Downstream Impact Analysis

### P0-1: Crawl Syntax Error
- **Blocks:** All ingestion (0 docs ingested)
- **Cascades to:** 
  - No retrieval possible (no vectors)
  - No query testing (no content to search)
  - No vision workflow (no images extracted)
  - All advanced agents have empty knowledge base
- **Fix Complexity:** LOW (single line change in script)
- **Verification:** Run `crawl --paths ".\kts_test_corpus"` manually

### P0-2: Query Pack Load Failure
- **Blocks:** All 50 query tests
- **Cascades to:**
  - Cannot measure citation quality
  - Cannot measure query accuracy
  - Cannot validate expected doc matches
- **Fix Complexity:** LOW (fix PowerShell JSON navigation)
- **Verification:** Script should log "Query pack: 50 queries loaded"

### P1-1 & P1-2: Advanced Agent CLI Errors
- **Blocks:** Training and Impact agent testing
- **Does NOT block:** 
  - Basic ingestion/retrieval/search
  - Freshness agent (ran successfully)
  - Pytest suite (all passed)
- **Fix Complexity:** LOW (correct CLI flags)
- **Verification:** Commands should return results, not usage errors

## Recommended Fix Order

1. **P0-1:** Fix crawl command (highest impact, simplest fix)
2. **P0-2:** Fix query pack parsing (unblocks full test coverage)
3. **P1-1:** Fix training command signature
4. **P1-2:** Fix impact command signature
5. **Re-run full suite** and validate all exit criteria

## Expected Post-Fix Metrics

| Metric | Current | Expected After Fix |
|--------|---------|-------------------|
| Documents ingested | 0 | 14 (all corpus files) |
| Queries executed | 0 | 50 (full pack) |
| Queries with citations | N/A | 50/50 (100%) |
| Query accuracy | N/A | >= 45/50 (90%) |
| Advanced agents success | 1/3 | 3/3 (100%) |
| Pytest | 46/46 | 46/46 (stable) |
| **Overall exit criteria** | 3/6 | 6/6 ✅ |

## Logs and Artifacts

- **Console log:** `scripts\logs\autopilot_20260214_131137\autopilot_console.log`
- **Results JSON:** `scripts\logs\autopilot_20260214_131137\results.json`
- **Metrics JSON:** `scripts\logs\autopilot_20260214_131137\metrics.json`
- **Individual command logs:** `scripts\logs\autopilot_20260214_131137\*.log`
