# Phase 12: Named Scoped Knowledge Spaces — Architecture Document

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## 1. Architectural Principles

| Decision | Rationale |
|----------|-----------|
| **Folder IS the namespace** | No manual configuration. The file system is the source of truth for scope boundaries. |
| **`.kts` lives inside the folder** | Embeddings travel with their source documents. Move folder → move index. Delete folder → delete index. No orphaned state. |
| **Slug derived from folder name** | No registration step. No config file. The command is the name. |
| **Two-level scope via metadata filter** | Doc-type narrowing uses ChromaDB `where` clauses — not separate collections. Same index, zero duplication. |
| **Deal catalog is a catalog, not an index** | The catalog is keyword-searchable metadata, not vector-embedded. Speed over semantic similarity for scope routing. |
| **Federated search is exceptions-safe** | A failed scope search skips that scope and continues. 9,999 scopes succeeding is more valuable than crashing on 1 failure. |
| **Global scope remains as fallback** | Existing `~/.kts/` global space is preserved. Unscoped queries fall through to it. No breaking change. |

---

## 2. Layer Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                    VS CODE CHAT API                             │
│   @kts /bear_stearns_2006_HE1 /psa  What is the closing date? │
│          └── scope slug ──┘ └─ doc filter ─┘                   │
├────────────────────────────────────────────────────────────────┤
│              PRESENTATION LAYER (participant.js)                │
│   + scope_discovery.js              NEW 12.2                   │
│   │ Scan knowledgeSourceRoot on activation                      │
│   │ Register slash command per indexed folder                   │
│   │ Refresh on kts.refreshScopes command                        │
│                                                                 │
│   + parseQuery()                    NEW 12.3                   │
│   │ Extract scope, doc_type_filter, clean query                 │
│   POST /query { query, scope, doc_type_filter, ... }           │
├────────────────────────────────────────────────────────────────┤
│              ★ SCOPE LAYER (NEW Phase 12)                      │
│   backend/retrieval/scope_router.py      NEW 12.4              │
│   • Single-scope: route to named collection directly           │
│   • Cross-scope: catalog query → fan-out → merge → rerank      │
│   • No-scope: fallback to global ~/.kts/                        │
│                                                                 │
│   backend/vector/deal_catalog.py         NEW 12.4              │
│   • SQLite catalog: one row per indexed folder                  │
│   • Keyword search (issuer, year, type)                         │
│   • Updated at ingest time                                      │
├────────────────────────────────────────────────────────────────┤
│              VECTOR LAYER (Modified)                            │
│   backend/vector/store.py               MODIFIED 12.1          │
│   • Collection named by scope slug                              │
│   • ChromaDB path = [folder]/.kts/                             │
│   • where= filter support for doc_type                          │
├────────────────────────────────────────────────────────────────┤
│              FILESYSTEM (Source of Truth)                       │
│   knowledge_source/                                             │
│       bear_stearns_2006_HE1/                                    │
│           ├── psa.docx                                          │
│           ├── trust_agreement.docx                              │
│           └── .kts/  ← embedding space for THIS folder ONLY    │
│       bear_stearns_2006_HE2/                                    │
│           └── .kts/  ← completely isolated                      │
└────────────────────────────────────────────────────────────────┘
```

---

## 3. Scope Routing Decision Tree

```
Incoming Query
    │
    ├─ Explicit scope slug present? (/bear_stearns_2006_HE1)
    │       │
    │       ├─ YES → Load [folder]/.kts/ collection
    │       │         ├─ Doc-type filter present? (/psa)
    │       │         │       ├─ YES → ChromaDB where={"doc_type": "PSA"}
    │       │         │       └─ NO  → Full scope search
    │       │         └─ Return results from THIS scope only
    │       │
    │       └─ NO (unscoped query)
    │               │
    │               ├─ Query mentions known deal/issuer name?
    │               │       ├─ YES → Catalog lookup → fan-out to N matching scopes
    │               │       │         (parallel, exceptions-safe, reranked)
    │               │       └─ NO  → Fallback: global ~/.kts/ collection
    │               │
    │               └─ Too many matches (>100 scopes)?
    │                       └─ Return: "Please narrow scope with /[scope_name]"
```

---

## 4. Collection Naming Convention

| Folder Name | Collection Name (ChromaDB) | `.kts` Path |
|-------------|---------------------------|-------------|
| `bear_stearns_2006_HE1` | `kts_bear_stearns_2006_HE1` | `deals/bear_stearns_2006_HE1/.kts/` |
| `Training Materials` | `kts_training_materials` | `knowledge_source/Training Materials/.kts/` |
| Global (legacy) | `kts_default` | `~/.kts/` |

Prefix `kts_` prevents collision with user-created ChromaDB collections.

---

## 5. Deal Catalog Schema

```
deal_catalog table
─────────────────────────────────────────────────────────
folder_name        TEXT PRIMARY KEY  "bear_stearns_2006_HE1"
slug               TEXT              "bear_stearns_2006_HE1"
kts_path           TEXT              "/deals/bear_stearns_2006_HE1/.kts"
doc_count          INTEGER           5
doc_types          JSON              ["PSA","PROSUPP","TRUST","INDENTURE"]
issuers            JSON              ["Bear Stearns"]
years              JSON              ["2006"]
collateral_types   JSON              ["HELOC","Subprime"]
key_parties        JSON              ["Wells Fargo","Deutsche Bank Trust"]
last_indexed       TIMESTAMP
─────────────────────────────────────────────────────────
```

Catalog is populated by `ingestion_agent.py` after each successful ingest. Catalog queries use SQLite FTS5 (full-text search) — millisecond latency at 10,000 rows.

---

## 6. Phase 12 Enables All Future Phases

Phase 12 is the foundation that unlocks:

| Future Phase | Dependency on Phase 12 |
|-------------|----------------------|
| Phase 14 `/compare` command | Requires two named scopes to compare |
| Phase 15 Cross-deal contradiction detection | Requires isolated per-deal embedding spaces |
| Phase 15 Anomaly detection | Requires comparing specific deal scope against baseline |
| Phase 15 Cross-deal comps | Federated search across N deal scopes |

Without Phase 12, cross-deal intelligence (Phase 15) is impossible at scale. Phase 12 is the architectural prerequisite for the entire deal intelligence tier.
