"""Phase 17 — Deal Catalog Schema tests (Step 4)."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.vector.deal_catalog import (
    CatalogEntry,
    DealCatalog,
    _parse_deal_folder_name,
)


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture()
def catalog(tmp_path: Path) -> DealCatalog:
    """Return a DealCatalog backed by a temp SQLite file."""
    db_path = str(tmp_path / "deal_catalog.db")
    return DealCatalog(db_path=db_path)


def _seed_bear_stearns(cat: DealCatalog) -> None:
    """Helper: insert a Bear Stearns deal with full metadata."""
    cat.upsert_deal(
        scope_slug="bear_stearns_2006_he1",
        folder_path=str(Path("/deals/Bear_Stearns_2006_HE1")),
        deal_name="Bear Stearns",
        vintage=2006,
        series="HE1",
        issuer="Bear Stearns",
        doc_types=["PSA", "PROSUPP"],
        chunk_count=120,
        status="active",
    )


# ── 1. Schema upgrade adds new columns ───────────────────────


def test_schema_upgrade_adds_new_columns(catalog: DealCatalog) -> None:
    conn = sqlite3.connect(catalog.db_path)
    try:
        cursor = conn.execute("PRAGMA table_info(deal_catalog)")
        col_names = {row[1] for row in cursor.fetchall()}
    finally:
        conn.close()

    for col in ("deal_name", "vintage", "series", "chunk_count", "status"):
        assert col in col_names, f"Phase 17 column '{col}' missing from deal_catalog"


# ── 2. Upsert deal with full metadata ────────────────────────


def test_upsert_deal_with_full_metadata(catalog: DealCatalog) -> None:
    _seed_bear_stearns(catalog)
    entry = catalog.get_by_slug("bear_stearns_2006_he1")
    assert entry is not None
    assert entry.slug == "bear_stearns_2006_he1"
    assert entry.folder_name == "Bear_Stearns_2006_HE1"
    assert entry.doc_count == 2  # len(["PSA", "PROSUPP"])
    assert "PSA" in entry.doc_types
    assert "PROSUPP" in entry.doc_types


# ── 3. Upsert same slug twice — no duplicate ─────────────────


def test_upsert_deal_update_existing(catalog: DealCatalog) -> None:
    _seed_bear_stearns(catalog)
    # upsert again with updated chunk_count
    catalog.upsert_deal(
        scope_slug="bear_stearns_2006_he1",
        folder_path=str(Path("/deals/Bear_Stearns_2006_HE1")),
        deal_name="Bear Stearns",
        vintage=2006,
        series="HE1",
        issuer="Bear Stearns",
        doc_types=["PSA", "PROSUPP", "INDENTURE"],
        chunk_count=200,
        status="active",
    )
    all_deals = catalog.list_all_deals()
    matching = [d for d in all_deals if d["slug"] == "bear_stearns_2006_he1"]
    assert len(matching) == 1, "Expected exactly one entry after two upserts"
    assert matching[0]["chunk_count"] == 200


# ── 4. search_deals by wildcard pattern ──────────────────────


def test_search_deals_by_pattern_wildcard(catalog: DealCatalog) -> None:
    _seed_bear_stearns(catalog)
    results = catalog.search_deals(pattern="bear_stearns*")
    assert len(results) >= 1
    assert results[0]["slug"] == "bear_stearns_2006_he1"


# ── 5. search_deals by pattern — no match ────────────────────


def test_search_deals_by_pattern_no_match(catalog: DealCatalog) -> None:
    _seed_bear_stearns(catalog)
    results = catalog.search_deals(pattern="nomatch_xyz*")
    assert results == []


# ── 6. search_deals by deal_name ─────────────────────────────


def test_search_deals_by_deal_name(catalog: DealCatalog) -> None:
    _seed_bear_stearns(catalog)
    results = catalog.search_deals(deal_name="Bear Stearns")
    assert len(results) >= 1
    assert results[0]["deal_name"] == "Bear Stearns"


# ── 7. search_deals by vintage ───────────────────────────────


def test_search_deals_by_vintage(catalog: DealCatalog) -> None:
    _seed_bear_stearns(catalog)
    results = catalog.search_deals(vintage=2006)
    assert len(results) >= 1
    assert results[0]["vintage"] == 2006


# ── 8. search_deals combined filters ─────────────────────────


def test_search_deals_combined_filters(catalog: DealCatalog) -> None:
    _seed_bear_stearns(catalog)
    # Also add a 2006 deal with different name
    catalog.upsert_deal(
        scope_slug="gsaa_2006_af1",
        folder_path=str(Path("/deals/GSAA_2006_AF1")),
        deal_name="GSAA",
        vintage=2006,
        series="AF1",
    )
    # Both are vintage=2006, but only one matches deal_name
    results = catalog.search_deals(deal_name="Bear Stearns", vintage=2006)
    assert len(results) == 1
    assert results[0]["slug"] == "bear_stearns_2006_he1"


# ── 9. get_doc_types ─────────────────────────────────────────


def test_get_doc_types(catalog: DealCatalog) -> None:
    _seed_bear_stearns(catalog)
    doc_types = catalog.get_doc_types("bear_stearns_2006_he1")
    assert isinstance(doc_types, list)
    assert "PSA" in doc_types
    assert "PROSUPP" in doc_types


# ── 10. get_doc_types — nonexistent ──────────────────────────


def test_get_doc_types_nonexistent(catalog: DealCatalog) -> None:
    result = catalog.get_doc_types("nonexistent_slug")
    assert result == []


# ── 11. list_all_deals ───────────────────────────────────────


def test_list_all_deals(catalog: DealCatalog) -> None:
    _seed_bear_stearns(catalog)
    catalog.upsert_deal(
        scope_slug="gsaa_2006_af1",
        folder_path=str(Path("/deals/GSAA_2006_AF1")),
        deal_name="GSAA",
        vintage=2006,
        series="AF1",
    )
    deals = catalog.list_all_deals()
    assert len(deals) == 2
    slugs = {d["slug"] for d in deals}
    assert "bear_stearns_2006_he1" in slugs
    assert "gsaa_2006_af1" in slugs


# ── 12. list_all_deals — empty DB ────────────────────────────


def test_list_all_deals_empty_db(catalog: DealCatalog) -> None:
    deals = catalog.list_all_deals()
    assert deals == []


# ── 13. _parse_deal_folder_name — full ───────────────────────


def test_parse_deal_folder_name_full() -> None:
    result = _parse_deal_folder_name("Bear_Stearns_2006_HE1")
    assert result["deal_name"] == "Bear Stearns"
    assert result["vintage"] == 2006
    assert result["series"] == "HE1"


# ── 14. _parse_deal_folder_name — simple (no year/series) ────


def test_parse_deal_folder_name_simple() -> None:
    result = _parse_deal_folder_name("Fin_deal1")
    assert result["deal_name"] == "Fin deal1"
    assert result["vintage"] == 0
    assert result["series"] == ""


# ── 15. _parse_deal_folder_name — year only ──────────────────


def test_parse_deal_folder_name_year_only() -> None:
    result = _parse_deal_folder_name("GSAA_2006")
    assert result["deal_name"] == "GSAA"
    assert result["vintage"] == 2006
    assert result["series"] == ""


# ── 16. Catalog backward compatible — fresh migration ────────


def test_catalog_backward_compatible(tmp_path: Path) -> None:
    db_path = str(tmp_path / "legacy.db")
    # Create a bare-bones legacy DB without Phase 17 columns
    conn = sqlite3.connect(db_path)
    conn.execute(DealCatalog._CREATE_SQL)
    conn.execute(
        "INSERT INTO deal_catalog (folder_name, slug, kts_path) "
        "VALUES ('LegacyDeal', 'legacydeal', '/deals/LegacyDeal/.kts')"
    )
    conn.commit()
    conn.close()

    # Now open with DealCatalog — migration should run without breaking
    cat = DealCatalog(db_path=db_path)
    entry = cat.get("LegacyDeal")
    assert entry is not None
    assert entry.slug == "legacydeal"

    # Phase 17 columns should now exist
    conn2 = sqlite3.connect(db_path)
    col_names = {r[1] for r in conn2.execute("PRAGMA table_info(deal_catalog)").fetchall()}
    conn2.close()
    for col in ("deal_name", "vintage", "series", "chunk_count", "status"):
        assert col in col_names


# ── 17. get_by_slug ──────────────────────────────────────────


def test_get_by_slug(catalog: DealCatalog) -> None:
    _seed_bear_stearns(catalog)
    entry = catalog.get_by_slug("bear_stearns_2006_he1")
    assert entry is not None
    assert entry.folder_name == "Bear_Stearns_2006_HE1"
    assert entry.slug == "bear_stearns_2006_he1"


# ── 18. Upsert with partial metadata ─────────────────────────


def test_upsert_deal_partial_metadata(catalog: DealCatalog) -> None:
    catalog.upsert_deal(
        scope_slug="partial_deal",
        folder_path=str(Path("/deals/Partial_Deal")),
        deal_name="Partial",
        # vintage, series, issuer, doc_types, chunk_count omitted → defaults
    )
    results = catalog.search_deals(deal_name="Partial")
    assert len(results) == 1
    d = results[0]
    assert d["deal_name"] == "Partial"
    assert d["vintage"] == 0
    assert d["series"] == ""
    assert d["chunk_count"] == 0
    assert d["status"] == "active"
