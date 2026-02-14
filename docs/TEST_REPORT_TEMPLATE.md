# GSF IR KTS — Test Execution Report

**Test Date**: ________________  
**Test Lead**: ________________  
**Test Environment**: Local / Staging / Production  
**Corpus Used**: C:\Users\Karmsud\Projects\gsf_ir_kts_agentic_system\kts_test_corpus  
**Test Suite Version**: 1.0  
**Backend Commit**: ________________  
**Extension Version**: ________________

---

## Executive Summary

**Overall Status**: ⬜ PASS / ⬜ FAIL / ⬜ CONDITIONAL PASS  
**Pass Rate**: _____% (_____ passed out of _____ total tests)  
**Critical Issues**: _____ (blocking issues that must be resolved before go-live)  
**Major Issues**: _____ (non-blocking but require attention)  
**Minor Issues**: _____ (cosmetic or low-priority)

**Recommendation**:  
⬜ **GO**: System ready for production  
⬜ **NO-GO**: Critical issues must be resolved  
⬜ **CONDITIONAL GO**: Proceed with documented limitations/workarounds

---

## Test Summary by Stage

| Stage | Test Count | Passed | Failed | Warnings | Status | Notes |
|-------|-----------|--------|--------|----------|--------|-------|
| Crawl | | | | | ⬜ PASS / ⬜ FAIL | |
| Ingest | | | | | ⬜ PASS / ⬜ FAIL | |
| Status Check | | | | | ⬜ PASS / ⬜ FAIL | |
| Vision Workflow | | | | | ⬜ PASS / ⬜ FAIL | |
| Retrieval Queries | | | | | ⬜ PASS / ⬜ FAIL | |
| Idempotency | | | | | ⬜ PASS / ⬜ FAIL | |
| **TOTAL** | | | | | | |

---

## Agent-Level Coverage

| Agent | Unit Tests | Integration Tests | CLI Tests | Scenario Tests | Status | Issues Found |
|-------|-----------|-------------------|-----------|----------------|--------|--------------|
| 1. Crawler | ___/10 | ___/3 | ✓/✗ | ✓/✗ | ⬜ PASS / ⬜ FAIL | |
| 2. Ingestion | ___/15 | ___/10 | ✓/✗ | ✓/✗ | ⬜ PASS / ⬜ FAIL | |
| 3. Vision | ___/10 | ___/10 | ✓/✗ | ✓/✗ | ⬜ PASS / ⬜ FAIL | |
| 4. Taxonomy | ___/10 | ___/10 | N/A | ✓/✗ | ⬜ PASS / ⬜ FAIL | |
| 5. Version | ___/10 | ___/10 | N/A | ✓/✗ | ⬜ PASS / ⬜ FAIL | |
| 6. Graph Builder | ___/10 | ___/10 | N/A | ✓/✗ | ⬜ PASS / ⬜ FAIL | |
| 7. Retrieval Service | ___/10 | ___/10 | ✓/✗ | ✓/✗ | ⬜ PASS / ⬜ FAIL | |
| 8. Training Path | ___/10 | ___/10 | ✓/✗ | ✓/✗ | ⬜ PASS / ⬜ FAIL | |
| 9. Change Impact | ___/10 | ___/10 | ✓/✗ | ✓/✗ | ⬜ PASS / ⬜ FAIL | |
| 10. Freshness | ___/10 | ___/10 | ✓/✗ | ✓/✗ | ⬜ PASS / ⬜ FAIL | |

---

## Top 50 Queries Results

### Query Performance Summary

| Category | Total Queries | Passed | Failed | Avg Confidence | Citation Issues | Escalation Issues |
|----------|---------------|--------|--------|----------------|-----------------|-------------------|
| Error Code Queries | 10 | | | | | |
| How-To Queries | 10 | | | | | |
| Release Note Queries | 5 | | | | | |
| Training Path Queries | 10 | | | | | |
| Impact Queries | 10 | | | | | |
| Freshness Queries | 5 | | | | | |
| **TOTALS** | **50** | | | | | |

### Citation Quality Scorecard

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| All results have citations | 100% | _____% | ⬜ PASS / ⬜ FAIL |
| Citations have file:// URIs | 100% | _____% | ⬜ PASS / ⬜ FAIL |
| Citations have doc_id | 100% | _____% | ⬜ PASS / ⬜ FAIL |
| Citations have version | 100% | _____% | ⬜ PASS / ⬜ FAIL |
| URIs point to existing files | 100% | _____% | ⬜ PASS / ⬜ FAIL |
| Section/page refs accurate (±1) | 90% | _____% | ⬜ PASS / ⬜ FAIL |
| Freshness badges correct | 100% | _____% | ⬜ PASS / ⬜ FAIL |

### Confidence Threshold Compliance

| Confidence Level | Count | Escalation Rate | Status |
|------------------|-------|-----------------|--------|
| HIGH (>0.7) | _____ | _____ escalations (should be 0) | ⬜ PASS / ⬜ FAIL |
| MEDIUM (0.5-0.7) | _____ | _____ escalations (optional) | ⬜ PASS / ⬜ FAIL |
| LOW (<0.5) | _____ | _____ escalations (should be 100%) | ⬜ PASS / ⬜ FAIL |

### Sample Failed Queries (if any)

**Query ID**: Q___  
**Query Text**: "_______________________________________________"  
**Expected**: _________________________________________________  
**Actual**: ___________________________________________________  
**Failure Reason**: ⬜ No citations / ⬜ Wrong doc cited / ⬜ Low confidence / ⬜ No escalation / ⬜ Other: _______

*(Repeat for each failed query)*

---

## Multi-Modal Pipeline Validation

### Image Extraction Results

| Source Type | Expected Count | Extracted Count | Status | Notes |
|-------------|----------------|-----------------|--------|-------|
| Standalone images (Reference/images/) | 4 | _____ | ⬜ PASS / ⬜ FAIL | |
| DOCX embedded images | _____ | _____ | ⬜ PASS / ⬜ FAIL / ⬜ N/A | |
| PDF embedded images | _____ | _____ | ⬜ PASS / ⬜ FAIL / ⬜ N/A | |
| PPTX embedded images | _____ | _____ | ⬜ PASS / ⬜ FAIL / ⬜ N/A | |
| Markdown image refs | _____ | _____ | ⬜ PASS / ⬜ FAIL / ⬜ N/A | |
| **TOTAL** | | | | |

### Vision Workflow Validation

**describe pending output**:
```
Pending count: _____
Expected: ≥4 (from Reference/images/)
Status: ⬜ PASS / ⬜ FAIL
```

**Sample description completion** (if pending > 0):
- Selected image: _____________________________
- Description provided: _______________________
- Indexing status: ⬜ Success / ⬜ Failed
- Retrieval test: ⬜ Searchable / ⬜ Not found

**Image notes in retrieval**:
- Query tested: "___________________________________"
- Result included image_note: ⬜ YES / ⬜ NO
- Image note text: "______________________________"
- Image reference accurate: ⬜ YES / ⬜ NO / ⬜ N/A

---

## Idempotency Validation

### Re-Crawl Test

**First crawl**:
- New files: _____
- Modified files: _____
- Deleted files: _____
- Unchanged files: _____

**Second crawl (same directory)**:
- New files: _____ (should be 0)
- Modified files: _____ (should be 0)
- Unchanged files: _____ (should match first crawl total)
- **Status**: ⬜ PASS (no duplicates) / ⬜ FAIL (duplicates found)

### Re-Ingest Test

**Status before re-ingest**:
- Document count: _____
- Graph node count: _____
- Vector chunk count: _____

**Status after re-ingest --force**:
- Document count: _____ (should be same)
- Graph node count: _____ (should be same)
- Vector chunk count: _____ (should be same)
- **Status**: ⬜ PASS (counts stable) / ⬜ FAIL (counts changed)

---

## Defect Log

### Critical Defects (P0 - Blocking)

**Defect ID**: DEF-001  
**Title**: _______________________________________________________________  
**Component**: ⬜ Crawler / ⬜ Ingestion / ⬜ Vision / ⬜ Taxonomy / ⬜ Version / ⬜ Graph / ⬜ Retrieval / ⬜ Training / ⬜ Impact / ⬜ Freshness  
**Description**: _________________________________________________________  
**Reproduction Steps**:  
1. ___________________________________________________________________  
2. ___________________________________________________________________  
3. ___________________________________________________________________  
**Expected**: ____________________________________________________________  
**Actual**: ______________________________________________________________  
**Impact**: Can't proceed with testing / Results unreliable / Data corruption / Other: _______  
**Status**: ⬜ Open / ⬜ In Progress / ⬜ Resolved / ⬜ Deferred  
**Assigned To**: _________________________________________________________

*(Repeat for each critical defect)*

### Major Defects (P1 - High Impact)

**Defect ID**: DEF-___  
**Title**: _______________________________________________________________  
*(Same structure as Critical)*

### Minor Defects (P2 - Low Impact)

**Defect ID**: DEF-___  
**Title**: _______________________________________________________________  
*(Same structure as Critical)*

---

## Exit Criteria Evaluation

| Criterion | Target | Actual | Met? | Notes |
|-----------|--------|--------|------|-------|
| All 46 existing backend tests pass | 46/46 | _____/46 | ⬜ YES / ⬜ NO | |
| All 10 existing extension tests pass | 10/10 | _____/10 | ⬜ YES / ⬜ NO | |
| Full corpus smoke test passes | GREEN | ⬜ GREEN / ⬜ RED | ⬜ YES / ⬜ NO | |
| Top 50 queries achieve >80% correct | >80% | _____% | ⬜ YES / ⬜ NO | |
| Zero hallucinations | 0 | _____ | ⬜ YES / ⬜ NO | Define: Results without citations = hallucination |
| Idempotency validated | STABLE | ⬜ STABLE / ⬜ UNSTABLE | ⬜ YES / ⬜ NO | Re-run produces identical results |
| Multi-modal pipeline functional | END-TO-END | ⬜ WORKING / ⬜ PARTIAL / ⬜ BROKEN | ⬜ YES / ⬜ NO | Vision workflow pending → described → searchable |
| All CLI commands return valid JSON | 100% | _____% | ⬜ YES / ⬜ NO | |
| Extension commands execute without errors | 100% | _____% | ⬜ YES / ⬜ NO | |
| Chat participant returns structured markdown | YES | ⬜ YES / ⬜ NO | ⬜ YES / ⬜ NO | With citations and formatting |

**Overall Exit Criteria Status**: ⬜ ALL MET / ⬜ SOME NOT MET  
**Gate Decision**: ⬜ APPROVE GO-LIVE / ⬜ DEFER GO-LIVE

---

## Observations & Recommendations

### What Went Well
- ___________________________________________________________________
- ___________________________________________________________________
- ___________________________________________________________________

### What Needs Improvement
- ___________________________________________________________________
- ___________________________________________________________________
- ___________________________________________________________________

### Risks & Mitigation
| Risk | Likelihood | Impact | Mitigation Plan |
|------|-----------|--------|-----------------|
| _____ | ⬜ High / ⬜ Med / ⬜ Low | ⬜ High / ⬜ Med / ⬜ Low | ________________ |
| _____ | ⬜ High / ⬜ Med / ⬜ Low | ⬜ High / ⬜ Med / ⬜ Low | ________________ |

### Known Limitations (Document for Users)
- ___________________________________________________________________
- ___________________________________________________________________
- ___________________________________________________________________

### Recommendations for Next Iteration
1. ___________________________________________________________________
2. ___________________________________________________________________
3. ___________________________________________________________________

---

## Approvals

**Test Lead**: ________________________________ Date: __________  
Signature: ____________________________________

**Engineering Lead**: ________________________________ Date: __________  
Signature: ____________________________________

**QA Manager**: ________________________________ Date: __________  
Signature: ____________________________________

**Business Owner**: ________________________________ Date: __________  
Signature: ____________________________________

---

## Appendices

### A. Test Execution Logs
- Crawl log: `scripts/logs/crawl_YYYYMMDD_HHMMSS.json`
- Ingest log: `scripts/logs/ingest_YYYYMMDD_HHMMSS.json`
- Status log: `scripts/logs/status_YYYYMMDD_HHMMSS.json`
- Query logs: `scripts/logs/query_*_YYYYMMDD_HHMMSS.json`
- Summary log: `scripts/logs/test_suite_summary_YYYYMMDD_HHMMSS.json`

### B. Environment Details
- OS: Windows _____
- Python version: _____
- VS Code version: _____
- Extension version: _____
- Knowledge base path: _____
- Corpus size: _____ files, _____ MB

### C. Test Data Catalog
- [Corpus file list]
- [Doc types distribution]
- [Tool/entity coverage]

---

**Report Version**: 1.0  
**Template Last Updated**: 2026-02-14
