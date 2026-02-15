# GSF IR KTS — Reuse Map (Current)

This map reflects the **current implemented architecture** (10 agents, retrieval service, VS Code extension bridge).

---

## 1. Reuse Summary

| Category | Direct Reuse | Adapted Reuse | New | Total |
|---|---:|---:|---:|---:|
| Agent patterns/contracts | 1 | 4 | 5 | 10 |
| Common modules | 2 | 3 | 1 | 6 |
| Ingestion stack | 0 | 2 | 3 | 5 |
| Storage/graph stack | 0 | 3 | 1 | 4 |
| UX/integration layer | 0 | 0 | 1 | 1 |

Interpretation:
- Core architecture style is heavily reused/adapted.
- KTS-specific business value is concentrated in new agents and extension integration.

---

## 2. Agent-Level Reuse (10 Agents)

### 2.1 Adapted from prior architecture patterns
| KTS Agent | Reuse Type | Notes |
|---|---|---|
| `IngestionAgent` | Adapted | Reuses document conversion pattern, extended for multi-format + metadata + chunking |
| `VersionAgent` | Adapted | Reuses change-tracking concept, implemented for section/image diffing |
| `GraphBuilderAgent` | Adapted | Reuses graph-construction approach with KTS-specific schema |
| `RetrievalService` | Adapted | Reuses retrieval/ranking approach; answer generation removed from backend |

### 2.2 New in KTS implementation
| KTS Agent | Why New |
|---|---|
| `CrawlerAgent` | File-share discovery and hash-based delta detection |
| `VisionAgent` | Human-in-the-loop image description lifecycle |
| `TaxonomyAgent` | Document-type classification for operational corpora |
| `TrainingPathAgent` | Learning-path generation from graph relationships |
| `ChangeImpactAgent` | Cross-entity blast-radius analysis |
| `FreshnessAgent` | Staleness monitoring and recommendations |

### 2.3 Removed from prior planning
| Component | Status |
|---|---|
| Conductor Agent | Removed from implemented architecture |

---

## 3. Common Module Reuse

| Module | Reuse Type | Current Use |
|---|---|---|
| `backend/common/quality_gate.py` | Direct | Confidence routing and quality gates |
| `backend/common/escalation.py` | Direct | Structured low-confidence escalation |
| `backend/common/models.py` | Adapted | KTS-specific dataclasses and payload contracts |
| `backend/common/manifest.py` | Adapted | File and image lifecycle state tracking |
| `backend/common/text_utils.py` | Adapted | Chunking/cleaning for retrieval indexing |
| `backend/common/hashing.py` | New | Deterministic file-change detection |

---

## 4. Storage and Graph Reuse

| Area | Reuse Type | Current State |
|---|---|---|
| Vector store wrapper | Adapted | Local index operations and metadata-aware retrieval |
| Graph persistence | Adapted | Local JSON persistence for graph state |
| Graph builder/query patterns | Adapted | KTS entities: tools/processes/docs/topics/people |
| Retrieval metadata conventions | New | Citation URI + freshness/image notes for Copilot-compatible context |

---

## 5. New Integration Surface (No Prior Equivalent)

### 5.1 VS Code Extension Bridge
`extension/` is new and provides:
- command palette workflows wired to backend CLI
- shared backend runner (`extension/lib/kts_backend.js`)
- Copilot bridge module (`extension/copilot/kts_tool.js`) using real retrieval calls

### 5.2 Why this matters
The extension removes manual shell dependency for common operations while preserving backend as the source of truth.

---

## 6. Practical Reuse Guidance

- Prefer reusing **contracts and control flow patterns** (agent result shape, quality gates) over copying domain logic.
- Treat retrieval output shape (`context_chunks`, `citations`, `image_notes`) as stable integration API for UX layers.
- Keep extension thin: invoke backend CLI/services, avoid duplicating agent logic in JavaScript.

---

## 7. Risk and Mitigation

| Risk | Mitigation |
|---|---|
| Over-copying old assumptions (e.g., conductor-based routing) | Keep architecture anchored to current 10-agent + extension bridge design |
| Divergence between docs and code | Update docs alongside command/agent behavior changes |
| Duplicate business logic across Python and extension JS | Keep all core logic in backend; extension only orchestrates and renders |

---

## 8. Bottom Line

KTS is best understood as **pattern-reuse + domain-new capabilities**:
- reused foundation for reliability and maintainability,
- new retrieval-focused and operational agents for KTS value,
- new VS Code/Copilot integration layer for practical user workflow.
