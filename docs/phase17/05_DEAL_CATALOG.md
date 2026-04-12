# Phase 17 — Enhanced Deal Catalog

> **Document**: 05_DEAL_CATALOG.md
> **Phase**: 17 — Document-Level Isolation & Cross-Deal Intelligence
> **Status**: Design Specification
> **Last Updated**: 2025-07-14

---

## Table of Contents

1. [Overview](#1-overview)
2. [Current State Analysis](#2-current-state-analysis)
3. [Enhanced Schema Design](#3-enhanced-schema-design)
4. [Catalog Population (Write Path)](#4-catalog-population-write-path)
5. [Catalog Query API (Read Path)](#5-catalog-query-api-read-path)
6. [Wildcard & Glob Search](#6-wildcard--glob-search)
7. [Structured Query Support](#7-structured-query-support)
8. [Doc-Type Registry](#8-doc-type-registry)
9. [Catalog Maintenance](#9-catalog-maintenance)
10. [SQLite Migration Strategy](#10-sqlite-migration-strategy)
11. [API Reference](#11-api-reference)
12. [Performance Considerations](#12-performance-considerations)

---

## 1. Overview

The Deal Catalog is the central metadata registry that tracks every indexed deal
folder and every document within it. Phase 17 extends the existing Phase 12.4
SQLite-backed catalog with:

- **Document-level metadata** — Each document within a deal gets a catalog row,
  enabling document-specific queries and autocomplete.
- **Structured query fields** — Vintage year, issuer name, series, collateral
  type become first-class filterable fields.
- **Wildcard / glob search** — Supports `*` patterns for cross-deal queries
  like "all PSAs from 2006."
- **Doc-type registry** — Per-deal list of available document types for
  autocomplete and validation.

### Design Principles

| Principle | Rationale |
|-----------|-----------|
| Zero-cost migration | New columns with defaults; old data remains valid |
| Sub-millisecond lookups | SQLite + FTS5 for keyword search, B-tree indexes for structured queries |
| Single source of truth | All scope/doc metadata flows through the catalog |
| Lightweight footprint | No external dependencies beyond SQLite (bundled with Python) |

---

## 2. Current State Analysis

### Existing Schema (Phase 12.4)

```sql
CREATE TABLE IF NOT EXISTS deal_catalog (
    folder_name     TEXT PRIMARY KEY,
    slug            TEXT NOT NULL,
    kts_path        TEXT NOT NULL,
    doc_count       INTEGER DEFAULT 0,
    doc_types       TEXT DEFAULT '[]',     -- JSON array
    issuers         TEXT DEFAULT '[]',     -- JSON array
    years           TEXT DEFAULT '[]',     -- JSON array
    collateral_types TEXT DEFAULT '[]',    -- JSON array
    key_parties     TEXT DEFAULT '[]',     -- JSON array
    last_indexed    TEXT                   -- ISO timestamp
);
```

### Existing FTS5 Index

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS deal_catalog_fts USING fts5(
    folder_name, slug, issuers, key_parties, years, collateral_types,
    content='deal_catalog',
    content_rowid='rowid'
);
```

### Current Capabilities

| Capability | Supported | Notes |
|------------|-----------|-------|
| Keyword search (FTS5) | ✅ | Millisecond latency |
| Keyword search (LIKE fallback) | ✅ | For SQLite builds without FTS5 |
| Upsert deal entry | ✅ | ON CONFLICT DO UPDATE |
| List all scopes | ✅ | `all_scopes()` method |
| Discover scopes from filesystem | ✅ | `discover_scopes()` function |
| Search by doc_name_prefix | ❌ | **Gap** |
| List doc types per deal | ❌ | Stored as JSON but not queryable |
| Wildcard / glob search | ❌ | **Gap** |
| Structured field filters | ❌ | JSON arrays not indexed |

### Current Python Classes

```
backend/vector/deal_catalog.py
├── CatalogEntry (dataclass)
│   ├── folder_name, slug, kts_path
│   ├── doc_count, doc_types, issuers, years
│   ├── collateral_types, key_parties
│   └── last_indexed
├── DealCatalog
│   ├── __init__(db_path)
│   ├── upsert(entry)
│   ├── delete(folder_name)
│   ├── get(folder_name) → CatalogEntry
│   ├── search(query) → List[Dict]
│   ├── all_scopes() → List[Dict]
│   └── count() → int
└── discover_scopes(root) → List[CatalogEntry]
```

---

## 3. Enhanced Schema Design

### 3.1 New `deal_documents` Table

A second table to track individual documents within each deal:

```sql
CREATE TABLE IF NOT EXISTS deal_documents (
    doc_id          TEXT PRIMARY KEY,        -- "{folder_name}::{doc_name_prefix}"
    folder_name     TEXT NOT NULL,           -- FK → deal_catalog.folder_name
    doc_name_prefix TEXT NOT NULL,           -- e.g. "PSA_2006-HE1"
    doc_type        TEXT NOT NULL DEFAULT '',-- e.g. "PSA", "PROSUPP", "INDENTURE"
    original_filename TEXT DEFAULT '',       -- Original source filename
    page_count      INTEGER DEFAULT 0,
    chunk_count     INTEGER DEFAULT 0,      -- Number of items in ChromaDB
    section_count   INTEGER DEFAULT 0,      -- Number of sections ingested
    definition_count INTEGER DEFAULT 0,     -- Defined terms extracted
    rule_count      INTEGER DEFAULT 0,      -- Rules extracted
    file_size_bytes INTEGER DEFAULT 0,
    ingested_at     TEXT,                    -- ISO timestamp
    metadata_json   TEXT DEFAULT '{}'       -- Extensible JSON blob
);

CREATE INDEX IF NOT EXISTS idx_deal_docs_folder
    ON deal_documents(folder_name);
CREATE INDEX IF NOT EXISTS idx_deal_docs_type
    ON deal_documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_deal_docs_prefix
    ON deal_documents(doc_name_prefix);
```

### 3.2 Enhanced `deal_catalog` Columns

Add structured query columns to the existing table:

```sql
ALTER TABLE deal_catalog ADD COLUMN vintage_year    INTEGER DEFAULT 0;
ALTER TABLE deal_catalog ADD COLUMN primary_issuer  TEXT DEFAULT '';
ALTER TABLE deal_catalog ADD COLUMN series_name     TEXT DEFAULT '';
ALTER TABLE deal_catalog ADD COLUMN deal_type       TEXT DEFAULT '';  -- "RMBS", "CMBS", "CLO", etc.
ALTER TABLE deal_catalog ADD COLUMN total_chunks    INTEGER DEFAULT 0;
ALTER TABLE deal_catalog ADD COLUMN total_sections  INTEGER DEFAULT 0;
ALTER TABLE deal_catalog ADD COLUMN total_definitions INTEGER DEFAULT 0;
ALTER TABLE deal_catalog ADD COLUMN total_rules     INTEGER DEFAULT 0;
ALTER TABLE deal_catalog ADD COLUMN graph_node_count INTEGER DEFAULT 0;
ALTER TABLE deal_catalog ADD COLUMN graph_edge_count INTEGER DEFAULT 0;
```

### 3.3 Enhanced `CatalogEntry` Dataclass

```python
@dataclass
class CatalogEntry:
    """One row in the deal catalog — enhanced for Phase 17."""

    folder_name: str
    slug: str
    kts_path: str
    doc_count: int = 0
    doc_types: List[str] = field(default_factory=list)
    issuers: List[str] = field(default_factory=list)
    years: List[str] = field(default_factory=list)
    collateral_types: List[str] = field(default_factory=list)
    key_parties: List[str] = field(default_factory=list)
    last_indexed: Optional[str] = None

    # ── Phase 17 additions ──────────────────────────────────
    vintage_year: int = 0              # Extracted from folder name or docs
    primary_issuer: str = ""           # First/primary issuer entity
    series_name: str = ""              # E.g. "2006-HE1"
    deal_type: str = ""                # "RMBS", "CMBS", "CLO", etc.
    total_chunks: int = 0              # Sum of all doc chunks
    total_sections: int = 0
    total_definitions: int = 0
    total_rules: int = 0
    graph_node_count: int = 0
    graph_edge_count: int = 0
```

### 3.4 New `DocumentEntry` Dataclass

```python
@dataclass
class DocumentEntry:
    """One row in the deal_documents table."""

    doc_id: str                       # "{folder_name}::{doc_name_prefix}"
    folder_name: str
    doc_name_prefix: str
    doc_type: str = ""
    original_filename: str = ""
    page_count: int = 0
    chunk_count: int = 0
    section_count: int = 0
    definition_count: int = 0
    rule_count: int = 0
    file_size_bytes: int = 0
    ingested_at: Optional[str] = None
    metadata_json: Dict[str, Any] = field(default_factory=dict)

    @property
    def doc_id_computed(self) -> str:
        return f"{self.folder_name}::{self.doc_name_prefix}"
```

---

## 4. Catalog Population (Write Path)

### 4.1 Population Flow

During ingestion, the catalog is populated in two stages:

```
Source Files → IngestionAgent
    │
    ├─ Per-document: upsert_document()
    │   ├─ doc_name_prefix extracted from filename
    │   ├─ doc_type classified by NER/filename heuristics
    │   ├─ chunk_count, section_count tallied during ingestion
    │   └─ definition_count, rule_count counted post-extraction
    │
    └─ Per-deal (after all docs ingested): upsert_deal()
        ├─ Aggregate doc_count, total_chunks, total_sections
        ├─ Extract vintage_year from folder name or doc dates
        ├─ Extract primary_issuer from NER entities
        ├─ Extract series_name from folder name patterns
        └─ Build doc_types list from all DocumentEntry rows
```

### 4.2 Document Metadata Extraction

```python
def _extract_document_metadata(
    self,
    filename: str,
    ingestion_stats: Dict[str, Any],
) -> DocumentEntry:
    """Extract metadata for a single ingested document.

    Called by IngestionAgent after processing each file.
    """
    doc_name_prefix = self._extract_doc_name_prefix(filename)
    doc_type = self._classify_doc_type(filename, doc_name_prefix)

    return DocumentEntry(
        doc_id=f"{self._current_deal}::{doc_name_prefix}",
        folder_name=self._current_deal,
        doc_name_prefix=doc_name_prefix,
        doc_type=doc_type,
        original_filename=filename,
        page_count=ingestion_stats.get("page_count", 0),
        chunk_count=ingestion_stats.get("chunk_count", 0),
        section_count=ingestion_stats.get("section_count", 0),
        definition_count=ingestion_stats.get("definition_count", 0),
        rule_count=ingestion_stats.get("rule_count", 0),
        file_size_bytes=ingestion_stats.get("file_size_bytes", 0),
        ingested_at=datetime.now(timezone.utc).isoformat(),
    )
```

### 4.3 Deal-Level Aggregation

```python
def _aggregate_deal_metadata(
    self,
    folder_name: str,
    documents: List[DocumentEntry],
) -> CatalogEntry:
    """Aggregate document-level metadata into deal-level entry.

    Called after all documents in a deal folder are processed.
    """
    doc_types = sorted(set(d.doc_type for d in documents if d.doc_type))
    total_chunks = sum(d.chunk_count for d in documents)
    total_sections = sum(d.section_count for d in documents)
    total_definitions = sum(d.definition_count for d in documents)
    total_rules = sum(d.rule_count for d in documents)

    # Extract vintage year from folder name
    year_match = re.search(r'\b(19|20)\d{2}\b', folder_name)
    vintage_year = int(year_match.group()) if year_match else 0

    # Extract series name (e.g. "2006-HE1")
    series_match = re.search(r'(\d{4}-\w+)', folder_name)
    series_name = series_match.group(1) if series_match else ""

    return CatalogEntry(
        folder_name=folder_name,
        slug=slugify(folder_name),
        kts_path=str(Path(self._knowledge_source_root) / folder_name / ".kts"),
        doc_count=len(documents),
        doc_types=doc_types,
        vintage_year=vintage_year,
        series_name=series_name,
        total_chunks=total_chunks,
        total_sections=total_sections,
        total_definitions=total_definitions,
        total_rules=total_rules,
    )
```

### 4.4 Ingestion Agent Integration

The ingestion agent calls catalog population at two points:

```python
# In IngestionAgent.ingest_folder():

for file_path in source_files:
    # ... existing ingestion logic ...
    stats = self._ingest_single_file(file_path)

    # Phase 17: Register document in catalog
    doc_entry = self._extract_document_metadata(file_path.name, stats)
    self._catalog.upsert_document(doc_entry)

# After all files in deal processed:
deal_docs = self._catalog.get_documents(folder_name)
deal_entry = self._aggregate_deal_metadata(folder_name, deal_docs)
self._catalog.upsert(deal_entry)
```

---

## 5. Catalog Query API (Read Path)

### 5.1 New Methods on `DealCatalog`

```python
class DealCatalog:
    """Phase 17 enhanced methods (additions to existing class)."""

    # ── Document-Level Queries ─────────────────────────────

    def upsert_document(self, entry: DocumentEntry) -> None:
        """Insert or update a document catalog entry."""
        ...

    def get_documents(self, folder_name: str) -> List[DocumentEntry]:
        """Get all documents for a deal folder."""
        ...

    def get_document(self, folder_name: str, doc_name_prefix: str) -> Optional[DocumentEntry]:
        """Get a specific document by deal + doc_name_prefix."""
        ...

    def get_doc_types(self, folder_name: str) -> List[str]:
        """Get available doc types for a specific deal.

        Returns sorted unique list, e.g. ["INDENTURE", "PROSUPP", "PSA"].
        Used for autocomplete in extension.
        """
        ...

    def list_documents(self, folder_name: str) -> List[Dict[str, Any]]:
        """List all documents with summary stats.

        Returns:
            [{"doc_name_prefix": "PSA_2006-HE1",
              "doc_type": "PSA",
              "chunk_count": 450,
              "definition_count": 120,
              "rule_count": 85}, ...]
        """
        ...

    # ── Structured Queries ─────────────────────────────────

    def search_by_vintage(self, year: int) -> List[CatalogEntry]:
        """Find all deals from a specific vintage year."""
        ...

    def search_by_issuer(self, issuer: str) -> List[CatalogEntry]:
        """Find all deals by issuer name (fuzzy match)."""
        ...

    def search_by_deal_type(self, deal_type: str) -> List[CatalogEntry]:
        """Find all deals of a specific type (RMBS, CMBS, CLO)."""
        ...

    def search_by_doc_type(self, doc_type: str) -> List[Dict[str, Any]]:
        """Find all deals that contain a specific document type.

        Returns deals (not documents) that have at least one doc of the
        specified type.

        Used for wildcard queries: `//PSA what is Realized Loss?`
        """
        ...

    # ── Glob / Wildcard ────────────────────────────────────

    def glob_search(self, pattern: str) -> List[CatalogEntry]:
        """Search deals using glob-like patterns.

        Patterns:
            "bear*"     → all deals starting with "bear"
            "*2006*"    → all deals containing "2006"
            "*HE*"      → all deals with "HE" in the name
        """
        ...

    # ── Statistics ─────────────────────────────────────────

    def catalog_stats(self) -> Dict[str, Any]:
        """Return aggregate catalog statistics.

        Returns:
            {"total_deals": 42,
             "total_documents": 168,
             "total_chunks": 50000,
             "vintage_range": [2004, 2024],
             "doc_types": ["PSA", "PROSUPP", "INDENTURE", ...],
             "issuers": ["Bear Stearns", "Morgan Stanley", ...]}
        """
        ...
```

### 5.2 SQL Queries Behind New Methods

#### `get_doc_types`

```sql
SELECT DISTINCT doc_type
FROM deal_documents
WHERE folder_name = ?
ORDER BY doc_type;
```

#### `search_by_vintage`

```sql
SELECT * FROM deal_catalog
WHERE vintage_year = ?
ORDER BY folder_name;
```

#### `search_by_doc_type` (cross-deal)

```sql
SELECT DISTINCT dc.*
FROM deal_catalog dc
JOIN deal_documents dd ON dc.folder_name = dd.folder_name
WHERE dd.doc_type = ?
ORDER BY dc.folder_name;
```

#### `glob_search`

```sql
SELECT * FROM deal_catalog
WHERE folder_name GLOB ?
   OR slug GLOB ?
ORDER BY folder_name;
```

---

## 6. Wildcard & Glob Search

### 6.1 Wildcard Pattern Syntax

| Pattern | Meaning | Example |
|---------|---------|---------|
| `*` | Match any sequence of characters | `bear*` → "Bear Stearns 2006-HE1" |
| `?` | Match exactly one character | `200?` → "2004", "2006", "2007" |
| `[...]` | Character class | `[0-9]` → any digit |
| `*keyword*` | Contains keyword | `*mortgage*` → any deal with "mortgage" |

### 6.2 Glob Search Implementation

```python
def glob_search(self, pattern: str) -> List[CatalogEntry]:
    """Search deals using glob-like patterns.

    Supports * (any chars), ? (single char), [...] (char class).
    Searches across folder_name and slug.
    """
    # Normalize: lowercase the pattern for slug matching
    slug_pattern = slugify(pattern.replace("*", "GLOB_STAR").replace("?", "GLOB_Q"))
    slug_pattern = slug_pattern.replace("glob_star", "*").replace("glob_q", "?")

    conn = self._connect()
    try:
        # SQLite GLOB is case-sensitive; use both original and slug
        rows = conn.execute(
            """SELECT * FROM deal_catalog
               WHERE folder_name GLOB ? COLLATE NOCASE
                  OR slug GLOB ?
               ORDER BY folder_name""",
            (pattern, slug_pattern),
        ).fetchall()
        return [self._row_to_entry(row) for row in rows]
    finally:
        conn.close()
```

### 6.3 Cross-Deal Doc-Type Wildcard

The especially powerful wildcard pattern is `//DOC_TYPE` which searches
across ALL deals for a specific document type:

```python
def search_by_doc_type_across_deals(
    self, doc_type: str
) -> List[Dict[str, Any]]:
    """Find all deal/doc combinations matching a document type.

    Returns:
        [{"folder_name": "Bear Stearns 2006-HE1",
          "slug": "bear_stearns_2006_he1",
          "doc_name_prefix": "PSA_2006-HE1",
          "kts_path": "/path/.kts"}, ...]
    """
    conn = self._connect()
    try:
        rows = conn.execute(
            """SELECT dc.folder_name, dc.slug, dc.kts_path,
                      dd.doc_name_prefix, dd.doc_type
               FROM deal_catalog dc
               JOIN deal_documents dd ON dc.folder_name = dd.folder_name
               WHERE UPPER(dd.doc_type) = UPPER(?)
               ORDER BY dc.folder_name""",
            (doc_type,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
```

---

## 7. Structured Query Support

### 7.1 Structured Query Fields

Phase 17 makes the following fields **first-class indexed columns** instead
of JSON arrays:

| Field | Column | Type | Index |
|-------|--------|------|-------|
| Vintage year | `vintage_year` | INTEGER | B-tree |
| Primary issuer | `primary_issuer` | TEXT | B-tree |
| Series name | `series_name` | TEXT | B-tree |
| Deal type | `deal_type` | TEXT | B-tree |

### 7.2 Composite Query Support

```python
def structured_search(
    self,
    *,
    vintage_year: Optional[int] = None,
    issuer: Optional[str] = None,
    doc_type: Optional[str] = None,
    deal_type: Optional[str] = None,
    collateral_type: Optional[str] = None,
) -> List[CatalogEntry]:
    """Structured multi-field search with AND semantics.

    All non-None parameters are combined with AND.

    Examples:
        # All RMBS deals from 2006 by Bear Stearns
        structured_search(vintage_year=2006, issuer="Bear Stearns",
                          deal_type="RMBS")

        # All deals with PSA documents
        structured_search(doc_type="PSA")
    """
    conditions = []
    params = []

    if vintage_year is not None:
        conditions.append("vintage_year = ?")
        params.append(vintage_year)

    if issuer is not None:
        conditions.append("primary_issuer LIKE ? COLLATE NOCASE")
        params.append(f"%{issuer}%")

    if deal_type is not None:
        conditions.append("deal_type = ? COLLATE NOCASE")
        params.append(deal_type)

    if collateral_type is not None:
        conditions.append("collateral_types LIKE ? COLLATE NOCASE")
        params.append(f'%"{collateral_type}"%')

    if doc_type is not None:
        # Join with deal_documents for doc-type filtering
        conditions.append(
            "folder_name IN (SELECT folder_name FROM deal_documents "
            "WHERE UPPER(doc_type) = UPPER(?))"
        )
        params.append(doc_type)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    conn = self._connect()
    try:
        rows = conn.execute(
            f"SELECT * FROM deal_catalog WHERE {where_clause} ORDER BY folder_name",
            params,
        ).fetchall()
        return [self._row_to_entry(row) for row in rows]
    finally:
        conn.close()
```

### 7.3 Key-Value Filter Syntax

The command syntax supports `key:value` tokens that map to structured queries:

| Token | Maps To | Example |
|-------|---------|---------|
| `/year:2006` | `vintage_year=2006` | All 2006 deals |
| `/issuer:morgan` | `issuer="morgan"` | All Morgan Stanley deals |
| `/type:RMBS` | `deal_type="RMBS"` | All RMBS deals |
| `/collateral:HELOC` | `collateral_type="HELOC"` | All HELOC deals |

---

## 8. Doc-Type Registry

### 8.1 Purpose

The doc-type registry provides autocomplete suggestions for `/{scope}/DOC_TYPE`
commands. It answers: "What document types are available in this deal?"

### 8.2 Registry Data

```python
# Automatically populated during ingestion; not hard-coded.
# Example registry for a typical deal:

deal_doc_types = {
    "bear_stearns_2006_he1": [
        {"doc_type": "PSA", "count": 1, "doc_name_prefix": "PSA_2006-HE1"},
        {"doc_type": "PROSUPP", "count": 1, "doc_name_prefix": "PROSUPP_2006-HE1"},
        {"doc_type": "INDENTURE", "count": 1, "doc_name_prefix": "IND_2006-HE1"},
        {"doc_type": "SAA", "count": 1, "doc_name_prefix": "SAA_2006-HE1"},
    ],
}
```

### 8.3 Extension Integration

The doc-type registry is exposed to the VS Code extension via the backend CLI:

```
kts catalog doc-types --scope bear_stearns_2006_he1
```

Output:
```json
{
  "scope": "bear_stearns_2006_he1",
  "doc_types": ["INDENTURE", "PROSUPP", "PSA", "SAA"],
  "documents": [
    {"doc_type": "INDENTURE", "doc_name_prefix": "IND_2006-HE1", "chunks": 320},
    {"doc_type": "PROSUPP", "doc_name_prefix": "PROSUPP_2006-HE1", "chunks": 180},
    {"doc_type": "PSA", "doc_name_prefix": "PSA_2006-HE1", "chunks": 450},
    {"doc_type": "SAA", "doc_name_prefix": "SAA_2006-HE1", "chunks": 95}
  ]
}
```

### 8.4 Autocomplete Flow

```
User types: @kts /bear_stearns_2006_he1 /
                                           ↑ Trigger autocomplete

Extension calls: catalog.get_doc_types("bear_stearns_2006_he1")

Returns: ["INDENTURE", "PROSUPP", "PSA", "SAA"]

User sees:
  /PSA         - Pooling and Servicing Agreement (450 chunks)
  /PROSUPP     - Prospectus Supplement (180 chunks)
  /INDENTURE   - Indenture (320 chunks)
  /SAA         - Sale and Assignment Agreement (95 chunks)
```

---

## 9. Catalog Maintenance

### 9.1 Re-indexing

When a deal is re-ingested, the catalog is updated:

```python
def reindex_deal(self, folder_name: str, documents: List[DocumentEntry]) -> None:
    """Re-index a deal: delete old document entries, insert new ones.

    Called when `kts ingest --force` is used.
    """
    with self._lock:
        conn = self._connect()
        try:
            # Delete old document entries
            conn.execute(
                "DELETE FROM deal_documents WHERE folder_name = ?",
                (folder_name,),
            )
            # Insert new document entries
            for doc in documents:
                self._insert_document(conn, doc)
            conn.commit()
        finally:
            conn.close()

    # Update deal-level aggregation
    deal_entry = self._aggregate_deal_metadata(folder_name, documents)
    self.upsert(deal_entry)
```

### 9.2 Pruning Stale Entries

```python
def prune_stale(self, knowledge_source_root: str) -> int:
    """Remove catalog entries for deals no longer present on disk.

    Returns number of entries pruned.
    """
    all_entries = self.all_scopes()
    pruned = 0
    for entry in all_entries:
        deal_path = Path(knowledge_source_root) / entry["folder_name"]
        if not deal_path.exists():
            self.delete(entry["folder_name"])
            pruned += 1
    return pruned
```

### 9.3 CLI Commands

```bash
# Show catalog statistics
kts catalog stats

# List all deals
kts catalog list

# List documents in a deal
kts catalog docs --scope bear_stearns_2006_he1

# Prune stale entries
kts catalog prune

# Search
kts catalog search "bear stearns 2006"

# Structured search
kts catalog search --year 2006 --issuer "Bear Stearns" --doc-type PSA
```

---

## 10. SQLite Migration Strategy

### 10.1 Migration Approach

Phase 17 uses **additive migration** — new columns and tables are added
without modifying existing data:

```python
_MIGRATION_V17_SQL = [
    # New columns on deal_catalog
    "ALTER TABLE deal_catalog ADD COLUMN vintage_year INTEGER DEFAULT 0",
    "ALTER TABLE deal_catalog ADD COLUMN primary_issuer TEXT DEFAULT ''",
    "ALTER TABLE deal_catalog ADD COLUMN series_name TEXT DEFAULT ''",
    "ALTER TABLE deal_catalog ADD COLUMN deal_type TEXT DEFAULT ''",
    "ALTER TABLE deal_catalog ADD COLUMN total_chunks INTEGER DEFAULT 0",
    "ALTER TABLE deal_catalog ADD COLUMN total_sections INTEGER DEFAULT 0",
    "ALTER TABLE deal_catalog ADD COLUMN total_definitions INTEGER DEFAULT 0",
    "ALTER TABLE deal_catalog ADD COLUMN total_rules INTEGER DEFAULT 0",
    "ALTER TABLE deal_catalog ADD COLUMN graph_node_count INTEGER DEFAULT 0",
    "ALTER TABLE deal_catalog ADD COLUMN graph_edge_count INTEGER DEFAULT 0",

    # New deal_documents table
    """CREATE TABLE IF NOT EXISTS deal_documents (
        doc_id TEXT PRIMARY KEY,
        folder_name TEXT NOT NULL,
        doc_name_prefix TEXT NOT NULL,
        doc_type TEXT NOT NULL DEFAULT '',
        original_filename TEXT DEFAULT '',
        page_count INTEGER DEFAULT 0,
        chunk_count INTEGER DEFAULT 0,
        section_count INTEGER DEFAULT 0,
        definition_count INTEGER DEFAULT 0,
        rule_count INTEGER DEFAULT 0,
        file_size_bytes INTEGER DEFAULT 0,
        ingested_at TEXT,
        metadata_json TEXT DEFAULT '{}'
    )""",

    # Indexes
    "CREATE INDEX IF NOT EXISTS idx_deal_docs_folder ON deal_documents(folder_name)",
    "CREATE INDEX IF NOT EXISTS idx_deal_docs_type ON deal_documents(doc_type)",
    "CREATE INDEX IF NOT EXISTS idx_deal_docs_prefix ON deal_documents(doc_name_prefix)",

    # B-tree indexes on deal_catalog
    "CREATE INDEX IF NOT EXISTS idx_catalog_vintage ON deal_catalog(vintage_year)",
    "CREATE INDEX IF NOT EXISTS idx_catalog_issuer ON deal_catalog(primary_issuer)",
    "CREATE INDEX IF NOT EXISTS idx_catalog_deal_type ON deal_catalog(deal_type)",
]
```

### 10.2 Migration Execution

```python
def _run_migrations(self, conn: sqlite3.Connection) -> None:
    """Run database migrations. Safe to call multiple times.

    Each ALTER TABLE is wrapped in try/except because SQLite raises
    an error if the column already exists.
    """
    for sql in self._MIGRATION_V17_SQL:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError as exc:
            if "duplicate column" not in str(exc).lower():
                logger.debug("[DealCatalog] Migration step skipped: %s", exc)
    conn.commit()
```

### 10.3 Schema Version Tracking

```sql
CREATE TABLE IF NOT EXISTS catalog_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Set on successful migration
INSERT OR REPLACE INTO catalog_meta(key, value) VALUES ('schema_version', '17.0');
```

---

## 11. API Reference

### 11.1 `DealCatalog` — Complete Method Reference

| Method | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `__init__` | `db_path: str` | — | Initialize catalog, run migrations |
| `upsert` | `entry: CatalogEntry` | `None` | Insert/update deal entry |
| `upsert_document` | `entry: DocumentEntry` | `None` | Insert/update document entry |
| `delete` | `folder_name: str` | `None` | Remove deal and all its documents |
| `get` | `folder_name: str` | `CatalogEntry?` | Get deal by folder name |
| `get_document` | `folder_name, doc_prefix` | `DocumentEntry?` | Get specific document |
| `get_documents` | `folder_name: str` | `List[DocumentEntry]` | Get all docs in deal |
| `get_doc_types` | `folder_name: str` | `List[str]` | Doc types for a deal |
| `list_documents` | `folder_name: str` | `List[Dict]` | Docs with summary stats |
| `search` | `query: str` | `List[Dict]` | FTS5 keyword search |
| `glob_search` | `pattern: str` | `List[CatalogEntry]` | Glob pattern search |
| `structured_search` | `**kwargs` | `List[CatalogEntry]` | Multi-field AND search |
| `search_by_vintage` | `year: int` | `List[CatalogEntry]` | Filter by vintage year |
| `search_by_issuer` | `issuer: str` | `List[CatalogEntry]` | Filter by issuer |
| `search_by_deal_type` | `deal_type: str` | `List[CatalogEntry]` | Filter by RMBS/CMBS/etc. |
| `search_by_doc_type` | `doc_type: str` | `List[Dict]` | Cross-deal doc-type search |
| `all_scopes` | — | `List[Dict]` | All deal scopes |
| `count` | — | `int` | Total deal count |
| `catalog_stats` | — | `Dict` | Aggregate statistics |
| `reindex_deal` | `folder_name, docs` | `None` | Re-index a deal |
| `prune_stale` | `root: str` | `int` | Remove orphaned entries |

### 11.2 Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                     INGESTION (Write)                         │
│                                                               │
│  Source File → IngestionAgent                                 │
│       │                                                       │
│       ├─→ Extract doc_name_prefix, doc_type                   │
│       ├─→ Count chunks, sections, definitions, rules          │
│       ├─→ catalog.upsert_document(DocumentEntry)              │
│       │                                                       │
│  [After all files in deal]                                    │
│       └─→ catalog.upsert(CatalogEntry)  ← aggregated stats   │
│                                                               │
├──────────────────────────────────────────────────────────────┤
│                     RETRIEVAL (Read)                           │
│                                                               │
│  User Query → ScopeResolver → DealCatalog                     │
│       │                                                       │
│       ├─→ catalog.get_doc_types(scope) → autocomplete         │
│       ├─→ catalog.search("bear stearns") → scope routing      │
│       ├─→ catalog.glob_search("bear*") → wildcard routing     │
│       ├─→ catalog.search_by_doc_type("PSA") → cross-deal      │
│       └─→ catalog.structured_search(year=2006) → structured   │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 12. Performance Considerations

### 12.1 Expected Scale

| Metric | Typical | Large Deployment |
|--------|---------|-----------------|
| Deals | 10–50 | 500–5,000 |
| Documents per deal | 3–8 | 3–15 |
| Total documents | 30–400 | 1,500–75,000 |
| Catalog DB size | < 1 MB | < 50 MB |

### 12.2 Query Performance

| Operation | Expected Latency | Mechanism |
|-----------|-----------------|-----------|
| FTS5 keyword search | < 1 ms | FTS5 inverted index |
| Glob search | < 5 ms | SQLite GLOB + B-tree scan |
| Structured search | < 1 ms | B-tree index lookups |
| Get doc types | < 1 ms | Index on (folder_name, doc_type) |
| Catalog stats | < 10 ms | Aggregate queries |

### 12.3 Thread Safety

All write operations are protected by `threading.Lock()`. Read operations
use separate connections and are safe for concurrent access. The SQLite
WAL (Write-Ahead Logging) mode is recommended for concurrent read/write:

```python
def _init_db(self) -> None:
    with self._lock:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")  # Phase 17
            conn.execute(self._CREATE_SQL)
            self._run_migrations(conn)
            ...
```

---

*End of Document — 05_DEAL_CATALOG.md*
