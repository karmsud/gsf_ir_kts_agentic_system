# Phase 23: Implementation Plan
## Step-by-Step Execution Guide

**Document Version:** 1.0  
**Date:** February 26, 2026  
**Status:** Proposal — Pending Approval  
**Total Effort:** 8–10 hours (~2–3 work days)

---

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Dependency Graph](#dependency-graph)
3. [Step-by-Step Plan](#step-by-step-plan)
4. [Rollback Strategy](#rollback-strategy)

---

## Prerequisites

Before starting Phase 23:

| Prerequisite | Status Required |
|-------------|----------------|
| Phase 21 complete | All ABS domain code in `backend/abs/` |
| Phase 22 complete | All adapters wired, LLM bridge functional |
| `python -m pytest tests/ -x` passes | Green on all Phase 21+22 tests |
| Node.js 18+ installed | For TypeScript compilation |
| VS Code Extension API familiarity | For chat participant development |

---

## Dependency Graph

```
Step 1: ABSOrchestrator
   ↓
Step 2: CLI command group     Step 5: absParticipant.ts (independent)
   ↓                            ↓
Step 3: 5 CLI commands        Step 6: absRequestHandler.ts
   ↓                            ↓
Step 4: CLI smoke test        Step 7: absLLMBridge.ts
                                ↓
                              Step 8: absFollowups.ts
                                ↓
                              Step 9: package.json
                                ↓
Step 10: PyInstaller spec ←── Step 9
   ↓
Step 11: Build script
   ↓
Step 12: End-to-end validation
```

Steps 2–4 (CLI) and Steps 5–9 (Extension) can be done in parallel.

---

## Step-by-Step Plan

### Step 1: ABSOrchestrator (45 minutes)

**Create:** `backend/abs/orchestrator.py` (~200 lines)

The convergence layer that both CLI and chat participant delegate to.

**Implementation:**
1. Create `IngestResult`, `GenerateResult`, `AuditResult`, `QAResult`, `StatusResult` dataclasses
2. Implement `ABSOrchestrator.__init__(config, llm_callable)`
3. Implement `ingest()` — wires to `IngestionOrchestrator`
4. Implement `generate()` — wires to `ModelCreationAgent`
5. Implement `audit()` — wires to `AuditAgent`
6. Implement `qa()` — wires to `QAAgent`
7. Implement `status()` — wires to `DealManifest`

**Validation:**
```powershell
# Unit test
python -c "
from backend.abs.orchestrator import ABSOrchestrator, IngestResult
from config.settings import KTSConfig
orch = ABSOrchestrator(config=KTSConfig())
print('ABSOrchestrator instantiation: OK')
print('Result dataclasses:', IngestResult.__dataclass_fields__.keys())
"
```

---

### Step 2: CLI Command Group (15 minutes)

**Create:** `cli/abs/__init__.py` (~25 lines)

**Implementation:**
1. Create Click group `abs_group`
2. Import and register all 5 subcommands
3. Add `abs_group` to `cli/main.py`

**Validation:**
```powershell
python -m cli.main abs --help
# Should show: ingest, generate, audit, qa, status
```

---

### Step 3: CLI Commands (1.5 hours)

**Create:** 5 files in `cli/abs/` (~250 lines total)

| File | Lines | Options |
|------|-------|---------|
| `ingest_cmd.py` | ~55 | `--deal-id`, `--source-dir`, `--llm-mode`, `--force`, `-v` |
| `generate_cmd.py` | ~50 | `--deal-id`, `--output-dir`, `--llm-mode`, `--max-retries`, `-v` |
| `audit_cmd.py` | ~50 | `--deal-id`, `--model-path`, `--expected-csv`, `--llm-mode`, `-v` |
| `qa_cmd.py` | ~50 | `--deal-id`, `--query`, `--max-results`, `--llm-mode`, `-v` |
| `status_cmd.py` | ~25 | `--deal-id`, `-v` |

Each command follows the same pattern:
1. Parse options
2. Create `KTSConfig` and `create_llm_callable()`
3. Instantiate `ABSOrchestrator`
4. Call appropriate method
5. Format and display result

**Validation:**
```powershell
# Verify each command has correct options
python -m cli.main abs ingest --help
python -m cli.main abs generate --help
python -m cli.main abs audit --help
python -m cli.main abs qa --help
python -m cli.main abs status --help
```

---

### Step 4: CLI Smoke Test (30 minutes)

**Verify CLI works end-to-end with mock LLM.**

```powershell
# Status (no deal ingested)
python -m cli.main abs status

# Ingest with mock LLM
python -m cli.main abs ingest `
    --deal-id smoke_test `
    --source-dir deals/smoke_test `
    --llm-mode mock -v

# Generate with mock
python -m cli.main abs generate `
    --deal-id smoke_test `
    --llm-mode mock -v

# Q&A with mock
python -m cli.main abs qa `
    --deal-id smoke_test `
    --query "What is the Distribution Waterfall?" `
    --llm-mode mock -v

# Audit
python -m cli.main abs audit `
    --deal-id smoke_test `
    --llm-mode mock -v

# Status (after ingestion)
python -m cli.main abs status --deal-id smoke_test -v
```

---

### Step 5: Chat Participant Registration (30 minutes)

**Create:** `extension/src/abs/absParticipant.ts` (~45 lines)

**Implementation:**
1. Create `registerABSParticipant()` function
2. Call `vscode.chat.createChatParticipant('abs', handler)`
3. Set icon and followup provider
4. Push to `context.subscriptions`

**Modify:** `extension/src/extension.ts`
1. Import `registerABSParticipant`
2. Call in `activate()`

**Validation:**
```powershell
cd extension
npx tsc --noEmit
# Should compile without errors
```

---

### Step 6: Request Handler (1 hour)

**Create:** `extension/src/abs/absRequestHandler.ts` (~250 lines)

**Implementation:**
1. Define `ABSSessionState` interface
2. Implement `handleABSRequest()` — main router
3. Implement `cmdIngest()`, `cmdGenerate()`, `cmdAudit()`, `cmdStatus()`, `cmdQA()`
4. Implement `detectDealId()` — regex + history search

**Validation:**
```powershell
cd extension
npx tsc --noEmit
```

---

### Step 7: LLM Bridge (45 minutes)

**Create:** `extension/src/abs/absLLMBridge.ts` (~90 lines)

**Implementation:**
1. Implement `getModel(tier)` — two-tier model selection
2. Implement `handleLLMRequest()` — forward LLM requests to VS Code API
3. Implement `spawnBackend()` — delegate to existing `PythonIPC`

**Validation:**
```powershell
cd extension
npx tsc --noEmit
```

---

### Step 8: Follow-ups Provider (15 minutes)

**Create:** `extension/src/abs/absFollowups.ts` (~45 lines)

**Implementation:**
1. Switch on `result.metadata.command`
2. Return contextual follow-up suggestions

**Validation:**
```powershell
cd extension
npx tsc --noEmit
```

---

### Step 9: Package Configuration (30 minutes)

**Modify:** `extension/package.json`

**Implementation:**
1. Add `@abs` entry to `contributes.chatParticipants`
2. Define 4 slash commands: `/ingest`, `/generate`, `/audit`, `/status`
3. Set description, icon, sticky flag

**Also create:** `backend/abs/ipc_protocol.py` (~40 lines) and `backend/abs/streaming.py` (~70 lines)

**Validation:**
```powershell
# Validate JSON
python -c "import json; json.load(open('extension/package.json'))"

# Check participant registration
python -c "
import json
pkg = json.load(open('extension/package.json'))
participants = pkg['contributes']['chatParticipants']
names = [p['name'] for p in participants]
assert 'kts' in names and 'abs' in names
print(f'Chat participants: {names}')
"
```

---

### Step 10: PyInstaller Configuration (30 minutes)

**Modify:** `packaging/kts.spec`

**Implementation:**
1. Add all `backend.abs.*` modules to `hiddenimports`
2. Add all `cli.abs.*` modules to `hiddenimports`
3. Add ABS data files to `datas`

**Validation:**
```powershell
# Verify spec is valid Python
python -c "exec(open('packaging/kts.spec').read())"

# Test build (may take several minutes)
pyinstaller packaging/kts.spec --noconfirm --clean 2>&1 | Select-Object -Last 5
```

---

### Step 11: Build Script (15 minutes)

**Create:** `scripts/build_combined.ps1` (~40 lines)

**Implementation:**
1. Build Python backend with PyInstaller
2. Compile TypeScript
3. Run tests
4. Package VSIX

**Validation:**
```powershell
# Dry run (check script syntax)
powershell -File scripts/build_combined.ps1 -Version "0.0.1-test"
```

---

### Step 12: End-to-End Validation (1 hour)

**Full validation checklist:**

```powershell
# ═══════════════════════════════════════════════
# Phase 23 Final Validation
# ═══════════════════════════════════════════════

Write-Host "=== 1. Python tests ==="
python -m pytest tests/ -x -q --tb=short

Write-Host "`n=== 2. TypeScript compilation ==="
Push-Location extension
npx tsc --noEmit
Pop-Location

Write-Host "`n=== 3. CLI commands ==="
python -m cli.main abs --help
python -m cli.main abs status

Write-Host "`n=== 4. Package.json validation ==="
python -c "
import json
pkg = json.load(open('extension/package.json'))
ps = pkg['contributes']['chatParticipants']
abs_p = [p for p in ps if p['name'] == 'abs'][0]
cmds = [c['name'] for c in abs_p['commands']]
assert cmds == ['ingest', 'generate', 'audit', 'status']
print(f'@abs commands: {cmds}  ✅')
"

Write-Host "`n=== 5. Orchestrator import ==="
python -c "
from backend.abs.orchestrator import ABSOrchestrator
print('ABSOrchestrator import: ✅')
"

Write-Host "`n=== 6. IPC protocol types ==="
python -c "
from backend.abs.ipc_protocol import ProgressMessage, LLMRequest, LLMResponse
print('IPC types import: ✅')
"

Write-Host "`n=== 7. Streaming module ==="
python -c "
from backend.abs.streaming import ABSStream
s = ABSStream(mode='terminal')
s.progress('Test step', 'done')
print('Streaming: ✅')
"

Write-Host "`n=== PHASE 23 VALIDATION COMPLETE ==="
```

---

## Effort Summary

| Step | Task | Time | Dependency |
|------|------|------|-----------|
| 1 | ABSOrchestrator | 45 min | Phase 22 complete |
| 2 | CLI command group | 15 min | Step 1 |
| 3 | 5 CLI commands | 1.5 hrs | Step 2 |
| 4 | CLI smoke test | 30 min | Step 3 |
| 5 | Chat participant reg | 30 min | None (parallel) |
| 6 | Request handler | 1 hr | Step 5 |
| 7 | LLM bridge | 45 min | Step 6 |
| 8 | Follow-ups | 15 min | Step 7 |
| 9 | Package config | 30 min | Step 8 |
| 10 | PyInstaller spec | 30 min | Step 9 |
| 11 | Build script | 15 min | Step 10 |
| 12 | End-to-end validation | 1 hr | All steps |
| **Total** | | **~8 hrs** | |

---

## Rollback Strategy

### If Any CLI Command Fails

```powershell
# Remove ABS CLI registration from cli/main.py
# Revert to pre-Phase 23 state:
git checkout -- cli/main.py
# ABS CLI directory can remain (unused if not registered)
```

### If Chat Participant Fails

```powershell
# Remove ABS registration from extension.ts
git checkout -- extension/src/extension.ts
# Remove @abs from package.json:
git checkout -- extension/package.json
```

### If Build Fails

```powershell
# Revert PyInstaller spec:
git checkout -- packaging/kts.spec
# Build KTS-only VSIX (pre-Phase 23 behavior):
pyinstaller packaging/kts.spec --noconfirm --clean
```

### Nuclear Option

```powershell
# Revert all Phase 23 changes:
git stash
# Or if committed:
git revert HEAD~1
```

Phase 23 is designed to be **fully separable** — removing ABS CLI and chat participant does not affect any KTS functionality.
