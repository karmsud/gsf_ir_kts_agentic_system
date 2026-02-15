# EVIDENCE GAP CLOSURE REPORT - PHASE A (TAXONOMY FIX)

**Date**: 2026-02-14  
**Phase**: A - Taxonomy Filename Pattern Recognition  
**Objective**: Raise Evidence Found from 78% to ≥95% without changing retrieval ranking

---

## PHASE A RESULTS SUMMARY

### Metrics Comparison

| Metric | Before (Phase 7) | After (Phase A) | Change |  Status |
|--------|-----------------|----------------|--------|---------|
| **V2 Tune Top-1** | 100.0% | 100.0% | 0% | ✅ MAINTAINED |
| **V2 Holdout Top-1** | 100.0% | 100.0% | 0% | ✅ MAINTAINED |
| **V2 Overall Top-1** | 100.0% | 100.0% | 0% | ✅ MAINTAINED |
| **V2 Overall Top-3** | 100.0% | 100.0% | 0% | ✅ MAINTAINED |
| **V2 Evidence Found** | 78.0 % (39/50) | **80.0%** (40/50) | **+2%** | ⚠️ BELOW TARGET (95%) |
| **V1 Overall Top-1** | 98.0% | 98.0% | 0% | ✅ NO REGRESSION |
| **V1 Evidence Found** | 100.0% | 100.0% | 0% | ✅ NO REGRESSION |

### Changes Implemented

**File Modified**: [backend/agents/taxonomy_agent.py](backend/agents/taxonomy_agent.py)

Added filename prefix and contains pattern matching (lines 19-53):

```python
# PHASE 1: Filename prefix pattern matching (highest priority)
prefix_rules = {
    "ARCH_": "ARCHITECTURE",
    "POSTMORTEM_": "INCIDENT",
    "INC-": "INCIDENT",
    "REF_": "REFERENCE",
    "LEGACY_": "TROUBLESHOOT",
    "DEPRECATED_": "RELEASE_NOTE",
}

# PHASE 2: Filename contains pattern matching (medium priority)
contains_rules = {
    "glossary": "REFERENCE",
    "catalog": "REFERENCE",
    "_archived": "RELEASE_NOTE",
    "_old": "TROUBLESHOOT",
}

# Add ARCHIVED tag for LEGACY/DEPRECATED files
if prefix in ["LEGACY_", "DEPRECATED_"]:
    tags.append("ARCHIVED")
```

**Impact**:
- ✅ ARCH_Connector_Pipeline_Overview.md: TROUBLESHOOT → ARCHITECTURE
- ✅ POSTMORTEM_BatchBridge_RateLimit_INC-0021.md: SOP → INCIDENT
- ✅ Glossary.md: SOP → REFERENCE
- ✅ error_code_catalog_v2.json: SOP/TROUBLESHOOT → REFERENCE
- ✅ LEGACY_*_OLD.md: TROUBLESHOOT + ARCHIVED tag added

**KB Status**: 31/33 files ingested (91% coverage, missing 2 config files + 1 CSV)

---

## QUERY-LEVEL EVIDENCE IMPROVEMENTS

### Fixed Queries (Phase A)

| Query ID | Query Text | Before | After | Root Cause Fixed |
|----------|-----------|--------|-------|------------------|
| **V2-Q42** | "Which release notes are archived..." | ✗ FAIL | ✅ PASS | LEGACY doc now has ARCHIVED tag detected |

**Evidence Found Delta**: +1 query fixed = +2% improvement (39/50 → 40/50)

---

## REMAINING EVIDENCE FAILURES (10 queries, 20%)

### Category A: Missing Files (5 queries)

| Query ID | Expected Evidence | Root Cause | Can Fix? |
|----------|------------------|------------|----------|
| **V2-Q28** | `incident_log_sample.csv` | CSV file NOT INGESTED | ✅ Phase B (CSV converter) |
| **V2-Q30** | `pac_url`, `read_seconds` | opsflow_network.ini NOT INGESTED | ✅ Phase B (INI converter) |
| **V2-Q31** | `max_concurrency` | batchbridge_connector_defaults.yaml NOT INGESTED | ✅ Phase B (YAML converter) |
| **V2-Q32** | `base_seconds`, `max_seconds` | batchbridge_connector_defaults.yaml NOT INGESTED | ✅ Phase B (YAML converter) |
| **V2-Q43** | `incident_log_sample.csv` | CSV file NOT INGESTED | ✅ Phase B (CSV converter) |
| **V2-Q47** | `trust_store`, `system` | Config files (.yaml/.ini) NOT INGESTED | ✅ Phase B (YAML/INI converter) |

**Expected Impact of Phase B**: +5 queries  = +10% (80% → 90%)

### Category B: Retrieval Ranking Issues (4 queries)

**PROOF OF ISSUE**: Documents exist in KB with correct doc_types and contain required evidence, but are NOT being retrieved.

| Query ID | Query Text | Expected Doc | Expected Evidence | Top-1 Retrieved | Contains Evidence? |
|----------|-----------|-------------|-------------------|-----------------|-------------------|
| **V2-Q26** | "Which documents look archived..." | LEGACY_*_OLD.md (TROUBLESHOOT + ARCHIVED) | `ARCHIVED`, `DEPRECATED` | UserGuide_BatchBridge_QuickStart.md | ❌ NO (wrong doc) |
| **V2-Q27** | "Summarize incident INC-0021..." | POSTMORTEM_*_INC-0021.md (INCIDENT) | `INC-0021`, `ERR-RATE-429` | UserGuide_BatchBridge_QuickStart.md | ❌ NO (wrong doc) |
| **V2-Q34** | "Find where upload gateway..." | ARCH_Connector_Pipeline_Overview.md (ARCHITECTURE) | `Upload Gateway` | UserGuide_BatchBridge_QuickStart.md | ❌ NO (wrong doc) |
| **V2-Q36** | "In the training deck, what..." | Training_*_SecureVault.pptx (TRAINING) | `ERR-ACL-002`, `ERR-MFA-009` | UserGuide_SecureVault_QuickStart.md | ❌ NO (wrong doc) |

**Verification Evidence**:

```bash
# V2-Q27: POSTMORTEM document DOES contain evidence
File: POSTMORTEM_BatchBridge_RateLimit_INC-0021.md
Content: "# Postmortem: BatchBridge Rate Limiting Spike (INC-0021)
          Primary signal: HTTP 429 / ERR-RATE-429"
doc_type: INCIDENT ✅ (correctly classified)
Top-1 Retrieved: UserGuide_BatchBridge_QuickStart.md (USER_GUIDE) ❌ WRONG

# V2-Q34: ARCH document DOES exist and is correctly classified
File: ARCH_Connector_Pipeline_Overview.md
doc_type: ARCHITECTURE ✅ (correctly classified after Phase A)
Top-1 Retrieved: UserGuide_BatchBridge_QuickStart.md (USER_GUIDE) ❌ WRONG
```

**Root Cause**: USER_GUIDE QuickStart documents are over-ranking specialized docs (INCIDENT, ARCHITECTURE, TRAINING) due to:
1. Short, generic content (high vector similarity for common terms)
2. Multiple duplicates in KB (5 QuickStart guides for 5 products)
3. Intent detection not boosting specialty doc_types sufficiently

**Expected Impact of Ranking Fix**: +3-4 queries = +6-8% (80% → 86-88%)  
**Combined Phase B + Ranking Fix**: 90% + 6% = **~96% Evidence Found** (target ≥95%)

---

## ROOT CAUSE ANALYSIS - WHY IS EVIDENCE FOUND < 95%?

### PRIMARY: Missing File Support (50% of failures)
- **Issue**: 3 files (CSV, YAML, INI) not ingested - 9% of V2 corpus
- **Queries Affected**: 5/10 failures (V2-Q28, V2-Q30, V2-Q31, V2-Q32, V2-Q43, V2-Q47)
- **Solution**: Phase B - add CSV/YAML/INI converters
- **Effort**: Medium (3 new converter modules)
- **Risk**: Low (no ranking changes, generalizable)

### SECONDARY: Retrieval Ranking Weights (40% of failures)
- **Issue**: USER_GUIDE docs over-rank specialty docs (INCIDENT, ARCHITECTURE, TRAINING)
- **Queries Affected**: 4/10 failures (V2-Q26, V2-Q27, V2-Q34, V2-Q36)  
- **Solution**: Adjust doc_type ranking weights OR intent detection boosts
- **Effort**: Low (single file change)
- **Risk**: Medium (requires re-validation, might affect V1)

### TERTIARY: Query Pack Design (10% of failures)
- **Issue**: Some queries may have overly specific must_include_terms
- **Queries Affected**: Potentially V2-Q26 (asks for "ARCHIVED" but LEGACY doc may not have exact term in content)
- **Solution**: Relax must_include_terms or accept as query pack limitation
- **Effort**: Low (edit golden_queries_v2.json)
- **Risk**: None (test data only)

---

## RECOMMENDATIONS

### Option 1: PHASE B ONLY (Recommended if user wants NO ranking changes)

**Approach**: Add CSV/YAML/INI converter support

**Expected Outcome**:
- Evidence Found: 80% → **90%** (+10%)
- Accuracy: 100% maintained
- V1 Regression: None (no ranking changes)
- **Falls SHORT of 95% target by 5%**

**Effort**: 2-3 hours (3 new converter modules)

### Option 2: PHASE B + MINIMAL RANKING ADJUSTMENT (Recommended for ≥95% target)

**Approach**:  
1. Implement Phase B (CSV/YAML/INI converters) → 90%
2. Add intent detection boost for specialty queries:
   - "incident" / "postmortem" → boost INCIDENT doc_type 1.5x
   - "architecture" / "overview" → boost ARCHITECTURE doc_type 1.5x
   - "training deck" / "slides" → boost TRAINING doc_type 1.5x

**Expected Outcome**:
- Evidence Found: 80% → **96%** (+16%)
- Accuracy: 100% maintained (or validated)
- V1 Regression: Low risk (intent terms don't overlap V1 corpus)
- **MEETS 95% target** ✅

**Effort**: 3-4 hours (Phase B + retrieval_service.py)

### Option 3: ACCEPT 80% AS REASONABLE BASELINE

**Rationale**:
- 80% with taxonomy fixes only
- Remaining 20% requires either:
  - Missing file converters (5 queries, +10%)
  - Ranking adjustments (4 queries, +8%)
- V2 corpus coverage already at 91% (31/33 files)
- Accuracy targets all met (100% Top-1, 100% Top-3)

**Outcome**: 
- Evidence Found: **80%** (current)
- No additional changes
- Safe for production use with disclaimer on CONFIG/CSV/TABLE queries

---

## PHASE A GIT DIFF

```diff
diff --git a/backend/agents/taxonomy_agent.py b/backend/agents/taxonomy_agent.py
index abc123..def456 100644
--- a/backend/agents/taxonomy_agent.py
+++ b/backend/agents/taxonomy_agent.py
@@ -17,6 +17,53 @@ class TaxonomyAgent(AgentBase):
     def execute(self, request: dict) -> AgentResult:
         filename = (request.get("filename") or "").lower()
         text = (request.get("text") or "").lower()
+        best_label = "UNKNOWN"
+        best_score = 0.0
+        tags: list[str] = []
+        matched_rules: list[str] = []
+
+        # PHASE 1: Filename prefix pattern matching (highest priority)
+        filename_stem = Path(filename).stem if filename else ""
+        prefix_rules = {
+            "ARCH_": "ARCHITECTURE",
+            "POSTMORTEM_": "INCIDENT",
+            "INC-": "INCIDENT",
+            "REF_": "REFERENCE",
+            "LEGACY_": "TROUBLESHOOT",
+            "DEPRECATED_": "RELEASE_NOTE",
+        }
+        
+        for prefix, label in prefix_rules.items():
+            if filename_stem.upper().startswith(prefix):
+                best_label = label
+                best_score = 1.0  # High confidence for prefix match
+                matched_rules.append(f"filename_prefix:{label}:{prefix}")
+                
+                # Add ARCHIVED tag for LEGACY/DEPRECATED
+                if prefix in ["LEGACY_", "DEPRECATED_"]:
+                    tags.append("ARCHIVED")
+                break
+        
+        # PHASE 2: Filename contains pattern matching (medium priority)
+        if best_score < 1.0:
+            contains_rules = {
+                "glossary": "REFERENCE",
+                "catalog": "REFERENCE",
+                "_archived": "RELEASE_NOTE",
+                "_old": "TROUBLESHOOT",
+            }
+            
+            for pattern, label in contains_rules.items():
+                if pattern in filename_stem:
+                    best_label = label
+                    best_score = 0.8  # Medium confidence for contains match
+                    matched_rules.append(f"filename_contains:{label}:{pattern}")
+                    
+                    if pattern in ["_archived", "_old"]:
+                        tags.append("ARCHIVED")
+                    break
+
+        # PHASE 3: Content-based keyword matching (original logic, lower priority)
         ...existing content keyword logic...
```

---

## DECISION POINTS FOR USER

1. **Accept 80% Evidence Found?** If YES → No further action, mark complete
2. **Proceed with Phase B (CSV/YAML/INI)?** If YES → Expect 90% (+10%)
3. **Allow minimal ranking adjustments for specialty doc_types?** If YES → Expect 96% (+16%, meets target)

**Recommendation**: Proceed with Option 2 (Phase B + Minimal Ranking) to meet 95% target with minimal risk.

---

**END OF REPORT**
