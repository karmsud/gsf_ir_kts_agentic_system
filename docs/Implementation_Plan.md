# GSF IR KTS — Implementation Plan

## Build Philosophy

- **Dependency-driven order**: Each phase depends on the previous one being complete
- **Tests alongside code**: Every agent gets tests in the same phase it's built
- **Smoke test each phase**: Run `scripts/smoke.py` after each phase to verify integration
- **Incremental usability**: After Phase 3, the system can already ingest docs and answer questions

---

## Phase Overview

| Phase | Name | Agents Built | Deliverable | Est. Files |
|-------|------|-------------|-------------|------------|
| 0 | Project Scaffold | — | Folder structure, config, requirements | ~15 |
| 1 | Foundation Layer | AgentBase | Base classes, models, quality gates, escalation | ~10 |
| 2 | Ingestion Pipeline | Crawler, Ingestion | Scan file shares → convert docs → extract images | ~12 |
| 3 | Storage + Basic Q&A | Graph Builder, Q&A | Vector store, knowledge graph, basic question answering | ~10 |
| 4 | Multi-Modal | Vision | Image manifest, description workflow, image indexing | ~6 |
| 5 | Intelligence | Taxonomy, Version | Auto-classification, version tracking, diffing | ~8 |
| 6 | Advanced Queries | Training Path, Change Impact, Freshness | Graph-based analysis agents | ~8 |
| 7 | Orchestration | Conductor | Intent classification, pipeline routing | ~4 |
| 8 | User Interface | — | CLI + Streamlit UI | ~8 |
| 9 | Integration & Polish | — | Integration tests, seed data, documentation | ~6 |

**Total estimated files: ~87**

---

## Phase 0: Project Scaffold

### Goal
Create the folder structure, config files, and development environment.

### Deliverables

```
gsf_ir_kts_agentic_system/
├── README.md                        # Project overview + quickstart
├── requirements.txt                 # All Python dependencies
├── setup.py                         # Package setup for imports
├── .gitignore                       # Ignore knowledge_base/, __pycache__, etc.
├── config/
│   ├── __init__.py
│   ├── settings.py                  # KTSConfig dataclass
│   ├── taxonomy_rules.json          # Document classification rules
│   └── file_share_paths.json        # Source paths (empty template)
├── backend/
│   ├── __init__.py
│   ├── agents/__init__.py
│   ├── common/__init__.py
│   ├── ingestion/__init__.py
│   ├── vector/__init__.py
│   └── graph/__init__.py
├── extension/                       # VS Code Extension
│   ├── package.json                 # Extension manifest
│   ├── extension.js                 # Entry point
│   ├── commands/
│   ├── panels/
│   └── copilot/
├── prompts/                         # Empty prompt templates
├── cli/__init__.py
├── knowledge_base/                  # Runtime directory
│   ├── documents/
│   ├── vectors/
│   └── graph/
├── scripts/
├── tests/
│   ├── __init__.py
│   └── conftest.py                  # Shared fixtures
└── docs/                            # Already created
```

### Dependencies (requirements.txt)

```
# Document conversion
python-docx>=1.1.0
PyMuPDF>=1.24.0
python-pptx>=0.6.23
markdownify>=0.13.1
beautifulsoup4>=4.12.0

# Vector store
chromadb>=0.5.0

# Knowledge graph
networkx>=3.2

# CLI
click>=8.1.0

# Utilities
Pillow>=10.4.0           # Image handling
tqdm>=4.66.0             # Progress bars

# Testing
pytest>=8.0.0
pytest-cov>=5.0.0
```

### Verification
- [ ] `pip install -r requirements.txt` succeeds
- [ ] `python -c "from config.settings import KTSConfig; print('OK')"` works
- [ ] All `__init__.py` files exist

---

## Phase 1: Foundation Layer

### Goal
Build the reusable base classes that all agents depend on.

### Files to Create

| File | Content | Reused from ABS? |
|------|---------|-----------------|
| `backend/agents/base_agent.py` | `AgentBase`, `AgentResult`, `Citation` | Yes — adapted |
| `backend/common/models.py` | All shared dataclasses (see Data_Model.md) | Partially |
| `backend/common/quality_gate.py` | `QualityAssessment`, `QualityGate`, `ConfidenceRouter` | Yes — direct |
| `backend/common/escalation.py` | `EscalationReport`, `EscalationManager` | Yes — direct |
| `backend/common/manifest.py` | `FileManifest`, `ImageManifest`, `ManifestManager` | New (inspired by ABS) |
| `backend/common/hashing.py` | `compute_file_hash()`, `compute_content_hash()` | New |
| `backend/common/text_utils.py` | `chunk_text()`, `clean_markdown()`, `extract_headings()` | Partially |
| `tests/test_models.py` | Tests for all dataclasses | — |
| `tests/test_quality_gate.py` | Tests for quality gate logic | — |
| `tests/test_manifest.py` | Tests for manifest operations | — |

### Verification
- [ ] All dataclasses serialize/deserialize correctly
- [ ] Quality gate routes correctly at 0.90/0.66 boundaries
- [ ] Manifest tracks file state correctly
- [ ] `pytest tests/test_models.py tests/test_quality_gate.py tests/test_manifest.py` — all pass

---

## Phase 2: Ingestion Pipeline

### Goal
Scan file shares and convert documents to Markdown + extracted images.

### Files to Create

| File | Content |
|------|---------|
| `backend/ingestion/docx_converter.py` | Word → Markdown + images using python-docx |
| `backend/ingestion/pdf_converter.py` | PDF → Markdown + images using PyMuPDF |
| `backend/ingestion/pptx_converter.py` | PowerPoint → Markdown + images using python-pptx |
| `backend/ingestion/html_converter.py` | HTML → Markdown using markdownify + BeautifulSoup |
| `backend/ingestion/image_extractor.py` | Shared image save/catalog logic |
| `backend/agents/crawler_agent.py` | Scan paths, hash files, compare to manifest |
| `backend/agents/ingestion_agent.py` | Orchestrate conversion + image extraction |
| `tests/test_crawler.py` | Crawler tests with mock file system |
| `tests/test_ingestion.py` | Converter tests with sample documents |
| `tests/fixtures/` | Sample .docx, .pdf, .pptx files for testing |

### Key Design Decisions

1. **One converter per format** — each converter implements:
   ```python
   class DocxConverter:
       def convert(self, file_path: Path) -> ConversionResult:
           """Returns markdown text + list of extracted images."""
   ```

2. **Image extraction is automatic** — every embedded image is saved to `knowledge_base/documents/{doc_id}/images/` and cataloged in the image manifest.

3. **Metadata extraction** — each converter extracts:
   - Title (from document properties or first heading)
   - Author (from document properties)
   - Created date / modified date
   - Page count / slide count / word count

### Verification
- [ ] Can convert a .docx with images → Markdown + extracted .png files
- [ ] Can convert a .pdf with images → Markdown + extracted .png files
- [ ] Can convert a .pptx → Markdown + extracted .png files
- [ ] Crawler detects new files on a test directory
- [ ] Crawler detects modified files (changed hash)
- [ ] Crawler skips unchanged files
- [ ] `pytest tests/test_crawler.py tests/test_ingestion.py` — all pass

---

## Phase 3: Storage + Basic Q&A

### Goal
Store ingested text in ChromaDB, build knowledge graph, answer basic questions.

### Files to Create

| File | Content |
|------|---------|
| `backend/vector/store.py` | ChromaDB wrapper: add_chunks, search, delete_document |
| `backend/vector/chunker.py` | Text chunking with overlap + metadata attachment |
| `backend/graph/schema.py` | Node types, edge types, validation functions |
| `backend/graph/builder.py` | Build graph nodes/edges from document metadata |
| `backend/graph/queries.py` | Common traversals: related_docs, find_tool, find_process |
| `backend/graph/persistence.py` | Save/load NetworkX graph to/from JSON |
| `backend/agents/graph_builder_agent.py` | Agent wrapper for graph construction |
| `backend/agents/qa_agent.py` | RAG: vector search + graph enrichment + answer generation |
| `tests/test_vector.py` | Vector store tests |
| `tests/test_graph.py` | Graph construction + query tests |
| `tests/test_qa.py` | Q&A agent tests with mock data |

### Milestone
**After Phase 3, the system is usable**: ingest docs → ask questions → get answers with citations.

### Verification
- [ ] Text chunks are stored and searchable in ChromaDB
- [ ] Knowledge graph can be built from document metadata
- [ ] Graph traversal returns related docs for a given tool
- [ ] Q&A agent returns relevant answers with source citations
- [ ] End-to-end: ingest a doc → ask a question about it → get correct answer
- [ ] `pytest tests/test_vector.py tests/test_graph.py tests/test_qa.py` — all pass

---

## Phase 4: Multi-Modal Pipeline

### Goal
Implement the human-in-the-loop image description workflow.

### Files to Create

| File | Content |
|------|---------|
| `backend/agents/vision_agent.py` | Image manifest management, description indexing |
| `prompts/image_description.md` | Template for Maintenance Engineer |
| `tests/test_vision.py` | Vision workflow tests |

### Workflow Implementation

```
1. Ingestion creates pending_descriptions.json for each doc with images
2. CLI command: `kts describe pending` — lists all pending images
3. Maintenance Engineer describes images using GitHub Models + template
4. CLI command: `kts describe complete <doc_id>` — reads descriptions.json,
   indexes in vector store, updates graph
```

### Verification
- [ ] Image manifest correctly tracks pending vs described images
- [ ] Description indexing adds chunks to vector store with `is_image_desc=True`
- [ ] Q&A agent can find answers from image descriptions
- [ ] `kts describe pending` shows correct pending count
- [ ] `pytest tests/test_vision.py` — all pass

---

## Phase 5: Intelligence Agents

### Goal
Auto-classify documents and track versions over time.

### Files to Create

| File | Content |
|------|---------|
| `backend/agents/taxonomy_agent.py` | Rule-based + LLM fallback classification |
| `backend/agents/version_agent.py` | Diff engine, version chain management |
| `config/taxonomy_rules.json` | Rule-based classification patterns |
| `tests/test_taxonomy.py` | Classification tests |
| `tests/test_version.py` | Version tracking + diff tests |

### Key Design

**Taxonomy**: Two-tier approach
1. Rule-based: filename patterns + content keyword patterns → fast, free, ~70% coverage
2. LLM fallback: flagged as `UNKNOWN` in `pending_classifications.json` for human review

**Version**: Hash-based detection
1. Crawler detects changed hash → triggers Version Agent
2. Version Agent loads old content, diffs against new
3. Produces `VersionDiff` with added/removed/modified sections
4. Updates graph: new `DocVersion` node + `SUPERSEDES` edge
5. Re-indexes only changed chunks (not entire document)

### Verification
- [ ] SOPs correctly classified from filename pattern
- [ ] Release notes correctly classified from content keywords
- [ ] Unknown docs flagged for human review
- [ ] Version diff correctly identifies added/removed/modified sections
- [ ] Graph version chain is correct (v1 → v2 → v3)
- [ ] Re-indexing only affects changed chunks
- [ ] `pytest tests/test_taxonomy.py tests/test_version.py` — all pass

---

## Phase 6: Advanced Query Agents

### Goal
Build the graph-powered analysis agents.

### Files to Create

| File | Content |
|------|---------|
| `backend/agents/training_path_agent.py` | Prerequisite graph traversal, path assembly |
| `backend/agents/change_impact_agent.py` | Reverse dependency analysis |
| `backend/agents/freshness_agent.py` | Stale content detection |
| `prompts/training_path.md` | Training path prompt template |
| `tests/test_training_path.py` | Training path tests |
| `tests/test_change_impact.py` | Impact analysis tests |
| `tests/test_freshness.py` | Freshness detection tests |

### Verification
- [ ] Training path returns correctly ordered learning sequence
- [ ] Change impact identifies all affected docs when a tool node changes
- [ ] Freshness agent correctly flags stale docs based on threshold
- [ ] Freshness agent detects stale screenshots (image described before tool update)
- [ ] `pytest tests/test_training_path.py tests/test_change_impact.py tests/test_freshness.py` — all pass

---

## Phase 7: Conductor (Orchestration)

### Goal
Build the central routing agent that classifies user intent and orchestrates multi-agent pipelines.

### Files to Create

| File | Content |
|------|---------|
| `backend/conductor.py` | Intent classification, pipeline orchestration |
| `prompts/intent_classification.md` | Conductor system prompt |
| `tests/test_conductor.py` | Intent routing tests |

### Intent Classification

```python
INTENTS = {
    "QUESTION":  "User wants an answer to a question",
    "TRAINING":  "User wants a learning path or onboarding guidance",
    "IMPACT":    "User wants to know what's affected by a change",
    "INGEST":    "User wants to add new documents",
    "AUDIT":     "User wants a freshness/health report",
    "CLASSIFY":  "User wants to review/set document classifications",
    "DESCRIBE":  "User wants to manage image descriptions",
    "STATUS":    "User wants system status/stats",
}
```

### Verification
- [ ] "How do I..." → routes to Q&A Agent
- [ ] "I'm new to..." → routes to Training Path Agent
- [ ] "What changed..." → routes to Change Impact Agent
- [ ] "Ingest..." → routes to Crawler → Ingestion pipeline
- [ ] "Audit..." → routes to Freshness Agent
- [ ] `pytest tests/test_conductor.py` — all pass

---

## Phase 8: User Interfaces

### Goal
Build the CLI for automation/power users and VS Code Extension for end users + admin functions.

### Files to Create

| File | Content |
|------|---------|
| `cli/main.py` | Click-based CLI with all subcommands |
| `extension/package.json` | VS Code Extension manifest |
| `extension/extension.js` | Extension entry point, command registration |
| `extension/commands/crawl_ingest.js` | "KTS: Crawl & Ingest" command |
| `extension/commands/view_status.js` | "KTS: View Status" command (generates markdown report) |
| `extension/commands/training_path.js` | "KTS: Training Path" command |
| `extension/commands/change_impact.js` | "KTS: Change Impact" command |
| `extension/commands/freshness_audit.js` | "KTS: Freshness Audit" command |
| `extension/panels/image_description.js` | Custom webview panel for image description workflow |
| `extension/panels/status_report.js` | Renders status markdown in panel |
| `extension/copilot/kts_tool.js` | @kts tool registration for Copilot Chat |

### Verification
- [ ] `kts crawl --dry-run` works (CLI)
- [ ] `kts ingest --path <dir>` works (CLI)
- [ ] `kts search "how do I..."` returns context (CLI test for retrieval service)
- [ ] `kts describe pending` shows pending images (CLI)
- [ ] `kts freshness --report` generates report (CLI)
- [ ] VS Code Extension loads without errors
- [ ] Command Palette shows all "KTS:" commands
- [ ] @kts tool responds to queries in Copilot Chat
- [ ] Image Description panel displays images and accepts descriptions
- [ ] Status command generates and displays markdown report

---

## Phase 9: Integration & Polish

### Goal
End-to-end integration tests, seed data, documentation finalization.

### Files to Create

| File | Content |
|------|---------|
| `tests/test_integration.py` | Full pipeline tests: ingest → query → answer |
| `scripts/smoke.py` | Quick system health check |
| `scripts/seed_demo.py` | Create sample docs for demo/testing |
| `scripts/run_freshness_audit.py` | Standalone freshness audit script |
| `README.md` | Updated with full quickstart guide |
| `docs/QUICKSTART.md` | Maintenance Engineer onboarding guide |

### Verification
- [ ] End-to-end: seed docs → ingest → describe images → ask question → get answer → check impact → generate training path
- [ ] All unit tests pass: `pytest tests/ --tb=short`
- [ ] Smoke test passes: `python scripts/smoke.py`
- [ ] README quickstart instructions work from scratch

---

## Dependency Graph (Phase Order)

```
Phase 0: Scaffold
    │
    ▼
Phase 1: Foundation ◄─── Everything depends on this
    │
    ▼
Phase 2: Ingestion ◄─── Needs base classes
    │
    ├──────────────────────┐
    ▼                      ▼
Phase 3: Storage + Q&A    Phase 4: Multi-Modal
    │                      │
    ├──────────────────────┘
    ▼
Phase 5: Intelligence (Taxonomy + Version)
    │
    ▼
Phase 6: Advanced Queries (Training + Impact + Freshness)
    │
    ▼
Phase 7: Conductor
    │
    ▼
Phase 8: CLI + UI
    │
    ▼
Phase 9: Integration
```

**Note**: Phases 3 and 4 can be built in parallel since they're independent.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Image extraction yields poor quality from PDFs | Medium | High | Use PyMuPDF's `get_images()` with fallback to page-level rendering |
| ChromaDB performance degrades with 10K+ chunks | Low | Medium | Use persistent storage, proper chunking, consider batch operations |
| OneNote exports have inconsistent HTML structure | High | Low | Build robust HTML parser, test with multiple export formats |
| Taxonomy rules are too simplistic | Medium | Medium | Start with rules, iterate; human review catches misclassifications |
| File share path changes break ingestion | Medium | Low | All paths in `config/file_share_paths.json`, not hardcoded |
| Vision descriptions are inconsistent quality | Medium | High | Provide detailed prompt template; Maintenance Engineer training |

---

*This plan produces a fully functional 11-agent KTS system across 9 phases. See Agent_Catalog.md for per-agent specifications and Data_Model.md for all data structures.*
