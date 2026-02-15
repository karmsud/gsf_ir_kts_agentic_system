# GSF IR KTS — Comprehensive Test Plan Summary

**Version:** 1.0  
**Date:** 2026-02-14  
**Status:** PLANNING COMPLETE - Ready for Execution  
**Test Lead:** [To be assigned]  
**Corpus:** C:\Users\Karmsud\Projects\gsf_ir_kts_agentic_system\kts_test_corpus

---

## Executive Overview

This document summarizes the complete, repeatable test plan for the GSF IR KTS agentic system. All planning artifacts have been created and are ready for execution.

### System Summary

**10 Agents (No Conductor)**:
1. **Crawler** - File discovery & change detection
2. **Ingestion** - Format conversion & metadata extraction
3. **Vision** - Image description lifecycle (human-in-loop)
4. **Taxonomy** - Document classification
5. **Version** - Change tracking & diffs
6. **Graph Builder** - Knowledge graph construction
7. **Retrieval Service** - Context retrieval (NOT answer generation)
8. **Training Path** - Learning sequence generation
9. **Change Impact** - Impact analysis for changes
10. **Freshness** - Staleness detection & auditing

**Key Architecture Principles**:
- Backend returns context + citations + metadata only
- GitHub Copilot generates final answers (not backend)
- Multi-modal via image extraction + human-in-loop description
- Citation-first: Every result includes file:// URIs
- Confidence thresholding: Low confidence triggers escalation

### Test Corpus Structure

**14 Files Across 5 Doc Types**:
- **Reference/** (6 files): 1 SOP (DOCX), 1 JSON error catalog, 4 PNG screenshots
- **Release_Notes/** (1 file): 1 release note (MD)
- **Training/** (2 files): 1 PDF training pack, 1 PPTX upload policy
- **Troubleshooting/** (4 files): 4 error-specific guides (MD)
- **User_Guides/** (1 file): 1 onboarding guide (MD)

**Tools Covered**: ToolX, ToolY, ToolZ  
**Error Codes Covered**: AUTH401, HTTP504, ERR-UPL-013, ERR-PWD-007

---

## Deliverables Produced

### ✅ A) TEST MASTER PLAN
**File**: [docs/TEST_MASTER_PLAN.md](TEST_MASTER_PLAN.md)

**Contents**:
- Test objectives, success criteria, non-goals
- 5 test layers: Unit, Integration, CLI, Scenario, UX Acceptance
- Pass/fail criteria (hallucination prevention, confidence thresholding, idempotency)
- Exit criteria (10 gates including >80% pass rate, zero hallucinations)
- Test data strategy with corpus coverage matrix
- Automation strategy (scripts, logs, CI/CD)
- Risk register with mitigation plans
- Roles & responsibilities matrix

**Key Metrics**:
- Target: 50-150 automated tests + 50 curated queries
- Exit gate: ≥80% pass rate, zero hallucinations
- 10 exit criteria must be met for production approval

---

### ✅ B) TRACEABILITY MATRIX
**File**: [docs/TEST_TRACEABILITY_MATRIX.md](TEST_TRACEABILITY_MATRIX.md)

**Contents**:
- Agent coverage matrix: All 10 agents mapped to unit/integration/CLI/scenario tests
- Feature coverage matrix: All major features mapped to test types and corpus files
- Top 50 queries mapped to expected doc types and validation methods
- Corpus file → test mapping (which tests use which files)
- Test automation coverage (scripts and validation layers)
- Exit criteria traceability (evidence location for each criterion)

**Coverage Summary**:
- 146 planned tests (46 existing backend + 10 existing extension + 90 new comprehensive)
- Every agent has 10+ test scenarios
- Every corpus file used in at least one test
- All exit criteria have validation tests

---

### ✅ C) TOP 50 USER QUERIES PACK
**Files**: 
- [docs/TEST_QUERIES_TOP_50.md](TEST_QUERIES_TOP_50.md) (human-readable)
- [docs/TEST_QUERIES_TOP_50.json](TEST_QUERIES_TOP_50.json) (machine-readable)

**Contents**:
- **10 Error Code Queries** (Q1-Q10): AUTH401, HTTP504, ERR-UPL-013, ERR-PWD-007 lookups
- **10 How-To Queries** (Q11-Q20): Onboarding, login, upload, configuration, unknown procedures
- **5 Release Note Queries** (Q21-Q25): Release features, version history, breaking changes
- **10 Training Path Queries** (Q26-Q35): Beginner paths, troubleshooting training, prerequisites
- **10 Impact Queries** (Q36-Q45): Tool changes, policy updates, UI redesigns, unknown entities
- **5 Freshness Queries** (Q46-Q50): Stale content audits, tool-specific freshness, STALE-rated docs

**Each Query Specifies**:
- Query text and intent (QUESTION/TRAINING/IMPACT/AUDIT)
- Expected doc types and specific doc IDs
- Expected confidence level (HIGH/MEDIUM/LOW)
- Expected failure mode (None/ESCALATION_LOW_CONFIDENCE/ESCALATION_MISSING_INFO)
- Validation criteria (citation fields, escalation requirements, doc type matching)

**Scoring Rubric**: 500 points total (10 per query), 90%+ = production-ready

---

### ✅ D) REPEATABLE EXECUTION HARNESS
**File**: [scripts/run_kts_test_suite.ps1](../scripts/run_kts_test_suite.ps1)

**Automation Features**:
- **Stage 1**: Crawl corpus for new/modified/deleted files
- **Stage 2**: Ingest documents (convert, extract, index)
- **Stage 3**: Status check (documents, graph, vectors)
- **Stage 4**: Vision workflow (pending images)
- **Stage 5**: Sample retrieval queries (first 10 by default, configurable)
- **Stage 6**: Idempotency validation (re-crawl should find no new files)
- **Logging**: Timestamped JSON logs in `scripts/logs/`
- **Exit Criteria Evaluation**: Auto-checks 4 critical gates

**Usage**:
```powershell
# Full automated run
.\scripts\run_kts_test_suite.ps1

# Run all 50 queries, skip ingestion (if already done)
.\scripts\run_kts_test_suite.ps1 -QueryLimit 50 -SkipIngestion

# Verbose mode
.\scripts\run_kts_test_suite.ps1 -Verbose
```

**Output**:
- Console summary with color-coded pass/fail
- Timestamped logs: `scripts/logs/test_suite_summary_YYYYMMDD_HHMMSS.json`
- Individual query logs: `scripts/logs/query_Q{ID}_YYYYMMDD_HHMMSS.json`
- Exit criteria evaluation with GO/NO-GO recommendation

---

### ✅ E) MULTI-MODAL DIAGNOSTICS
**File**: [docs/TEST_MULTIMODAL_DIAGNOSTICS.md](TEST_MULTIMODAL_DIAGNOSTICS.md)

**Contents**:
- **Decision tree**: Diagnose why `describe pending` returns 0
- **Section 1**: Embedded image extraction failure (DOCX/PDF/PPTX return empty lists)
- **Section 2**: Markdown image reference parsing (`![](image.png)` not harvested)
- **Section 3**: Standalone image discovery (PNG/JPG files ignored by crawler)
- **Section 4**: Manifest corruption troubleshooting
- **Section 5**: Expected outputs reference for test corpus
- **Section 6**: Testing image extraction (harness and validation workflow)
- **Section 7**: Recommended implementation order (4 phases)
- **Section 8**: Exit criteria for multi-modal pipeline

**Key Insight**:
The current implementation has a known gap: image extraction not implemented for embedded images or markdown references. Standalone images in `Reference/images/` are not discovered by default. This is documented as a limitation with fix guidance provided.

**PowerShell Diagnostic Commands**:
- Check for extracted images on disk
- Inspect converter source code
- Examine pending manifest
- Search for markdown image references
- Validate image file existence

---

### ✅ F) TEST REPORT TEMPLATE
**File**: [docs/TEST_REPORT_TEMPLATE.md](TEST_REPORT_TEMPLATE.md)

**Sections**:
1. **Executive Summary**: Overall status, pass rate, recommendation (GO/NO-GO)
2. **Test Summary by Stage**: Table with pass/fail counts per stage
3. **Agent-Level Coverage**: Coverage matrix for all 10 agents
4. **Top 50 Queries Results**: Category-level results, citation quality scorecard
5. **Multi-Modal Pipeline Validation**: Image extraction results, vision workflow status
6. **Idempotency Validation**: Re-crawl and re-ingest stability checks
7. **Defect Log**: Critical/major/minor defects with reproduction steps
8. **Exit Criteria Evaluation**: YES/NO checklist for all 10 criteria
9. **Observations & Recommendations**: What went well, improvements, risks, limitations
10. **Approvals**: Signature blocks for stakeholders

**How to Use**:
- Fill out after running test suite
- Document all findings (pass/fail, defects, observations)
- Obtain stakeholder approvals before go-live
- Save as `docs/TEST_REPORT_YYYYMMDD.md`

---

### ✅ BONUS: EXECUTION CHECKLIST
**File**: [docs/TEST_EXECUTION_CHECKLIST.md](TEST_EXECUTION_CHECKLIST.md)

**Step-by-Step Guide**:
- **Pre-Execution**: Environment setup, dependency checks, knowledge base reset
- **Step 1**: Run automated test suite (5-15 min)
- **Step 2**: Run full Top 50 query pack (10-20 min)
- **Step 3**: Manual vision workflow validation
- **Step 4**: Extension integration testing (optional)
- **Step 5**: Idempotency deep validation
- **Step 6**: Negative test cases (invalid inputs)
- **Step 7**: Fill out test report template
- **Post-Execution**: Tag release if passed, prioritize defects if failed

**Includes**:
- Cheat sheet of common commands
- Troubleshooting quick reference table
- Success indicators checklist

---

## Key Workflows Covered

### Workflow 1: Full Ingestion Pipeline
```
Crawl → Ingest → Classify → Graph Build → Vector Index → Status Check
```
**Tests**: Smoke test, idempotency test, status validation

### Workflow 2: Retrieval with Citations
```
User Query → Retrieval Service → Context Chunks + Citations → Copilot → Answer
```
**Tests**: Top 50 queries, citation quality scorecard, confidence thresholding

### Workflow 3: Multi-Modal Vision Flow
```
Ingest → Extract Images → Pending Manifest → Human Description → Index → Retrieval with Image Notes
```
**Tests**: Vision workflow scenario, describe pending validation, image note checks

### Workflow 4: Training Path Generation
```
Topic Request → Graph Traversal → Prerequisite Ordering → Learning Steps → Time Estimation
```
**Tests**: Training path queries (Q26-Q35), prerequisite validation

### Workflow 5: Change Impact Analysis
```
Entity Change → Graph Search → Direct Docs + Indirect Docs → Stale Images → Impact Report
```
**Tests**: Impact queries (Q36-Q45), severity assignment, transitive doc discovery

### Workflow 6: Freshness Auditing
```
Scope Filter → Age Calculation → Badge Assignment → Stale List → Recommendations
```
**Tests**: Freshness queries (Q46-Q50), badge accuracy, threshold overrides

---

## Known Issues & Limitations

### 🔴 CRITICAL (Known, Documented)

**1. Image Extraction Gap**
- **Issue**: DOCX/PDF/PPTX converters return empty image lists
- **Impact**: `describe pending` returns 0 even for screenshot-heavy corpus
- **Workaround**: None (requires implementation)
- **Fix Guidance**: TEST_MULTIMODAL_DIAGNOSTICS.md Section 1-3
- **Status**: Documented as known limitation, fix phases outlined

**2. Markdown Image References Not Parsed**
- **Issue**: `![](image.png)` references in MD files not harvested
- **Impact**: Referenced images not added to pending manifest
- **Workaround**: None
- **Fix Guidance**: TEST_MULTIMODAL_DIAGNOSTICS.md Section 2

**3. Standalone Images Not Discovered**
- **Issue**: PNG/JPG files in corpus ignored (not in crawler extension list)
- **Impact**: `Reference/images/` folder (4 PNGs) not processed
- **Workaround**: None
- **Fix Guidance**: TEST_MULTIMODAL_DIAGNOSTICS.md Section 3

### 🟡 MEDIUM (Expected Behavior)

**1. Keyword-Based Vector Search**
- **Issue**: Using simple keyword overlap, not semantic embeddings
- **Impact**: Retrieval accuracy limited for synonym/paraphrase queries
- **Workaround**: Clear query phrasing
- **Future**: Migrate to semantic embeddings (Phase 3)

**2. Manual Image Description Required**
- **Issue**: No automatic image captioning (by design)
- **Impact**: Human-in-loop workflow adds operational overhead
- **Workaround**: None (it's the intended design)
- **Future**: Evaluate auto-captioning with Azure Computer Vision

### 🟢 LOW (Acceptable)

**1. Limited Corpus Diversity (14 Files)**
- **Issue**: Test corpus is small and focused
- **Impact**: Scale testing not possible with current corpus
- **Workaround**: Supplement with synthetic edge cases
- **Future**: Expand corpus to 100+ files for scale testing

---

## Exit Criteria Summary

### Mandatory Gates (All Must Pass)

| # | Criterion | Target | Validation Method |
|---|-----------|--------|-------------------|
| 1 | All 46 existing backend tests pass | 46/46 | `pytest tests/ -v` |
| 2 | All 10 existing extension tests pass | 10/10 | `npm test` (in extension/) |
| 3 | Full corpus smoke test passes | GREEN | `scripts/run_kts_test_suite.ps1` |
| 4 | Top 50 queries achieve >80% correct | >80% | Query validation in test suite |
| 5 | Zero hallucinations | 0 | Manual review: all results have citations |
| 6 | Idempotency validated | STABLE | Re-crawl/re-ingest tests |
| 7 | Multi-modal pipeline functional | END-TO-END | Vision workflow validation (or documented limitation) |
| 8 | All CLI commands return valid JSON | 100% | CLI integration tests |
| 9 | Extension commands execute without errors | 100% | Extension integration tests |
| 10 | Chat participant returns structured markdown | YES | Chat participant tests |

**Gate Decision**:
- **GO**: All 10 gates pass
- **NO-GO**: Any P0 (critical) defect, or <80% pass rate
- **CONDITIONAL GO**: Known limitations documented, workarounds in place, post-launch fix plan

---

## Execution Timeline

### Week 1: Automated Testing
- **Day 1-2**: Run test harness, validate results
- **Day 3-4**: Run Top 50 queries, document failures
- **Day 5**: Fill initial test report sections

### Week 2: Multi-Modal Focus
- **Day 1-2**: Implement image extraction fixes (optional, if prioritized)
- **Day 3-4**: Re-test vision workflow
- **Day 5**: Update test report with vision results

### Week 3: Manual & Integration Testing
- **Day 1-2**: Extension testing (if applicable)
- **Day 3**: Idempotency deep validation
- **Day 4**: Negative test cases
- **Day 5**: Complete test report, obtain approvals

### Week 4: Decision & Launch Prep
- **Day 1-2**: Review test report with stakeholders
- **Day 3**: Fix critical defects (P0) if any
- **Day 4**: Regression run (re-test affected areas)
- **Day 5**: Final gate decision, tag release or defer

**Total Duration**: 4 weeks for comprehensive testing  
**Fast-Track Option**: 1 week for automated tests only (skip manual validation)

---

## Commands to Run the Plan

### Complete Automated Test Suite (Start Here)
```powershell
# 1. Ensure environment ready
.\.venv\Scripts\Activate.ps1
pytest tests/ -v  # Should see 46 passed

# 2. Run automated test suite
.\scripts\run_kts_test_suite.ps1

# 3. Review results
Get-Content .\scripts\logs\test_suite_summary_*.json | ConvertFrom-Json

# 4. If passed, run full query pack
.\scripts\run_kts_test_suite.ps1 -QueryLimit 50 -SkipIngestion
```

### Manual Validation Steps
```powershell
# Vision workflow
.\.venv\Scripts\python.exe -m cli.main describe pending

# If pending > 0, complete sample description
# Create descriptions.json, then:
.\.venv\Scripts\python.exe -m cli.main describe complete <doc_id> --descriptions-file descriptions.json

# Idempotency
.\.venv\Scripts\python.exe -m cli.main crawl --paths .\kts_test_corpus
# (Run twice, compare outputs)

# Negative tests
.\.venv\Scripts\python.exe -m cli.main crawl --paths "C:\NonExistent"
.\.venv\Scripts\python.exe -m cli.main search --query ""
```

### Fill Out Report
```powershell
# Open template
code .\docs\TEST_REPORT_TEMPLATE.md

# Save completed report
# docs/TEST_REPORT_20260214.md
```

---

## Documentation Map

All artifacts are in `docs/` folder:

```
docs/
├── TEST_MASTER_PLAN.md                  ← Start here: Overall strategy
├── TEST_TRACEABILITY_MATRIX.md          ← Coverage mapping
├── TEST_QUERIES_TOP_50.md               ← Human-readable query pack
├── TEST_QUERIES_TOP_50.json             ← Machine-readable query pack
├── TEST_MULTIMODAL_DIAGNOSTICS.md       ← Troubleshooting vision workflow
├── TEST_REPORT_TEMPLATE.md              ← Fill out after execution
└── TEST_EXECUTION_CHECKLIST.md          ← Step-by-step execution guide
```

Scripts are in `scripts/`:

```
scripts/
├── run_kts_test_suite.ps1               ← Main automated harness
├── run_kts_test_corpus.ps1              ← Quick corpus ingestion (existing)
└── logs/                                ← Timestamped execution logs
    ├── test_suite_summary_*.json
    ├── crawl_*.json
    ├── ingest_*.json
    ├── status_*.json
    ├── vision_pending_*.json
    └── query_*_*.json
```

---

## Next Steps (For Execution Engineer)

### Immediate Actions (Today)

1. **Read all documentation**:
   - [ ] TEST_MASTER_PLAN.md (objectives, strategy)
   - [ ] TEST_EXECUTION_CHECKLIST.md (step-by-step guide)
   - [ ] TEST_MULTIMODAL_DIAGNOSTICS.md (troubleshooting reference)

2. **Validate environment**:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   pytest tests/ -v  # Expect 46 passed
   ```

3. **Run first test suite execution**:
   ```powershell
   .\scripts\run_kts_test_suite.ps1
   ```

4. **Review initial results**:
   - Check pass rate
   - Identify any immediate blockers
   - Document unexpected failures

### This Week

- [ ] Complete automated test suite runs (with varying -QueryLimit)
- [ ] Validate vision workflow (or document as known limitation)
- [ ] Run idempotency tests
- [ ] Start filling out TEST_REPORT_TEMPLATE.md

### Next Week

- [ ] Extension testing (if applicable)
- [ ] Negative test cases
- [ ] Complete test report
- [ ] Review with Test Lead

### Week 3-4

- [ ] Stakeholder review of test report
- [ ] Fix P0 defects (if any)
- [ ] Regression testing
- [ ] Final gate decision
- [ ] Tag release or create fix backlog

---

## Success Metrics

**You'll know you're ready for production when**:

✅ Automated test suite runs without errors  
✅ Pass rate ≥80% (ideally 90%+)  
✅ Zero results without citations  
✅ Low-confidence results include escalation  
✅ Idempotency validated (stable re-runs)  
✅ Multi-modal pipeline works (or limitation documented)  
✅ Extension commands functional (if applicable)  
✅ Test report completed with stakeholder sign-off  
✅ All P0 defects resolved  
✅ Known limitations communicated to users

---

## Contact & Escalation

**Test Lead**: [To be assigned]  
**Engineering Lead**: [To be assigned]  
**QA Manager**: [To be assigned]  
**Business Owner**: [To be assigned]

**Escalation Path**:
- P0 defects → Immediate escalation to Engineering Lead
- Test blocker → Report to Test Lead
- Timeline risk → Report to QA Manager
- Scope change request → Escalate to Business Owner

---

## Appendix: Agent Contracts Summary

Quick reference for what each agent should do:

| Agent | Input | Output | Key Validation |
|-------|-------|--------|----------------|
| Crawler | Paths | `CrawlResult` (new/modified/deleted files) | Idempotency: re-run shows unchanged |
| Ingestion | `FileInfo` | `IngestedDocument` (markdown, metadata, images) | All formats converted correctly |
| Vision | Operation + descriptions | `VisionResult` (pending count, indexed images) | pending → described → indexed → searchable |
| Taxonomy | Doc content | `ClassificationResult` (doc_type, confidence) | Correct doc_type, confidence >0.5 |
| Version | Old + new content | `VersionDiff` (sections changed, SUPERSEDES edge) | Changed chunks identified |
| Graph Builder | Doc metadata + entities | `GraphBuildResult` (nodes/edges added) | Entities linked, no duplicates |
| Retrieval | Query | `SearchResult` (context + citations) | All results have citations |
| Training Path | Topic | `TrainingPath` (ordered learning steps) | Prerequisites ordered correctly |
| Change Impact | Entity | `ImpactReport` (affected docs, severity) | Transitive docs included |
| Freshness | Scope + threshold | `FreshnessReport` (current/aging/stale counts) | Badges calculated correctly |

---

**Plan Status**: ✅ COMPLETE - Ready for execution  
**Last Updated**: 2026-02-14  
**Maintained By**: Test Lead  
**Next Review**: After first execution cycle
