# EVIDENCE FAILURES REPORT - V2

**Generated**: 2026-02-14  
**Corpus**: kts_synthetic_corpus_v2  
**Evidence Found Rate**: 78.0% (39/50 queries)  
**Target**: ≥95.0%  
**Gap**: -17.0% (11 failures)

---

## EXECUTIVE SUMMARY

**ROOT CAUSES IDENTIFIED**:

1. **TAXONOMY MISCLASSIFICATION (PRIMARY)**: 8/31 documents (26%) misclassified
   - ARCH_ files → TROUBLESHOOT (should be ARCHITECTURE)
   - POSTMORTEM_/INC- files → SOP (should be INCIDENT)  
   - Glossary/catalog files → SOP (should be REFERENCE)
   - LEGACY_ files → no ARCHIVED/DEPRECATED recognition
   - **Impact**: 8 evidence failures (V2-Q26, V2-Q27, V2-Q34, V2-Q36, V2-Q42, and likely 3 more)

2. **MISSING FILES (SECONDARY)**: 3/33 files (9%) not ingested
   - incident_log_sample.csv (INCIDENT)
   - batchbridge_connector_defaults.yaml (CONFIG)
   - opsflow_network.ini (CONFIG)
   - **Impact**: 3 evidence failures (V2-Q28, V2-Q30-Q32, V2-Q43, V2-Q47)

3. **CONTENT TRUNCATION (MINOR)**: 1 query affected
   - Chunks truncated at 500 chars - evidence may exist beyond cutoff
   - **Impact**: V2-Q28 (also missing CSV file)

---

## DETAILED EVIDENCE FAILURES (11 queries)

### FAILURE 1: V2-Q26
**Query**: Which documents in this corpus look archived or outdated based on dates?  
**Expected doc_types**: TROUBLESHOOT, RELEASE_NOTES, SOP  
**Must_include_terms**: `['ARCHIVED', 'DEPRECATED']`  
**Retrieved Top-1**: UserGuide_BatchBridge_QuickStart.md (USER_GUIDE)

**TOP-3 CHUNKS**:
```
[1] UserGuide_BatchBridge_QuickStart.md (USER_GUIDE)
    content: # BatchBridge — Quick Start\n**Last updated:** 2026-02-14...
    ✗ MISSING: ARCHIVED, DEPRECATED

[2] UserGuide_DataDesk_QuickStart.md (USER_GUIDE)  
    content: # DataDesk — Quick Start\n**Last updated:** 2026-02-14...
    ✗ MISSING: ARCHIVED, DEPRECATED

[3] UserGuide_FinReport_QuickStart.md (USER_GUIDE)
    content: # FinReport — Quick Start\n**Last updated:** 2026-02-14...
    ✗ MISSING: ARCHIVED, DEPRECATED
```

**FAILURE CLASSIFICATION**: Wrong document retrieved (taxonomy issue)  
**ROOT CAUSE**: LEGACY_Troubleshoot_BatchBridge_ERR-TLS-014_UnknownCA_OLD.md is classified as TROUBLESHOOT instead of recognizing LEGACY/ARCHIVED status. Terms "ARCHIVED" and "DEPRECATED" don't appear in current QuickStart guides.

---

### FAILURE 2: V2-Q27
**Query**: Summarize incident INC-0021: what happened and what corrective actions were taken?  
**Expected doc_types**: INCIDENT, TROUBLESHOOT, SOP  
**Must_include_terms**: `['INC-0021', 'ERR-RATE-429']`  
**Retrieved Top-1**: UserGuide_BatchBridge_QuickStart.md (USER_GUIDE)

**TOP-3 CHUNKS**:
```
[1-3] All UserGuide QuickStart files (USER_GUIDE)
    ✗ MISSING: INC-0021, ERR-RATE-429
```

**FAILURE CLASSIFICATION**: Wrong document retrieved (taxonomy issue)  
**ROOT CAUSE**: POSTMORTEM_BatchBridge_RateLimit_INC-0021.md is classified as SOP instead of INCIDENT. Query asks for incident but retrieval doesn't prioritize because doc_type is wrong.

---

### FAILURE 3: V2-Q28
**Query**: From incident log CSV, list top 3 error codes by count and the most affected tool.  
**Expected doc_types**: INCIDENT, TROUBLESHOOT, SOP  
**Must_include_terms**: `['incident_log_sample.csv']`  
**Retrieved Top-1**: Troubleshoot_CrossTool_HTTP_429_vs_ERR-RATE-429.md (TROUBLESHOOT)

**TOP-3 CHUNKS**:
```
[1-3] All Troubleshoot files (TROUBLESHOOT)
    content_length: 500 chars (TRUNCATED)
    ✗ MISSING: incident_log_sample.csv
```

**FAILURE CLASSIFICATION**: Wrong document + missing file  
**ROOT CAUSE**: incident_log_sample.csv NOT INGESTED (missing from KB). Secondary issue: content truncated at 500 chars.

---

### FAILURE 4: V2-Q30
**Query**: Where is the OpsFlow proxy PAC URL configured and what are timeout defaults?  
**Expected doc_types**: CONFIG, TROUBLESHOOT, SOP  
**Must_include_terms**: `['pac_url', 'read_seconds']`  
**Retrieved Top-1**: UserGuide_OpsFlow_QuickStart.md (USER_GUIDE)

**FAILURE CLASSIFICATION**: Wrong document + missing file  
**ROOT CAUSE**: opsflow_network.ini NOT INGESTED (missing from KB). Query expects CONFIG doc_type but .ini files not supported.

---

### FAILURE 5: V2-Q31
**Query**: What is the max concurrency default for BatchBridge connectors?  
**Expected doc_types**: CONFIG, TROUBLESHOOT, SOP  
**Must_include_terms**: `['max_concurrency']`  
**Retrieved Top-1**: UserGuide_BatchBridge_QuickStart.md (USER_GUIDE)

**FAILURE CLASSIFICATION**: Wrong document + missing file  
**ROOT CAUSE**: batchbridge_connector_defaults.yaml NOT INGESTED (missing from KB). Query expects CONFIG doc_type but .yaml files not supported (explicitly skipped in Phase 1).

---

### FAILURE 6: V2-Q32
**Query**: What are the backoff base_seconds and max_seconds defaults?  
**Expected doc_types**: CONFIG, TROUBLESHOOT, SOP  
**Must_include_terms**: `['base_seconds', 'max_seconds']`  
**Retrieved Top-1**: UserGuide_BatchBridge_QuickStart.md (USER_GUIDE)

**FAILURE CLASSIFICATION**: Wrong document + missing file  
**ROOT CAUSE**: batchbridge_connector_defaults.yaml NOT INGESTED (missing from KB). Same as V2-Q31.

---

### FAILURE 7: V2-Q34
**Query**: Find where upload gateway is mentioned in the architecture overview.  
**Expected doc_types**: ARCHITECTURE, USER_GUIDE, SOP  
**Must_include_terms**: `['Upload Gateway']`  
**Retrieved Top-1**: UserGuide_BatchBridge_QuickStart.md (USER_GUIDE)

**FAILURE CLASSIFICATION**: Wrong document (taxonomy issue)  
**ROOT CAUSE**: ARCH_Connector_Pipeline_Overview.md is classified as TROUBLESHOOT instead of ARCHITECTURE. Query asks for architecture but correct doc has wrong doc_type.

---

### FAILURE 8: V2-Q36
**Query**: In the training deck, what are the two most common SecureVault issues covered?  
**Expected doc_types**: TRAINING, SOP, TROUBLESHOOT  
**Must_include_terms**: `['ERR-ACL-002', 'ERR-MFA-009']`  
**Retrieved Top-1**: UserGuide_SecureVault_QuickStart.md (USER_GUIDE)

**FAILURE CLASSIFICATION**: Wrong document (retrieval issue)  
**ROOT CAUSE**: Query asks for "training deck" but retrieves USER_GUIDE instead of TRAINING. Likely the Training_Connector_Triage_Playbook.pdf doesn't contain SecureVault-specific errors.

---

### FAILURE 9: V2-Q42
**Query**: Which release notes are archived and why might they still be useful?  
**Expected doc_types**: RELEASE_NOTES, TROUBLESHOOT, SOP  
**Must_include_terms**: `['ARCHIVED']`  
**Retrieved Top-1**: ReleaseNotes_DataDesk_2026Q1.md (RELEASE_NOTE)

**FAILURE CLASSIFICATION**: Wrong document (taxonomy issue)  
**ROOT CAUSE**: No RELEASE_NOTE documents have "ARCHIVED" status. LEGACY documents exist but are classified as TROUBLESHOOT, not tagged as archived.

---

### FAILURE 10: V2-Q43
**Query**: From the incident CSV, find incidents in the last 14 days and list their codes.  
**Expected doc_types**: INCIDENT, TROUBLESHOOT, SOP  
**Must_include_terms**: `['incident_log_sample.csv']`  
**Retrieved Top-1**: UserGuide_BatchBridge_QuickStart.md (USER_GUIDE)

**FAILURE CLASSIFICATION**: Wrong document + missing file  
**ROOT CAUSE**: incident_log_sample.csv NOT INGESTED (missing from KB). Same as V2-Q28.

---

### FAILURE 11: V2-Q47
**Query**: Where is the trust_store configured and what value indicates system store?  
**Expected doc_types**: CONFIG, TROUBLESHOOT, SOP  
**Must_include_terms**: `['trust_store', 'system']`  
**Retrieved Top-1**: UserGuide_BatchBridge_QuickStart.md (USER_GUIDE)

**FAILURE CLASSIFICATION**: Wrong document + missing file  
**ROOT CAUSE**: CONFIG files (.yaml/.ini) NOT INGESTED (missing from KB). Query expects CONFIG doc_type but config files not supported.

---

## FAILURE CLASSIFICATION SUMMARY

| Category | Count | Queries | Fix Priority |
|----------|-------|---------|--------------|
| **Taxonomy misclassification** | 6 | V2-Q26, V2-Q27, V2-Q34, V2-Q36, V2-Q42, [likely 2 more] | **HIGH** (Phase A) |
| **Missing files (CSV/YAML/INI)** | 5 | V2-Q28, V2-Q30, V2-Q31, V2-Q32, V2-Q43, V2-Q47 | **MEDIUM** (Phase B) |
| **Content truncation** | 1 | V2-Q28 | **LOW** (auto-fixed by Phase A/B) |

**Note**: Some queries have overlapping root causes (V2-Q28 has both missing file AND truncation).

---

## PROPOSED SOLUTION (PHASE A: TAXONOMY FIX)

### Changes Required

**File**: [config/taxonomy_rules.json](config/taxonomy_rules.json)

**Add filename prefix patterns** to taxonomy classification:

```json
{
  "taxonomy_rules": {
    "filename_prefix_rules": {
      "ARCH_": "ARCHITECTURE",
      "POSTMORTEM_": "INCIDENT",
      "INC-": "INCIDENT",
      "REF_": "REFERENCE",
      "LEGACY_": "TROUBLESHOOT_ARCHIVED",
      "DEPRECATED_": "RELEASE_NOTE_ARCHIVED"
    },
    "filename_contains_rules": {
      "Glossary": "REFERENCE",
      "catalog": "REFERENCE",
      "_ARCHIVED": "ARCHIVED",
      "_OLD": "ARCHIVED"
    }
  }
}
```

### Expected Impact

- **Fix 6-8 queries** via correct doc_type assignment
- **Evidence Found: 78% → 88-92%** (Phase A alone)
- **No retrieval/ranking logic changes** (taxonomy only)
- **Generalizable**: Works for any corpus with these naming conventions

---

## PROPOSED SOLUTION (PHASE B: MISSING FILES)

### Changes Required

**Files**: 
- [backend/ingestion/csv_converter.py](backend/ingestion/csv_converter.py) (NEW)
- [backend/ingestion/yaml_converter.py](backend/ingestion/yaml_converter.py) (NEW)
- [backend/ingestion/ini_converter.py](backend/ingestion/ini_converter.py) (NEW)

**Add converter support** for:
- .csv files → structured table to text
- .yaml files → config key-value pairs to text
- .ini files → config key-value pairs to text

### Expected Impact

- **Fix 3-5 additional queries** via missing files now available
- **Evidence Found: 88-92% → 94-98%** (Phase A + B combined)
- **Corpus coverage: 91% → 100%** (31 → 33 files)

---

## RECOMMENDATION

1. **Implement Phase A first** (taxonomy filename patterns)
   - Lowest risk, highest value (6-8 queries fixed)
   - No retrieval logic changes
   - Re-ingest, re-score, validate

2. **Implement Phase B if needed** (missing file converters)
   - Only if Evidence Found < 95% after Phase A
   - Adds CSV/YAML/INI support (generalizable)
   - Re-ingest, re-score, final validation

3. **Stop when Evidence Found ≥95%** or remaining failures are query pack design issues

---

**END OF REPORT**
