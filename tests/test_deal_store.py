"""
Tests for the per-deal SQLite data store (backend.abs.store.DealStore).

Covers schema init, CRUD for every entity, the definition resolution tree
(including cycle safety), the SEP approve/override/reject workflow with audit
trail, statelessness, and the async wrapper.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend.abs.store import DealStore, SCHEMA_VERSION, all_table_names


DEAL = "cbass_2002_cb4"


@pytest.fixture()
def store(tmp_path: Path) -> DealStore:
    return DealStore.for_deal_dir(tmp_path / DEAL)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def test_schema_initialises_and_versions(store: DealStore):
    assert store.schema_version() == SCHEMA_VERSION
    assert store.db_path.exists()


def test_all_tables_created(store: DealStore):
    with store._connect() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    names = {r["name"] for r in rows}
    for expected in all_table_names():
        assert expected in names


def test_init_is_idempotent(tmp_path: Path):
    d = tmp_path / DEAL
    DealStore.for_deal_dir(d)
    # Re-open without error and keep version.
    s2 = DealStore.for_deal_dir(d)
    assert s2.schema_version() == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Documents / sections / chunks
# ---------------------------------------------------------------------------

def test_document_crud(store: DealStore):
    doc_id = store.add_document(
        {"deal_id": DEAL, "doc_type": "PSA", "title": "Pooling & Servicing", "page_count": 300}
    )
    got = store.get_document(doc_id)
    assert got["doc_type"] == "PSA"
    assert got["status"] == "draft"
    assert store.list_documents(DEAL)[0]["doc_id"] == doc_id


def test_sections_and_chunks_with_pages(store: DealStore):
    doc_id = store.add_document({"deal_id": DEAL, "doc_type": "PSA"})
    store.add_sections(
        [
            {"section_id": "s1", "doc_id": doc_id, "section_path": "Article I", "title": "Definitions",
             "level": 1, "ordinal": 0, "page_start": 5, "page_end": 40},
            {"section_id": "s2", "doc_id": doc_id, "section_path": "Article V", "title": "Distributions",
             "level": 1, "ordinal": 1, "page_start": 60, "page_end": 75},
        ]
    )
    secs = store.list_sections(doc_id)
    assert [s["section_path"] for s in secs] == ["Article I", "Article V"]
    assert secs[0]["page_start"] == 5

    n = store.add_chunks(
        [
            {"chunk_id": "c1", "doc_id": doc_id, "section_id": "s1", "ordinal": 0,
             "text": "Available Funds means ...", "page_start": 6, "page_end": 6},
        ]
    )
    assert n == 1
    assert store.get_chunk("c1")["text"].startswith("Available Funds")


# ---------------------------------------------------------------------------
# Definitions + resolution tree
# ---------------------------------------------------------------------------

def _seed_definitions(store: DealStore) -> dict[str, str]:
    """Available Funds -> Net Interest -> Stated Interest (a 3-level chain)."""
    af = store.add_definition({"deal_id": DEAL, "term_name": "Available Funds",
                               "raw_definition": "the Net Interest plus principal", "page": 6})
    ni = store.add_definition({"deal_id": DEAL, "term_name": "Net Interest",
                               "raw_definition": "the Stated Interest less fees", "page": 8})
    si = store.add_definition({"deal_id": DEAL, "term_name": "Stated Interest",
                               "raw_definition": "rate times balance", "page": 9})
    store.add_definition_edge(af, ni)
    store.add_definition_edge(ni, si)
    return {"af": af, "ni": ni, "si": si}


def test_definition_dependencies_and_top_level(store: DealStore):
    ids = _seed_definitions(store)
    # Available Funds is the only root (nothing depends on it).
    roots = store.list_top_level_definitions(DEAL)
    assert {r["term_name"] for r in roots} == {"Available Funds"}
    deps = store.get_dependencies(ids["af"])
    assert deps[0]["term_name"] == "Net Interest"


def test_resolution_tree_is_nested_n_levels(store: DealStore):
    ids = _seed_definitions(store)
    tree = store.resolution_tree(ids["af"])
    assert tree["term_name"] == "Available Funds"
    assert tree["children"][0]["term_name"] == "Net Interest"
    assert tree["children"][0]["children"][0]["term_name"] == "Stated Interest"


def test_resolution_tree_is_cycle_safe(store: DealStore):
    a = store.add_definition({"deal_id": DEAL, "term_name": "A", "raw_definition": "uses B"})
    b = store.add_definition({"deal_id": DEAL, "term_name": "B", "raw_definition": "uses A"})
    store.add_definition_edge(a, b)
    store.add_definition_edge(b, a)  # cycle
    tree = store.resolution_tree(a)
    # Must terminate; the cycle back to A is flagged, not infinitely expanded.
    child_b = tree["children"][0]
    assert child_b["term_name"] == "B"
    grand = child_b["children"][0]
    assert grand["term_name"] == "A"
    assert grand.get("cyclic_or_truncated") is True


def test_update_resolved_definition(store: DealStore):
    ids = _seed_definitions(store)
    store.update_resolved_definition(ids["si"], "the certificate rate multiplied by the balance", depth=0)
    assert store.get_definition(ids["si"])["resolved_definition"].startswith("the certificate rate")


# ---------------------------------------------------------------------------
# SEP artifacts: approve / reject / override
# ---------------------------------------------------------------------------

def test_sep_artifact_add_and_list(store: DealStore):
    aid = store.add_sep_artifact(
        {"deal_id": DEAL, "sep_name": "fees", "field_path": "servicer_fee",
         "value": {"rate": 0.005, "frequency": "monthly"}, "citation": "§3.05 p.30", "confidence": 0.92}
    )
    art = store.get_sep_artifact(aid)
    assert art["status"] == "pending_review"
    assert json.loads(art["value"])["rate"] == 0.005
    assert len(store.list_sep_artifacts(DEAL, "fees")) == 1


def test_sep_approve_writes_audit(store: DealStore):
    aid = store.add_sep_artifact({"deal_id": DEAL, "sep_name": "fees", "value": {"x": 1}})
    assert store.approve_sep_artifact(aid, actor="alice") is True
    assert store.get_sep_artifact(aid)["status"] == "approved"
    audit = store.list_audit(object_type="sep_artifact", object_id=aid)
    assert any(a["action"] == "approve_sep_artifact" and a["actor"] == "alice" for a in audit)


def test_sep_override_requires_rationale_and_preserves_prior(store: DealStore):
    aid = store.add_sep_artifact({"deal_id": DEAL, "sep_name": "certificates", "value": {"balance": 100}})
    with pytest.raises(ValueError):
        store.override_sep_artifact(aid, new_value={"balance": 200}, rationale="  ", actor="bob")
    assert store.override_sep_artifact(
        aid, new_value={"balance": 200}, rationale="corrected per §2.1", actor="bob"
    ) is True
    art = store.get_sep_artifact(aid)
    assert art["status"] == "overridden"
    assert json.loads(art["value"])["balance"] == 200
    assert json.loads(art["prior_value"])["balance"] == 100
    assert art["version"] == 2


def test_sep_reject(store: DealStore):
    aid = store.add_sep_artifact({"deal_id": DEAL, "sep_name": "accounts", "value": {"a": 1}})
    assert store.reject_sep_artifact(aid, actor="carol", rationale="wrong account") is True
    assert store.get_sep_artifact(aid)["status"] == "rejected"


def test_approve_missing_artifact_returns_false(store: DealStore):
    assert store.approve_sep_artifact("nope", actor="x") is False


# ---------------------------------------------------------------------------
# Governing doc / payment model / monthly runs
# ---------------------------------------------------------------------------

def test_governing_clause_roundtrip(store: DealStore):
    gid = store.add_governing_clause(
        {"deal_id": DEAL, "verbatim": "On each Distribution Date ...",
         "plain_english": "Each month, pay interest first.",
         "math_formula": "interest = rate/12 * balance",
         "resolved_terms": {"Distribution Date": "the 25th of each month"},
         "citation": "§5.01 p.62"}
    )
    clauses = store.list_governing_clauses(DEAL)
    assert clauses[0]["gd_id"] == gid
    assert json.loads(clauses[0]["resolved_terms"])["Distribution Date"].startswith("the 25th")


def test_payment_model_versioning(store: DealStore):
    store.add_payment_model({"deal_id": DEAL, "python_source": "class M: pass", "version": 1})
    store.add_payment_model({"deal_id": DEAL, "python_source": "class M2: pass", "version": 2})
    latest = store.get_latest_payment_model(DEAL)
    assert latest["version"] == 2


def test_monthly_run_roundtrip(store: DealStore):
    rid = store.add_monthly_run(
        {"deal_id": DEAL, "run_date": "2024-09-25", "results": {"A-1": {"interest": 100.0}}}
    )
    runs = store.list_monthly_runs(DEAL)
    assert runs[0]["run_id"] == rid
    assert json.loads(runs[0]["results"])["A-1"]["interest"] == 100.0


# ---------------------------------------------------------------------------
# Statelessness + async
# ---------------------------------------------------------------------------

def test_stateless_two_instances_share_db(tmp_path: Path):
    d = tmp_path / DEAL
    s1 = DealStore.for_deal_dir(d)
    doc_id = s1.add_document({"deal_id": DEAL, "doc_type": "PSA"})
    # A brand-new instance (no shared connection/state) sees the committed row.
    s2 = DealStore.for_deal_dir(d, init=False)
    assert s2.get_document(doc_id) is not None


def test_async_wrapper(store: DealStore):
    async def _run():
        doc_id = await store.run_async(
            "add_document", {"deal_id": DEAL, "doc_type": "PSA"}
        )
        got = await store.run_async("get_document", doc_id)
        return got

    got = asyncio.run(_run())
    assert got["doc_type"] == "PSA"
