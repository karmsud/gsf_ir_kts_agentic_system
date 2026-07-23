# Architecture

## Overview

The project is a VS Code extension with a local Python backend. The extension exposes KTS document intelligence and ABS Waterfall modeling as separate user experiences that share the workspace, runtime selection, logging conventions, and packaging pipeline.

```mermaid
flowchart LR
  U[VS Code user] --> E[Extension activation]
  E --> K[@kts participant and commands]
  E --> A[@abs participant]
  E --> W[ABS Waterfall webview]
  K --> R[Python KTS CLI backend]
  A --> S[Python ABS orchestration]
  W --> I[JSON-lines IPC server]
  R --> D[Local documents, vectors, graphs]
  S --> M[Deal artifacts and reports]
  I --> M
  K -. Copilot model requests .-> C[VS Code Language Model API]
  A -. Copilot model requests .-> C
  W -. Copilot model requests .-> C
```

## Extension Layer

`extension/extension.js` activates the extension, initializes backend execution, registers KTS commands, and registers both chat participants. It registers `abs.open` before optional chat initialization so the primary ABS webview remains available even when a chat or backend dependency fails during startup.

`extension/package.json` is the source of truth for VS Code-visible commands, settings, and chat participants:

- `@kts`: document retrieval and analysis modes.
- `@abs`: ingestion, generation, audit, and status modes for payment models.
- `abs.open`: opens the ABS Waterfall webview.

## KTS Data Flow

KTS operates on local source folders.

1. Crawl detects supported documents and updates a manifest.
2. Ingest extracts content, classifies documents, writes metadata, chunks content, and indexes vectors.
3. Graph construction records relationships and retrieval metadata.
4. Retrieval combines local vector, graph, and optional ranking techniques.
5. The extension formats retrieved context and uses the VS Code Language Model API when an answer-generation step is needed.

KTS supports folder-scoped data. When ingesting a root that contains subfolders, the backend can isolate each direct subfolder into its own `.kts` store for scope-aware retrieval.

## ABS Waterfall Data Flow

`extension/panels/abs_app.js` creates the webview and starts `backend.abs.serve` in source mode or a compatible bundled backend in packaged mode. The webview and backend communicate using newline-delimited JSON.

1. The user opens the ABS app and selects source material.
2. The backend ingests governing documents into deal-scoped storage.
3. Generation produces a payment-waterfall model and associated artifacts.
4. Audit compares generated work with governing-document evidence.
5. The webview receives progress and result messages; VS Code handles native file dialogs, output channels, and Copilot model requests.

The backend never receives a direct remote API credential from the webview. When it needs an LLM operation, it sends an `llm_request`; the extension selects an available Copilot model through the VS Code Language Model API and returns the response over IPC.

## Runtime Selection

The extension supports a bundled executable, a managed environment, and workspace-source development. `auto` mode prefers a compatible bundled executable; source development commonly uses `venv` mode and the workspace backend channel. Platform resolution covers macOS, Windows, and Linux bundle naming conventions.

## Persistence and Logs

- KTS stores manifests, extracted documents, vector data, graph data, and staging artifacts in `.kts` folders.
- ABS stores deal-specific documents, graphs, reports, runs, logs, and generated model artifacts under the active workspace's deal root.
- The `KTS` and `ABS Waterfall` output channels are the first diagnostic surface for extension and backend failures.

Detailed implementation and settings references live in [Configuration](CONFIGURATION.md), [CLI Reference](CLI_REFERENCE.md), and [Developer Setup](DEVELOPER_SETUP.md).