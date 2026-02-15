# KTS Extension - Acceptance Test Script

## Test Environment
- **Date**: 2026-02-14
- **Extension Version**: 1.0.0
- **Backend Version**: 1.0.0
- **Platform**: Windows 10/11
- **Python Version**: 3.10+

## Prerequisites
- [ ] Python 3.10+ installed
- [ ] VS Code installed
- [ ] Test corpus available (use `kts_synthetic_corpus_v2`)

## Test Execution

### Phase 1: Installation & Bootstrap

#### Test 1.1: Extension Installation
**Steps**:
1. Open VS Code
2. Go to Extensions view (Ctrl+Shift+X)
3. Click **...** → **Install from VSIX**
4. Select `extension/dist/gsf-ir-kts-1.0.0.vsix`

**Expected**:
- [x] Extension installs without errors
- [x] Extension appears in Extensions list
- [x] Status: "KTS: Setting up backend..." notification appears

**Result**: ___________

#### Test 1.2: Bootstrap Verification
**Steps**:
1. Wait for bootstrap to complete (~30-90 seconds)
2. Check Output panel → Select "KTS" channel

**Expected**:
- [x] "[VenvManager] Bootstrap complete!" message
- [x] "KTS: Backend setup complete ✓" notification
- [x] No errors in output

**Result**: ___________

#### Test 1.3: Doctor Diagnostics
**Steps**:
1. Command Palette (Ctrl+Shift+P)
2. Run: **KTS: Doctor**

**Expected Output**:
```json
{
  "configuration": {
    "sourcePath": "(not set)",
    "backendChannel": "bundled",
    ...
  },
  "environment": {
    "pythonDetected": "py -3" | "python",
    "pythonVersion": "Python 3.10.x",
    "venvExists": true,
    "backendExists": true,
    "healthCheck": true
  },
  ...
}
```

**Expected**:
- [x] All checks passed
- [x] venvExists: true
- [x] backendExists: true
- [x] healthCheck: true

**Result**: ___________

**Log File**: `logs/test_1_doctor.txt`

---

### Phase 2: Configuration

#### Test 2.1: Select Source Path
**Steps**:
1. Command Palette → **KTS: Select Source Folder**
2. Navigate to: `<repo>\kts_synthetic_corpus_v2`
3. Select folder

**Expected**:
- [x] Folder picker opens
- [x] Notification: "KTS Source Path updated: <path>"
- [x] Settings updated

**Verification**:
```
Settings → Search "kts.sourcePath" → Value shows selected path
```

**Result**: ___________

---

### Phase 3: Crawl & Ingest

#### Test 3.1: Crawl
**Steps**:
1. Command Palette → **KTS: Crawl**
2. Wait for completion
3. Check Output panel

**Expected Output**:
```
[KTS Crawl] Source: C:\...\kts_synthetic_corpus_v2
{
  "status": "success",
  "files_found": <N>,
  ...
}
```

**Expected**:
- [x] Notification: "KTS Crawl complete: N file(s) discovered"
- [x] N > 50 (corpus has ~100+ files)
- [x] No errors

**Result**: ___________
**Files Found**: ___________

**Log File**: `logs/test_3_crawl.txt`

#### Test 3.2: Ingest
**Steps**:
1. Command Palette → **KTS: Ingest**
2. Wait for completion (~2-5 minutes for corpus)
3. Check Output panel

**Expected Output**:
```
[KTS Ingest] Source: C:\...\kts_synthetic_corpus_v2
{
  "status": "success",
  "ingested_count": <N>,
  ...
}
```

**Expected**:
- [x] Notification: "KTS Ingest complete: N document(s) ingested"
- [x] N matches crawl count
- [x] No errors

**Result**: ___________
**Documents Ingested**: ___________

**Log File**: `logs/test_3_ingest.txt`

---

### Phase 4: Query & Retrieval

#### Test 4.1: Status Check
**Steps**:
1. Command Palette → **KTS: Status**
2. Check output

**Expected Output**:
```json
{
  "document_count": <N>,
  "total_chunks": <M>,
  "last_crawl": "2026-02-14T...",
  "last_ingest": "2026-02-14T...",
  ...
}
```

**Expected**:
- [x] document_count > 0
- [x] total_chunks > document_count
- [x] last_crawl and last_ingest timestamps present

**Result**: ___________

**Log File**: `logs/test_4_status.txt`

#### Test 4.2: Search Query 1
**Query**: "How do I configure BatchBridge connector?"

**Steps**:
1. Command Palette → **KTS: Search**
2. Enter query
3. Check output

**Expected Output**:
```json
{
  "results": [
    {
      "doc_id": "...",
      "chunk_id": "...",
      "score": <float>,
      "content": "...",
      "metadata": {
        "source_path": "...BatchBridge..."
      }
    },
    ...
  ]
}
```

**Expected**:
- [x] Results contain "BatchBridge" references
- [x] At least 3-5 results
- [x] Scores > 0.5

**Result**: ___________
**Top Document**: ___________

**Log File**: `logs/test_4_search_q1.txt`

#### Test 4.3: Search Query 2
**Query**: "What are the steps to deploy OpsFlow?"

**Steps**: Same as 4.2

**Expected**:
- [x] Results contain "OpsFlow" references
- [x] Results mention deployment steps

**Result**: ___________
**Top Document**: ___________

**Log File**: `logs/test_4_search_q2.txt`

#### Test 4.4: Search Query 3
**Query**: "Troubleshooting ToolX authentication issues"

**Steps**: Same as 4.2

**Expected**:
- [x] Results contain "ToolX" and "authentication" references
- [x] Troubleshooting context present

**Result**: ___________
**Top Document**: ___________

**Log File**: `logs/test_4_search_q3.txt`

---

### Phase 5: Chat Integration

#### Test 5.1: Copilot Chat Search
**Steps**:
1. Open Copilot Chat panel
2. Enter: `@kts /search How do I configure BatchBridge connector?`
3. Check response

**Expected**:
- [x] Chat shows results inline
- [x] Results include citations
- [x] Context is relevant

**Result**: ___________

**Screenshot**: `logs/test_5_chat.png`

---

### Phase 6: Logs & Diagnostics

#### Test 6.1: Open Logs
**Steps**:
1. Command Palette → **KTS: Open Logs**

**Expected**:
- [x] File Explorer opens to logs directory
- [x] Directory contains recent log files:
  - `YYYYMMDD_HHMMSS_crawl.log`
  - `YYYYMMDD_HHMMSS_ingest.log`
  - `YYYYMMDD_HHMMSS_search.log`

**Result**: ___________

**Logs Directory**: ___________

#### Test 6.2: Final Doctor Run
**Steps**:
1. Command Palette → **KTS: Doctor**
2. Verify all checks pass

**Expected**:
- [x] "All checks passed ✓"
- [x] sourcePath is set
- [x] KB has documents
- [x] Recent logs present

**Result**: ___________

**Log File**: `logs/test_6_doctor_final.txt`

---

## Summary

### Test Results
- **Total Tests**: 13
- **Passed**: ___ / 13
- **Failed**: ___ / 13

### Issues Encountered
1. ___________
2. ___________
3. ___________

### Performance Metrics
- **Bootstrap Time**: ___ seconds
- **Crawl Time**: ___ seconds
- **Ingest Time**: ___ seconds
- **Average Search Time**: ___ seconds

### Proof Artifacts
All logs saved to: `<kbWorkspace>/logs/acceptance_test_YYYYMMDD/`

Files:
- test_1_doctor.txt
- test_3_crawl.txt
- test_3_ingest.txt
- test_4_status.txt
- test_4_search_q1.txt
- test_4_search_q2.txt
- test_4_search_q3.txt
- test_5_chat.png
- test_6_doctor_final.txt

### Sign-Off
- **Tester**: ___________
- **Date**: ___________
- **Status**: [ ] PASS [ ] FAIL [ ] BLOCKED
- **Notes**: ___________
