"""
ABS Deal Store — SQLite schema (the structured spine).

This module defines the per-deal relational data model that powers
explainability, traceability, attributability, and audit. Every deal owns an
isolated ``deal_store.db`` (SQLite) living at ``<deal>/data/deal_store.db``.

Design goals
------------
* **Lineage first** — foreign keys chain every artifact back to a source
  document section + page, so any output can be traced to the governing PDF.
* **Stateless access** — see :mod:`backend.abs.store.deal_store`; this module
  only declares DDL.
* **Idempotent** — all statements use ``IF NOT EXISTS`` so applying the schema
  to an existing database is safe.

The status vocabulary mirrors the MVP FRD lifecycle:
``draft → pending_review → approved → rejected → overridden → published
→ superseded → exception``.
"""

from __future__ import annotations

# Schema version — bump when DDL changes; stored in ``schema_meta``.
SCHEMA_VERSION = 4

# Canonical artifact lifecycle statuses (FRD §8).
STATUS_VALUES = (
    "draft",
    "pending_review",
    "approved",
    "rejected",
    "overridden",
    "published",
    "superseded",
    "exception",
)

_STATUS_CHECK = "(" + ", ".join(f"'{s}'" for s in STATUS_VALUES) + ")"


# ---------------------------------------------------------------------------
# DDL — ordered so that referenced tables are created before referencing ones.
# ---------------------------------------------------------------------------

SCHEMA_STATEMENTS: tuple[str, ...] = (
    # -- meta -----------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS schema_meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    # -- documents ------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS documents (
        doc_id        TEXT PRIMARY KEY,
        deal_id       TEXT NOT NULL,
        doc_type      TEXT NOT NULL,
        title         TEXT,
        version       TEXT,
        source_path   TEXT,
        content_hash  TEXT,
        page_count    INTEGER,
        status        TEXT NOT NULL DEFAULT 'draft'
                          CHECK (status IN """ + _STATUS_CHECK + """),
        is_operative  INTEGER NOT NULL DEFAULT 0,
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_documents_deal ON documents(deal_id)",
    "CREATE INDEX IF NOT EXISTS ix_documents_hash ON documents(content_hash)",
    # -- sections (TOC-aware hierarchy) --------------------------------------
    """
    CREATE TABLE IF NOT EXISTS sections (
        section_id    TEXT PRIMARY KEY,
        doc_id        TEXT NOT NULL,
        section_path  TEXT NOT NULL,
        title         TEXT,
        level         INTEGER NOT NULL DEFAULT 0,
        ordinal       INTEGER NOT NULL DEFAULT 0,
        page_start    INTEGER,
        page_end      INTEGER,
        parent_id     TEXT,
        char_start    INTEGER,
        char_end      INTEGER,
        FOREIGN KEY (doc_id)    REFERENCES documents(doc_id)   ON DELETE CASCADE,
        FOREIGN KEY (parent_id) REFERENCES sections(section_id) ON DELETE SET NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_sections_doc ON sections(doc_id)",
    "CREATE INDEX IF NOT EXISTS ix_sections_parent ON sections(parent_id)",
    "CREATE INDEX IF NOT EXISTS ix_sections_path ON sections(doc_id, section_path)",
    # -- chunks (embedding units, keyword-enhanced) --------------------------
    """
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id        TEXT PRIMARY KEY,
        section_id      TEXT,
        doc_id          TEXT NOT NULL,
        ordinal         INTEGER NOT NULL DEFAULT 0,
        text            TEXT NOT NULL,
        enhancement_md  TEXT,
        embedding_ref   TEXT,
        page_start      INTEGER,
        page_end        INTEGER,
        token_count     INTEGER,
        FOREIGN KEY (doc_id)     REFERENCES documents(doc_id)   ON DELETE CASCADE,
        FOREIGN KEY (section_id) REFERENCES sections(section_id) ON DELETE SET NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_chunks_doc ON chunks(doc_id)",
    "CREATE INDEX IF NOT EXISTS ix_chunks_section ON chunks(section_id)",
    # -- chunk_vectors (dense embeddings for cosine retrieval) ---------------
    """
    CREATE TABLE IF NOT EXISTS chunk_vectors (
        chunk_id  TEXT PRIMARY KEY,
        deal_id   TEXT NOT NULL,
        provider  TEXT NOT NULL,
        dim       INTEGER NOT NULL,
        vector    TEXT NOT NULL,            -- JSON list of floats
        FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_vectors_deal ON chunk_vectors(deal_id)",
    # -- definitions (defined terms + resolved text) -------------------------
    """
    CREATE TABLE IF NOT EXISTS definitions (
        term_id             TEXT PRIMARY KEY,
        deal_id             TEXT NOT NULL,
        doc_id              TEXT,
        term_name           TEXT NOT NULL,
        raw_definition      TEXT,
        resolved_definition TEXT,
        section_id          TEXT,
        page                INTEGER,
        citation            TEXT,
        is_cyclic           INTEGER NOT NULL DEFAULT 0,
        depth               INTEGER,
        status              TEXT NOT NULL DEFAULT 'draft'
                                CHECK (status IN """ + _STATUS_CHECK + """),
        version             INTEGER NOT NULL DEFAULT 1,
        approved_by         TEXT,
        approved_at         TEXT,
        created_at          TEXT NOT NULL,
        FOREIGN KEY (doc_id)     REFERENCES documents(doc_id)   ON DELETE SET NULL,
        FOREIGN KEY (section_id) REFERENCES sections(section_id) ON DELETE SET NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_definitions_deal ON definitions(deal_id)",
    "CREATE INDEX IF NOT EXISTS ix_definitions_name ON definitions(deal_id, term_name)",
    # -- definition_edges (the dependency DAG) -------------------------------
    """
    CREATE TABLE IF NOT EXISTS definition_edges (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        from_term_id  TEXT NOT NULL,
        to_term_id    TEXT NOT NULL,
        edge_type     TEXT NOT NULL DEFAULT 'DEPENDS_ON',
        FOREIGN KEY (from_term_id) REFERENCES definitions(term_id) ON DELETE CASCADE,
        FOREIGN KEY (to_term_id)   REFERENCES definitions(term_id) ON DELETE CASCADE,
        UNIQUE (from_term_id, to_term_id, edge_type)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_edges_from ON definition_edges(from_term_id)",
    "CREATE INDEX IF NOT EXISTS ix_edges_to ON definition_edges(to_term_id)",
    # -- governing_doc (verbatim ↔ interpreted ↔ formula bridge) -------------
    """
    CREATE TABLE IF NOT EXISTS governing_doc (
        gd_id             TEXT PRIMARY KEY,
        deal_id           TEXT NOT NULL,
        doc_id            TEXT,
        section_id        TEXT,
        ordinal           INTEGER NOT NULL DEFAULT 0,
        verbatim          TEXT,
        plain_english     TEXT,
        math_formula      TEXT,
        code_hint         TEXT,
        resolved_terms    TEXT,            -- JSON: {term: resolved_text}
        citation          TEXT,
        status            TEXT NOT NULL DEFAULT 'draft'
                              CHECK (status IN """ + _STATUS_CHECK + """),
        version           INTEGER NOT NULL DEFAULT 1,
        approved_by       TEXT,
        approved_at       TEXT,
        created_at        TEXT NOT NULL,
        FOREIGN KEY (doc_id)     REFERENCES documents(doc_id)   ON DELETE SET NULL,
        FOREIGN KEY (section_id) REFERENCES sections(section_id) ON DELETE SET NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_governing_deal ON governing_doc(deal_id)",
    # -- sep_artifacts (structured extraction outputs) -----------------------
    """
    CREATE TABLE IF NOT EXISTS sep_artifacts (
        artifact_id   TEXT PRIMARY KEY,
        deal_id       TEXT NOT NULL,
        sep_name      TEXT NOT NULL,
        field_path    TEXT,
        value         TEXT,                -- JSON payload for the item
        citation      TEXT,
        section_id    TEXT,
        page          INTEGER,
        confidence    REAL,
        status        TEXT NOT NULL DEFAULT 'draft'
                          CHECK (status IN """ + _STATUS_CHECK + """),
        version       INTEGER NOT NULL DEFAULT 1,
        prior_value   TEXT,                -- preserved on override
        rationale     TEXT,                -- required on override
        approved_by   TEXT,
        approved_at   TEXT,
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL,
        FOREIGN KEY (section_id) REFERENCES sections(section_id) ON DELETE SET NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_sep_deal ON sep_artifacts(deal_id)",
    "CREATE INDEX IF NOT EXISTS ix_sep_name ON sep_artifacts(deal_id, sep_name)",
    "CREATE INDEX IF NOT EXISTS ix_sep_status ON sep_artifacts(deal_id, status)",
    # -- payment_model (generated python + audit) ----------------------------
    """
    CREATE TABLE IF NOT EXISTS payment_model (
        model_id          TEXT PRIMARY KEY,
        deal_id           TEXT NOT NULL,
        python_source     TEXT,
        formula_map       TEXT,            -- JSON: line -> citation
        audit_report      TEXT,            -- JSON: auditor checks
        validation_status TEXT NOT NULL DEFAULT 'draft'
                              CHECK (validation_status IN """ + _STATUS_CHECK + """),
        version           INTEGER NOT NULL DEFAULT 1,
        generated_at      TEXT NOT NULL,
        approved_by       TEXT,
        approved_at       TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_model_deal ON payment_model(deal_id)",
    # -- monthly_runs (production execution) ---------------------------------
    """
    CREATE TABLE IF NOT EXISTS monthly_runs (
        run_id          TEXT PRIMARY KEY,
        deal_id         TEXT NOT NULL,
        run_date        TEXT NOT NULL,
        input_csv_path  TEXT,
        output_pdf_path TEXT,
        model_version   INTEGER,
        results         TEXT,              -- JSON: class-level outputs
        exceptions      TEXT,              -- JSON
        created_at      TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_runs_deal ON monthly_runs(deal_id)",
    # -- audit_log (append-only attributability) -----------------------------
    """
    CREATE TABLE IF NOT EXISTS audit_log (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        ts           TEXT NOT NULL,
        actor        TEXT,
        action       TEXT NOT NULL,
        object_type  TEXT,
        object_id    TEXT,
        before_json  TEXT,
        after_json   TEXT,
        evidence     TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_audit_object ON audit_log(object_type, object_id)",
    "CREATE INDEX IF NOT EXISTS ix_audit_ts ON audit_log(ts)",
    # -- correction_events (AI exception & learning loop) ---------------------
    """
    CREATE TABLE IF NOT EXISTS correction_events (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        ts               TEXT NOT NULL,
        deal_id          TEXT NOT NULL,
        object_type      TEXT,
        object_id        TEXT,
        lifecycle_stage  TEXT,
        original_value   TEXT,
        corrected_value  TEXT,
        root_cause       TEXT,
        severity         TEXT NOT NULL DEFAULT 'medium',
        actor            TEXT,
        status           TEXT NOT NULL DEFAULT 'open'
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_corr_deal ON correction_events(deal_id)",
    # -- llm_costs (AI cost management) ---------------------------------------
    """
    CREATE TABLE IF NOT EXISTS llm_costs (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        ts             TEXT NOT NULL,
        deal_id        TEXT,
        command        TEXT,
        model          TEXT,
        input_tokens   INTEGER NOT NULL DEFAULT 0,
        output_tokens  INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_cost_deal ON llm_costs(deal_id)",
    # -- entitlements (deal-level RBAC) ---------------------------------------
    """
    CREATE TABLE IF NOT EXISTS entitlements (
        actor    TEXT NOT NULL,
        deal_id  TEXT NOT NULL,
        role     TEXT NOT NULL,
        PRIMARY KEY (actor, deal_id)
    )
    """,
    # -- assumptions (CPR/CDR scenario library, Layer B.4) --------------------
    """
    CREATE TABLE IF NOT EXISTS assumptions (
        assumption_id  TEXT PRIMARY KEY,
        deal_id        TEXT NOT NULL,
        scenario_name  TEXT NOT NULL,
        assumption_type TEXT NOT NULL,   -- cpr, cdr, severity, recovery_lag, etc.
        value          TEXT NOT NULL,    -- JSON: {rate, timing, description}
        version        INTEGER NOT NULL DEFAULT 1,
        is_active      INTEGER NOT NULL DEFAULT 1,
        created_at     TEXT NOT NULL,
        actor          TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_assumptions_deal ON assumptions(deal_id)",
    "CREATE INDEX IF NOT EXISTS ix_assumptions_scenario ON assumptions(deal_id, scenario_name)",
    # -- agent_results (store outputs from any agent run) --------------------
    """
    CREATE TABLE IF NOT EXISTS agent_results (
        result_id    TEXT PRIMARY KEY,
        deal_id      TEXT NOT NULL,
        agent_name   TEXT NOT NULL,
        task_json    TEXT,
        result_json  TEXT,
        status       TEXT NOT NULL DEFAULT 'done',
        created_at   TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_agent_results_deal ON agent_results(deal_id)",
    "CREATE INDEX IF NOT EXISTS ix_agent_results_name ON agent_results(deal_id, agent_name)",
    # -- jobs (async job queue, Layer B.12) ----------------------------------
    """
    CREATE TABLE IF NOT EXISTS jobs (
        job_id       TEXT PRIMARY KEY,
        deal_id      TEXT,
        command      TEXT NOT NULL,
        params       TEXT,
        status       TEXT NOT NULL DEFAULT 'queued',
        progress     TEXT,
        result       TEXT,
        error        TEXT,
        queued_at    TEXT NOT NULL,
        started_at   TEXT,
        finished_at  TEXT,
        actor        TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_jobs_deal ON jobs(deal_id)",
    "CREATE INDEX IF NOT EXISTS ix_jobs_status ON jobs(status)",
    # -- run_details (waterfall trace per class per monthly run) --------------
    """
    CREATE TABLE IF NOT EXISTS run_details (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id        TEXT NOT NULL,
        deal_id       TEXT NOT NULL,
        class_name    TEXT NOT NULL,
        step_name     TEXT,
        step_order    INTEGER,
        interest      REAL DEFAULT 0,
        principal     REAL DEFAULT 0,
        beginning_bal REAL DEFAULT 0,
        ending_bal    REAL DEFAULT 0,
        FOREIGN KEY (run_id) REFERENCES monthly_runs(run_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_run_details_run ON run_details(run_id)",
    "CREATE INDEX IF NOT EXISTS ix_run_details_deal ON run_details(deal_id)",
)


def all_table_names() -> tuple[str, ...]:
    """Return the canonical table names defined by this schema."""
    return (
        "schema_meta",
        "documents",
        "sections",
        "chunks",
        "chunk_vectors",
        "definitions",
        "definition_edges",
        "governing_doc",
        "sep_artifacts",
        "payment_model",
        "monthly_runs",
        "audit_log",
        "correction_events",
        "llm_costs",
        "entitlements",
        "assumptions",
        "agent_results",
        "jobs",
        "run_details",
    )
