# Building KTS Option A2 VSIX on a Fresh Windows Machine

This guide describes how to build the self-contained KTS extension (Option A2) from source on a clean Windows environment (e.g., US Bank laptop).

## Prerequisites

Ensure the following are installed:
1.  **Python 3.10+** (Add to PATH)
    - Verify: `python --version`
2.  **Node.js 16+** (Add to PATH)
    - Verify: `node --version`
    - Verify: `npm --version`
3.  **Git** (Add to PATH)
4.  **PowerShell 5.1+** (Default on Windows)

## Build Instructions

### 1. Clone Repository
```powershell
git clone <repo-url> gsf_ir_kts
cd gsf_ir_kts
```

### 2. Setup Python Environment
Create a virtual environment to build the backend executable.
```powershell
# Create venv
python -m venv .venv

# Activate venv
.\.venv\Scripts\Activate

# Install dependencies
pip install -r requirements.txt
pip install pyinstaller codesign
```

### 3. Build Backend Executable (Option A2)
This compiles the Python backend into a standalone `.exe` located in `extension/bin/win-x64/kts-backend`.
```powershell
# Run build script
.\scripts\build_backend_exe.ps1 -Clean
```

### 4. Package Extension (VSIX)
This packages the VS Code extension including the backend executable.
```powershell
cd extension

# Install Node dependencies
npm install

# Install vsce packaging tool (if not global)
npm install -g @vscode/vsce

# Package VSIX
# Use --allow-missing-repository if repo field is missing in package.json
npm run package:vsix
```
The output file `gsf-ir-kts-extension-1.1.0.vsix` will be in `extension/`.

### 5. Deployment
Copy the `.vsix` file to your network share or target location.

## Quick Verification (Smoke Test)

1.  **Install Extension**:
    - Open VS Code.
    - Extensions View -> `...` -> `Install from VSIX...`.
    - Select generated `.vsix`.

2.  **Verify Activation**:
    - Output Panel -> Select "KTS".
    - Look for: `[KTS] Executable backend found.`

3.  **Test Commands**:
    - `Ctrl+Shift+P` -> `KTS: Doctor` (Check health).
    - `Ctrl+Shift+P` -> `KTS: Status`.
