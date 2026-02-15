# V1 Full Regression Validation Report
**Date**: 2026-02-14  
**Session**: POST-INGESTION FIX VALIDATION  
**Mode**: Autonomous, Evidence-Based  
**Validation ID**: 20260214_144637

---

## EXECUTIVE SUMMARY

✅ **DECISION: GO**

Ingestion fix (JSON support + REFERENCE taxonomy) successfully validated through clean re-ingestion and full accuracy testing. All targets met with **no regressions detected**. System ready for v2 corpus validation.

---

## VALIDATION PROTOCOL

### Objectives
1. Verify JSON ingestion fix reproducible after clean KB rebuild
2. Confirm Q7 "List all error codes" has REFERENCE candidates post-ingestion
3. Maintain all accuracy targets: Tune ≥99%, Holdout ≥90%, Top-3 ≥98%
4. Compare metrics to baseline (pre-JSON fix, Iteration 10)
5. Evidence-based: raw terminal outputs for all operations

### Test Environment
- **Workspace**: `c:\Users\Karmsud\Projects\gsf_ir_kts_agentic_system`
- **Corpus**: kts_test_corpus (v1, 10 documents)
- **Golden Queries**: tests/golden_queries.json (50 queries: 40 tune, 10 holdout)
- **Python**: 3.13.5
- **Git**: Not in version control (workspace-only validation)

---

## VALIDATION STEPS

### Step 1: Clean-Slate Verification ✅
**Goal**: Document current ingestion state before destructive re-ingest

**Commands Executed**:
```powershell
# Check git status
git status 2>&1; git rev-parse HEAD 2>&1

# Verify JSON ingestion components
Select-String -Path backend\ingestion\__init__.py -Pattern "json_converter"
Select-String -Path config\settings.py -Pattern "supported_extensions"
Select-String -Path config\taxonomy_rules.json -Pattern "REFERENCE"
```

**Findings**:
- Workspace not in git (acceptable for validation)
- JSON converter imported: ✅ `from .json_converter import convert_json, extract_json_metadata`
- JSON extension supported: ✅ `.json` in `supported_extensions`
- REFERENCE taxonomy present: ✅ `"REFERENCE": ["reference catalog", "error codes catalog", ...]`

---

### Step 2: Re-Ingest V1 Corpus ✅
**Goal**: Clean KB and re-ingest kts_test_corpus to validate reproducibility

**Commands Executed**:
```powershell
# Clean knowledge base
Remove-Item -Recurse -Force knowledge_base\documents, knowledge_base\vectors, knowledge_base\graph

# Re-ingest corpus
.venv\Scripts\python.exe -m cli.main ingest --paths kts_test_corpus
```

**Ingestion Results**:
```json
{
  "count": 10,
  "ingested": [
    {
      "doc_id": "doc_9738473",
      "path": "kts_test_corpus\\Reference\\error_code_catalog.json",
      "chunk_count": 1,
      "doc_type": "REFERENCE"  ← CRITICAL: JSON file successfully ingested!
    },
    ...9 more docs (TROUBLESHOOT, USER_GUIDE, TRAINING, RELEASE_NOTE, SOP)
  ]
}
```

**Outcome**: ✅ error_code_catalog.json ingested as doc_type=REFERENCE (doc_id=doc_9738473)

---

### Step 3: Q7 Candidate Generation Check ✅
**Goal**: Verify REFERENCE docs appear in Q7 retrieval results

**Query**: "List all error codes for ToolX"  
**Command**: `.venv\Scripts\python.exe scripts\check_q7_candidates.py`

**Results**:
```
=== Q7 CANDIDATE CHECK ===
Query: List all error codes for ToolX
Candidates: 10

  1. doc_id=doc_9738473 , doc_type=REFERENCE         ← RANK 1! ✅
  2. doc_id=doc_8495270 , doc_type=TROUBLESHOOT
  3. doc_id=doc_8678565 , doc_type=TROUBLESHOOT
  4. doc_id=doc_3474149 , doc_type=TROUBLESHOOT
  5. doc_id=doc_8222427 , doc_type=TROUBLESHOOT
  6. doc_id=doc_1737647 , doc_type=RELEASE_NOTE
  7. doc_id=doc_6566053 , doc_type=USER_GUIDE
  8. doc_id=doc_3405059 , doc_type=TROUBLESHOOT
  9. doc_id=doc_1337304 , doc_type=TRAINING
  10. doc_id=doc_2787452 , doc_type=TROUBLESHOOT

[PASS] GATE CHECK: REFERENCE in top-5 = True
```

**Outcome**: ✅ REFERENCE at rank 1 (doc_9738473) - Q7 will pass

---

### Step 4: Full Scoring Run ✅
**Goal**: Execute all 50 golden queries and compute accuracy metrics

**Command**: `.\scripts\run_accuracy_tuning.ps1 -Mode baseline -SkipIngest`

**Accuracy Results**:
```
--- TUNE SET (40 queries) ---
  Top-1 Accuracy: 100.0% (40/40) [TARGET: >=99%]  ✅
  Top-3 Accuracy: 100.0% (40/40)
  Evidence Found: 100.0%
  Status: PASS

--- HOLDOUT SET (10 queries) ---
  Top-1 Accuracy: 90.0% (9/10) [TARGET: >=90%]  ✅
  Top-3 Accuracy: 100.0% (10/10)
  Evidence Found: 100.0%
  Status: PASS

--- OVERALL (50 queries) ---
  Top-1 Accuracy: 98.0% (49/50)
  Top-3 Accuracy: 100.0% (50/50) [TARGET: >=98%]  ✅
  Evidence Found: 100.0%
  Status: PASS

--- SAFE TARGETS STATUS ---
  Tune Top-1 >= 99%:     PASS  ✅
  Holdout Top-1 >= 90%:  PASS  ✅
  Overall Top-3 >= 98%:  PASS  ✅

  ALL TARGETS MET: YES  ✅
```

**Outcome**: ✅ All queries executed successfully, all targets passed

---

### Step 5: Regression Analysis ✅
**Goal**: Compare current metrics to baseline (pre-JSON fix)

| Metric | Baseline (Iteration 10) | Current (Post-JSON Fix) | Delta | Status |
|--------|-------------------------|-------------------------|-------|--------|
| **Tune Top-1** | 97.5% (39/40) | **100.0% (40/40)** | +2.5% | ✅ Improved |
| **Holdout Top-1** | 90.0% (9/10) | **90.0% (9/10)** | 0% | ✅ Maintained |
| **Overall Top-3** | 98.0% (49/50) | **100.0% (50/50)** | +2.0% | ✅ Improved |
| **Citations** | 100.0% | **100.0%** | 0% | ✅ Maintained |
| **Q7 Status** | ❌ REFERENCE missing | ✅ REFERENCE rank 1 | FIXED | ✅ |

**Regression Status**:
- Tune: NO REGRESSION (+2.5% improvement)
- Holdout: NO REGRESSION (maintained 90%)
- Top-3: NO REGRESSION (+2.0% improvement)
- Citations: NO REGRESSION (maintained 100%)

**Outcome**: ✅ No regressions detected - ingestion fix validated

---

### Step 6: GO/NO-GO Decision ✅

**Pass Criteria**:
- ✅ Holdout Top-1 ≥ 90% (Actual: 90.0%)
- ✅ Overall Top-3 ≥ 98% (Actual: 100.0%)
- ✅ Citations = 100% (Actual: 100.0%)
- ✅ Q7 has REFERENCE in top-5 (Actual: rank 1)
- ✅ No regressions vs baseline

**Validation Items**:
- ✅ Clean KB + re-ingestion successful
- ✅ JSON converter active (error_code_catalog.json ingested as REFERENCE)
- ✅ REFERENCE taxonomy present in taxonomy_rules.json
- ✅ Q7 returns REFERENCE at rank 1 (doc_id=doc_9738473)
- ✅ All 50 golden queries executed successfully
- ✅ Tune 100% (40/40), Holdout 90% (9/10), Top-3 100% (50/50)
- ✅ +2.5% improvement on Tune set, +2.0% on Overall Top-3

**DECISION**: **[GO] ✅**

---

## REPRODUCIBILITY EVIDENCE

All logs saved to: `scripts\logs\20260214_144637\`

**File Inventory**:
1. `ingest.log` - Full ingestion output (10 docs, JSON converter invoked)
2. `q7_check.log` - Q7 candidate generation (REFERENCE at rank 1)
3. `full_scoring.log` - All 50 queries + accuracy report
4. `go_no_go_decision.log` - Final validation decision

**Search Results**: `tests\accuracy_tuning_output\search_results.json` (50 query results)  
**Accuracy Scores**: `tests\accuracy_tuning_output\accuracy_scores.json` (detailed scoring evidence)

---

## INGESTION FIX COMPONENTS

### Files Modified (Phase 2 - Ingestion Coverage Fix)
1. **backend/ingestion/json_converter.py** (NEW, 128 lines)
   - `convert_json()`: Converts JSON catalog to indexable text with titles, sections, entries
   - `extract_json_metadata()`: Returns doc_type=REFERENCE, error_codes[], tool_names[], categories[]

2. **backend/ingestion/__init__.py** (+2 exports)
   - Exports: `convert_json`, `extract_json_metadata`

3. **backend/agents/ingestion_agent.py** (+26 lines)
   - Line 30: Added `.json` case to `_convert()` method
   - Lines 62-84: JSON metadata enrichment (doc_type, error_codes, tool_names, categories)

4. **config/settings.py** (line 12: added `".json"`)
   - `supported_extensions = [".docx", ".pdf", ".pptx", ".htm", ".html", ".md", ".txt", ".json"]`

5. **config/taxonomy_rules.json** (+1 category)
   - Added `"REFERENCE": ["reference catalog", "error codes catalog", "error code list", "catalog", "api reference", "code dictionary", "complete list"]`

---

## RECOMMENDATION

✅ **Ingestion fix VALIDATED and PRODUCTION-READY.**

**Evidence**:
- Clean re-ingestion reproduces expected metrics
- Q7 blocker resolved (REFERENCE at rank 1)
- All accuracy targets maintained (Tune 100%, Holdout 90%, Top-3 100%)
- No regressions vs. baseline (improvements: Tune +2.5%, Top-3 +2.0%)
- Citations 100% maintained

**Next Steps**:
1. Proceed to **v2 corpus validation** (larger dataset)
2. Monitor Q7 performance on v2 (verify REFERENCE docs present in v2 corpus)
3. Consider documenting JSON ingestion in architecture docs

---

## RISK ASSESSMENT

**Low Risk Areas** ✅:
- JSON converter stable (128 lines, no external dependencies)
- Taxonomy rules non-invasive (additive only)
- Ranking logic unchanged (validation-only phase)

**Medium Risk Areas** ⚠️:
- v2 corpus may have different JSON structure (need validation)
- REFERENCE taxonomy may need tuning for v2 keywords

**Mitigation**:
- Test v2 corpus ingestion separately before full regression
- Monitor Q7 and similar "list all" queries on v2

---

## APPENDIX: TERMINAL OUTPUTS

### A. Ingestion Output
```json
{
  "ingested": [
    {
      "doc_id": "doc_9738473",
      "path": "kts_test_corpus\\Reference\\error_code_catalog.json",
      "chunk_count": 1,
      "doc_type": "REFERENCE"
    },
    {
      "doc_id": "doc_8678565",
      "path": "kts_test_corpus\\Reference\\SOP_ToolX_Login_Failures_v1.docx",
      "chunk_count": 1,
      "doc_type": "TROUBLESHOOT"
    },
    ...8 more docs
  ],
  "count": 10
}
```

### B. Q7 Candidate Check
```
=== Q7 CANDIDATE CHECK ===
Query: List all error codes for ToolX
Candidates: 10

  1. doc_id=doc_9738473 , doc_type=REFERENCE
  2. doc_id=doc_8495270 , doc_type=TROUBLESHOOT
  3. doc_id=doc_8678565 , doc_type=TROUBLESHOOT
  4. doc_id=doc_3474149 , doc_type=TROUBLESHOOT
  5. doc_id=doc_8222427 , doc_type=TROUBLESHOOT
  6. doc_id=doc_1737647 , doc_type=RELEASE_NOTE
  7. doc_id=doc_6566053 , doc_type=USER_GUIDE
  8. doc_id=doc_3405059 , doc_type=TROUBLESHOOT
  9. doc_id=doc_1337304 , doc_type=TRAINING
  10. doc_id=doc_2787452 , doc_type=TROUBLESHOOT

[PASS] GATE CHECK: REFERENCE in top-5 = True
```

### C. Full Accuracy Report
```
--- TUNE SET (40 queries) ---
  Top-1 Accuracy: 100.0% (40/40) [TARGET: >=99%]
  Top-3 Accuracy: 100.0% (40/40)
  Evidence Found: 100.0%
  Status: PASS

--- HOLDOUT SET (10 queries) ---
  Top-1 Accuracy: 90.0% (9/10) [TARGET: >=90%]
  Top-3 Accuracy: 100.0% (10/10)
  Evidence Found: 100.0%
  Status: PASS

--- OVERALL (50 queries) ---
  Top-1 Accuracy: 98.0% (49/50)
  Top-3 Accuracy: 100.0% (50/50) [TARGET: >=98%]
  Evidence Found: 100.0%
  Status: PASS

--- SAFE TARGETS STATUS ---
  Tune Top-1 >= 99%:     PASS
  Holdout Top-1 >= 90%:  PASS
  Overall Top-3 >= 98%:  PASS

  ALL TARGETS MET: YES
```

---

**Report Generated**: 2026-02-14 14:46:37 UTC  
**Validation Engineer**: GitHub Copilot (Claude Sonnet 4.5)  
**Session Type**: Autonomous, Evidence-Based  
**Validation Status**: ✅ PASSED - GO FOR V2 CORPUS VALIDATION
