"""
Phase 12.4 — Deal Catalog.

Lightweight SQLite-backed catalog with one row per deal folder.
Supports keyword search for cross-scope routing and deal discovery.

Populated at ingest time.  Queried at retrieval time.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Slugification ─────────────────────────────────────────────

def slugify(name: str) -> str:
    """Convert folder name to slug (slash command name).

    Rules: lowercase, spaces → underscore, hyphens → underscore,
    remove most special chars but keep alphanumeric and underscores.
    """
    s = name.strip().lower()
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


# ── Catalog Entry ─────────────────────────────────────────────

@dataclass
class CatalogEntry:
    """One row in the deal catalog."""

    folder_name: str
    slug: str
    kts_path: str
    doc_count: int = 0
    doc_types: List[str] = field(default_factory=list)
    issuers: List[str] = field(default_factory=list)
    years: List[str] = field(default_factory=list)
    collateral_types: List[str] = field(default_factory=list)
    key_parties: List[str] = field(default_factory=list)
    last_indexed: Optional[str] = None  # ISO timestamp

    def to_dict(self) -> Dict[str, Any]:
        return {
            "folder_name": self.folder_name,
            "slug": self.slug,
            "kts_path": self.kts_path,
            "doc_count": self.doc_count,
            "doc_types": self.doc_types,
            "issuers": self.issuers,
            "years": self.years,
            "collateral_types": self.collateral_types,
            "key_parties": self.key_parties,
            "last_indexed": self.last_indexed,
        }


# ── Deal Catalog ──────────────────────────────────────────────

class DealCatalog:
    """
    SQLite-backed deal catalog for Phase 12.4 cross-scope routing.

    Usage::

        catalog = DealCatalog(db_path="~/.kts/deal_catalog.db")
        catalog.upsert(CatalogEntry(
            folder_name="Bear Stearns 2006-HE1",
            slug="bear_stearns_2006_he1",
            kts_path="/deals/bear_stearns_2006_HE1/.kts",
            doc_count=4,
            doc_types=["PSA", "PROSUPP"],
            issuers=["Bear Stearns"],
        ))
        matches = catalog.search("bear stearns")
    """

    _CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS deal_catalog (
        folder_name TEXT PRIMARY KEY,
        slug TEXT NOT NULL,
        kts_path TEXT NOT NULL,
        doc_count INTEGER DEFAULT 0,
        doc_types TEXT DEFAULT '[]',
        issuers TEXT DEFAULT '[]',
        years TEXT DEFAULT '[]',
        collateral_types TEXT DEFAULT '[]',
        key_parties TEXT DEFAULT '[]',
        last_indexed TEXT
    )
    """

    # Phase 12.4 spec: SQLite FTS5 for millisecond keyword search at 10k+ rows
    _CREATE_FTS_SQL = """
    CREATE VIRTUAL TABLE IF NOT EXISTS deal_catalog_fts USING fts5(
        folder_name, slug, issuers, key_parties, years, collateral_types,
        content='deal_catalog',
        content_rowid='rowid'
    )
    """

    # Keep FTS in sync via triggers
    _FTS_TRIGGERS_SQL = [
        """CREATE TRIGGER IF NOT EXISTS deal_catalog_ai AFTER INSERT ON deal_catalog BEGIN
            INSERT INTO deal_catalog_fts(rowid, folder_name, slug, issuers, key_parties, years, collateral_types)
            VALUES (new.rowid, new.folder_name, new.slug, new.issuers, new.key_parties, new.years, new.collateral_types);
        END""",
        """CREATE TRIGGER IF NOT EXISTS deal_catalog_ad AFTER DELETE ON deal_catalog BEGIN
            INSERT INTO deal_catalog_fts(deal_catalog_fts, rowid, folder_name, slug, issuers, key_parties, years, collateral_types)
            VALUES ('delete', old.rowid, old.folder_name, old.slug, old.issuers, old.key_parties, old.years, old.collateral_types);
        END""",
        """CREATE TRIGGER IF NOT EXISTS deal_catalog_au AFTER UPDATE ON deal_catalog BEGIN
            INSERT INTO deal_catalog_fts(deal_catalog_fts, rowid, folder_name, slug, issuers, key_parties, years, collateral_types)
            VALUES ('delete', old.rowid, old.folder_name, old.slug, old.issuers, old.key_parties, old.years, old.collateral_types);
            INSERT INTO deal_catalog_fts(rowid, folder_name, slug, issuers, key_parties, years, collateral_types)
            VALUES (new.rowid, new.folder_name, new.slug, new.issuers, new.key_parties, new.years, new.collateral_types);
        END""",
    ]

    _UPSERT_SQL = """
    INSERT INTO deal_catalog
        (folder_name, slug, kts_path, doc_count, doc_types, issuers, years,
         collateral_types, key_parties, last_indexed)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(folder_name) DO UPDATE SET
        slug=excluded.slug,
        kts_path=excluded.kts_path,
        doc_count=excluded.doc_count,
        doc_types=excluded.doc_types,
        issuers=excluded.issuers,
        years=excluded.years,
        collateral_types=excluded.collateral_types,
        key_parties=excluded.key_parties,
        last_indexed=excluded.last_indexed
    """

    # ── Phase 12.4: FTS5-first search with LIKE fallback ──────

    _FTS_SEARCH_SQL = """
    SELECT dc.* FROM deal_catalog dc
    JOIN deal_catalog_fts fts ON dc.rowid = fts.rowid
    WHERE deal_catalog_fts MATCH ?
    """

    _SEARCH_SQL = """
    SELECT * FROM deal_catalog
    WHERE folder_name LIKE ? COLLATE NOCASE
       OR slug LIKE ? COLLATE NOCASE
       OR issuers LIKE ? COLLATE NOCASE
       OR key_parties LIKE ? COLLATE NOCASE
       OR years LIKE ? COLLATE NOCASE
       OR collateral_types LIKE ? COLLATE NOCASE
    """

    def __init__(self, db_path: str = "") -> None:
        if not db_path:
            kts_dir = os.path.join(os.path.expanduser("~"), ".kts")
            os.makedirs(kts_dir, exist_ok=True)
            db_path = os.path.join(kts_dir, "deal_catalog.db")
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute(self._CREATE_SQL)
                # Phase 17: Add new columns if they don't exist (migration)
                self._migrate_phase17(conn)
                # Phase 12.4: Create FTS5 virtual table + sync triggers
                try:
                    conn.execute(self._CREATE_FTS_SQL)
                    for trigger_sql in self._FTS_TRIGGERS_SQL:
                        conn.execute(trigger_sql)
                except Exception as exc:
                    # FTS5 may not be available on all SQLite builds; fall back gracefully
                    logger.debug("[DealCatalog] FTS5 setup skipped: %s", exc)
                conn.commit()
            finally:
                conn.close()

    @staticmethod
    def _migrate_phase17(conn: sqlite3.Connection) -> None:
        """Add Phase 17 columns to deal_catalog if they don't exist."""
        new_columns = [
            ("deal_name", "TEXT DEFAULT ''"),
            ("vintage", "INTEGER DEFAULT 0"),
            ("series", "TEXT DEFAULT ''"),
            ("chunk_count", "INTEGER DEFAULT 0"),
            ("status", "TEXT DEFAULT 'active'"),
        ]
        # Get existing columns
        cursor = conn.execute("PRAGMA table_info(deal_catalog)")
        existing = {row[1] for row in cursor.fetchall()}
        for col_name, col_def in new_columns:
            if col_name not in existing:
                try:
                    conn.execute(f"ALTER TABLE deal_catalog ADD COLUMN {col_name} {col_def}")
                    logger.info("[DealCatalog] Added Phase 17 column: %s", col_name)
                except Exception as exc:
                    logger.debug("[DealCatalog] Column %s migration skipped: %s", col_name, exc)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ── CRUD ────────────────────────────────────────────────

    def upsert(self, entry: CatalogEntry) -> None:
        """Insert or update a deal catalog entry."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(self._UPSERT_SQL, (
                    entry.folder_name,
                    entry.slug,
                    entry.kts_path,
                    entry.doc_count,
                    json.dumps(entry.doc_types),
                    json.dumps(entry.issuers),
                    json.dumps(entry.years),
                    json.dumps(entry.collateral_types),
                    json.dumps(entry.key_parties),
                    entry.last_indexed or datetime.now(timezone.utc).isoformat(),
                ))
                conn.commit()
            finally:
                conn.close()

    def delete(self, folder_name: str) -> None:
        """Remove a deal from the catalog."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM deal_catalog WHERE folder_name = ?",
                    (folder_name,),
                )
                conn.commit()
            finally:
                conn.close()

    def get(self, folder_name: str) -> Optional[CatalogEntry]:
        """Get a single entry by folder name."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM deal_catalog WHERE folder_name = ?",
                (folder_name,),
            ).fetchone()
            return self._row_to_entry(row) if row else None
        finally:
            conn.close()

    # ── Search ──────────────────────────────────────────────

    def search(self, query: str) -> List[Dict[str, Any]]:
        """
        Keyword search across catalog fields.

        Prefers FTS5 for O(1) full-text search.  Falls back to LIKE if FTS5
        is unavailable.

        Returns list of dicts with slug, folder_name, kts_path, score.
        """
        conn = self._connect()
        try:
            # Phase 12.4: Try FTS5 first (millisecond latency at 10k+ rows)
            try:
                # FTS5 query tokens: split on whitespace, prefix-match each
                tokens = query.strip().split()
                if tokens:
                    fts_query = " OR ".join(f'"{t}"*' for t in tokens)
                    rows = conn.execute(self._FTS_SEARCH_SQL, (fts_query,)).fetchall()
                    if rows:
                        return [
                            {
                                "slug": row["slug"],
                                "folder_name": row["folder_name"],
                                "kts_path": row["kts_path"],
                                "score": 0.9,
                            }
                            for row in rows
                        ]
            except Exception:
                pass  # FTS5 not available — fall through to LIKE

            # Fallback: LIKE pattern matching
            pattern = f"%{query}%"
            rows = conn.execute(
                self._SEARCH_SQL,
                (pattern, pattern, pattern, pattern, pattern, pattern),
            ).fetchall()
            return [
                {
                    "slug": row["slug"],
                    "folder_name": row["folder_name"],
                    "kts_path": row["kts_path"],
                    "score": 0.8,
                }
                for row in rows
            ]
        finally:
            conn.close()

    def all_scopes(self) -> List[Dict[str, Any]]:
        """Return all scopes as dicts."""
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM deal_catalog").fetchall()
            return [
                {
                    "slug": row["slug"],
                    "folder_name": row["folder_name"],
                    "kts_path": row["kts_path"],
                }
                for row in rows
            ]
        finally:
            conn.close()

    def count(self) -> int:
        """Return total number of entries."""
        conn = self._connect()
        try:
            return conn.execute("SELECT COUNT(*) FROM deal_catalog").fetchone()[0]
        finally:
            conn.close()

    # ── Phase 17: Enhanced query methods ───────────────────

    def upsert_deal(
        self,
        scope_slug: str,
        folder_path: str,
        *,
        deal_name: str = "",
        vintage: int = 0,
        series: str = "",
        issuer: str = "",
        doc_types: list[str] | None = None,
        chunk_count: int = 0,
        status: str = "active",
    ) -> None:
        """Insert or update a deal entry with full Phase 17 metadata.

        This supplements the existing ``upsert(CatalogEntry)`` method with
        structured metadata fields that enable pattern/wildcard search.
        """
        folder_name = Path(folder_path).name if folder_path else scope_slug
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT INTO deal_catalog
                        (folder_name, slug, kts_path, doc_count, doc_types,
                         deal_name, vintage, series, chunk_count, status,
                         issuers, years, collateral_types, key_parties, last_indexed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(folder_name) DO UPDATE SET
                        slug=excluded.slug,
                        kts_path=excluded.kts_path,
                        doc_count=excluded.doc_count,
                        doc_types=excluded.doc_types,
                        deal_name=excluded.deal_name,
                        vintage=excluded.vintage,
                        series=excluded.series,
                        chunk_count=excluded.chunk_count,
                        status=excluded.status,
                        issuers=excluded.issuers,
                        last_indexed=excluded.last_indexed
                    """,
                    (
                        folder_name,
                        scope_slug,
                        str(Path(folder_path) / ".kts") if folder_path else "",
                        len(doc_types) if doc_types else 0,
                        json.dumps(doc_types or []),
                        deal_name,
                        vintage,
                        series,
                        chunk_count,
                        status,
                        json.dumps([issuer] if issuer else []),
                        json.dumps([str(vintage)] if vintage else []),
                        json.dumps([]),
                        json.dumps([]),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def search_deals(
        self,
        *,
        deal_name: str = "",
        vintage: int = 0,
        pattern: str = "",
    ) -> list[dict]:
        """Search deals by structured metadata or wildcard pattern.

        Args:
            deal_name: Exact or prefix match on deal_name.
            vintage: Exact match on vintage year.
            pattern: Wildcard pattern (e.g., ``bear_stearns_2006*``).
                     ``*`` is converted to SQL ``%``.

        Returns:
            List of matching deal entries as dicts.
        """
        conn = self._connect()
        try:
            conditions: list[str] = []
            params: list[Any] = []

            if deal_name:
                conditions.append("deal_name LIKE ? COLLATE NOCASE")
                params.append(f"{deal_name}%")
            if vintage:
                conditions.append("vintage = ?")
                params.append(vintage)
            if pattern:
                sql_pattern = pattern.replace("*", "%")
                conditions.append(
                    "(slug LIKE ? COLLATE NOCASE OR folder_name LIKE ? COLLATE NOCASE)"
                )
                params.extend([sql_pattern, sql_pattern])

            where = " AND ".join(conditions) if conditions else "1=1"
            sql = f"SELECT * FROM deal_catalog WHERE {where}"
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_full_dict(row) for row in rows]
        finally:
            conn.close()

    def get_doc_types(self, scope_slug: str) -> list[str]:
        """Return list of document types ingested for a given deal scope."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT doc_types FROM deal_catalog WHERE slug = ?",
                (scope_slug,),
            ).fetchone()
            if row:
                return json.loads(row["doc_types"] or "[]")
            return []
        finally:
            conn.close()

    def list_all_deals(self) -> list[dict]:
        """Return all catalog entries with full Phase 17 metadata."""
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM deal_catalog ORDER BY slug").fetchall()
            return [self._row_to_full_dict(row) for row in rows]
        finally:
            conn.close()

    def get_by_slug(self, slug: str) -> Optional[CatalogEntry]:
        """Get a single entry by slug."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM deal_catalog WHERE slug = ?",
                (slug,),
            ).fetchone()
            return self._row_to_entry(row) if row else None
        finally:
            conn.close()

    # ── Helpers ─────────────────────────────────────────────

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> CatalogEntry:
        return CatalogEntry(
            folder_name=row["folder_name"],
            slug=row["slug"],
            kts_path=row["kts_path"],
            doc_count=row["doc_count"],
            doc_types=json.loads(row["doc_types"] or "[]"),
            issuers=json.loads(row["issuers"] or "[]"),
            years=json.loads(row["years"] or "[]"),
            collateral_types=json.loads(row["collateral_types"] or "[]"),
            key_parties=json.loads(row["key_parties"] or "[]"),
            last_indexed=row["last_indexed"],
        )

    @staticmethod
    def _row_to_full_dict(row: sqlite3.Row) -> dict:
        """Convert a row with Phase 17 columns to a full dict."""
        d = {
            "folder_name": row["folder_name"],
            "slug": row["slug"],
            "kts_path": row["kts_path"],
            "doc_count": row["doc_count"],
            "doc_types": json.loads(row["doc_types"] or "[]"),
            "issuers": json.loads(row["issuers"] or "[]"),
            "years": json.loads(row["years"] or "[]"),
            "collateral_types": json.loads(row["collateral_types"] or "[]"),
            "key_parties": json.loads(row["key_parties"] or "[]"),
            "last_indexed": row["last_indexed"],
        }
        # Phase 17 columns (may not exist on old DBs — safe access)
        for col in ("deal_name", "vintage", "series", "chunk_count", "status"):
            try:
                d[col] = row[col]
            except (IndexError, KeyError):
                d[col] = "" if col in ("deal_name", "series", "status") else 0
        return d


# ── Phase 17: Deal metadata extraction from folder name ──────

def _parse_deal_folder_name(folder_name: str) -> dict:
    """Heuristic extraction of deal metadata from folder name.

    Examples::

        _parse_deal_folder_name("Bear_Stearns_2006_HE1")
        → {"deal_name": "Bear Stearns", "vintage": 2006, "series": "HE1"}

        _parse_deal_folder_name("Fin_deal1")
        → {"deal_name": "Fin deal1", "vintage": 0, "series": ""}
    """
    tokens = re.split(r"[_\-\s]+", folder_name.strip())

    # Find year token (4-digit 19xx/20xx)
    vintage = 0
    year_idx = -1
    for i, t in enumerate(tokens):
        m = re.fullmatch(r"(19|20)\d{2}", t)
        if m:
            vintage = int(t)
            year_idx = i
            break

    # Everything before the year is the deal name
    if year_idx > 0:
        deal_name = " ".join(tokens[:year_idx])
    else:
        deal_name = " ".join(tokens)

    # Everything after the year is the series identifier
    series = ""
    if year_idx >= 0 and year_idx < len(tokens) - 1:
        series = "_".join(tokens[year_idx + 1:])

    return {
        "deal_name": deal_name,
        "vintage": vintage,
        "series": series,
    }


# ── Discovery Helper ─────────────────────────────────────────

def discover_scopes(knowledge_source_root: str) -> List[CatalogEntry]:
    """
    Scan a knowledge source directory for folders with ``.kts/`` sub-dirs.

    Returns a CatalogEntry per discovered folder (metadata populated from folder name).
    """
    root = Path(knowledge_source_root)
    if not root.is_dir():
        logger.warning("[DealCatalog] Knowledge source root not found: %s", root)
        return []

    entries: List[CatalogEntry] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        kts_path = child / ".kts"
        has_index = kts_path.is_dir()
        doc_count = sum(1 for f in child.iterdir() if f.is_file()) if has_index else 0

        slug = slugify(child.name)
        # Extract year-like tokens from folder name
        year_matches = re.findall(r"\b(?:19|20)\d{2}\b", child.name)

        entries.append(CatalogEntry(
            folder_name=child.name,
            slug=slug,
            kts_path=str(kts_path),
            doc_count=doc_count,
            years=year_matches,
            last_indexed=datetime.now(timezone.utc).isoformat() if has_index else None,
        ))

    return entries
