# Phase A: Development Environment Setup

**Created:** 2026-02-20  
**Status:** APPROVED — Ready for Implementation  
**Effort:** 1 hour  
**Priority:** P0 — Do First (everything else depends on this)

---

## 1. Problem Statement

### Current Development Cycle (10-15 minutes per iteration)

```
1. Edit JavaScript file                                    (~1 min)
2. Run build_vsix.ps1                                     (~3 min)
   - npx @vscode/vsce package
   - Produces 222 MB .vsix file
3. Install VSIX via Extensions panel                       (~1 min)
   - Extensions → "..." → Install from VSIX...
   - Wait for install
4. Reload VS Code window                                   (~30 sec)
5. Re-ingest test document (if backend changed)            (~5 min)
6. Open Copilot Chat, type question                        (~30 sec)
7. Wait for answer                                         (~15-30 sec)
8. Copy Output panel logs                                  (~30 sec)
9. Paste into chat with agent for analysis                 (~1 min)
10. Agent analyzes, suggests fix                           (~2 min)
11. GOTO step 1
```

**Total: 10-15 minutes per edit-test cycle.**
**At 10 iterations per feature: 2.5 hours per feature just on the build loop.**

### Target Development Cycle (< 5 seconds per iteration)

```
1. Edit JavaScript file                                    (~30 sec)
2. Save (Ctrl+S)                                           (~0 sec)
3. In Extension Development Host: Ctrl+R (reload)          (~2 sec)
4. Type question in chat                                   (~15 sec)
5. See answer immediately                                  (~15-30 sec)
```

**Total: < 1 minute including think time.**

---

## 2. What Is the Extension Development Host?

VS Code provides a built-in debugging workflow for extension development:

1. Press **F5** (or Run → Start Debugging)
2. VS Code launches a **second VS Code window** — the "Extension Development Host"
3. This second window runs your extension **from source** (not from a .vsix)
4. The first window (your editor) shows the Debug Console with live logs
5. When you edit JS files and save, press **Ctrl+R** in the dev host to reload
6. Changes take effect instantly — no build, no install, no VSIX

This is the **standard way** VS Code extensions are developed. We should have been using
this from day 1.

---

## 3. Implementation Plan

### 3.1 Create `.vscode/launch.json`

**File:** `c:\Users\Karmsud\Projects\gsf_ir_kts_agentic_system\.vscode\launch.json`

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Run KTS Extension (Dev Host)",
      "type": "extensionHost",
      "request": "launch",
      "args": [
        "--extensionDevelopmentPath=${workspaceFolder}/extension"
      ],
      "outFiles": [],
      "preLaunchTask": "",
      "env": {
        "KTS_DEV_MODE": "true",
        "KTS_LOG_LEVEL": "DEBUG"
      }
    },
    {
      "name": "Run KTS Extension (Dev Host + Test Folder)",
      "type": "extensionHost",
      "request": "launch",
      "args": [
        "--extensionDevelopmentPath=${workspaceFolder}/extension",
        "${workspaceFolder}/Knowledge Base test"
      ],
      "outFiles": [],
      "env": {
        "KTS_DEV_MODE": "true",
        "KTS_LOG_LEVEL": "DEBUG"
      }
    }
  ]
}
```

**What each field does:**

| Field | Value | Purpose |
|-------|-------|---------|
| `type` | `"extensionHost"` | Launches a VS Code Extension Development Host (not a generic debug session) |
| `request` | `"launch"` | Start a new dev host (vs. attaching to running one) |
| `args[0]` | `--extensionDevelopmentPath` | Points to the folder containing `package.json` and `extension.js` — our `extension/` directory |
| `args[1]` (2nd config) | Test folder path | Opens the dev host with the test corpus folder already loaded as workspace |
| `env.KTS_DEV_MODE` | `"true"` | Tells the extension to prefer venv over bundled exe |
| `env.KTS_LOG_LEVEL` | `"DEBUG"` | Maximum verbosity in dev mode |

### 3.2 Create `.vscode/settings.json` (Workspace Dev Defaults)

**File:** `c:\Users\Karmsud\Projects\gsf_ir_kts_agentic_system\.vscode\settings.json`

```json
{
  "kts.backendMode": "venv",
  "kts.logLevel": "DEBUG",
  "kts.backendChannel": "workspace",
  "files.exclude": {
    "**/__pycache__": true,
    "**/.pytest_cache": true,
    "**/build": true,
    "**/dist": true,
    "**/*.pyc": true
  },
  "search.exclude": {
    "**/node_modules": true,
    "**/.venv*": true,
    "**/build": true,
    "**/dist": true,
    "**/temp_*": true,
    "**/__pycache__": true
  }
}
```

**Key setting: `kts.backendMode: "venv"`**

This tells the extension to run the Python backend from the live source code in the
virtual environment, not from the compiled `kts-backend.exe`. When you change a
Python file, the next search call picks up the change immediately — no recompile needed.

The `backendChannel: "workspace"` setting tells the extension to look for backend code
in the workspace tree (git repo) rather than the bundled VSIX copy.

### 3.3 Backend Mode Flow (Already Implemented)

The extension already supports `venv` mode. Here's the existing flow in
`extension/extension.js` lines 43-60:

```javascript
async function bootstrapBackend(context, backendMode, backendChannel, ...) {
  // If exe mode or auto mode, check if exe exists
  if (backendMode === 'exe' || backendMode === 'auto') {
    const exePath = path.join(context.extensionPath, 'bin', 'win-x64', 'kts-backend', 'kts-backend.exe');
    if (fs.existsSync(exePath)) {
      outputChannel.appendLine('[KTS] Executable backend found. Skipping venv bootstrap.');
      return;
    }
    // Falls through to venv if exe not found
  }
  // Bootstrap venv...
}
```

And in `extension/copilot/kts_tool.js`, the tool selects between exe and venv:

```javascript
// Dispatches to either:
// 1. kts-backend.exe search <query> --flags
// 2. python -m cli.main search <query> --flags
```

**No backend code changes needed.** The venv path already works. We just need to
configure it as the default for development.

### 3.4 Verify the Virtual Environment

The dev host needs a working Python venv. Run this check:

```powershell
# Verify the build venv exists and has all dependencies
& .\.venv_build\Scripts\Activate.ps1
python -c "import backend; print('Backend importable')"
python -m cli.main --help
```

Expected output:
```
Backend importable
usage: main.py [-h] {crawl,ingest,search,...}
```

If this fails, the venv needs to be set up:
```powershell
python -m venv .venv_build
& .\.venv_build\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3.5 The Dev Workflow (Step by Step)

After setup, the daily development workflow is:

```
┌─────────────────────────────────────────────────────────────┐
│ EDITOR WINDOW (your main VS Code)                            │
│                                                              │
│  1. Open the project folder                                  │
│  2. Edit any file:                                           │
│     - extension/chat/participant.js (prompts, pipeline)      │
│     - extension/lib/*.js (Self-RAG, gap analyzer, etc.)      │
│     - backend/**/*.py (retrieval, graph, ingestion)          │
│     - config/settings.py (parameters)                        │
│  3. Save (Ctrl+S)                                            │
│  4. Press F5 → launches dev host                             │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│ EXTENSION DEVELOPMENT HOST (second VS Code window)           │
│                                                              │
│  5. The KTS extension is running from source                 │
│  6. Open Copilot Chat → type @kts <question>                 │
│  7. See the answer immediately                               │
│  8. Check Output panel (KTS channel) for debug logs          │
│                                                              │
│  After editing JS files:                                     │
│  9. Press Ctrl+R in the dev host → extension reloads         │
│  10. Type question again → see updated behavior              │
│                                                              │
│  After editing Python files:                                 │
│  11. No reload needed — next search call uses live source    │
│                                                              │
│  To stop:                                                    │
│  12. Close the dev host window (or press Shift+F5 in editor) │
└─────────────────────────────────────────────────────────────┘
```

**Key shortcuts:**
- **F5** — Launch dev host
- **Ctrl+R** (in dev host) — Reload extension (picks up JS changes)
- **Shift+F5** — Stop debugging
- **Ctrl+Shift+Y** (in dev host) — Open Output panel for logs

---

## 4. What About Ingestion?

Ingestion (crawl + ingest) still takes 3-5 minutes for the Bear Stearns PSA.
But you only need to re-ingest when:

1. You change the **ingestion pipeline** (chunking, graph building, embedding)
2. You change the **crawl** logic
3. You want to test with a different document

For retrieval/generation changes (which is 90% of our current work), the ingested
data persists in the `.kts/` workspace folder. You ingest once, then iterate on
retrieval/prompt changes indefinitely without re-ingesting.

**Workflow for ingestion changes:**

```
1. Edit ingestion code
2. In dev host: run "KTS: Crawl & Ingest" command (Ctrl+Shift+P)
3. Wait for ingestion to complete
4. Test retrieval normally
```

---

## 5. Testing Backend Changes Without the Extension

For pure backend changes (retrieval logic, graph queries), you can test directly
via the CLI without even launching the dev host:

```powershell
# Activate the build venv
& .\.venv_build\Scripts\Activate.ps1

# Run a search query directly
python -m cli.main search "What does Distribution Date mean?" `
  --workspace "path/to/.kts/folder" `
  --max-results 25 `
  --format json

# Run with verbose logging
python -m cli.main search "What is the distribution waterfall?" `
  --workspace "path/to/.kts/folder" `
  --max-results 50 `
  --deep `
  --log-level DEBUG
```

This is useful for:
- Debugging retrieval ranking changes
- Testing new backend features before wiring them to the extension
- Running automated tests (golden test harness will use this)

---

## 6. Files Created / Modified

| Action | File | Purpose |
|--------|------|---------|
| CREATE | `.vscode/launch.json` | F5 extension dev host configuration |
| CREATE | `.vscode/settings.json` | Workspace defaults for dev mode |
| VERIFY | `.venv_build/` | Ensure Python venv is functional |
| EDIT | `README.md` | Add "Development Workflow" section |

---

## 7. Acceptance Criteria

- [ ] Pressing F5 in the editor launches a second VS Code window (Extension Development Host)
- [ ] The dev host shows "KTS Knowledge Assistant" as an active extension
- [ ] In the dev host, `@kts what is Distribution Date?` produces an answer
- [ ] The Output panel (KTS channel) in the dev host shows debug logs
- [ ] Editing `extension/chat/participant.js`, saving, pressing Ctrl+R in dev host, and re-asking shows the updated behavior
- [ ] Editing a Python file (e.g., adding a log line to `retrieval_service.py`), then running a query in the dev host shows the new log line in the Output panel
- [ ] The dev host uses `venv` mode (not exe) — verified by Output panel showing `python -m cli.main` commands, not `kts-backend.exe`

---

## 8. Common Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| F5 does nothing | No `launch.json` | Create the file per section 3.1 |
| Dev host opens but extension not active | Wrong `extensionDevelopmentPath` | Must point to `extension/` (the folder with `package.json`), not the repo root |
| "Cannot find module 'vscode'" in Debug Console | Normal — `vscode` is provided by the host | Ignore; this is only an issue if the extension crashes on activate |
| Backend search returns error | Venv not set up or wrong Python | Run `python -m cli.main --help` to verify |
| Changes not reflected after Ctrl+R | Browser-cached JS module | Close dev host completely, F5 again |
| Ingestion fails in dev mode | Missing models in venv | Run `python scripts/download_models.py` |
| Output panel empty | Wrong channel selected | Select "KTS" (not "Log (Extension Host)") |

---

## 9. Why We Should Have Done This on Day 1

The Extension Development Host is the **standard** VS Code extension development experience.
It's documented in the [VS Code Extension Development Guide](https://code.visualstudio.com/api/get-started/your-first-extension).
Every extension in the VS Code marketplace was developed using F5.

We skipped this setup because the initial focus was on the backend Python pipeline, and the
extension was treated as a thin shell. But the extension has grown to 1,920 lines of JavaScript
with complex multi-stage orchestration (prompt selection, context building, Self-RAG, critique,
follow-ups). At this scale, the 10-minute VSIX cycle is an engineering bottleneck that dwarfs
the actual coding time.

One hour of setup saves hundreds of hours of iteration time.
