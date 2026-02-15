# GSF IR KTS — Test Execution Checklist

**Purpose**: Step-by-step guide to run the complete test suite  
**User**: Test Lead / QA Engineer  
**Duration**: ~30-60 minutes (depending on corpus size and query count)  
**Prerequisites**: Python venv activated, corpus extracted, all docs read

---

## Pre-Execution Checklist

### Environment Setup

- [ ] **Python venv activated**
  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```

- [ ] **Dependencies installed**
  ```powershell
  pip install -r requirements.txt
  ```

- [ ] **Test corpus extracted**
  ```powershell
  # Should see:
  Get-ChildItem .\kts_test_corpus -Directory
  # Output: Reference, Release_Notes, Training, Troubleshooting, User_Guides
  ```

- [ ] **Existing backend tests passing**
  ```powershell
  pytest tests/ -v
  # Expected: 46 tests passed
  ```

- [ ] **Existing extension tests passing** (optional if not testing extension)
  ```powershell
  cd extension
  npm test
  # Expected: 10 tests passed
  ```

- [ ] **Read all test documentation**
  - [ ] docs/TEST_MASTER_PLAN.md
  - [ ] docs/TEST_TRACEABILITY_MATRIX.md
  - [ ] docs/TEST_QUERIES_TOP_50.md
  - [ ] docs/TEST_MULTIMODAL_DIAGNOSTICS.md
  - [ ] docs/TEST_REPORT_TEMPLATE.md

### Knowledge Base Reset (Optional)

If you want a clean slate:

- [ ] **Backup existing knowledge base** (if any)
  ```powershell
  if (Test-Path .\knowledge_base) {
      Copy-Item -Path .\knowledge_base -Destination .\knowledge_base_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss') -Recurse
      Remove-Item -Path .\knowledge_base -Recurse -Force
  }
  ```

---

## Execution Steps

### Step 1: Run Automated Test Suite

**Command**:
```powershell
.\scripts\run_kts_test_suite.ps1
```

**What it does**:
1. Crawls corpus for files
2. Ingests documents (converts to markdown, extracts metadata)
3. Checks system status (documents, graph, vectors)
4. Checks vision workflow (pending images)
5. Runs first 10 queries from Top 50 pack (configurable via `-QueryLimit`)
6. Validates idempotency (re-crawl should find no new files)
7. Generates timestamped logs in `scripts/logs/`
8. Produces summary JSON with pass/fail results

**Expected Duration**: 5-15 minutes (depending on corpus size)

**Expected Output**:
```
========================================
KTS Test Suite - 20260214_153045
========================================

Corpus path: .\kts_test_corpus
Log directory: .\scripts\logs
Timestamp: 20260214_153045

========================================
Stage 1: Crawl File System
========================================

[15:30:46] Scanning corpus for new/modified/deleted files...
  ✓ Success
  Files found: new=9, modified=0, deleted=0, unchanged=0

========================================
Stage 2: Ingest Documents
========================================

[15:31:02] Converting documents to markdown and extracting metadata...
  ✓ Success
  Documents ingested: 9

...
[15:32:15] Test Suite Summary
========================================

Total Tests: 14
Passed: 13
Failed: 1
Warnings: 1
Pass Rate: 92.9%

========================================
Exit Criteria Evaluation
========================================

  ✓ PASS - Pass rate ≥80%
  ✗ FAIL - Zero failed tests
  ✓ PASS - Status check passed
  ✓ PASS - Idempotency validated

⚠ SOME EXIT CRITERIA NOT MET - Review failures before go-live
```

**If test suite FAILS**:
- [ ] Review logs in `scripts/logs/test_suite_summary_YYYYMMDD_HHMMSS.json`
- [ ] Check individual stage logs (crawl, ingest, status, queries)
- [ ] Refer to TEST_MULTIMODAL_DIAGNOSTICS.md for troubleshooting
- [ ] Document failures in TEST_REPORT_TEMPLATE.md

**If test suite PASSES**:
- [ ] Proceed to Step 2

---

### Step 2: Run Full Top 50 Query Pack

**Command**:
```powershell
.\scripts\run_kts_test_suite.ps1 -QueryLimit 50 -SkipIngestion
```

**What it does**:
- Skips crawl/ingest (already done in Step 1)
- Runs all 50 queries from the Top 50 pack
- Validates citations, confidence, escalation for each
- Generates detailed logs for each query

**Expected Duration**: 10-20 minutes

**Expected Output**:
- Individual query logs: `scripts/logs/query_Q{01-50}_YYYYMMDD_HHMMSS.json`
- Summary showing pass/fail for each query category
- Citation quality scorecard

**Manual Review Required**:
- [ ] Open `scripts/logs/test_suite_summary_YYYYMMDD_HHMMSS.json`
- [ ] For each failed query:
  - [ ] Review expected vs. actual citations
  - [ ] Check if confidence level was appropriate
  - [ ] Verify escalation triggered when required
- [ ] Document results in TEST_REPORT_TEMPLATE.md

---

### Step 3: Manual Vision Workflow Validation

**Command**:
```powershell
# Check pending images
.\.venv\Scripts\python.exe -m cli.main describe pending
```

**Expected Outcomes**:

**Scenario A: Pending count = 0** ⚠️
- This indicates image extraction gap (current known issue)
- [ ] Follow diagnostics in TEST_MULTIMODAL_DIAGNOSTICS.md Section 1-3
- [ ] Document as "Known Limitation" in test report
- [ ] Mark vision workflow as PARTIAL/BROKEN

**Scenario B: Pending count > 0** ✅
- [ ] Pick one image from the list
- [ ] Open image in viewer: `start <image_path>`
- [ ] Describe the image (be specific, include UI elements, error messages, colors)
- [ ] Create descriptions file:
  ```json
  {
    "descriptions": {
      "img_001": "Screenshot of ToolX login page showing red error banner with text 'AUTH401: Unauthorized'. Username field contains 'john.doe' and password field is obscured. Login button is dimmed/disabled."
    }
  }
  ```
- [ ] Save as `descriptions.json`
- [ ] Complete descriptions:
  ```powershell
  .\.venv\Scripts\python.exe -m cli.main describe complete <doc_id> --descriptions-file descriptions.json
  ```
- [ ] Verify indexing:
  ```powershell
  .\.venv\Scripts\python.exe -m cli.main search --query "red error banner login" --max-results 3
  ```
- [ ] Check result includes `image_note` referencing the described image
- [ ] Document in test report

---

### Step 4: Extension Integration Testing (Optional)

**Prerequisites**:
- VS Code with extension installed (VSIX or dev mode)
- Backend must be running (or commands must invoke CLI)

**Tests to run**:

- [ ] **Command: KTS: Crawl & Ingest from File Shares**
  - Trigger from command palette
  - Verify prompt for path
  - Confirm backend execution
  - Check output channel for results

- [ ] **Command: KTS: View Status Report**
  - Trigger from command palette
  - Verify webview panel opens
  - Confirm displays document/graph/vector stats

- [ ] **Command: KTS: Generate Training Path**
  - Trigger from command palette
  - Enter topic: "ToolX"
  - Verify training path displayed with ordered steps

- [ ] **Command: KTS: Analyze Change Impact**
  - Trigger from command palette
  - Enter entity: "ToolX"
  - Verify impact report shows affected docs

- [ ] **Command: KTS: Run Freshness Audit**
  - Trigger from command palette
  - Verify freshness report with badges

- [ ] **Chat Participant: @kts**
  - Open Copilot Chat
  - Type: `@kts What does error AUTH401 mean?`
  - Verify response includes citations with file:// URIs
  - Verify markdown formatting with context chunks

- [ ] **Copilot Tool: @kts**
  - In code file, trigger inline completion
  - Reference @kts in prompt
  - Verify tool returns context JSON

**Document results**: Extension section of TEST_REPORT_TEMPLATE.md

---

### Step 5: Idempotency Deep Validation

**Test 1: Triple Crawl**
```powershell
# First crawl
.\.venv\Scripts\python.exe -m cli.main crawl --paths .\kts_test_corpus | Out-File .\crawl1.json

# Second crawl (should show all unchanged)
.\.venv\Scripts\python.exe -m cli.main crawl --paths .\kts_test_corpus | Out-File .\crawl2.json

# Third crawl (should be identical to second)
.\.venv\Scripts\python.exe -m cli.main crawl --paths .\kts_test_corpus | Out-File .\crawl3.json

# Compare
Compare-Object (Get-Content .\crawl2.json) (Get-Content .\crawl3.json)
# Expected: No differences
```

**Test 2: Status Stability**
```powershell
# Capture status before re-ingest
.\.venv\Scripts\python.exe -m cli.main status | Out-File .\status_before.json

# Re-ingest with force
.\.venv\Scripts\python.exe -m cli.main ingest --paths .\kts_test_corpus --force

# Capture status after re-ingest
.\.venv\Scripts\python.exe -m cli.main status | Out-File .\status_after.json

# Compare counts (should be identical)
$before = Get-Content .\status_before.json | ConvertFrom-Json
$after = Get-Content .\status_after.json | ConvertFrom-Json

Write-Host "Documents: $($before.documents) -> $($after.documents)"
Write-Host "Graph nodes: $($before.graph_nodes) -> $($after.graph_nodes)"
Write-Host "Graph edges: $($before.graph_edges) -> $($after.graph_edges)"
Write-Host "Vector chunks: $($before.vector_chunks) -> $($after.vector_chunks)"

# All should be unchanged or acceptably close
```

**Pass Criteria**:
- [ ] Re-crawl shows 0 new files, 0 modified files
- [ ] Status counts remain stable (±5% acceptable for re-indexing variance)
- [ ] No duplicate doc_ids created
- [ ] No orphaned graph nodes

---

### Step 6: Negative Test Cases

**Test invalid inputs**:

- [ ] **Crawl non-existent path**
  ```powershell
  .\.venv\Scripts\python.exe -m cli.main crawl --paths "C:\NonExistent\Path"
  # Expected: Error message, exit code != 0, no crash
  ```

- [ ] **Ingest unsupported extension**
  ```powershell
  # Create dummy file
  echo "test" > test.xyz
  .\.venv\Scripts\python.exe -m cli.main ingest --paths test.xyz
  # Expected: Reject with "Unsupported extension" error
  Remove-Item test.xyz
  ```

- [ ] **Search with empty query**
  ```powershell
  .\.venv\Scripts\python.exe -m cli.main search --query ""
  # Expected: Error or empty results, no crash
  ```

- [ ] **Unknown entity in impact analysis**
  ```powershell
  .\.venv\Scripts\python.exe -m cli.main impact --entity "UnknownToolXYZ"
  # Expected: Escalation with "entity not found", suggested_action
  ```

- [ ] **Training path for non-existent topic**
  ```powershell
  .\.venv\Scripts\python.exe -m cli.main training --topic "NonExistentTopic"
  # Expected: Empty path or escalation
  ```

**Pass Criteria**:
- [ ] No crashes/exceptions on invalid input
- [ ] Clear error messages returned
- [ ] Appropriate exit codes
- [ ] System remains stable after errors

---

### Step 7: Fill Out Test Report

**Command**:
```powershell
# Open template in VS Code
code .\docs\TEST_REPORT_TEMPLATE.md
```

**Sections to complete**:

1. **Executive Summary**
   - [ ] Overall status (PASS/FAIL/CONDITIONAL)
   - [ ] Pass rate from test suite
   - [ ] Critical/major/minor issue counts
   - [ ] Recommendation (GO/NO-GO/CONDITIONAL GO)

2. **Test Summary by Stage**
   - [ ] Fill in test counts, pass/fail for each stage
   - [ ] Add notes for any failures

3. **Agent-Level Coverage**
   - [ ] Fill in unit/integration/CLI/scenario test results per agent
   - [ ] Document issues found

4. **Top 50 Queries Results**
   - [ ] Fill in category-level pass/fail counts
   - [ ] Complete citation quality scorecard
   - [ ] Document failed queries with reproduction steps

5. **Multi-Modal Pipeline Validation**
   - [ ] Fill in expected vs. actual image extraction counts
   - [ ] Document vision workflow status
   - [ ] Note known limitations

6. **Idempotency Validation**
   - [ ] Fill in re-crawl and re-ingest results
   - [ ] Confirm counts stable or document variances

7. **Defect Log**
   - [ ] Create entries for each defect found
   - [ ] Assign priority (P0/P1/P2)
   - [ ] Assign owner
   - [ ] Document reproduction steps

8. **Exit Criteria Evaluation**
   - [ ] Check YES/NO for each criterion
   - [ ] Mark overall gate decision

9. **Observations & Recommendations**
   - [ ] What went well
   - [ ] What needs improvement
   - [ ] Risks & mitigation
   - [ ] Known limitations
   - [ ] Recommendations for next iteration

10. **Approvals**
    - [ ] Obtain signatures from Test Lead, Engineering Lead, QA Manager, Business Owner

**Save completed report**: `docs/TEST_REPORT_YYYYMMDD.md`

---

## Post-Execution Actions

### If ALL EXIT CRITERIA MET ✅

- [ ] **Tag release**
  ```powershell
  git tag -a v1.0.0 -m "Production release - all tests passed"
  git push origin v1.0.0
  ```

- [ ] **Package extension VSIX** (if applicable)
  ```powershell
  cd extension
  npm run package
  # Generates kts-extension-1.0.0.vsix
  ```

- [ ] **Update README with release notes**
- [ ] **Schedule go-live with stakeholders**
- [ ] **Prepare runbook for maintenance engineers** (ref: MAINTENANCE_ENGINEER_GUIDE.md)
- [ ] **Set up monitoring/alerting** (ref: LAUNCH_CHECKLIST.md)

### If EXIT CRITERIA NOT MET ❌

- [ ] **Prioritize defects** (P0 must be fixed before go-live)
- [ ] **Assign defects to developers**
- [ ] **Create fix branch**
  ```powershell
  git checkout -b fix/test-failures
  ```
- [ ] **Implement fixes**
- [ ] **Re-run test suite** (start from Step 1 of this checklist)
- [ ] **Update test report with re-test results**
- [ ] **Re-evaluate exit criteria**

### If CONDITIONAL GO ⚠️

- [ ] **Document known limitations clearly** (README, user guide, go-live approval)
- [ ] **Create workaround procedures** for known issues
- [ ] **Schedule post-launch fix sprint** for P1 issues
- [ ] **Communicate limitations to users**
- [ ] **Set up feedback channel** for users to report issues

---

## Cheat Sheet: Common Commands

```powershell
# Full automated test suite
.\scripts\run_kts_test_suite.ps1

# Crawl only
.\.venv\Scripts\python.exe -m cli.main crawl --paths .\kts_test_corpus

# Ingest only
.\.venv\Scripts\python.exe -m cli.main ingest --paths .\kts_test_corpus

# Status check
.\.venv\Scripts\python.exe -m cli.main status

# Vision pending
.\.venv\Scripts\python.exe -m cli.main describe pending

# Sample search
.\.venv\Scripts\python.exe -m cli.main search --query "What does error AUTH401 mean?" --max-results 3

# Training path
.\.venv\Scripts\python.exe -m cli.main training --topic "ToolX" --level beginner

# Impact analysis
.\.venv\Scripts\python.exe -m cli.main impact --entity "ToolX" --entity-type tool

# Freshness audit
.\.venv\Scripts\python.exe -m cli.main freshness --scope all --threshold 180

# Run backend tests
pytest tests/ -v

# Run extension tests
cd extension; npm test
```

---

## Troubleshooting Quick Reference

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| `describe pending` returns 0 | Image extraction gap | See TEST_MULTIMODAL_DIAGNOSTICS.md Section 1-3 |
| Crawl finds 0 files | Corpus path wrong | Verify path with `Get-ChildItem .\kts_test_corpus` |
| Ingest fails with import error | Missing dependency | Run `pip install -r requirements.txt` |
| Search returns no results | Vector store empty | Check status → vector_chunks > 0 |
| Citations missing file:// URIs | Retrieval bug | Check backend/agents/retrieval_service.py |
| Graph nodes = 0 | Graph builder not running | Check ingest logs, ensure graph builder called |
| Re-crawl shows all files as new | Manifest corrupted | Backup and remove knowledge_base/manifest.json |
| Extension commands not working | Backend not wired | Check extension/lib/kts_backend.js |

---

## Success Indicators

You know the system is ready for production when:

✅ All 46 backend tests pass  
✅ All 10 extension tests pass  
✅ Test suite pass rate ≥80%  
✅ Zero hallucinations (all results have citations)  
✅ Idempotency validated (stable re-runs)  
✅ Multi-modal pipeline functional (or documented as limitation)  
✅ All CLI commands operational  
✅ Extension commands functional  
✅ Chat participant returns structured markdown  
✅ Test report completed and approved  
✅ Known limitations documented for users

---

**Checklist Version**: 1.0  
**Last Updated**: 2026-02-14  
**Maintained By**: Test Lead
