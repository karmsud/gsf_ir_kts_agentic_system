# Developer Setup

This guide describes the supported source-development workflow for the combined KTS and ABS Waterfall VS Code extension. It supersedes older instructions that refer to separate KTS model extensions, Windows-only development, or a mandatory VSIX rebuild for every edit.

## Prerequisites

- VS Code `1.95.0` or later, with GitHub Copilot available for AI-backed flows.
- Python `3.10+` with `venv` support.
- Node.js `18+` and npm.
- Git.
- On Windows, PowerShell for the packaging scripts.
- On macOS, `bash` for `scripts/setup_env.sh`.

The source workflow requires internet access to install Python and npm dependencies. Runtime use is local except when a Copilot-backed operation is requested.

## Clone and Prepare the Environment

From the repository root on macOS:

```bash
bash scripts/setup_env.sh
source .venv/bin/activate
cd extension
npm install
cd ..
```

`setup_env.sh` creates `.venv`, installs the backend dependencies, downloads the spaCy model, and verifies core imports. Download the local embedding assets when the retrieval workflow requires them:

```bash
bash scripts/download_models.sh
```

On Windows, create and activate a virtual environment, install `requirements.txt`, then install the extension dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cd extension
npm install
cd ..
```

Use `python -m spacy download en_core_web_sm` if the validation step reports that the spaCy model is missing.

## Run from Source

Open the repository in VS Code and press **F5**. VS Code launches an Extension Development Host with the extension loaded directly from `extension/`.

In the development host:

1. Run **ABS Waterfall: Open** to exercise the webview and its JSON-lines backend process.
2. Use `@kts` for document intelligence or `@abs` for deal-model operations.
3. Reload the development host after JavaScript changes.
4. Re-run the affected operation after Python changes; source-mode backend invocations load the current Python code.

Use the `KTS` and `ABS Waterfall` output channels for diagnostics. Do not use a production VSIX as the normal edit-test loop.

## Local Configuration

The extension's backend mode defaults to `auto`, which prefers a compatible bundled executable when one exists. For source development, configure these workspace settings:

```json
{
  "kts.backendMode": "venv",
  "kts.backendChannel": "workspace",
  "kts.pythonPath": "/absolute/path/to/ABS_Waterfall/.venv/bin/python"
}
```

On Windows, use the equivalent `.venv\\Scripts\\python.exe` path. `kts.pythonPath` is optional when the extension can discover Python, but pinning it removes ambiguity when multiple interpreters are installed.

The ABS webview resolves its deal root from the open workspace folder. Its development backend uses `ABS_PYTHON` when set; otherwise it invokes `python3`. Set `ABS_PYTHON` to the virtual-environment interpreter if `python3` does not resolve to the intended environment.

## Validate Changes

Run the narrowest appropriate checks before packaging:

```bash
source .venv/bin/activate
python -m pytest tests/ -q
cd extension && npm test
```

Use the Command Palette entries **KTS: Run Golden Answer Tests** and **KTS: Run TS Guide Golden Tests** only in an Extension Development Host. They are development-only commands and are not included in the packaged VSIX.

For a basic backend smoke check:

```bash
source .venv/bin/activate
python -m cli.main --help
python -m cli.main abs --help
```

## Package a VSIX

The combined packaging script validates the two chat participants, runs Python tests unless skipped, bundles the backend when available, and packages the extension:

```powershell
.\scripts\build_combined.ps1
```

Useful variants:

```powershell
.\scripts\build_combined.ps1 -SkipTests
.\scripts\build_combined.ps1 -SkipBackend
.\scripts\build_combined.ps1 -DryRun
```

The script updates the extension version before packaging. Review the resulting working-tree change intentionally before committing or publishing. For backend model-layout requirements and release steps, use the [Build Guide](BUILD_GUIDE.md).

## Common Problems

| Symptom | Check |
|---|---|
| `ABS Waterfall: Open` does not open | Check the `KTS` output channel for a panel-load error and verify `extension/panels/abs_app.js` plus `extension/media/abs/` are present. |
| ABS backend cannot start | Activate `.venv`, set `ABS_PYTHON` if necessary, and run `python -m backend.abs.serve --help`. |
| KTS backend cannot start | Set `kts.backendMode` to `venv`, `kts.backendChannel` to `workspace`, and point `kts.pythonPath` at the active environment. Then run **KTS: Doctor (Diagnostics)**. |
| Retrieval models are missing | Run `bash scripts/download_models.sh` on macOS or the equivalent model-download PowerShell script on Windows. |
| A change is absent in the dev host | Reload the Extension Development Host after JavaScript changes; re-run the command after Python changes. |

The [user guide](USER_GUIDE.md) describes end-user workflows; keep implementation and packaging details in this document and the [Build Guide](BUILD_GUIDE.md).