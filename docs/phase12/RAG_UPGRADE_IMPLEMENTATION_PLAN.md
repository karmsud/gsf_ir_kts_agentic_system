# Phase 12: Named Scoped Knowledge Spaces — Implementation Plan

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## 1. Motivation — The Namespace Problem in RAG

### 1.1 Why Shared Embedding Spaces Fail at Scale

Every document in KTS today lives in a single ChromaDB collection. Ten documents or ten thousand — same space. This creates a fundamental problem:

**Scope bleed**: When a user asks about "Bear Stearns 2006-HE1", the retriever searches across all ingested documents simultaneously. Every retrieved chunk competes on cosine similarity alone, regardless of which deal it came from. With 10,000 deal folders, each containing 5-10 documents, that is 50,000-100,000 documents in a single embedding space.

The consequences:
1. **Cross-contamination**: An answer about Bear Stearns 2006-HE1's Determination Date may include a highly similar clause from Bear Stearns 2006-HE2 — same template language, different dates, wrong answer
2. **Performance**: Similarity search over 50 million chunks is slow. Scope-bounded search over 500 chunks (one deal folder) is instant
3. **Trust**: Users cannot be certain the answer was grounded in the documents they intended to query. They cannot verify scope.
4. **Accidental cross-deal hallucination**: LLM sees 15 chunks from 5 different deals and synthesizes a "deal" that doesn't exist

### 1.2 The Solution: Folder = Embedding Namespace

The insight is architectural: **each folder in the knowledge source directory is its own isolated embedding space.** The folder name becomes the scope identifier. The embedded `.kts` directory lives *inside* the folder it indexes. Users select scope through slash commands — and the slash commands are *derived automatically from folder names*.

This is not a new concept in vector databases (ChromaDB supports named collections natively), but applying it as a first-class user-facing feature — where the folder IS the namespace, the name IS the command, and scope selection is a natural part of the query syntax — is the key design innovation here.

---

## 2. The Three Scenarios (Canonical Examples)

### 2.1 Example 1 — Functional Knowledge Silos

```
knowledge_source/
├── training/          → .kts/ (training embedding space)
│   ├── onboarding.pdf, policy.docx, ...
├── knowledge/         → .kts/ (knowledge base embedding space)
│   ├── sop_guide.pdf, faq.docx, ...
└── support/           → .kts/ (support embedding space)
    ├── hp_guide.pdf, troubleshooting.docx, ...
```

User interaction:
```
@kts /training  what is the 30-day onboarding checklist?
@kts /support   my printer shows error code E-5
@kts /knowledge what is the escalation policy for P1 incidents?
```

Each query is **locked to its embedding space**. Training questions cannot accidentally retrieve support documentation. A performance question cannot surface a training document. The scope is explicit, the grounding is guaranteed.

### 2.2 Example 2 — Deal-Per-Folder with Two-Level Scope Narrowing

```
deals/
├── bear_stearns_2006_HE1/    → .kts/ (deal embedding space)
│   ├── psa.docx              → doc_type: PSA
│   ├── prospectus_supp.docx  → doc_type: PROSUPP
│   ├── indenture.docx        → doc_type: INDENTURE
│   └── trust_agreement.docx  → doc_type: TRUST
├── bear_stearns_2006_HE2/    → .kts/ (separate deal embedding space)
│   ├── psa.docx
│   └── ...
└── ... (10,000 more deals)
```

**Level 1 scope — deal only:**
```
@kts /bear_stearns_2006_HE1  What is the Determination Date?
```
Retrieves only from `bear_stearns_2006_HE1/.kts/` — zero risk of contamination from HE2 or any other deal.

**Level 2 scope — deal + document type:**
```
@kts /bear_stearns_2006_HE1 /psa  What is the Determination Date?
```
Retrieves only from `bear_stearns_2006_HE1/.kts/`, filtered to chunks with `doc_type: PSA`. This exploits ChromaDB's `where` clause — no separate collection needed. The embedding space is the deal; the doc_type is a metadata filter within it.

**Why does this improve RAG quality?** When you narrow to `/psa`, you eliminate:
- Duplicate or conflicting definitions from the Prospectus Supplement
- Trust Agreement language that uses similar terms with different meanings
- Indenture cross-references that expand the LLM context with irrelevant material

Precision goes up. Retrieval noise goes down. Answer quality improves measurably.

### 2.3 Example 3 — Smart Cross-Scope Federated Search

```
@kts  how many bear deals have the concept "dscr loans"?
```

No scope specified. The user wants a cross-deal answer. The naive approach — query all 10,000 collections — is unusable (10,000 × 500ms = hours).

**The smart approach: two-stage federated retrieval**

**Stage 1 — Deal Catalog Query** (milliseconds)  
A lightweight "deal catalog" index is maintained separately. It contains one entry per deal with: deal name, slugified folder name, deal type, key metadata tags (issuer, year, collateral type, party names). This catalog is tiny (~10,000 rows) and searchable in milliseconds.

Query the catalog for "bear deals":
- Exact match: all folders whose name contains "bear"
- Returns: 50-60 deal folder paths

**Stage 2 — Scoped Federated Search** (seconds, parallelized)  
Query only those 50-60 deal collections in parallel for "dscr loans". Fan-out, collect, aggregate.

Result:
```
Found "DSCR loans" in 12 of 58 Bear Stearns deals:
- bear_stearns_2006_HE1: Section 2.01, 2.03 (3 references)
- bear_stearns_2007_ALT_A: Section 1.01 (1 reference)
- ...
```

This is **federated multi-scope RAG with smart routing**. The user never specifies which 58 collections — the system figures it out from the catalog query.

---

## 3. Implementation Order

| Order | Increment | Impact | Risk | Rationale |
|-------|-----------|--------|------|-----------|
| **12.1** | Per-folder `.kts` directory + named ChromaDB collections | HIGH | LOW | Foundation. Change how collections are named and created. |
| **12.2** | Auto-discovery + dynamic slash command registration | VERY HIGH | MEDIUM | Scan knowledge source on startup, register slash commands per folder |
| **12.3** | Two-level scope narrowing (`/deal /doctype`) | VERY HIGH | LOW | ChromaDB `where` filter — metadata only, no new collections |
| **12.4** | Deal catalog index + smart cross-scope routing | HIGH | MEDIUM | Separate lightweight catalog. Fan-out federated search. |

---

## 4. Increment 12.1 — Per-Folder `.kts` Directories

### 4.1 Storage Architecture Change

**Current:**
```
~/.kts/                    ← global ChromaDB location
    chroma.sqlite3
    collections/
        default/           ← everything in one collection
```

**Phase 12:**
```
knowledge_source/
    bear_stearns_2006_HE1/
        psa.docx
        trust_agreement.docx
        .kts/              ← per-deal embedding space
            chroma.sqlite3
            collections/
                bear_stearns_2006_HE1/   ← single collection per folder
    bear_stearns_2006_HE2/
        .kts/
            ...
```

The `.kts` directory lives *inside the folder it indexes*. Move the folder — the embeddings move with it. Delete the folder — the embeddings are deleted too. No orphaned index state.

### 4.2 Backward Compatibility

The global `~/.kts/` path remains supported. Documents ingested without a scope continue to use it. Per-folder `.kts/` is additive — it does not break any existing index.

---

## 5. Increment 12.2 — Auto-Discovery & Dynamic Slash Commands

### 5.1 Discovery on Extension Activation

On VS Code startup (and on `kts.refreshScopes` command), the extension scans the configured `kts.knowledgeSourceRoot` directory:

```javascript
async function discoverScopes(knowledgeSourceRoot) {
    const scopes = [];
    const entries = await fs.readdir(knowledgeSourceRoot, { withFileTypes: true });
    for (const entry of entries) {
        if (entry.isDirectory()) {
            const ktsPath = path.join(knowledgeSourceRoot, entry.name, '.kts');
            const hasIndex = await pathExists(ktsPath);
            scopes.push({
                name: entry.name,
                slug: slugify(entry.name),    // "Bear Stearns 2006-HE1" → "bear_stearns_2006_HE1"
                ktsPath: ktsPath,
                indexed: hasIndex
            });
        }
    }
    return scopes;
}
```

### 5.2 Dynamic Command Registration

VS Code Chat Participant slash commands can be registered programmatically at activation time. Each discovered scope with a `.kts` directory becomes a registered slash command:

```javascript
participant.commandHandler = [{
    name: 'bear_stearns_2006_HE1',
    description: 'Query the Bear Stearns 2006-HE1 deal knowledge base'
}, {
    name: 'bear_stearns_2006_HE2',
    description: 'Query the Bear Stearns 2006-HE2 deal knowledge base'
}
// ... auto-generated for each indexed folder
];
```

**The folder name IS the command.** No manual registration. No config file. Add a new deal folder, run `/ingest`, the command appears.

### 5.3 Slugification Rules

| Folder Name | Slug (Slash Command) |
|-------------|---------------------|
| `Bear Stearns 2006-HE1` | `bear_stearns_2006_HE1` |
| `Training Materials` | `training_materials` |
| `HP Support Docs` | `hp_support_docs` |
| `Q3 2025 Deals` | `q3_2025_deals` |

Rules: lowercase, spaces→underscore, hyphens→underscore, remove special chars.

---

## 6. Increment 12.3 — Two-Level Scope Narrowing

### 6.1 Syntax

```
@kts /[scope_slug] /[doc_type]  [question]

Example:
@kts /bear_stearns_2006_HE1 /psa  What is the Determination Date?
```

### 6.2 Implementation

The second token (`/psa`) is NOT a registered slash command — it is a **query modifier parsed from the command string**. The extension parses it and passes `doc_type_filter: "PSA"` to the backend.

```javascript
function parseQuery(request) {
    // request.command = 'bear_stearns_2006_HE1'  (first /slug)
    // request.prompt = '/psa What is the Determination Date?'
    
    const docTypeMatch = request.prompt.match(/^\/(\w+)\s+(.*)/);
    if (docTypeMatch) {
        return {
            scope: request.command,
            doc_type_filter: docTypeMatch[1].toUpperCase(),  // 'PSA'
            query: docTypeMatch[2]                           // 'What is the Determination Date?'
        };
    }
    return { scope: request.command, doc_type_filter: null, query: request.prompt };
}
```

Backend ChromaDB query with filter:
```python
# Without doc_type filter
results = collection.query(query_embeddings=[q_emb], n_results=20)

# With doc_type filter
results = collection.query(
    query_embeddings=[q_emb],
    n_results=20,
    where={"doc_type": {"$eq": "PSA"}}
)
```

Zero new collections. Same index. Filter is a metadata query — ChromaDB handles it natively.

---

## 7. Increment 12.4 — Deal Catalog & Smart Cross-Scope Routing

### 7.1 The Deal Catalog Index

A separate lightweight SQLite table (or small ChromaDB collection) with one row per deal folder:

```sql
CREATE TABLE deal_catalog (
    folder_name TEXT PRIMARY KEY,
    slug TEXT,
    kts_path TEXT,
    doc_count INTEGER,
    doc_types TEXT,          -- JSON array: ["PSA", "PROSUPP", "INDENTURE"]
    issuers TEXT,            -- JSON array: ["Bear Stearns", "WSHFC"]
    years TEXT,              -- JSON array: ["2006", "2007"]
    collateral_types TEXT,   -- JSON array: ["HELOC", "Subprime", "Alt-A"]
    key_parties TEXT,        -- JSON array: ["Wells Fargo", "Deutsche Bank"]
    last_indexed TIMESTAMP
);
```

This catalog is populated at ingest time (one row per folder) and updated when docs are added or removed.

### 7.2 Cross-Scope Routing Logic

When no scope is specified in the query:

```python
def route_query(query: str, catalog: DealCatalog) -> list[str]:
    """Return list of scope slugs to search."""
    
    # 1. Try exact scope mention detection
    for scope in catalog.all_scopes():
        if scope.slug in query.lower().replace(' ', '_'):
            return [scope.slug]  # exact scope match
    
    # 2. Try issuer/keyword matching
    matching_scopes = catalog.search(query)  # fast keyword search
    if len(matching_scopes) <= 100:
        return [s.slug for s in matching_scopes]  # federated search this subset
    
    # 3. Too many matches — ask user to narrow scope
    return None  # triggers "please specify a scope" message
```

### 7.3 Federated Search Fan-out

```python
async def federated_search(query: str, scope_slugs: list[str], top_k: int = 5) -> list[Chunk]:
    """Search multiple scopes in parallel, merge results."""
    tasks = [
        search_scope(query, slug, top_k=top_k)
        for slug in scope_slugs
    ]
    per_scope_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Merge, dedup, re-rank
    all_chunks = []
    for results in per_scope_results:
        if isinstance(results, Exception):
            continue  # skip failed scope, don't crash
        all_chunks.extend(results)
    
    return rerank(all_chunks, query, top_k=20)
```

---

## 8. Files Changed

| File | Change Type | Phase |
|------|------------|-------|
| `backend/vector/store.py` | Modified | 12.1 (per-folder collection naming) |
| `backend/agents/ingestion_agent.py` | Modified | 12.1, 12.4 (catalog population) |
| `backend/agents/retrieval_service.py` | Modified | 12.2, 12.3, 12.4 |
| `backend/retrieval/scope_router.py` | New | 12.4 |
| `backend/vector/deal_catalog.py` | New | 12.4 |
| `extension/chat/participant.js` | Modified | 12.2, 12.3 |
| `extension/lib/scope_discovery.js` | New | 12.2 |
| `config/settings.py` | Modified | 12.1 (knowledgeSourceRoot setting) |

---

## 9. Success Metrics

| Metric | Baseline | Target (Phase 12) |
|--------|----------|------------------|
| Cross-deal answer contamination rate | ~15% | <1% |
| Scoped retrieval latency vs. global | Baseline | 10x faster on single-scope queries |
| Two-level scope precision improvement | Baseline | ~25% precision gain on doc-type filtered queries |
| Cross-scope routing accuracy (correct scope selected) | N/A | >90% on named-entity queries |
| User scope selection adoption | N/A | >70% of multi-deal users use scopes within 1 week |
