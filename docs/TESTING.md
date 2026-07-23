# Testing

Use the smallest check that exercises the change, then run the broader suites before packaging.

## Backend Tests

Activate the project environment and run the Python suite:

```bash
source .venv/bin/activate
python -m pytest tests/ -q
```

Run a focused module or test when working on a narrow backend behavior:

```bash
source .venv/bin/activate
python -m pytest tests/test_name.py -q
```

## Extension Tests

The extension's Node test command is declared in `extension/package.json`:

```bash
cd extension
npm test
```

## CLI Smoke Checks

These verify that the two documented command families load:

```bash
source .venv/bin/activate
python -m cli.main --help
python -m cli.main abs --help
```

For an ABS source-mode smoke test, also verify the IPC server can load:

```bash
source .venv/bin/activate
python -m backend.abs.serve --help
```

## Extension Development Host

Press **F5** in VS Code to run the extension from source. In the Development Host:

1. Confirm **ABS Waterfall: Open** renders a nonblank webview.
2. Confirm `@kts` and `@abs` appear in Copilot Chat.
3. Run a small KTS crawl, ingest, and search cycle.
4. Run ABS ingest, generate, audit, and status against a test deal.
5. Inspect the `KTS` and `ABS Waterfall` output channels.

The Command Palette entries **KTS: Run Golden Answer Tests** and **KTS: Run TS Guide Golden Tests** are development-host tools. They are registered only when the source test harness is present and are excluded from packaged VSIX releases.

## Package Validation

Before publishing a VSIX, run the combined build and install its output into an isolated VS Code profile. Validate the same two participant registrations, the ABS webview, backend startup, and a representative KTS and ABS workflow. See [Build Guide](BUILD_GUIDE.md) for the release checklist.