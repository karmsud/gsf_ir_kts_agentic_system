# KTS Architecture & Design

**Source of Truth**: `backend/agents/`, `backend/ingestion/`, `cli/main.py`
**Last Updated**: 2026-02-14

## 1. System Overview

GSF IR KTS is a **local, workspace-scoped** knowledge retrieval system. It runs entirely on the user's machine, indexing documentation from a local folder or network share into a `.kts` folder.

- **Frontend**: VS Code Extension (Visual Studio Code 1.96+)
- **Backend**: Python 3.10+ (compiled to single-file executable or bundled source)
- **Data**: Local specific `.kts` folder containing vector store, graph, and manifest.

## 2. Pipeline Stages

The system follows a strict `crawl -> ingest -> index` pipeline.

### 2.1 Crawl (`backend/agents/crawler_agent.py`)
- Scans `source_path` for supported files (`.md`, `.docx`, `.pdf`, `.pptx`, `.html`, `.json`).
- Generates `manifest.json` tracking file stats (size, mtime, hash).
- **Idempotency**: Only marks files as "changed" if hash differs from previous run.

### 2.2 Ingestion & Conversion (`backend/agents/ingestion_agent.py`)
- Processes files marked "changed" in manifest.
- **Atomic Swap**: Converts to `.kts/staging/<doc_id>`, then moves to `.kts/documents/<doc_id>`.
- **Image Pipeline**:
  - Extracts embedded images from DOCX/PDF/PPTX to `.kts/documents/<doc_id>/images/`.
  - **Deduplication**: Uses SHA-256 content hashing to avoid duplicate images on disk.
  - **Filters**: Reference to `.kts` folder itself is strictly excluded.

### 2.3 Indexing (`backend/vector/`)
- chunks text (Markdown-aware splitter).
- Embeds chunks using local models (e.g., `sentence-transformers/all-MiniLM-L6-v2`).
- Stores in ChromaDB (`.kts/vectors/chroma`).

### 2.4 Knowledge Graph (`backend/graph/`)
- Builds NetworkX graph (`knowledge_graph.json`) linking documents, chunks, and concepts.
- Used for "multi-hop" reasoning and finding related documents.

## 3. Data Model (`backend/common/models.py`)

### 3.1 Artifacts (in `.kts/`)
- `manifest.json`: Single source of truth for all known files.
- `knowledge_graph.json`: Node-link data for graph traversal.
- `descriptions.json`: Stores AI-generated image descriptions (mapped by image hash).

### 3.2 Key Classes
- **AgentResult**: Standard return type (success, data, confidence, reasoning).
- **Document**: Internal representation with metadata and content.
- **Citation**: Return object for search, including file URI and confidence score.

## 4. Extension Architecture (`extension/`)

- **Activator** (`extension.js`): Registers commands, providers.
- **Backend Manager** (`lib/kts_backend.js`): Manages the Python process (spawn/kill).
- **Copilot Integration** (`chat/participant.js`): Defines `@kts` chat participant.
- **Image Description** (`lib/image_describer.js`): Uses VS Code Language Model API to describe pending images.

## 5. Deployment Tiers

The backend is built in two tiers to manage size:
1.  **Option A2 (Full)**: Includes PyMuPDF, python-pptx. Supports generic enterprise docs.
2.  **Option A3 (Word+Images)**: Stripped down. Supports DOCX/HTML only. ~60% smaller.
