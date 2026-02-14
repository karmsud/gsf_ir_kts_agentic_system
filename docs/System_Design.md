# GSF IR KTS — System Design (Current Implementation)

## 1. Runtime Topology

GSF IR KTS is implemented as a **local, workspace-scoped** system with:
- Python backend agents and storage under `knowledge_base/`
- CLI orchestration via `python -m cli.main`
- VS Code extension command surface under `extension/`
- Copilot bridge module (`extension/copilot/kts_tool.js`) that calls retrieval

There is **no Conductor agent** and **no Streamlit app** in the shipped implementation.

---

## 2. Implemented Project Structure

```text
gsf_ir_kts_agentic_system/
├── backend/
│   ├── agents/
│   │   ├── base_agent.py
│   │   ├── crawler_agent.py
│   │   ├── ingestion_agent.py
│   │   ├── vision_agent.py
│   │   ├── taxonomy_agent.py
│   │   ├── version_agent.py
│   │   ├── graph_builder_agent.py
│   │   ├── retrieval_service.py
│   │   ├── training_path_agent.py
│   │   ├── change_impact_agent.py
│   │   └── freshness_agent.py
│   ├── common/
│   ├── graph/
│   ├── ingestion/
│   └── vector/
├── cli/
│   └── main.py
├── config/
├── extension/
│   ├── extension.js
│   ├── package.json
│   ├── lib/kts_backend.js
│   ├── commands/
│   │   ├── crawl_ingest.js
│   │   ├── view_status.js
│   │   ├── training_path.js
│   │   ├── change_impact.js
│   │   └── freshness_audit.js
│   ├── copilot/kts_tool.js
│   ├── panels/
│   └── tests/
├── knowledge_base/
├── scripts/
└── tests/
```

---

## 3. Agent Set (10)

1. `CrawlerAgent` — file discovery and hash-based change detection
2. `IngestionAgent` — document conversion + chunking + metadata
3. `VisionAgent` — image description lifecycle and indexing
4. `TaxonomyAgent` — document type classification
5. `VersionAgent` — section/image diffs between versions
6. `GraphBuilderAgent` — graph node/edge creation and persistence
7. `RetrievalService` — context retrieval for Copilot/CLI (not answer generation)
8. `TrainingPathAgent` — topic/level learning sequence construction
9. `ChangeImpactAgent` — direct/indirect dependency impact analysis
10. `FreshnessAgent` — stale-content and freshness reporting

---

## 4. Data and Storage Design

### 4.1 Local Data Plane
- `knowledge_base/manifest.json`: tracked files and ingestion state
- `knowledge_base/documents/`: per-document extracted content and metadata
- `knowledge_base/graph/knowledge_graph.json`: graph persistence
- `knowledge_base/vectors/`: local vector index persistence

### 4.2 Retrieval Output Contract
`RetrievalService` returns structured context payload including:
- `context_chunks`
- `citations` with `uri`
- `image_notes`
- `freshness`
- `confidence` and optional escalation metadata

Answer generation remains outside backend and is handled by Copilot-facing UX.

---

## 5. Implemented Workflows

### 5.1 Ingestion Flow
1. `crawl` finds new/modified/deleted files
2. `ingest` converts supported files, chunks content, updates metadata
3. taxonomy classification and graph build are applied
4. vision manifests are initialized for extracted images

### 5.2 Retrieval Flow
1. Query submitted from CLI (`search`) or Copilot bridge (`@kts` module)
2. vector search + graph enrichment + ranking
3. structured `SearchResult` returned with citations

### 5.3 Analysis Flows
- `training`: graph-driven learning path
- `impact`: change blast-radius report
- `freshness`: bucketed current/aging/stale report
- `status`: document/manifest/graph counts

---

## 6. VS Code Extension Design (Implemented)

### 6.1 Command Surface
Contributed and wired commands:
- `KTS: Crawl & Ingest`
- `KTS: View Status`
- `KTS: Training Path`
- `KTS: Change Impact`
- `KTS: Freshness Audit`

Each command invokes Python backend via `extension/lib/kts_backend.js` and writes full JSON output to a dedicated `KTS` output channel.

### 6.2 Copilot Bridge
`extension/copilot/kts_tool.js` now executes real retrieval through:
- `python -m cli.main search <query>`
- returns structured result payload under `search_result`

### 6.3 Panels
Panel modules exist under `extension/panels/`; these remain lightweight and can be expanded for richer admin UX.

---

## 7. CLI Contract (Current)

`cli/main.py` exposes:
- `crawl`
- `ingest`
- `search`
- `training`
- `impact`
- `freshness`
- `describe pending|complete|status`
- `status`
- `diff`

All commands return JSON suitable for extension and automation consumption.

---

## 8. Validation Status

Current validated status in repository:
- `pytest -q` passes (46 tests)
- `scripts/smoke.py` passes
- extension integration tests validate backend bridge and `@kts` retrieval invocation

See `docs/phase2/` for detailed traceability, test matrix, and production readiness notes.
