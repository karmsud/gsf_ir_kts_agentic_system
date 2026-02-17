# Phase 6: Extension Lifecycle Testing - Test Plan

**Status**: ⚠️ DEFERRED TO POST-BUILD  
**Date**: 2024  
**Reason**: Extensions must be packaged as VSIX before lifecycle testing  

## Prerequisites

- All 3 VSIX packages built:
  - `gsf-ir-kts-core-X.Y.Z.vsix`
  - `gsf-ir-kts-models-spacy-X.Y.Z.vsix`
  - `gsf-ir-kts-models-crossencoder-X.Y.Z.vsix`
- Clean VS Code environment (or dedicated test profile)
- Test workspace with sample documents
- Know KB (.kts) directory for verification

## Test Scenarios

### 1. Fresh Installation (S1 → S2 → S3)

**Objective**: Verify clean install path and tier progression

#### 1.1 Install Core Extension
```
Steps:
1. [ ] Install gsf-ir-kts-core VSIX
2. [ ] Restart VS Code
3. [ ] Verify Core extension appears in Extensions view
4. [ ] Open KTS panel/command palette
5. [ ] Ingest a test document
6. [ ] Run retrieval query
7. [ ] Verify S1 behavior (Core tier, no NER)

Expected:
- Extension loads without errors
- Ingestion completes successfully
- Queries return results (basic semantic search)
- No spaCy/cross-encoder warnings in logs
```

#### 1.2 Add spaCy Extension (S1 → S2)
```
Steps:
1. [ ] Install gsf-ir-kts-models-spacy VSIX
2. [ ] Restart VS Code
3. [ ] Verify spaCy extension appears
4. [ ] Check extension dependencies (should list Core as dependency)
5. [ ] Run retrieval query
6. [ ] Check logs for "NER enabled" or similar

Expected:
- spaCy extension installs alongside Core
- Core extension still functional
- Queries now use entity extraction (S2 tier)
- Entity metadata visible in results
```

#### 1.3 Add Cross-Encoder Extension (S2 → S3)
```
Steps:
1. [ ] Install gsf-ir-kts-models-crossencoder VSIX
2. [ ] Restart VS Code
3. [ ] Verify cross-encoder extension appears
4. [ ] Run retrieval query
5. [ ] Check logs for "Cross-encoder reranking" or similar
6. [ ] Verify latency increase (~2s expected)

Expected:
- Cross-encoder extension installs alongside Core + spaCy
- All 3 extensions functional
- Queries use full pipeline (S3 tier)
- Cross-encoder reranking logged
- Results noticeably more accurate
```

### 2. Uninstall Testing (S3 → S2 → S1)

**Objective**: Verify graceful degradation when removing extensions

#### 2.1 Uninstall Cross-Encoder (S3 → S2)
```
Steps:
1. [ ] Starting state: All 3 extensions installed
2. [ ] Uninstall gsf-ir-kts-models-crossencoder
3. [ ] Restart VS Code
4. [ ] Verify Core + spaCy still present
5. [ ] Run retrieval query
6. [ ] Verify NO cross-encoder reranking

Expected:
- Core + spaCy extensions unaffected
- Queries still use entity extraction (S2)
- No errors about missing cross-encoder
- Latency returns to ~200ms
```

#### 2.2 Uninstall spaCy (S2 → S1)
```
Steps:
1. [ ] Starting state: Core + spaCy installed
2. [ ] Uninstall gsf-ir-kts-models-spacy
3. [ ] Restart VS Code
4. [ ] Verify only Core present
5. [ ] Run retrieval query
6. [ ] Verify NO entity extraction

Expected:
- Core extension unaffected
- Queries revert to basic semantic search (S1)
- No errors about missing spaCy
- System still functional
```

#### 2.3 Uninstall Core
```
Steps:
1. [ ] Starting state: Only Core installed
2. [ ] Uninstall gsf-ir-kts-core
3. [ ] Restart VS Code
4. [ ] Verify KTS commands/panel removed

Expected:
- All KTS functionality removed cleanly
- No orphaned commands or UI elements
- .kts directory preserved (user data safety)
```

### 3. Reload/Restart Stability

**Objective**: Ensure extensions survive VS Code lifecycle events

#### 3.1 Window Reload
```
Steps:
1. [ ] Install all 3 extensions
2. [ ] Ingest documents, run queries (establish baseline)
3. [ ] Reload VS Code window (Cmd/Ctrl+Shift+P → "Reload Window")
4. [ ] Run same queries immediately after reload
5. [ ] Verify results consistent

Expected:
- Extensions re-initialize without errors
- ChromaDB state preserved
- Query results identical to pre-reload
- No re-ingestion required
```

#### 3.2 VS Code Restart
```
Steps:
1. [ ] Install all 3 extensions
2. [ ] Close VS Code completely
3. [ ] Reopen VS Code
4. [ ] Run retrieval query

Expected:
- Extensions activate on startup
- No manual reconfiguration needed
- Query succeeds immediately
```

#### 3.3 Workspace Switch
```
Steps:
1. [ ] Open workspace A, ingest documents
2. [ ] Open workspace B (different folder)
3. [ ] Verify separate .kts directory
4. [ ] Run queries in workspace B
5. [ ] Switch back to workspace A
6. [ ] Verify workspace A .kts still intact

Expected:
- Each workspace has isolated .kts
- No cross-contamination between workspaces
- Extensions work in both workspaces
```

### 4. Update/Upgrade Testing

**Objective**: Verify smooth version updates

#### 4.1 Core Extension Update
```
Steps:
1. [ ] Install Core v1.0.0
2. [ ] Ingest documents, create .kts
3. [ ] Update to Core v1.0.1 (or newer)
4. [ ] Restart VS Code
5. [ ] Verify existing .kts still works
6. [ ] Run queries

Expected:
- Update completes without data loss
- Existing knowledge base preserved
- Backward compatibility maintained
- No re-ingestion required
```

#### 4.2 Model Extension Update
```
Steps:
1. [ ] Install spaCy extension v1.0.0
2. [ ] Update to v1.0.1
3. [ ] Restart VS Code
4. [ ] Run queries

Expected:
- Model update succeeds
- No Core extension breakage
- Queries still functional
```

### 5. Error Scenarios

**Objective**: Test edge cases and failure modes

#### 5.1 Install spaCy Without Core
```
Steps:
1. [ ] Clean VS Code (no KTS extensions)
2. [ ] Attempt to install gsf-ir-kts-models-spacy VSIX

Expected:
- VS Code warns about missing Core dependency (if configured)
- OR spaCy installs but is inactive without Core
- No crashes or errors
```

#### 5.2 Corrupted Extension Files
```
Steps:
1. [ ] Install all 3 extensions
2. [ ] Manually delete a model file (e.g., spaCy model folder)
3. [ ] Restart VS Code
4. [ ] Run queries

Expected:
- Extension logs error about missing model
- System degrades gracefully to lower tier
- No extension crash
- User-friendly error message
```

#### 5.3 Concurrent Installations
```
Steps:
1. [ ] Install Core extension
2. [ ] Immediately install spaCy (don't wait for restart)
3. [ ] Immediately install Cross-encoder
4. [ ] Restart VS Code once
5. [ ] Verify all 3 active

Expected:
- All 3 extensions install successfully
- No conflicts or race conditions
- Single restart activates all
```

## Verification Checklist

After each test scenario, verify:

- [ ] No errors in Output → "Log (Extension Host)"
- [ ] No unhandled exceptions in Developer Tools Console (Help → Toggle Developer Tools)
- [ ] KTS commands present in Command Palette (Cmd/Ctrl+Shift+P)
- [ ] Extension status visible in Extensions view (Cmd/Ctrl+Shift+X)
- [ ] .kts directory structure intact
- [ ] ChromaDB accessible (queries return results)
- [ ] Logs show correct tier (S1/S2/S3)

## Performance Benchmarks

For each configuration, measure:

| Config | Startup Time | Query Latency | Memory Usage |
|--------|--------------|---------------|--------------|
| Core (S1) | ___ms | ___ms | ___MB |
| Core + spaCy (S2) | ___ms | ___ms | ___MB |
| All 3 (S3) | ___ms | ___ms | ___MB |

Target metrics (from Phase 5):
- Startup: <2s
- Query S1: ~175ms
- Query S2: ~225ms
- Query S3: ~2000ms
- Peak memory: <300MB

## Failure Modes to Document

During testing, document any:
- [ ] Error messages that appear
- [ ] Unexpected behavior
- [ ] Performance degradation
- [ ] Missing features
- [ ] Confusing UX
- [ ] Installation issues

## Sign-Off

Testing completed by: _________________  
Date: _________________  
All tests passed: [ ] Yes [ ] No (see notes)  

Notes:
```
(Document any issues found)
```

---

**Status**: This test plan will be executed after VSIX packages are built in Phase 9.  
**Next**: Proceed to Phase 7 (Documentation Verification) while extensions are pending.
