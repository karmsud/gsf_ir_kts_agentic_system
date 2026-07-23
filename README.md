# ABS Waterfall and KTS

Local document intelligence and structured-finance modeling in a single VS Code extension.

The extension provides two connected experiences:

- **KTS Knowledge Assistant** (`@kts`) indexes local document collections and answers questions with retrieved context and citations.
- **ABS Waterfall** (`@abs` and the **ABS Waterfall: Open** command) ingests deal documents, generates a payment-waterfall model, audits it against governing documents, and presents the workflow in a dedicated VS Code webview.

The Python backend runs locally. GitHub Copilot is used only for features that request language-model or vision assistance, such as answer generation, definition resolution, and model generation.

## What You Can Do

### Query a knowledge base with KTS

- Select a local source folder and ingest supported documents.
- Search with `@kts` using `/search`, `/deep`, `/define`, `/extract`, `/compare`, `/audit`, `/summary`, and `/scope`.
- Use the Command Palette for crawl, ingest, status, diagnostics, freshness, image-description, and scope-refresh workflows.
- Retrieve from local vector and graph indexes with document and section attribution where available.

### Build and audit an ABS waterfall

- Open **ABS Waterfall: Open** from the Command Palette.
- Ingest a governing PDF and organize processing by deal folder.
- Generate payment-waterfall models and supporting artifacts.
- Audit generated output against source material and ask deal-specific questions.
- Follow progress and diagnostics through the `ABS Waterfall` output channel.

The webview is the primary ABS workflow. The `@abs` participant also exposes `/ingest`, `/generate`, `/audit`, and `/status` for chat-driven work.

## Install a Release

1. Download the current `.vsix` from the repository's GitHub Releases page.
2. In VS Code, open the Command Palette and run **Extensions: Install from VSIX...**.
3. Select the downloaded file and reload VS Code when prompted.
4. Open the Command Palette and run **ABS Waterfall: Open**, or open Copilot Chat and address `@kts` or `@abs`.

The released VSIX may include a bundled backend for supported platform builds. When no compatible bundled executable is available, the extension can bootstrap and use a local Python environment; see the [developer setup guide](docs/DEVELOPER_SETUP.md) for the source workflow.

## Quick Start

### KTS document intelligence

1. Open the folder containing the documents you want to index in VS Code.
2. Run **KTS: Select Source Folder** and choose the source folder.
3. Run **KTS: Crawl & Ingest**.
4. In Copilot Chat, ask a question such as `@kts /search What are the payment priorities?`.

### ABS Waterfall

1. Open the workspace that will contain deal folders.
2. Run **ABS Waterfall: Open**.
3. Use the app to select and ingest a governing PDF, then generate and audit the model.
4. Use `@abs /status` to inspect a deal from chat, or `@abs /audit` to initiate an audit.

For full workflows, settings, and troubleshooting, see the [user guide](docs/USER_GUIDE.md).

## Development

The development workflow targets macOS and Windows. On macOS, the quickest initial setup is:

```bash
bash scripts/setup_env.sh
source .venv/bin/activate
```

Install the extension's JavaScript dependencies from `extension/`, then start an Extension Development Host with **F5**. The development host runs the extension directly from source, so JavaScript changes take effect after reloading that window; Python changes are picked up by the next backend invocation.

```bash
cd extension
npm install
```

Run focused validation from the repository root:

```bash
source .venv/bin/activate
python -m pytest tests/ -q
```

For platform-specific setup, packaging, and release validation, read [Developer Setup](docs/DEVELOPER_SETUP.md), [Build Guide](docs/BUILD_GUIDE.md), and [Testing](docs/TESTING.md).

## Repository Guide

- [User Guide](docs/USER_GUIDE.md): install, ingest, query, and ABS webview workflows.
- [Developer Setup](docs/DEVELOPER_SETUP.md): local environment and Extension Development Host workflow.
- [Build Guide](docs/BUILD_GUIDE.md): test, package, and release the combined VSIX.
- [Architecture](docs/ARCHITECTURE.md): runtime layers, data ownership, and request flows.
- [Configuration](docs/CONFIGURATION.md): supported settings and local data layout.
- [CLI Reference](docs/CLI_REFERENCE.md): source-mode KTS and ABS commands.
- [Testing](docs/TESTING.md): Python, extension, and packaging checks.

Historical phase plans, reports, and design proposals remain under `docs/phase*/`, `docs/redesign/`, and the dated report files. They are design history rather than current product documentation; the documents linked above are the maintained reference for GitHub readers.

## System Requirements

- VS Code `1.95.0` or later.
- GitHub Copilot access for AI-assisted KTS and ABS features.
- A compatible bundled backend for a fully packaged runtime, or Python 3.10+ for source and fallback development workflows.
- Node.js 18+ and npm to develop or package the extension.

## License

MIT. See [extension/LICENSE](extension/LICENSE).