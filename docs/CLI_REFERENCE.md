# CLI Reference

Use the source CLI from an activated project virtual environment:

```bash
python -m cli.main --help
python -m cli.main abs --help
```

The extension normally invokes these interfaces for you. The CLI is useful for development, automation, and narrow backend diagnostics.

## KTS Commands

### Crawl

Scans source paths and updates the manifest.

```bash
python -m cli.main crawl --paths /path/to/documents
python -m cli.main crawl --paths /path/to/documents --dry-run
```

Options: `--paths` can be repeated; `--dry-run` reports changes without persisting them; `--force` requests a complete scan.

### Ingest

Converts, classifies, chunks, and indexes files. When a supplied root contains direct subfolders, ingestion can create per-folder knowledge scopes.

```bash
python -m cli.main ingest --paths /path/to/documents
python -m cli.main ingest --paths /path/to/document.pdf --doc-type GOVERNING_DOC
```

Options: `--paths` can be repeated, `--doc-type` overrides automatic classification, and `--force` is retained for forward-compatible automation.

### Other KTS Operations

Run `python -m cli.main --help` for the complete command set supported by the current checkout. The extension also exposes user-oriented equivalents through the Command Palette, where it handles workspace paths and structured output.

## ABS Commands

ABS commands are grouped under `abs`:

```bash
python -m cli.main abs ingest --help
python -m cli.main abs generate --help
python -m cli.main abs audit --help
python -m cli.main abs qa --help
python -m cli.main abs status --help
```

Typical source-mode workflow:

```bash
python -m cli.main abs ingest --deal-id example_deal --source-dir ./deals/example_deal
python -m cli.main abs generate --deal-id example_deal
python -m cli.main abs audit --deal-id example_deal
python -m cli.main abs qa --deal-id example_deal -q "What is the payment waterfall?"
python -m cli.main abs status
```

Use each command's `--help` output for exact flags. Those options evolve with the orchestration models, while the webview and `@abs` participant remain the preferred interactive interfaces.

## Output and Errors

Commands return structured output where the extension expects JSON. Progress and diagnostic details may be written to standard error. Preserve standard output when scripting commands, and inspect the `KTS` or `ABS Waterfall` output channels when invoking the same operation through VS Code.