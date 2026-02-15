# KTS VS Code Extension Documentation

**Source of Truth**: `extension/package.json`, `extension/extension.js`

## 1. Overview

The KTS VS Code Extension provides the frontend UI for the Retrieval Augmented Generation system. It manages the Python backend process and integrates with Copilot via the `@kts` chat participant.

## 2. Deployment Architecture

The extension ships in two variants (Tiers) to support different enterprise environments:

### Option A2 (Full)
- **Artifact**: `gsf-ir-kts-1.1.0.vsix` (~41 MB)
- **Features**: Full support for `.pdf`, `.pptx`, `.docx`.
- **Backend**: Bundled as a standalone executable (`kts-backend.exe`) built with PyInstaller.
- **Use Case**: Standard deployment where PDF/PPTX support is critical.

### Option A3 (Word + Images)
- **Artifact**: `gsf-ir-kts-1.1.0-a3.vsix` (~16 MB)
- **Features**: Reduced support (DOCX/HTML only). No PDF/PPTX.
- **Backend**: Stripped-down executable excluding large dependencies (`PyMuPDF`, `Pillow`).
- **Use Case**: Lightweight deployment for restricted environments or slow networks.

## 3. Installation Guide

### Prerequisites
- VS Code 1.96+ (Insiders or Stable)
- No Python installation required on end-user machine (backend is self-contained).

### Steps
1.  **Download VSIX**: Obtain the appropriate `.vsix` file (A2 or A3).
2.  **Open VS Code**: Go to Extensions view (`Ctrl+Shift+X`).
3.  **Install**: Click `...` > `Install from VSIX...`
4.  **Reload**: Reload window if prompted.

### Verification
1.  Open Command Palette (`Ctrl+Shift+P`).
2.  Run `KTS: Doctor` or `KTS: Status`.
3.  Look for `[KTS] Backend connected: Version 1.1.0`.

## 4. Build Instructions (for Devs)

To adhere to security policies, the backend must be built from source on a clean Windows environment.

### Prerequisites (Dev Machine)
- Windows 10/11
- Python 3.10+
- Node.js 16+
- PowerShell 5.1+

### Build Process
1.  **Clone Repo**: `git clone <repo_url>`
2.  **Setup venv**: `python -m venv .venv` and `pip install -r requirements.txt`.
3.  **Build Tier A2**:
    ```powershell
    .\scripts\build_backend_exe.ps1 -Tier A2 -Clean
    .\scripts\package_vsix.ps1 -Tier A2
    ```
4.  **Build Tier A3**:
    ```powershell
    python -m venv .venv_a3
    .\.venv_a3\Scripts\pip install -r requirements_a3.txt
    .\scripts\build_backend_exe.ps1 -Tier A3 -Clean
    .\scripts\package_vsix.ps1 -Tier A3
    ```

Artifacts will be in `extension/dist/`.

## 5. Usage

### Commands
- `@kts /search ...`: Search knowledge base.
- `@kts /describe_images`: Launch image description workflow.
- `KTS: Select Source`: Choose a folder to index.
- `KTS: View Status`: Open webview dashboard.

### Logging
Logs are written to the extension output channel (`Output` > `KTS`) and stored in the extension's global storage path.
