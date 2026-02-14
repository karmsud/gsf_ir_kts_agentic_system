# V2 Corpus Validation Report - BLOCKED
**Date**: 2026-02-14  
**Session**: V2 CORPUS VALIDATION (VALIDATION-ONLY MODE)  
**Status**: ⚠️ BLOCKED - Query Format Incompatibility  
**Validation ID**: 20260214_150000

---

## EXECUTIVE SUMMARY

❌ **DECISION: NO-GO (BLOCKED)**

V2 corpus validation blocked by query format incompatibility between `golden_queries_v2.json` and the v1 `score_queries.py` scorer. Ingestion and retrieval components work correctly (31/44 docs ingested, all queries return chunks), but accuracy cannot be measured due to schema mismatch.

---

## VALIDATION RESULTS

### INGESTION: ⚠️ PARTIAL SUCCESS (71% coverage)

**Corpus Structure**:
```
Total files: 44
- Reference: 12 files
- Troubleshooting: 13 files
- User_Guides: 5 files
- SOPs: 3 files
- Release_Notes: 3 files
- Training: 2 files
- Incidents: 2 files
- Configs: 2 files
- Architecture: 1 file
```

**Ingestion Results**:
```json
{
  "ingested": 31,
  "count": 44,
  "coverage": "71%",
  "missing": 13
}
```

**Missing Files (Unsupported Formats)**:
1. **PNG Images (10 files)**: ui_01.png through ui_10.png - No image ingestion support
2. **Config Files (2 files)**: 
   - batchbridge_connector_defaults.yaml
   - opsflow_network.ini
3. **CSV File (1 file)**: incident_log_sample.csv

**KB Status**:
- Documents: 31
- Manifest files: 41
- Graph nodes: 33
- Graph edges: 24

**Ingestion Assessment**: ✅ Core ingestion works, format gap identified (PNG/YAML/INI/CSV not supported)

---

### RETRIEVAL: ✅ FUNCTIONAL

**Query Execution**:
- All 50 queries executed successfully
- Every query returned 5 chunks
- No retrieval errors

**Sample Results**:
```
V2-Q01: 5 chunks (Top: TROUBLESHOOT)
V2-Q02: 5 chunks (Top: TROUBLESHOOT)
V2-Q03: 5 chunks (Top: TROUBLESHOOT)
V2-Q04: 5 chunks (Top: TROUBLESHOOT)
V2-Q05: 5 chunks (Top: TROUBLESHOOT)
```

**Retrieval Assessment**: ✅ Ranking engine works, chunks returned

---

### SCORING: ❌ BLOCKED (0% accuracy due to format mismatch)

**Metrics (Invalid - Format Issue)**:
```
--- TUNE SET (40 queries) ---
  Top-1 Accuracy: 0.0% (0/40) [TARGET: >=99%]  ❌
  Top-3 Accuracy: 0.0% (0/40)
  Evidence Found: 0.0%

--- HOLDOUT SET (10 queries) ---
  Top-1 Accuracy: 0.0% (0/10) [TARGET: >=90%]  ❌
  Top-3 Accuracy: 0.0% (0/10)
  Evidence Found: 0.0%

--- OVERALL (50 queries) ---
  Top-1 Accuracy: 0.0% (0/50)
  Top-3 Accuracy: 0.0% (0/50) [TARGET: >=98%]  ❌
  Evidence Found: 0.0%
```

**⚠️ THESE METRICS ARE INVALID** - Caused by format incompatibility, not retrieval failure.

---

## ROOT CAUSE ANALYSIS

### BLOCKER: Query Pack Schema Mismatch

**V2 Query Format** (`golden_queries_v2.json`):
```json
{
  "query_id": "V2-Q01",
  "query_text": "OpsFlow shows ERR-RUN-204...",
  "expected_doc_types": [            ← V2 field name
    "TROUBLESHOOT",
    "SOP",
    "USER_GUIDE"
  ],
  "must_include_terms": [
    "ERR-RUN-204",
    "OOM"
  ],
  "expected_evidence_rules": {       ← V2 object
    "requires_citation": true,
    "must_include_terms_in_at_least_one_cited_chunk": true
  }
}
```

**V1 Scorer Expectation** (`score_queries.py`):
```python
expected_doc_types = golden_query.get("expected_doc_types_priority", [])  ← V1 field name
must_include_terms = golden_query.get("must_include_terms", [])
allow_any = golden_query.get("allow_any_result", False)  ← V1 boolean
```

**Mismatch**:
| Field | V2 Format | V1 Scorer Expects | Result |
|-------|-----------|-------------------|--------|
| Doc types | `expected_doc_types` | `expected_doc_types_priority` | **Empty array → all queries fail doc_type match** |
| Evidence rules | `expected_evidence_rules` (object) | `allow_any_result` (boolean) | **Missing → strict matching** |

**Impact**:
- Scorer reads `expected_doc_types_priority` from v2 queries → gets `None`
- Treats empty expected types as "no valid doc_types"
- All queries score 0% even though retrieval works

---

## ROOT CAUSE CATEGORY

❌ **Format Incompatibility** (query pack schema mismatch)  
✅ NOT a retrieval/ranking regression  
✅ NOT an ingestion regression (except known format gaps)  
✅ NOT a chunking issue

---

## REQUIRED ACTIONS

### Option 1: Adapt Scorer to Handle V2 Format ⭐ RECOMMENDED

**File**: `tests/score_queries.py`

**Changes Needed**:
```python
# Line ~54: Add fallback for v2 format
expected_doc_types = (
    golden_query.get("expected_doc_types_priority", []) or  # v1 format
    golden_query.get("expected_doc_types", [])              # v2 format
)

# Line ~57: Handle v2 evidence rules
evidence_rules = golden_query.get("expected_evidence_rules", {})
allow_any = golden_query.get("allow_any_result", False) or not evidence_rules.get("requires_citation", True)
```

**Effort**: ~10 lines, low risk

**Command to Test Fix**:
```powershell
$env:PYTHONPATH = "$PWD"
.venv\Scripts\python.exe tests\score_queries.py tests\golden_queries_v2.json tests\accuracy_tuning_output_v2\search_results.json
```

---

### Option 2: Convert V2 Queries to V1 Format

**Script Needed**: `scripts/convert_v2_to_v1_queries.py`

**Transformation**:
```python
{
    "expected_doc_types_priority": v2["expected_doc_types"],
    "allow_any_result": not v2["expected_evidence_rules"]["requires_citation"],
    # ... other fields unchanged
}
```

**Effort**: ~30 lines, moderate risk (data transformation errors)

---

### Option 3: Use V2-Specific Scorer

**Check if exists**:
```powershell
Get-ChildItem tests -Filter "*score*v2*.py"
```

**If not exists**: Create new scorer (high effort, not recommended for validation-only mode)

---

## INGESTION GAP ANALYSIS

### Missing Format Support

| Format | Files | Category | Impact | Priority |
|--------|-------|----------|--------|----------|
| **PNG** | 10 | Screenshots/UI | ⚠️ HIGH - Visual troubleshooting guides need images | P0 |
| **YAML** | 1 | Config | ⚠️ MEDIUM - Default configs for tools | P1 |
| **INI** | 1 | Config | ⚠️ MEDIUM - Network settings | P1 |
| **CSV** | 1 | Logs | ⚠️ MEDIUM - Incident data | P2 |

**Total Gap**: 13/44 files (29% missing)

**Recommendation**: Implement PNG extraction (vision agent exists but needs integration with ingestion)

---

## RETRIEVAL SMOKE TEST RESULTS

✅ **All queries returned chunks** (5 per query)  
✅ **Doc types look reasonable** (TROUBLESHOOT, SOP, USER_GUIDE, etc.)  
✅ **No retrieval errors**

**Cannot assess ranking quality** due to scorer blocker, but preliminary signs are positive.

---

## GO/NO-GO ASSESSMENT

### PASS CRITERIA (From User)

| Criterion | Status | Notes |
|-----------|--------|-------|
| Holdout Top-1 ≥ 90% | ❌ BLOCKED | Cannot measure due to format issue |
| Overall Top-3 ≥ 98% | ❌ BLOCKED | Cannot measure due to format issue |
| Citations 100% | ❌ BLOCKED | Cannot measure due to format issue |
| No ingestion regressions | ⚠️ PARTIAL | Format gap (PNG/YAML/INI/CSV) but core works |

### DECISION: [NO-GO] ⚠️

**Blockers**:
1. **Critical**: Query format incompatibility prevents accuracy measurement
2. **Medium**: 29% corpus not ingested (PNG/config/CSV formats unsupported)

**Positive Signals**:
- ✅ Ingestion pipeline works (31/44 docs)
- ✅ Retrieval engine functional (all queries return chunks)
- ✅ JSON ingestion from v1 works (error_code_catalog_v2.json ingested as REFERENCE)

**Recommendation**: Fix scorer format compatibility (Option 1), then re-run validation

---

## NEXT STEPS

### Immediate (MUST DO):
1. **Adapt scorer** to handle v2 format (Option 1 above)
2. **Re-run scoring** without re-ingestion:
   ```powershell
   $env:PYTHONPATH = "$PWD"
   .venv\Scripts\python.exe tests\score_queries.py tests\golden_queries_v2.json tests\accuracy_tuning_output_v2\search_results.json
   ```
3. **Analyze true accuracy** with corrected scorer

### Short-term (SHOULD DO):
4. **Implement PNG ingestion** (vision agent + ingestion integration)
5. **Implement YAML/INI parsing** (config file support)
6. **Implement CSV parsing** (tabular data support)
7. **Re-ingest v2 corpus** with full format support

### Medium-term (CONSIDER):
8. **Standardize query format** (v1 vs v2 schema)
9. **Create format migration guide**
10. **Add schema validation** to prevent future mismatches

---

## EVIDENCE ARTIFACTS

**Logs Directory**: `scripts\logs\20260214_150000\`

**Files**:
1. `ingest_v2.log` - Full ingestion output (31 docs, format gaps identified)
2. `scoring_v2.log` - Query execution + scoring (all queries executed)
3. `accuracy_v2.log` - Accuracy report (0% due to format issue)
4. `v2_validation_blocked.log` - Blocked state summary

**Search Results**: `tests\accuracy_tuning_output_v2\search_results.json` (50 queries, 250 chunks)  
**Accuracy Scores**: `tests\accuracy_tuning_output_v2\accuracy_scores.json` (invalid metrics due to format)

---

## APPENDIX: CONSOLE OUTPUTS

### A. Corpus Extraction

```
=== V2 CORPUS VALIDATION - LOG DIR: scripts\logs\20260214_150000 ===

[✓] Extracted corpus to: .\kts_synthetic_corpus_v2\
[✓] Extracted query pack to: .\tests\
Corpus file count: 44
[✓] golden_queries_v2.json found

Total files in v2 corpus: 44
  Architecture: 1 files
  Configs: 2 files
  Incidents: 2 files
  Reference: 12 files
  Release_Notes: 3 files
  SOPs: 3 files
  Training: 2 files
  Troubleshooting: 13 files
  User_Guides: 5 files
```

### B. Ingestion Results

```json
{
  "ingested": [
    {
      "doc_id": "doc_5608557",
      "path": "kts_synthetic_corpus_v2\\Reference\\error_code_catalog_v2.json",
      "chunk_count": 2,
      "doc_type": "REFERENCE"
    },
    ...30 more docs
  ],
  "count": 31
}
```

**KB Status**:
```json
{
  "documents": 31,
  "manifest_files": 41,
  "graph_nodes": 33,
  "graph_edges": 24
}
```

### C. Query Execution

```
=== EXECUTING V2 GOLDEN QUERIES ===

  [1/50] V2-Q01: OpsFlow shows ERR-RUN-204. What does it mean and what's the ...
  [2/50] V2-Q02: How do I troubleshoot OpsFlow ERR-AUTH-407 during SSO redire...
  ...
  [50/50] V2-Q50: Summarize the SecureVault training deck: key slides and take...

[✓] Results saved to tests\accuracy_tuning_output_v2\search_results.json
```

### D. Scoring Output (Invalid Metrics)

```
=== SCORING V2 QUERIES (RETRY) ===

================================================================================
QUERY ACCURACY SCORING REPORT
================================================================================

--- TUNE SET (40 queries) ---
  Top-1 Accuracy: 0.0% (0/40) [TARGET: >=99%]
  Top-3 Accuracy: 0.0% (0/40)
  Evidence Found: 0.0%
  Status: FAIL

--- HOLDOUT SET (10 queries) ---
  Top-1 Accuracy: 0.0% (0/10) [TARGET: >=90%]
  Top-3 Accuracy: 0.0% (0/10)
  Evidence Found: 0.0%
  Status: FAIL

--- OVERALL (50 queries) ---
  Top-1 Accuracy: 0.0% (0/50)
  Top-3 Accuracy: 0.0% (0/50) [TARGET: >=98%]
  Evidence Found: 0.0%
  Status: FAIL

  ALL TARGETS MET: NO
```

### E. Root Cause Investigation

```
=== INVESTIGATING 0% ACCURACY ===

Total queries in results: 50
Queries with zero chunks: 0

Sample query results (first 5):
  V2-Q01: 5 chunks
    Top doc_type: TROUBLESHOOT
  V2-Q02: 5 chunks
    Top doc_type: TROUBLESHOOT
  V2-Q03: 5 chunks
    Top doc_type: TROUBLESHOOT
```

**Conclusion**: Retrieval works, scoring blocked by format mismatch

---

**Report Generated**: 2026-02-14 15:00:00 UTC  
**Validation Engineer**: GitHub Copilot (Claude Sonnet 4.5)  
**Session Type**: Validation-Only (No Code Changes)  
**Validation Status**: ⚠️ BLOCKED - Scorer Format Compatibility Required
