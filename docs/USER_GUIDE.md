# User Guide

ABS Waterfall and KTS are delivered together as a VS Code extension. KTS is the document-intelligence experience; ABS Waterfall is the structured-finance modeling experience. Both use local workspace data and may request GitHub Copilot for AI-assisted operations.

## Install and Verify

Install the release VSIX with **Extensions: Install from VSIX...**, then reload VS Code. Open **View: Output** and select `KTS` or `ABS Waterfall` to inspect startup and operation logs.

The extension contributes two Copilot Chat participants:

| Participant | Purpose |
|---|---|
| `@kts` | Search and analyze local document collections. |
| `@abs` | Ingest deal documents, generate a waterfall model, audit it, and inspect deal status. |

## KTS Workflow

1. Open the workspace that contains the document source folder.
2. Run **KTS: Select Source Folder**.
3. Run **KTS: Crawl & Ingest** for a full initial index, or **KTS: Crawl** and **KTS: Ingest** separately when you need control over each stage.
4. Ask `@kts /search <question>` in Copilot Chat.

Useful chat modes:

| Mode | Use |
|---|---|
| `/search` | Concise question answering with retrieved context and citations. |
| `/deep` | Broader retrieval for complex questions. |
| `/define` | Defined-term lookup and dependency chains. |
| `/extract` | Structured extraction of parties, dates, or amounts. |
| `/compare` | Side-by-side comparison across scopes. |
| `/audit` | Topic-clustering audit with risk tags. |
| `/summary` | Fixed five-section deal summary. |
| `/scope` | Discover or target available knowledge scopes. |

The Command Palette also includes **KTS: Status**, **KTS: Search**, **KTS: Doctor (Diagnostics)**, **KTS: Freshness Audit**, image-description actions, and **KTS: Refresh Knowledge Scopes**.

## ABS Waterfall Workflow

Open **ABS Waterfall: Open** from the Command Palette. This opens the dedicated webview, which is the main workflow for ABS modeling.

1. Choose or create a deal identifier.
2. Select the governing PDF and ingest it.
3. Generate the payment-waterfall model.
4. Review generated artifacts and run an audit against the governing document.
5. Use the application's Copilot action or `@abs` to ask deal-specific questions.

The same flow is available through `@abs` chat commands:

| Mode | Use |
|---|---|
| `/ingest` | Ingest deal documents. |
| `/generate` | Generate a payment-waterfall model. |
| `/audit` | Audit generated results against source material. |
| `/status` | Show processing status for a deal. |

Deal folders and generated artifacts are stored under the open workspace folder. Keep each deal in its own folder so source documents, extracted content, generated models, audit reports, logs, and run artifacts remain isolated.

## Settings

Open VS Code Settings and search for `KTS`. The primary settings are:

| Setting | Purpose |
|---|---|
| `kts.sourceFolder` | Source documents for the selected knowledge base. |
| `kts.knowledgeSourceRoot` | Root used for scope discovery. |
| `kts.logLevel` | `normal` or `verbose` diagnostic output. |
| `kts.model` | Model selection for answer generation. |

Advanced settings control query expansion, HyDE, retrieval pool sizes, cross-encoder reranking, BM25, critique, CRAG, chunking, and LLM context limits. See [Configuration](CONFIGURATION.md) before changing those defaults.

Developer-only backend settings (`kts.backendMode`, `kts.backendChannel`, `kts.pythonPath`, and `kts.kbWorkspacePath`) are for source and packaging workflows, not normal end-user configuration.

## Troubleshooting

| Problem | Action |
|---|---|
| No KTS results | Run **KTS: Status**, confirm the source folder, then run **KTS: Crawl & Ingest**. |
| Backend setup fails | Run **KTS: Doctor (Diagnostics)** and inspect the `KTS` output channel. |
| ABS webview does not open | Inspect the `KTS` output channel for panel-load errors, then reload VS Code. |
| ABS operation fails or stalls | Open the `ABS Waterfall` output channel; it includes backend progress and stderr diagnostics. |
| AI operation is unavailable | Sign in to GitHub Copilot and confirm a chat model is available in VS Code. |

For source-environment troubleshooting, see [Developer Setup](DEVELOPER_SETUP.md).