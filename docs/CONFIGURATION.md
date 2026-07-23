# Configuration

`extension/package.json` is the authoritative list of VS Code settings. This guide explains the settings by operational purpose; it does not duplicate transient defaults from older phase documents.

## Core KTS Settings

| Setting | Purpose |
|---|---|
| `kts.sourceFolder` | Folder containing documents to crawl and ingest. |
| `kts.knowledgeSourceRoot` | Root used to discover document scopes. |
| `kts.logLevel` | `normal` for operational output or `verbose` for detailed diagnostics. |
| `kts.model` | Model selection for answer generation; `auto` uses the active Copilot model. |

## Model and Retrieval Settings

The settings UI exposes advanced controls for retrieval quality and latency:

- `kts.models.*`: model selection for critique and query expansion.
- `kts.rag.*`: multi-query and HyDE behavior for legal and non-legal documents.
- `kts.retrieval.*`: candidate pools, maximum context chunks, cross-encoder, and BM25 controls.
- `kts.critique.*`: directed critique loop behavior.
- `kts.crag.*`: post-generation claim verification behavior.
- `kts.phase19.*`: non-legal triple-store and troubleshooting-graph features.
- `kts.chunking.*`: legal and non-legal chunk size, overlap, and contextual headers.
- `kts.context.*`: prompt chunk cap and token-budget reservations.

Defaults favor usable latency. Raise retrieval, critique, CRAG, or context limits only when improved coverage is worth additional model calls and processing time.

## Developer Runtime Settings

| Setting | Purpose |
|---|---|
| `kts.backendMode` | `auto`, `venv`, or `exe`; selects executable versus Python execution. |
| `kts.backendChannel` | `bundled` or `workspace`; selects packaged versus source backend location. |
| `kts.pythonPath` | Optional explicit Python interpreter. |
| `kts.kbWorkspacePath` | Optional knowledge-base workspace override. |
| `kts.ingestionTimeoutMinutes` | Maximum ingestion duration used by the extension. |

For source development, use `venv` and `workspace` as described in [Developer Setup](DEVELOPER_SETUP.md).

## Environment Variables

| Variable | Purpose |
|---|---|
| `KTS_KB_PATH` | Overrides the default KTS knowledge-base data location for backend execution. |
| `ABS_PYTHON` | Python interpreter used by the ABS webview backend in source mode. |

## Local Data Layout

KTS writes local indexes beneath a `.kts` folder. Typical contents include a document manifest, extracted documents and metadata, vector storage, graph data, and staging files. Do not manually edit active vector or graph files while ingestion is running.

ABS uses the open workspace as its deal root. Generated document, graph, report, run, and log directories are deal artifacts, not portable source files. Keep them out of Git by default unless a curated test fixture or release artifact explicitly requires them.

## Copilot Availability

Retrieval and local data operations run locally. Features that generate natural-language answers, resolve definitions, produce models, audit with an LLM, or describe images need a GitHub Copilot model selected through VS Code. If no model is available, the operation reports the condition in the relevant output channel.