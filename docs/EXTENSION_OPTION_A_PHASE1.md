# Extension Option A Phase 1: Self-Contained Architecture

## Implementation Summary

**Date**: February 14, 2026  
**Backend Version**: 1.0.0  
**Extension Version**: 1.0.0

## Objective
Transform the KTS VS Code extension from Option B (thin wrapper requiring repo checkout) to Option A1 (self-contained extension with bundled backend).

## Key Changes

### 1. Architecture Shift
**Before (Option B)**:
- Extension expected user to clone repo
- Required `.venv` in workspace root
- Ran `python -m cli.main` from workspace

**After (Option A1)**:
- Extension bundles Python backend
- Creates managed venv in VS Code global storage
- No repo checkout required
- Users only need Python installed

### 2. Components Implemented

#### A. Backend Bundler (`extension/scripts/bundle_backend.ps1`)
- Packages minimal runtime backend into `extension/backend_bundle/`
- Includes: `cli/`, `backend/`, `config/`, `requirements.txt`
- Excludes: tests, `__pycache__`, dev files
- Creates version metadata

#### B. Venv Manager (`extension/lib/venv_manager.js`)
- Detects system Python (`py -3`, `python3`, `python`)
- Creates venv in `<globalStorage>/kts-venv/<version>/`
- Unpacks backend to `<globalStorage>/kts-backend/<version>/`
- Installs dependencies from bundled `requirements.txt`
- Performs health checks
- Provides diagnostics

#### C. Backend Bridge (`extension/lib/kts_backend.js`)
- Refactored to use managed venv
- Sets `KTS_KB_PATH` environment variable
- Supports both "bundled" and "workspace" channels
- KB workspace defaults to `<globalStorage>/kts-kb/default/`

#### D. New Commands
1. **KTS: Select Source Folder** - Configure source path
2. **KTS: Crawl** - Crawl source files
3. **KTS: Ingest** - Ingest documents
4. **KTS: Status** - Show KB status
5. **KTS: Search** - Interactive search
6. **KTS: Doctor** - Comprehensive diagnostics
7. **KTS: Open Logs** - Open logs directory

#### E. Configuration Settings (`contributes.configuration`)
- `kts.sourcePath` - Network/local folder with KB documents
- `kts.kbWorkspacePath` - Local KB workspace (default: global storage)
- `kts.pythonPath` - Optional Python path override
- `kts.backendChannel` - "bundled" (default) or "workspace" (dev mode)
- `kts.logLevel` - Log verbosity

### 3. Bootstrap Flow

1. **Extension Activation** (`onStartupFinished`)
2. **VenvManager Initialization**
3. **Bootstrap Check**:
   - Is venv valid?
   - If NO → Run bootstrap:
     a. Detect Python
     b. Create venv in global storage
     c. Unpack backend bundle
     d. Install dependencies
     e. Health check
   - If YES → Skip bootstrap
4. **Register Commands**
5. **Ready**

### 4. File Structure

```
extension/
├── backend_bundle/          # (Generated) Bundled Python backend
│   ├── cli/
│   ├── backend/
│   ├── config/
│   ├── requirements.txt
│   └── backend_version.json
├── commands/
│   ├── crawl.js
│   ├── ingest.js
│   ├── status.js
│   ├── search.js
│   ├── select_source.js
│   ├── doctor.js
│   ├── open_logs.js
│   └── ... (legacy commands)
├── lib/
│   ├── kts_backend.js       # Backend bridge
│   └── venv_manager.js      # Venv lifecycle manager
├── scripts/
│   └── bundle_backend.ps1   # Backend bundler script
├── dist/
│   └── gsf-ir-kts-1.0.0.vsix  # Packaged extension
├── extension.js              # Main entry point
├── package.json              # Extension manifest
├── .vscodeignore             # VSIX packaging rules
└── LICENSE                   # MIT License
```

### 5. Packaging

**Package Size**: 156.95 KB (111 files)  
**Backend Bundle**: 259.37 KB (86 files)  
**Output**: `extension/dist/gsf-ir-kts-1.0.0.vsix`

**Build Command**:
```powershell
cd extension
npm run package:vsix:no-deps
```

This runs:
1. `bundle_backend.ps1` - Creates `backend_bundle/`
2. `vsce package` - Creates VSIX

### 6. User Workflow

#### Installation
1. Download `gsf-ir-kts-1.0.0.vsix`
2. Install in VS Code: `Extensions → ... → Install from VSIX`
3. Extension auto-bootstraps on first activation

#### First Use
1. Extension activates → Shows "Setting up backend..."
2. Detects Python
3. Creates venv (~30-60 seconds)
4. Shows "Backend setup complete ✓"

#### Configuration
1. Run **KTS: Select Source Folder**
2. Choose network/local folder with documents

#### Operation
1. **KTS: Crawl** - Discover files
2. **KTS: Ingest** - Process into KB
3. **KTS: Search** - Query knowledge base
4. Chat with `@kts` in Copilot Chat

#### Troubleshooting
- **KTS: Doctor** - Shows diagnostics
- **KTS: Open Logs** - View operation logs

### 7. Storage Locations

Assuming global storage: `%APPDATA%\Code\User\globalStorage\gsf-ir.gsf-ir-kts-extension\`

```
globalStorage/
├── kts-venv/
│   └── 1.0.0/
│       ├── Scripts/
│       │   └── python.exe
│       └── Lib/
├── kts-backend/
│   └── 1.0.0/
│       ├── cli/
│       ├── backend/
│       └── config/
└── kts-kb/
    └── default/
        ├── manifest.json
        ├── documents/
        ├── vectors/
        ├── graph/
        └── logs/
```

### 8. Backward Compatibility

**Workspace Mode** (Dev/Testing):
- Set `kts.backendChannel` to `"workspace"`
- Extension falls back to Option B behavior
- Looks for `.venv` in workspace root
- Useful for development/debugging

### 9. Version Management

- Backend version from `backend_bundle/backend_version.json`
- Venv path includes version: `kts-venv/1.0.0/`
- Backend path includes version: `kts-backend/1.0.0/`
- Version bump → New venv created → Old one stays until manual cleanup

### 10. Known Limitations / Phase 1 Scope

**In Scope**:
- ✅ Self-contained extension
- ✅ Managed venv
- ✅ Bootstrap automation
- ✅ Basic commands (crawl, ingest, search)
- ✅ Diagnostics (doctor)
- ✅ Global storage KB workspace

**Out of Scope (Future Phases)**:
- ❌ Bundled Python runtime (still requires system Python)
- ❌ Wheelhouse for offline dependency install
- ❌ Multi-profile KB workspaces
- ❌ Auto-update mechanism
- ❌ Telemetry/usage tracking

### 11. Testing Checklist

See [EXTENSION_USER_GUIDE.md](EXTENSION_USER_GUIDE.md) for acceptance test procedure.

## Success Criteria

✅ **No Repo Checkout Required**: Users don't clone repo  
✅ **No Manual Venv Setup**: Extension auto-creates venv  
✅ **Self-Contained Backend**: Backend bundled in VSIX  
✅ **Network Source Path**: Points to network KB folder  
✅ **Works on Clean Machine**: Only Python prerequisite  

## Deliverables

1. ✅ Refactored extension code
2. ✅ Backend bundler script
3. ✅ Venv manager
4. ✅ New commands (doctor, crawl, ingest, etc.)
5. ✅ Configuration schema
6. ✅ Packaged VSIX (`dist/gsf-ir-kts-1.0.0.vsix`)
7. ✅ Documentation (this file + user guide)

## Next Steps (Phase 2)

1. **Bundled Python Embed**: Include `python-embed-win64` to eliminate Python install requirement
2. **Wheelhouse**: Pre-bundle `.whl` files for offline install
3. **Auto-Update**: Check for backend updates
4. **Multi-Profile**: Support multiple KB profiles (e.g., "production", "staging")
5. **Telemetry**: Optional usage tracking
6. **Signing**: Code signing for enterprise distribution
