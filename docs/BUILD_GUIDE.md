# Build Guide

This repository packages one VSIX containing the KTS and ABS Waterfall extension surfaces. The current extension manifest version is `0.0.9`; set a release version deliberately during packaging.

## Prerequisites

- Python 3.10+ and a project virtual environment.
- Node.js 18+ and npm.
- PowerShell for the maintained combined packaging script.
- PyInstaller and VS Code Extension Manager (`@vscode/vsce`), installed by the project's Python/npm setup as applicable.

Use [Developer Setup](DEVELOPER_SETUP.md) to prepare the source environment before building.

## Validate Before Packaging

From the repository root:

```bash
source .venv/bin/activate
python -m pytest tests/ -q
cd extension && npm test
```

Validate the source CLI interfaces that are packaged with the backend:

```bash
source .venv/bin/activate
python -m cli.main --help
python -m cli.main abs --help
```

## Combined VSIX Build

On Windows, run:

```powershell
.\scripts\build_combined.ps1 -Version "0.0.9"
```

The script performs these stages unless skipped:

1. Runs the Python test suite.
2. Bundles the Python backend when its build script is available.
3. Validates that both `@kts` and `@abs` are declared in `extension/package.json` and that the ABS modes are present.
4. Packages the extension with `@vscode/vsce`.

Common variants:

```powershell
.\scripts\build_combined.ps1 -SkipTests
.\scripts\build_combined.ps1 -SkipBackend
.\scripts\build_combined.ps1 -DryRun
```

`build_combined.ps1` writes the requested version to `extension/package.json`. Review that change together with the generated `.vsix` before committing.

## Backend and Model Assets

The backend package depends on local embedding assets. Download them before a fresh bundle when needed:

```bash
bash scripts/download_models.sh
```

On Windows use the corresponding PowerShell download script. The PyInstaller spec expects BGE ONNX assets at `packaging/models/bge/`, with tokenizer files alongside the model. See the packaging spec and model-download scripts when changing model versions or asset layout.

The extension resolves backend executables by platform, including macOS, Windows, and Linux naming conventions. Verify the actual generated bundle layout for every target platform; a successful package on one platform is not evidence that another platform's executable is present.

## Release Checks

Before publishing:

1. Install the VSIX in an isolated VS Code profile.
2. Confirm **ABS Waterfall: Open** renders the webview.
3. Confirm both `@kts` and `@abs` appear in Copilot Chat.
4. Exercise a KTS crawl/ingest/search cycle against a small corpus.
5. Exercise ABS ingest, generate, audit, and status against a test deal.
6. Inspect `KTS` and `ABS Waterfall` output channels for backend startup issues.

The release workflow in `.github/workflows/release.yml` and `scripts/release.ps1` publishes VSIX and checksum assets for tagged releases. Keep model bundles and generated runtime data out of source control unless they are intentional release assets.