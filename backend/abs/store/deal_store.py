"""
ABS Deal Store — stateless SQLite data-access layer.

``DealStore`` is the single gateway to a deal's structured spine
(``deal_store.db``). It is deliberately **stateless**: an instance holds only
the immutable database path, and every operation opens its own short-lived
connection (WAL mode, foreign keys enforced). This makes the store safe to use
concurrently and from multiple worker processes — a prerequisite for
horizontal scaling.

Synchronous methods are the primitives; :mod:`backend.abs.store` also exposes
``async`` wrappers (see :meth:`DealStore.run_async`) that off-load to a thread
so the event loop is never blocked by disk I/O.

Example
-------
>>> store = DealStore.open(Path("deals/cbass_2002_cb4/data/deal_store.db"))
>>> store.add_document({"doc_id": "d1", "deal_id": "cbass", "doc_type": "PSA"})
>>> store.get_document("d1")["doc_type"]
'PSA'
"""

from __future__ import annotations

import asyncio
import datetime
import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from backend.abs.store import schema as _schema


def _now() -> str:
    """Return an ISO-8601 UTC timestamp (Python 3.9-safe)."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def new_id(prefix: str = "") -> str:
    """Generate a short unique id, optionally namespaced by ``prefix``."""
    token = uuid.uuid4().hex[:12]
    return f"{prefix}{token}" if prefix else token


class DealStore:
    """Stateless gateway to a single deal's ``deal_store.db``."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    @classmethod
    def open(cls, db_path: Path, *, init: bool = True) -> "DealStore":
        """Open (and by default initialise) a deal store at ``db_path``."""
        store = cls(db_path)
        if init:
            store.init_schema()
        return store

    @classmethod
    def for_deal_dir(cls, deal_dir: Path, *, init: bool = True) -> "DealStore":
        """Open the store living at ``<deal_dir>/data/deal_store.db``."""
        db_path = Path(deal_dir) / "data" / "deal_store.db"
        return cls.open(db_path, init=init)

    # ------------------------------------------------------------------
    # Connection management (stateless: one connection per operation)
    # ------------------------------------------------------------------
    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            isolation_level=None,  # autocommit; we manage transactions explicitly
        )
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("BEGIN")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------
    def init_schema(self) -> None:
        """Create all tables/indexes if absent and record the schema version."""
        with self._connect() as conn:
            for stmt in _schema.SCHEMA_STATEMENTS:
                conn.execute(stmt)
            conn.execute(
                "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(_schema.SCHEMA_VERSION),),
            )

    def schema_version(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()
            return int(row["value"]) if row else 0

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict[str, Any]]:
        return dict(row) if row is not None else None

    @staticmethod
    def _rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
        return [dict(r) for r in rows]

    def _insert(self, conn: sqlite3.Connection, table: str, data: dict[str, Any]) -> None:
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        conn.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
            tuple(data.values()),
        )

    # ------------------------------------------------------------------
    # Audit (append-only attributability)
    # ------------------------------------------------------------------
    def audit(
        self,
        action: str,
        *,
        actor: str = "system",
        object_type: str = "",
        object_id: str = "",
        before: Any = None,
        after: Any = None,
        evidence: str = "",
    ) -> None:
        """Append an immutable audit entry."""
        with self._connect() as conn:
            self._insert(
                conn,
                "audit_log",
                {
                    "ts": _now(),
                    "actor": actor,
                    "action": action,
                    "object_type": object_type,
                    "object_id": object_id,
                    "before_json": json.dumps(before) if before is not None else None,
                    "after_json": json.dumps(after) if after is not None else None,
                    "evidence": evidence,
                },
            )

    def list_audit(self, *, object_type: str = "", object_id: str = "", limit: int = 500) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if object_type and object_id:
                rows = conn.execute(
                    "SELECT * FROM audit_log WHERE object_type=? AND object_id=? "
                    "ORDER BY id DESC LIMIT ?",
                    (object_type, object_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            return self._rows_to_dicts(rows)

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------
    def add_document(self, doc: dict[str, Any]) -> str:
        doc = dict(doc)
        doc.setdefault("doc_id", new_id("doc_"))
        doc.setdefault("status", "draft")
        now = _now()
        doc.setdefault("created_at", now)
        doc.setdefault("updated_at", now)
        with self._connect() as conn:
            self._insert(conn, "documents", doc)
        return doc["doc_id"]

    def get_document(self, doc_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            return self._row_to_dict(
                conn.execute("SELECT * FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
            )

    def list_documents(self, deal_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return self._rows_to_dicts(
                conn.execute(
                    "SELECT * FROM documents WHERE deal_id=? ORDER BY created_at", (deal_id,)
                ).fetchall()
            )

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------
    def add_sections(self, sections: list[dict[str, Any]]) -> int:
        if not sections:
            return 0
        with self._connect() as conn:
            for s in sections:
                s = dict(s)
                s.setdefault("section_id", new_id("sec_"))
                self._insert(conn, "sections", s)
        return len(sections)

    def list_sections(self, doc_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return self._rows_to_dicts(
                conn.execute(
                    "SELECT * FROM sections WHERE doc_id=? ORDER BY ordinal", (doc_id,)
                ).fetchall()
            )

    def get_section(self, section_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            return self._row_to_dict(
                conn.execute("SELECT * FROM sections WHERE section_id=?", (section_id,)).fetchone()
            )

    # ------------------------------------------------------------------
    # Chunks
    # ------------------------------------------------------------------
    def add_chunks(self, chunks: list[dict[str, Any]]) -> int:
        if not chunks:
            return 0
        with self._connect() as conn:
            for c in chunks:
                c = dict(c)
                c.setdefault("chunk_id", new_id("chk_"))
                self._insert(conn, "chunks", c)
        return len(chunks)

    def get_chunk(self, chunk_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            return self._row_to_dict(
                conn.execute("SELECT * FROM chunks WHERE chunk_id=?", (chunk_id,)).fetchone()
            )

    def list_chunks(self, doc_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return self._rows_to_dicts(
                conn.execute(
                    "SELECT * FROM chunks WHERE doc_id=? ORDER BY ordinal", (doc_id,)
                ).fetchall()
            )

    def list_chunks_for_deal(self, deal_id: str) -> list[dict[str, Any]]:
        """All chunks for a deal enriched with section_path (for citations)."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT c.*, s.section_path AS section_path
                FROM chunks c
                JOIN documents d ON d.doc_id = c.doc_id
                LEFT JOIN sections s ON s.section_id = c.section_id
                WHERE d.deal_id = ?
                ORDER BY c.doc_id, c.ordinal
                """,
                (deal_id,),
            ).fetchall()
            return self._rows_to_dicts(rows)

    def set_chunk_enhancement(self, chunk_id: str, enhancement_md: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE chunks SET enhancement_md=? WHERE chunk_id=?",
                (enhancement_md, chunk_id),
            )

    # ------------------------------------------------------------------
    # Chunk vectors (dense embeddings)
    # ------------------------------------------------------------------
    def set_chunk_vectors(
        self, deal_id: str, provider: str, vectors: list[tuple[str, list[float]]]
    ) -> int:
        """Upsert ``(chunk_id, vector)`` pairs for a deal."""
        if not vectors:
            return 0
        with self._connect() as conn:
            for chunk_id, vec in vectors:
                conn.execute(
                    "INSERT INTO chunk_vectors(chunk_id, deal_id, provider, dim, vector) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(chunk_id) DO UPDATE SET "
                    "provider=excluded.provider, dim=excluded.dim, vector=excluded.vector",
                    (chunk_id, deal_id, provider, len(vec), json.dumps(vec)),
                )
        return len(vectors)

    def get_chunk_vectors(self, deal_id: str) -> list[dict[str, Any]]:
        """Return chunk rows joined with their dense vectors + section_path."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT c.chunk_id, c.doc_id, c.section_id, c.text, c.enhancement_md,
                       c.page_start, c.page_end, s.section_path AS section_path,
                       v.vector AS vector
                FROM chunk_vectors v
                JOIN chunks c ON c.chunk_id = v.chunk_id
                LEFT JOIN sections s ON s.section_id = c.section_id
                WHERE v.deal_id = ?
                """,
                (deal_id,),
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                try:
                    d["vector"] = json.loads(d["vector"])
                except (json.JSONDecodeError, TypeError):
                    d["vector"] = []
                out.append(d)
            return out

    def count_chunk_vectors(self, deal_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM chunk_vectors WHERE deal_id=?", (deal_id,)
            ).fetchone()
            return int(row["n"]) if row else 0

    def get_source_context(
        self, *, chunk_id: Optional[str] = None, section_id: Optional[str] = None
    ) -> Optional[dict[str, Any]]:
        """Resolve a chunk or section to its full source context (for traceback).

        Returns the text, section path, page range, and the source document's
        title + file path so the UI can show the excerpt and open the PDF.
        """
        with self._connect() as conn:
            if chunk_id:
                row = conn.execute(
                    """
                    SELECT c.chunk_id, c.text, c.page_start, c.page_end, c.section_id,
                           s.section_path, s.title AS section_title,
                           d.doc_id, d.title AS doc_title, d.source_path
                    FROM chunks c
                    JOIN documents d ON d.doc_id = c.doc_id
                    LEFT JOIN sections s ON s.section_id = c.section_id
                    WHERE c.chunk_id = ?
                    """,
                    (chunk_id,),
                ).fetchone()
            elif section_id:
                row = conn.execute(
                    """
                    SELECT s.section_id, s.section_path, s.title AS section_title,
                           s.page_start, s.page_end,
                           d.doc_id, d.title AS doc_title, d.source_path
                    FROM sections s
                    JOIN documents d ON d.doc_id = s.doc_id
                    WHERE s.section_id = ?
                    """,
                    (section_id,),
                ).fetchone()
                # Include concatenated chunk text for the section.
                if row is not None:
                    chunks = conn.execute(
                        "SELECT text FROM chunks WHERE section_id=? ORDER BY ordinal",
                        (section_id,),
                    ).fetchall()
                    data = dict(row)
                    data["text"] = "\n\n".join(c["text"] for c in chunks)
                    return data
            else:
                return None
            return self._row_to_dict(row)

    # ------------------------------------------------------------------
    # Definitions + edges
    # ------------------------------------------------------------------
    def add_definition(self, term: dict[str, Any]) -> str:
        term = dict(term)
        term.setdefault("term_id", new_id("term_"))
        term.setdefault("status", "draft")
        term.setdefault("version", 1)
        term.setdefault("created_at", _now())
        with self._connect() as conn:
            self._insert(conn, "definitions", term)
        return term["term_id"]

    def add_definition_edge(self, from_term_id: str, to_term_id: str, edge_type: str = "DEPENDS_ON") -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO definition_edges(from_term_id, to_term_id, edge_type) "
                "VALUES (?, ?, ?)",
                (from_term_id, to_term_id, edge_type),
            )

    def get_definition(self, term_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            return self._row_to_dict(
                conn.execute("SELECT * FROM definitions WHERE term_id=?", (term_id,)).fetchone()
            )

    def find_definition_by_name(self, deal_id: str, term_name: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            return self._row_to_dict(
                conn.execute(
                    "SELECT * FROM definitions WHERE deal_id=? AND term_name=? "
                    "ORDER BY version DESC LIMIT 1",
                    (deal_id, term_name),
                ).fetchone()
            )

    def list_definitions(self, deal_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return self._rows_to_dicts(
                conn.execute(
                    "SELECT * FROM definitions WHERE deal_id=? ORDER BY term_name", (deal_id,)
                ).fetchall()
            )

    def list_top_level_definitions(self, deal_id: str) -> list[dict[str, Any]]:
        """Terms that nothing else depends on (roots of the dependency DAG)."""
        with self._connect() as conn:
            return self._rows_to_dicts(
                conn.execute(
                    """
                    SELECT d.* FROM definitions d
                    WHERE d.deal_id = ?
                      AND d.term_id NOT IN (SELECT to_term_id FROM definition_edges)
                    ORDER BY d.term_name
                    """,
                    (deal_id,),
                ).fetchall()
            )

    def get_dependencies(self, term_id: str) -> list[dict[str, Any]]:
        """Return the direct child definitions ``term_id`` DEPENDS_ON."""
        with self._connect() as conn:
            return self._rows_to_dicts(
                conn.execute(
                    """
                    SELECT d.* FROM definition_edges e
                    JOIN definitions d ON d.term_id = e.to_term_id
                    WHERE e.from_term_id = ? AND e.edge_type = 'DEPENDS_ON'
                    ORDER BY d.term_name
                    """,
                    (term_id,),
                ).fetchall()
            )

    def resolution_tree(self, term_id: str, *, max_depth: int = 12) -> dict[str, Any]:
        """Build the nested N-level dependency tree for a term (cycle-safe)."""

        def _walk(tid: str, visited: frozenset[str], depth: int) -> dict[str, Any]:
            node = self.get_definition(tid)
            if node is None:
                return {"term_id": tid, "missing": True, "children": []}
            entry: dict[str, Any] = {
                "term_id": tid,
                "term_name": node["term_name"],
                "raw_definition": node["raw_definition"],
                "resolved_definition": node["resolved_definition"],
                "page": node["page"],
                "citation": node["citation"],
                "status": node["status"],
                "children": [],
            }
            if tid in visited or depth >= max_depth:
                entry["cyclic_or_truncated"] = True
                return entry
            for child in self.get_dependencies(tid):
                entry["children"].append(
                    _walk(child["term_id"], visited | {tid}, depth + 1)
                )
            return entry

        return _walk(term_id, frozenset(), 0)

    def update_resolved_definition(self, term_id: str, resolved_text: str, *, depth: Optional[int] = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE definitions SET resolved_definition=?, depth=COALESCE(?, depth) "
                "WHERE term_id=?",
                (resolved_text, depth, term_id),
            )

    # ------------------------------------------------------------------
    # Governing doc
    # ------------------------------------------------------------------
    def add_governing_clause(self, clause: dict[str, Any]) -> str:
        clause = dict(clause)
        clause.setdefault("gd_id", new_id("gd_"))
        clause.setdefault("status", "draft")
        clause.setdefault("version", 1)
        clause.setdefault("created_at", _now())
        if isinstance(clause.get("resolved_terms"), (dict, list)):
            clause["resolved_terms"] = json.dumps(clause["resolved_terms"])
        with self._connect() as conn:
            self._insert(conn, "governing_doc", clause)
        return clause["gd_id"]

    def list_governing_clauses(self, deal_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return self._rows_to_dicts(
                conn.execute(
                    "SELECT * FROM governing_doc WHERE deal_id=? ORDER BY ordinal", (deal_id,)
                ).fetchall()
            )

    # ------------------------------------------------------------------
    # SEP artifacts (+ approval / override workflow)
    # ------------------------------------------------------------------
    def add_sep_artifact(self, artifact: dict[str, Any]) -> str:
        artifact = dict(artifact)
        artifact.setdefault("artifact_id", new_id("sep_"))
        artifact.setdefault("status", "pending_review")
        artifact.setdefault("version", 1)
        now = _now()
        artifact.setdefault("created_at", now)
        artifact.setdefault("updated_at", now)
        if isinstance(artifact.get("value"), (dict, list)):
            artifact["value"] = json.dumps(artifact["value"])
        with self._connect() as conn:
            self._insert(conn, "sep_artifacts", artifact)
        return artifact["artifact_id"]

    def get_sep_artifact(self, artifact_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            return self._row_to_dict(
                conn.execute(
                    "SELECT * FROM sep_artifacts WHERE artifact_id=?", (artifact_id,)
                ).fetchone()
            )

    def list_sep_artifacts(self, deal_id: str, sep_name: Optional[str] = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if sep_name:
                rows = conn.execute(
                    "SELECT * FROM sep_artifacts WHERE deal_id=? AND sep_name=? "
                    "ORDER BY created_at",
                    (deal_id, sep_name),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sep_artifacts WHERE deal_id=? ORDER BY sep_name, created_at",
                    (deal_id,),
                ).fetchall()
            return self._rows_to_dicts(rows)

    def approve_sep_artifact(self, artifact_id: str, *, actor: str) -> bool:
        before = self.get_sep_artifact(artifact_id)
        if before is None:
            return False
        ts = _now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE sep_artifacts SET status='approved', approved_by=?, approved_at=?, "
                "updated_at=? WHERE artifact_id=?",
                (actor, ts, ts, artifact_id),
            )
        self.audit(
            "approve_sep_artifact",
            actor=actor,
            object_type="sep_artifact",
            object_id=artifact_id,
            before=before,
            after={"status": "approved"},
        )
        return True

    def reject_sep_artifact(self, artifact_id: str, *, actor: str, rationale: str = "") -> bool:
        before = self.get_sep_artifact(artifact_id)
        if before is None:
            return False
        ts = _now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE sep_artifacts SET status='rejected', rationale=?, approved_by=?, "
                "approved_at=?, updated_at=? WHERE artifact_id=?",
                (rationale, actor, ts, ts, artifact_id),
            )
        self.audit(
            "reject_sep_artifact",
            actor=actor,
            object_type="sep_artifact",
            object_id=artifact_id,
            before=before,
            after={"status": "rejected", "rationale": rationale},
        )
        return True

    def supersede_sep_artifacts(self, deal_id: str, sep_name: str) -> int:
        """Mark all current artifacts of a profile as superseded (selective regen)."""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE sep_artifacts SET status='superseded', updated_at=? "
                "WHERE deal_id=? AND sep_name=? AND status NOT IN ('superseded','rejected')",
                (_now(), deal_id, sep_name),
            )
            return cur.rowcount

    def override_sep_artifact(
        self, artifact_id: str, *, new_value: Any, rationale: str, actor: str
    ) -> bool:
        """Override an artifact value. Rationale is mandatory; prior value preserved."""
        if not rationale or not rationale.strip():
            raise ValueError("Override requires a non-empty rationale.")
        before = self.get_sep_artifact(artifact_id)
        if before is None:
            return False
        ts = _now()
        value_str = json.dumps(new_value) if isinstance(new_value, (dict, list)) else str(new_value)
        with self._connect() as conn:
            conn.execute(
                "UPDATE sep_artifacts SET value=?, prior_value=?, rationale=?, "
                "status='overridden', version=version+1, approved_by=?, approved_at=?, "
                "updated_at=? WHERE artifact_id=?",
                (value_str, before.get("value"), rationale, actor, ts, ts, artifact_id),
            )
        self.audit(
            "override_sep_artifact",
            actor=actor,
            object_type="sep_artifact",
            object_id=artifact_id,
            before=before,
            after={"value": value_str, "rationale": rationale},
        )
        return True

    # ------------------------------------------------------------------
    # Payment model
    # ------------------------------------------------------------------
    def add_payment_model(self, model: dict[str, Any]) -> str:
        model = dict(model)
        model.setdefault("model_id", new_id("model_"))
        model.setdefault("validation_status", "draft")
        model.setdefault("version", 1)
        model.setdefault("generated_at", _now())
        for k in ("formula_map", "audit_report"):
            if isinstance(model.get(k), (dict, list)):
                model[k] = json.dumps(model[k])
        with self._connect() as conn:
            self._insert(conn, "payment_model", model)
        return model["model_id"]

    def get_latest_payment_model(self, deal_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            return self._row_to_dict(
                conn.execute(
                    "SELECT * FROM payment_model WHERE deal_id=? ORDER BY version DESC LIMIT 1",
                    (deal_id,),
                ).fetchone()
            )

    def set_model_audit(
        self, model_id: str, *, audit_report: Any, validation_status: str
    ) -> None:
        """Attach an audit report + validation verdict to an existing model in place."""
        report = json.dumps(audit_report) if isinstance(audit_report, (dict, list)) else audit_report
        with self._connect() as conn:
            conn.execute(
                "UPDATE payment_model SET audit_report=?, validation_status=? WHERE model_id=?",
                (report, validation_status, model_id),
            )

    # ------------------------------------------------------------------
    # Monthly runs
    # ------------------------------------------------------------------
    def add_monthly_run(self, run: dict[str, Any]) -> str:
        run = dict(run)
        run.setdefault("run_id", new_id("run_"))
        run.setdefault("created_at", _now())
        for k in ("results", "exceptions"):
            if isinstance(run.get(k), (dict, list)):
                run[k] = json.dumps(run[k])
        with self._connect() as conn:
            self._insert(conn, "monthly_runs", run)
        return run["run_id"]

    def list_monthly_runs(self, deal_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return self._rows_to_dicts(
                conn.execute(
                    "SELECT * FROM monthly_runs WHERE deal_id=? ORDER BY run_date DESC",
                    (deal_id,),
                ).fetchall()
            )

    # ------------------------------------------------------------------
    # Governance: correction events (AI exception / learning loop)
    # ------------------------------------------------------------------
    def add_correction_event(self, event: dict[str, Any]) -> int:
        event = dict(event)
        event.setdefault("ts", _now())
        event.setdefault("severity", "medium")
        event.setdefault("status", "open")
        for k in ("original_value", "corrected_value"):
            if isinstance(event.get(k), (dict, list)):
                event[k] = json.dumps(event[k])
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO correction_events"
                "(ts, deal_id, object_type, object_id, lifecycle_stage, original_value,"
                " corrected_value, root_cause, severity, actor, status) "
                "VALUES (:ts, :deal_id, :object_type, :object_id, :lifecycle_stage,"
                " :original_value, :corrected_value, :root_cause, :severity, :actor, :status)",
                {
                    "ts": event["ts"], "deal_id": event["deal_id"],
                    "object_type": event.get("object_type", ""), "object_id": event.get("object_id", ""),
                    "lifecycle_stage": event.get("lifecycle_stage", ""),
                    "original_value": event.get("original_value"), "corrected_value": event.get("corrected_value"),
                    "root_cause": event.get("root_cause", ""), "severity": event["severity"],
                    "actor": event.get("actor", ""), "status": event["status"],
                },
            )
            return int(cur.lastrowid)

    def list_correction_events(self, deal_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return self._rows_to_dicts(
                conn.execute(
                    "SELECT * FROM correction_events WHERE deal_id=? ORDER BY id DESC", (deal_id,)
                ).fetchall()
            )

    # ------------------------------------------------------------------
    # Governance: LLM cost tracking
    # ------------------------------------------------------------------
    def record_llm_cost(
        self, *, deal_id: str, command: str, model: str, input_tokens: int, output_tokens: int
    ) -> None:
        with self._connect() as conn:
            self._insert(conn, "llm_costs", {
                "ts": _now(), "deal_id": deal_id, "command": command, "model": model,
                "input_tokens": int(input_tokens), "output_tokens": int(output_tokens),
            })

    def cost_summary(self, deal_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS calls, COALESCE(SUM(input_tokens),0) AS in_tok, "
                "COALESCE(SUM(output_tokens),0) AS out_tok FROM llm_costs WHERE deal_id=?",
                (deal_id,),
            ).fetchone()
            by_cmd = conn.execute(
                "SELECT command, COUNT(*) AS calls, COALESCE(SUM(input_tokens+output_tokens),0) AS tok "
                "FROM llm_costs WHERE deal_id=? GROUP BY command ORDER BY tok DESC",
                (deal_id,),
            ).fetchall()
            return {
                "calls": int(row["calls"]),
                "input_tokens": int(row["in_tok"]),
                "output_tokens": int(row["out_tok"]),
                "total_tokens": int(row["in_tok"]) + int(row["out_tok"]),
                "by_command": [dict(r) for r in by_cmd],
            }

    # ------------------------------------------------------------------
    # Governance: deal-level RBAC entitlements
    # ------------------------------------------------------------------
    def set_entitlement(self, actor: str, deal_id: str, role: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO entitlements(actor, deal_id, role) VALUES (?, ?, ?) "
                "ON CONFLICT(actor, deal_id) DO UPDATE SET role=excluded.role",
                (actor, deal_id, role),
            )

    def get_role(self, actor: str, deal_id: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT role FROM entitlements WHERE actor=? AND deal_id=?", (actor, deal_id)
            ).fetchone()
            return row["role"] if row else None

    # ------------------------------------------------------------------
    # Async wrapper (keeps the event loop unblocked under load)
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Assumptions (CPR/CDR scenario library — Layer B.4)
    # ------------------------------------------------------------------
    def add_assumption(self, assumption: dict[str, Any]) -> str:
        assumption = dict(assumption)
        assumption.setdefault("assumption_id", new_id("assum_"))
        assumption.setdefault("version", 1)
        assumption.setdefault("is_active", 1)
        assumption.setdefault("created_at", _now())
        if isinstance(assumption.get("value"), (dict, list)):
            assumption["value"] = json.dumps(assumption["value"])
        with self._connect() as conn:
            self._insert(conn, "assumptions", assumption)
        return assumption["assumption_id"]

    def list_assumptions(self, deal_id: str, scenario_name: Optional[str] = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if scenario_name:
                rows = conn.execute(
                    "SELECT * FROM assumptions WHERE deal_id=? AND scenario_name=? ORDER BY assumption_type",
                    (deal_id, scenario_name),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM assumptions WHERE deal_id=? ORDER BY scenario_name, assumption_type",
                    (deal_id,),
                ).fetchall()
            return self._rows_to_dicts(rows)

    def list_scenarios(self, deal_id: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT scenario_name FROM assumptions WHERE deal_id=? ORDER BY scenario_name",
                (deal_id,),
            ).fetchall()
            return [r["scenario_name"] for r in rows]

    # ------------------------------------------------------------------
    # Agent results (store outputs from any agent run)
    # ------------------------------------------------------------------
    def add_agent_result(self, deal_id: str, agent_name: str, task: Any, result: Any) -> str:
        rid = new_id("ar_")
        with self._connect() as conn:
            self._insert(conn, "agent_results", {
                "result_id": rid, "deal_id": deal_id, "agent_name": agent_name,
                "task_json": json.dumps(task) if task is not None else None,
                "result_json": json.dumps(result, default=str) if result is not None else None,
                "status": "done", "created_at": _now(),
            })
        return rid

    def list_agent_results(self, deal_id: str, agent_name: Optional[str] = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if agent_name:
                rows = conn.execute(
                    "SELECT * FROM agent_results WHERE deal_id=? AND agent_name=? ORDER BY created_at DESC",
                    (deal_id, agent_name),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM agent_results WHERE deal_id=? ORDER BY created_at DESC",
                    (deal_id,),
                ).fetchall()
            return self._rows_to_dicts(rows)

    def get_latest_agent_result(self, deal_id: str, agent_name: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM agent_results WHERE deal_id=? AND agent_name=? ORDER BY created_at DESC LIMIT 1",
                (deal_id, agent_name),
            ).fetchone()
            return self._row_to_dict(row)

    # ------------------------------------------------------------------
    # Jobs (async job queue — Layer B.12)
    # ------------------------------------------------------------------
    def enqueue_job(self, deal_id: Optional[str], command: str, params: Any, actor: str = "user") -> str:
        jid = new_id("job_")
        with self._connect() as conn:
            self._insert(conn, "jobs", {
                "job_id": jid, "deal_id": deal_id, "command": command,
                "params": json.dumps(params) if params else None,
                "status": "queued", "queued_at": _now(), "actor": actor,
            })
        return jid

    def update_job(self, job_id: str, *, status: str, result: Any = None, error: str = "", progress: Any = None) -> None:
        now = _now()
        with self._connect() as conn:
            updates: dict[str, Any] = {"status": status}
            if status in ("running", "started"):
                updates["started_at"] = now
            if status in ("done", "failed", "cancelled"):
                updates["finished_at"] = now
            if result is not None:
                updates["result"] = json.dumps(result, default=str)
            if error:
                updates["error"] = error
            if progress is not None:
                updates["progress"] = json.dumps(progress, default=str)
            set_clause = ", ".join(f"{k}=?" for k in updates)
            conn.execute(
                f"UPDATE jobs SET {set_clause} WHERE job_id=?",
                list(updates.values()) + [job_id],
            )

    def list_jobs(self, deal_id: Optional[str] = None, *, status: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if deal_id and status:
                rows = conn.execute("SELECT * FROM jobs WHERE deal_id=? AND status=? ORDER BY queued_at DESC LIMIT ?", (deal_id, status, limit)).fetchall()
            elif deal_id:
                rows = conn.execute("SELECT * FROM jobs WHERE deal_id=? ORDER BY queued_at DESC LIMIT ?", (deal_id, limit)).fetchall()
            elif status:
                rows = conn.execute("SELECT * FROM jobs WHERE status=? ORDER BY queued_at DESC LIMIT ?", (status, limit)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM jobs ORDER BY queued_at DESC LIMIT ?", (limit,)).fetchall()
            return self._rows_to_dicts(rows)

    def get_job(self, job_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            return self._row_to_dict(conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone())

    # ------------------------------------------------------------------
    # Run details (waterfall trace per class)
    # ------------------------------------------------------------------
    def add_run_details(self, run_id: str, deal_id: str, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        with self._connect() as conn:
            for r in rows:
                self._insert(conn, "run_details", {
                    "run_id": run_id, "deal_id": deal_id,
                    "class_name": r.get("class_name", ""), "step_name": r.get("step_name", ""),
                    "step_order": r.get("step_order", 0), "interest": float(r.get("interest", 0) or 0),
                    "principal": float(r.get("principal", 0) or 0),
                    "beginning_bal": float(r.get("beginning_bal", 0) or 0),
                    "ending_bal": float(r.get("ending_bal", 0) or 0),
                })
        return len(rows)

    def get_run_details(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return self._rows_to_dicts(
                conn.execute("SELECT * FROM run_details WHERE run_id=? ORDER BY step_order, class_name", (run_id,)).fetchall()
            )

    async def run_async(self, method_name: str, /, *args: Any, **kwargs: Any) -> Any:
        """Invoke any sync method off-thread."""
        method = getattr(self, method_name)
        return await asyncio.to_thread(method, *args, **kwargs)