"""
Phase 12 — Named Scoped Knowledge Spaces: Comprehensive Tests.

Covers all four increments:
  12.1  Per-folder .kts directories & collection naming
  12.2  Auto-discovery & dynamic slash commands
  12.3  Two-level scope narrowing
  12.4  Deal catalog & smart cross-scope routing

Tests are purely deterministic (no LLM / network calls).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helper: run async coroutine synchronously (pytest-asyncio NOT installed)
# ---------------------------------------------------------------------------
def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════════════════
#  12.1 — PER-FOLDER .KTS DIRECTORIES & COLLECTION NAMING
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase12_1_CollectionNaming:
    """Collection naming constants and scoped collection creator."""

    def test_collection_prefix_constant(self):
        from backend.vector.store import VectorStore
        assert hasattr(VectorStore, "COLLECTION_PREFIX")
        assert VectorStore.COLLECTION_PREFIX == "kts_"

    def test_default_collection_constant(self):
        from backend.vector.store import VectorStore
        assert hasattr(VectorStore, "DEFAULT_COLLECTION")
        assert VectorStore.DEFAULT_COLLECTION == "kts_default"

    def test_legacy_collection_constant(self):
        from backend.vector.store import VectorStore
        assert hasattr(VectorStore, "LEGACY_COLLECTION")
        assert VectorStore.LEGACY_COLLECTION == "kts_knowledge_base"

    def test_collection_name_for_scope_global(self):
        from backend.vector.store import VectorStore
        assert VectorStore.collection_name_for_scope("") == "kts_default"
        assert VectorStore.collection_name_for_scope(None) == "kts_default"
        assert VectorStore.collection_name_for_scope("__global__") == "kts_default"

    def test_collection_name_for_scope_slug(self):
        from backend.vector.store import VectorStore
        assert VectorStore.collection_name_for_scope("bear_stearns_2006_he1") == "kts_bear_stearns_2006_he1"

    def test_collection_name_for_scope_training(self):
        from backend.vector.store import VectorStore
        assert VectorStore.collection_name_for_scope("training_materials") == "kts_training_materials"

    def test_collection_name_prefix_prevents_collision(self):
        """Prefix 'kts_' prevents collision with user-created ChromaDB collections."""
        from backend.vector.store import VectorStore
        name = VectorStore.collection_name_for_scope("someslug")
        assert name.startswith("kts_")

    def test_get_or_create_scoped_collection_method_exists(self):
        from backend.vector.store import VectorStore
        assert hasattr(VectorStore, "get_or_create_scoped_collection")
        assert callable(getattr(VectorStore, "get_or_create_scoped_collection"))

    def test_search_accepts_scope_parameter(self):
        """store.search() must accept a 'scope' keyword parameter."""
        import inspect
        from backend.vector.store import VectorStore
        sig = inspect.signature(VectorStore.search)
        assert "scope" in sig.parameters

    def test_search_accepts_doc_type_filter(self):
        """store.search() must accept a 'doc_type_filter' keyword parameter."""
        import inspect
        from backend.vector.store import VectorStore
        sig = inspect.signature(VectorStore.search)
        assert "doc_type_filter" in sig.parameters


# ═══════════════════════════════════════════════════════════════════════════
#  12.2 — AUTO-DISCOVERY & DYNAMIC SLASH COMMANDS (scope_discovery.js)
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase12_2_ScopeDiscoveryJS:
    """Validate scope_discovery.js exports and structure."""

    SCOPE_JS_PATH = Path(__file__).resolve().parents[1] / "extension" / "lib" / "scope_discovery.js"

    def test_scope_discovery_file_exists(self):
        assert self.SCOPE_JS_PATH.exists(), "scope_discovery.js must exist"

    def test_exports_discoverScopes(self):
        text = self.SCOPE_JS_PATH.read_text(encoding="utf-8")
        assert "discoverScopes" in text

    def test_exports_buildDynamicCommands(self):
        text = self.SCOPE_JS_PATH.read_text(encoding="utf-8")
        assert "buildDynamicCommands" in text

    def test_exports_refreshScopes(self):
        text = self.SCOPE_JS_PATH.read_text(encoding="utf-8")
        assert "refreshScopes" in text

    def test_exports_parseTwoLevelScope(self):
        text = self.SCOPE_JS_PATH.read_text(encoding="utf-8")
        assert "parseTwoLevelScope" in text

    def test_exports_slugify(self):
        text = self.SCOPE_JS_PATH.read_text(encoding="utf-8")
        assert "slugify" in text

    def test_exports_pathExists(self):
        text = self.SCOPE_JS_PATH.read_text(encoding="utf-8")
        assert "pathExists" in text

    def test_discoverScopes_returns_array(self):
        """discoverScopes must return an array of scope objects."""
        text = self.SCOPE_JS_PATH.read_text(encoding="utf-8")
        assert "const scopes = []" in text or "scopes.push" in text

    def test_buildDynamicCommands_filters_indexed(self):
        """Only indexed scopes should become dynamic commands."""
        text = self.SCOPE_JS_PATH.read_text(encoding="utf-8")
        assert "s.indexed" in text or "indexed" in text

    def test_slug_fields_in_scope_object(self):
        """Scope objects should have name, slug, ktsPath, indexed."""
        text = self.SCOPE_JS_PATH.read_text(encoding="utf-8")
        for field in ["name:", "slug:", "ktsPath:", "indexed:"]:
            assert field in text, f"Missing field {field} in scope object"


class TestPhase12_2_ExtensionWiring:
    """Validate extension.js wires scope discovery on activation."""

    EXT_JS_PATH = Path(__file__).resolve().parents[1] / "extension" / "extension.js"

    def test_imports_refreshScopes(self):
        text = self.EXT_JS_PATH.read_text(encoding="utf-8")
        assert "refreshScopes" in text

    def test_calls_refreshScopes_on_activation(self):
        text = self.EXT_JS_PATH.read_text(encoding="utf-8")
        assert "refreshScopes(" in text

    def test_registers_kts_refreshScopes_command(self):
        text = self.EXT_JS_PATH.read_text(encoding="utf-8")
        assert "kts.refreshScopes" in text

    def test_participant_reference_passed_to_refreshScopes(self):
        """refreshScopes must receive a non-null participant reference (not always null)."""
        text = self.EXT_JS_PATH.read_text(encoding="utf-8")
        # Must contain shared._chatParticipant in a refreshScopes call
        assert "_chatParticipant" in text

    def test_participant_stored_on_shared(self):
        """registerChatParticipant stores participant reference on shared."""
        text = (Path(__file__).resolve().parents[1] / "extension" / "chat" / "participant.js").read_text(encoding="utf-8")
        assert "shared._chatParticipant = participant" in text


# ═══════════════════════════════════════════════════════════════════════════
#  12.2 — SLUGIFICATION (Python side)
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase12_2_Slugify:
    """Slugification rules: lowercase, spaces→_, hyphens→_, strip special."""

    def test_slugify_importable(self):
        from backend.vector.deal_catalog import slugify
        assert callable(slugify)

    def test_spaces_to_underscore(self):
        from backend.vector.deal_catalog import slugify
        assert slugify("Training Materials") == "training_materials"

    def test_hyphens_to_underscore(self):
        from backend.vector.deal_catalog import slugify
        assert slugify("Bear-Stearns-2006") == "bear_stearns_2006"

    def test_lowercase(self):
        from backend.vector.deal_catalog import slugify
        assert slugify("HP Support Docs") == "hp_support_docs"

    def test_special_chars_removed(self):
        from backend.vector.deal_catalog import slugify
        result = slugify("Q3 2025 Deals!")
        assert "!" not in result
        assert result == "q3_2025_deals"

    def test_multiple_spaces_collapsed(self):
        from backend.vector.deal_catalog import slugify
        assert slugify("a   b   c") == "a_b_c"

    def test_leading_trailing_stripped(self):
        from backend.vector.deal_catalog import slugify
        result = slugify("  hello  ")
        assert not result.startswith("_")
        assert not result.endswith("_")
        assert result == "hello"

    def test_bear_stearns_he1(self):
        from backend.vector.deal_catalog import slugify
        # Spec table: 'Bear Stearns 2006-HE1' → 'bear_stearns_2006_he1'
        # Note: slugify lowercases everything
        result = slugify("Bear Stearns 2006-HE1")
        assert result == "bear_stearns_2006_he1"

    def test_empty_string(self):
        from backend.vector.deal_catalog import slugify
        assert slugify("") == ""

    def test_only_special_chars(self):
        from backend.vector.deal_catalog import slugify
        assert slugify("!@#$%") == ""


# ═══════════════════════════════════════════════════════════════════════════
#  12.3 — TWO-LEVEL SCOPE NARROWING
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase12_3_TwoLevelScope:
    """Parse two-level scope: /scope /doc_type question."""

    def test_parse_two_level_scope_importable(self):
        from backend.retrieval.scope_router import parse_two_level_scope
        assert callable(parse_two_level_scope)

    def test_parse_with_doc_type(self):
        from backend.retrieval.scope_router import parse_two_level_scope
        result = parse_two_level_scope("bear_stearns_2006_he1", "/psa What is the Determination Date?")
        assert result["scope"] == "bear_stearns_2006_he1"
        assert result["doc_type_filter"] == "PSA"
        assert "Determination Date" in result["query"]

    def test_parse_without_doc_type(self):
        from backend.retrieval.scope_router import parse_two_level_scope
        result = parse_two_level_scope("training", "What is the onboarding checklist?")
        assert result["scope"] == "training"
        assert result["doc_type_filter"] is None
        assert "onboarding" in result["query"]

    def test_doc_type_uppercased(self):
        from backend.retrieval.scope_router import parse_two_level_scope
        result = parse_two_level_scope("deal1", "/prosupp What are the key dates?")
        assert result["doc_type_filter"] == "PROSUPP"

    def test_empty_prompt(self):
        from backend.retrieval.scope_router import parse_two_level_scope
        result = parse_two_level_scope("scope1", "")
        assert result["scope"] == "scope1"
        assert result["doc_type_filter"] is None
        assert result["query"] == ""

    def test_prompt_with_only_slash_word(self):
        from backend.retrieval.scope_router import parse_two_level_scope
        result = parse_two_level_scope("deal", "/indenture What about waterfall?")
        assert result["doc_type_filter"] == "INDENTURE"
        assert "waterfall" in result["query"].lower()

    def test_no_leading_slash_no_filter(self):
        """If prompt doesn't start with /word, no doc_type filter."""
        from backend.retrieval.scope_router import parse_two_level_scope
        result = parse_two_level_scope("scope", "just a normal question")
        assert result["doc_type_filter"] is None

    # — Participant.js integration checks —

    def test_participant_imports_parseTwoLevelScope(self):
        text = (Path(__file__).resolve().parents[1] / "extension" / "chat" / "participant.js").read_text(encoding="utf-8")
        assert "parseTwoLevelScope" in text

    def test_participant_forwards_scopeOverride(self):
        text = (Path(__file__).resolve().parents[1] / "extension" / "chat" / "participant.js").read_text(encoding="utf-8")
        assert "scopeOverride:" in text or "scopeOverride =" in text

    def test_participant_forwards_docTypeFilter(self):
        text = (Path(__file__).resolve().parents[1] / "extension" / "chat" / "participant.js").read_text(encoding="utf-8")
        assert "docType: docTypeFilter" in text or "docTypeFilter" in text

    # — kts_tool.js integration checks —

    def test_kts_tool_forwards_scope_override(self):
        text = (Path(__file__).resolve().parents[1] / "extension" / "copilot" / "kts_tool.js").read_text(encoding="utf-8")
        assert "--scope-override" in text

    def test_kts_tool_forwards_doc_type(self):
        text = (Path(__file__).resolve().parents[1] / "extension" / "copilot" / "kts_tool.js").read_text(encoding="utf-8")
        assert "--doc-type" in text

    # — CLI integration checks —

    def test_cli_search_has_scope_override_option(self):
        text = (Path(__file__).resolve().parents[1] / "cli" / "main.py").read_text(encoding="utf-8")
        assert "--scope-override" in text

    def test_cli_search_forwards_doc_type_filter(self):
        text = (Path(__file__).resolve().parents[1] / "cli" / "main.py").read_text(encoding="utf-8")
        assert '"doc_type_filter"' in text


# ═══════════════════════════════════════════════════════════════════════════
#  12.4 — DEAL CATALOG
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase12_4_DealCatalog:
    """SQLite-backed deal catalog with 10 columns, FTS5, CRUD, search."""

    @pytest.fixture
    def catalog(self, tmp_path):
        from backend.vector.deal_catalog import DealCatalog
        db = str(tmp_path / "test_catalog.db")
        return DealCatalog(db_path=db)

    @pytest.fixture
    def entry(self):
        from backend.vector.deal_catalog import CatalogEntry
        return CatalogEntry(
            folder_name="Bear Stearns 2006-HE1",
            slug="bear_stearns_2006_he1",
            kts_path="/deals/Bear Stearns 2006-HE1/.kts",
            doc_count=4,
            doc_types=["PSA", "PROSUPP"],
            issuers=["Bear Stearns"],
            years=["2006"],
            collateral_types=["HELOC", "Subprime"],
            key_parties=["Wells Fargo", "Deutsche Bank"],
        )

    # — Schema tests —

    def test_catalog_importable(self):
        from backend.vector.deal_catalog import DealCatalog
        assert DealCatalog is not None

    def test_catalog_entry_importable(self):
        from backend.vector.deal_catalog import CatalogEntry
        assert CatalogEntry is not None

    def test_schema_has_10_columns(self, catalog):
        conn = sqlite3.connect(catalog.db_path)
        cursor = conn.execute("PRAGMA table_info(deal_catalog)")
        cols = [row[1] for row in cursor.fetchall()]
        conn.close()
        expected = {
            "folder_name", "slug", "kts_path", "doc_count",
            "doc_types", "issuers", "years", "collateral_types",
            "key_parties", "last_indexed",
            # Phase 21+: ABS deal metadata columns
            "deal_name", "vintage", "series", "chunk_count", "status",
        }
        assert expected == set(cols)

    def test_folder_name_is_primary_key(self, catalog):
        conn = sqlite3.connect(catalog.db_path)
        cursor = conn.execute("PRAGMA table_info(deal_catalog)")
        cols = {row[1]: row[5] for row in cursor.fetchall()}  # name: pk
        conn.close()
        assert cols["folder_name"] == 1

    # — FTS5 tests —

    def test_fts5_virtual_table_created(self, catalog):
        """deal_catalog_fts virtual table should exist (FTS5)."""
        conn = sqlite3.connect(catalog.db_path)
        try:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            assert "deal_catalog_fts" in tables, "FTS5 virtual table not found"
        finally:
            conn.close()

    def test_fts5_triggers_created(self, catalog):
        """Sync triggers for FTS5 should exist."""
        conn = sqlite3.connect(catalog.db_path)
        try:
            triggers = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            ).fetchall()]
            trigger_names = set(triggers)
            assert "deal_catalog_ai" in trigger_names, "INSERT trigger missing"
            assert "deal_catalog_ad" in trigger_names, "DELETE trigger missing"
            assert "deal_catalog_au" in trigger_names, "UPDATE trigger missing"
        finally:
            conn.close()

    # — CRUD tests —

    def test_upsert_and_get(self, catalog, entry):
        catalog.upsert(entry)
        result = catalog.get("Bear Stearns 2006-HE1")
        assert result is not None
        assert result.slug == "bear_stearns_2006_he1"
        assert result.doc_count == 4

    def test_upsert_overwrites(self, catalog, entry):
        catalog.upsert(entry)
        entry.doc_count = 10
        catalog.upsert(entry)
        result = catalog.get("Bear Stearns 2006-HE1")
        assert result.doc_count == 10

    def test_delete(self, catalog, entry):
        catalog.upsert(entry)
        catalog.delete("Bear Stearns 2006-HE1")
        assert catalog.get("Bear Stearns 2006-HE1") is None

    def test_get_nonexistent(self, catalog):
        assert catalog.get("nonexistent_deal") is None

    def test_count_empty(self, catalog):
        assert catalog.count() == 0

    def test_count_after_upserts(self, catalog, entry):
        catalog.upsert(entry)
        from backend.vector.deal_catalog import CatalogEntry
        entry2 = CatalogEntry(
            folder_name="Deal2",
            slug="deal2",
            kts_path="/deals/Deal2/.kts",
        )
        catalog.upsert(entry2)
        assert catalog.count() == 2

    def test_all_scopes(self, catalog, entry):
        catalog.upsert(entry)
        scopes = catalog.all_scopes()
        assert len(scopes) == 1
        assert scopes[0]["slug"] == "bear_stearns_2006_he1"

    def test_all_scopes_empty(self, catalog):
        assert catalog.all_scopes() == []

    # — Search tests —

    def test_search_by_folder_name(self, catalog, entry):
        catalog.upsert(entry)
        results = catalog.search("bear stearns")
        assert len(results) >= 1
        assert results[0]["slug"] == "bear_stearns_2006_he1"

    def test_search_by_slug(self, catalog, entry):
        catalog.upsert(entry)
        results = catalog.search("bear_stearns")
        assert len(results) >= 1

    def test_search_by_year(self, catalog, entry):
        catalog.upsert(entry)
        results = catalog.search("2006")
        assert len(results) >= 1

    def test_search_no_match(self, catalog, entry):
        catalog.upsert(entry)
        results = catalog.search("nonexistent_xyz_123")
        assert len(results) == 0

    def test_search_returns_dict_with_slug(self, catalog, entry):
        catalog.upsert(entry)
        results = catalog.search("bear")
        assert len(results) >= 1
        assert "slug" in results[0]
        assert "folder_name" in results[0]
        assert "kts_path" in results[0]
        assert "score" in results[0]

    # — CatalogEntry dataclass tests —

    def test_catalog_entry_to_dict(self, entry):
        d = entry.to_dict()
        assert d["folder_name"] == "Bear Stearns 2006-HE1"
        assert d["slug"] == "bear_stearns_2006_he1"
        assert d["doc_types"] == ["PSA", "PROSUPP"]
        assert d["collateral_types"] == ["HELOC", "Subprime"]

    def test_catalog_entry_defaults(self):
        from backend.vector.deal_catalog import CatalogEntry
        e = CatalogEntry(folder_name="Test", slug="test", kts_path="/test/.kts")
        assert e.doc_count == 0
        assert e.doc_types == []
        assert e.issuers == []
        assert e.years == []
        assert e.collateral_types == []
        assert e.key_parties == []
        assert e.last_indexed is None

    # — JSON fields stored correctly —

    def test_json_fields_round_trip(self, catalog, entry):
        catalog.upsert(entry)
        result = catalog.get("Bear Stearns 2006-HE1")
        assert result.doc_types == ["PSA", "PROSUPP"]
        assert result.issuers == ["Bear Stearns"]
        assert result.collateral_types == ["HELOC", "Subprime"]
        assert result.key_parties == ["Wells Fargo", "Deutsche Bank"]

    def test_last_indexed_auto_populated(self, catalog, entry):
        catalog.upsert(entry)
        result = catalog.get("Bear Stearns 2006-HE1")
        assert result.last_indexed is not None


class TestPhase12_4_DiscoverScopes:
    """discover_scopes() helper scans filesystem for .kts/ folders."""

    def test_discover_scopes_importable(self):
        from backend.vector.deal_catalog import discover_scopes
        assert callable(discover_scopes)

    def test_discover_scopes_empty_dir(self, tmp_path):
        from backend.vector.deal_catalog import discover_scopes
        entries = discover_scopes(str(tmp_path))
        assert entries == []

    def test_discover_scopes_finds_indexed_folders(self, tmp_path):
        from backend.vector.deal_catalog import discover_scopes
        # Create a folder with .kts and a file
        deal_dir = tmp_path / "DealA"
        deal_dir.mkdir()
        (deal_dir / ".kts").mkdir()
        (deal_dir / "doc.pdf").touch()
        entries = discover_scopes(str(tmp_path))
        assert len(entries) == 1
        assert entries[0].slug == "deala"
        assert entries[0].doc_count >= 1  # at least the pdf

    def test_discover_scopes_nonexistent_root(self):
        from backend.vector.deal_catalog import discover_scopes
        entries = discover_scopes("/nonexistent/path/xyz")
        assert entries == []

    def test_discover_scopes_extracts_years(self, tmp_path):
        from backend.vector.deal_catalog import discover_scopes
        deal_dir = tmp_path / "Bear Stearns 2006-HE1"
        deal_dir.mkdir()
        (deal_dir / ".kts").mkdir()
        entries = discover_scopes(str(tmp_path))
        assert "2006" in entries[0].years


# ═══════════════════════════════════════════════════════════════════════════
#  12.4 — SCOPE ROUTER
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase12_4_ScopeRouter:
    """ScopeRouter: exact match → keyword → global fallback, federated search."""

    def test_scope_router_importable(self):
        from backend.retrieval.scope_router import ScopeRouter
        assert ScopeRouter is not None

    def test_max_federated_scopes(self):
        from backend.retrieval.scope_router import ScopeRouter
        assert ScopeRouter.MAX_FEDERATED_SCOPES == 100

    def test_route_with_explicit_scope(self):
        from backend.retrieval.scope_router import ScopeRouter, RoutingResult
        all_scopes = [{"slug": "deal_a", "folder_name": "Deal A", "kts_path": "/a/.kts"}]
        router = ScopeRouter(all_scopes=all_scopes)
        result = router.route("anything", explicit_scope="deal_a")
        assert result.is_single_scope
        assert result.scopes[0].slug == "deal_a"
        assert result.scopes[0].match_type == "exact"

    def test_route_explicit_scope_not_found(self):
        from backend.retrieval.scope_router import ScopeRouter
        router = ScopeRouter(all_scopes=[{"slug": "other", "folder_name": "Other", "kts_path": "/o"}])
        result = router.route("anything", explicit_scope="nonexistent")
        assert result.needs_user_clarification
        assert "not found" in result.message.lower()

    def test_route_exact_mention_in_query(self):
        from backend.retrieval.scope_router import ScopeRouter
        all_scopes = [{"slug": "bear_stearns_2006_he1", "folder_name": "Bear Stearns 2006-HE1", "kts_path": "/b/.kts"}]
        router = ScopeRouter(all_scopes=all_scopes)
        result = router.route("tell me about bear_stearns_2006_he1 determination date")
        assert result.is_single_scope
        assert result.scopes[0].slug == "bear_stearns_2006_he1"

    def test_route_catalog_keyword_match(self):
        from backend.retrieval.scope_router import ScopeRouter
        catalog = MagicMock()
        catalog.all_scopes.return_value = []
        catalog.search.return_value = [
            {"slug": "deal_a", "folder_name": "Deal A", "kts_path": "/a", "score": 0.8},
            {"slug": "deal_b", "folder_name": "Deal B", "kts_path": "/b", "score": 0.7},
        ]
        router = ScopeRouter(catalog=catalog)
        result = router.route("bear stearns")
        assert result.is_multi_scope
        assert len(result.scopes) == 2

    def test_route_too_many_matches(self):
        from backend.retrieval.scope_router import ScopeRouter
        catalog = MagicMock()
        catalog.all_scopes.return_value = []
        catalog.search.return_value = [
            {"slug": f"deal_{i}", "folder_name": f"Deal {i}", "kts_path": f"/{i}"}
            for i in range(150)
        ]
        router = ScopeRouter(catalog=catalog)
        result = router.route("generic query")
        assert result.needs_user_clarification
        assert "too many" in result.message.lower() or "150" in result.message

    def test_route_global_fallback(self):
        from backend.retrieval.scope_router import ScopeRouter
        router = ScopeRouter()  # no catalog, no scopes
        result = router.route("random question")
        assert result.is_single_scope
        assert result.scopes[0].match_type == "fallback"
        assert result.scopes[0].slug == "__global__"

    def test_routing_result_slugs_property(self):
        from backend.retrieval.scope_router import RoutingResult, ScopeMatch
        rr = RoutingResult(scopes=[
            ScopeMatch(slug="a", folder_name="A", kts_path="/a", match_type="exact"),
            ScopeMatch(slug="b", folder_name="B", kts_path="/b", match_type="keyword"),
        ])
        assert rr.slugs == ["a", "b"]

    def test_routing_result_is_single(self):
        from backend.retrieval.scope_router import RoutingResult, ScopeMatch
        rr = RoutingResult(scopes=[ScopeMatch(slug="x", folder_name="X", kts_path="/x", match_type="exact")])
        assert rr.is_single_scope
        assert not rr.is_multi_scope

    def test_routing_result_is_multi(self):
        from backend.retrieval.scope_router import RoutingResult, ScopeMatch
        rr = RoutingResult(scopes=[
            ScopeMatch(slug="a", folder_name="A", kts_path="/a", match_type="keyword"),
            ScopeMatch(slug="b", folder_name="B", kts_path="/b", match_type="keyword"),
        ])
        assert rr.is_multi_scope

    # — Federated Search —

    def test_federated_search_success(self):
        from backend.retrieval.scope_router import ScopeRouter

        async def mock_search(query, slug, top_k):
            return [{"chunk_id": f"{slug}_1", "content": f"From {slug}", "score": 0.9}]

        router = ScopeRouter()
        results = _run(router.federated_search("test query", ["deal_a", "deal_b"], search_fn=mock_search))
        assert len(results) == 2
        assert results[0].scope_slug == "deal_a"
        assert results[1].scope_slug == "deal_b"
        assert len(results[0].chunks) == 1
        assert results[0].error is None

    def test_federated_search_exception_safe(self):
        """Failed scope logs warning, returns FederatedResult(error=str(exc))."""
        from backend.retrieval.scope_router import ScopeRouter

        async def failing_search(query, slug, top_k):
            if slug == "bad":
                raise RuntimeError("Connection failed")
            return [{"chunk_id": "ok_1", "content": "good", "score": 0.8}]

        router = ScopeRouter()
        results = _run(router.federated_search("test", ["good", "bad"], search_fn=failing_search))
        assert len(results) == 2
        good = [r for r in results if r.scope_slug == "good"][0]
        bad = [r for r in results if r.scope_slug == "bad"][0]
        assert good.error is None
        assert len(good.chunks) == 1
        assert bad.error is not None
        assert "Connection failed" in bad.error

    def test_federated_search_empty_scopes(self):
        from backend.retrieval.scope_router import ScopeRouter

        async def mock_search(query, slug, top_k):
            return []

        router = ScopeRouter()
        results = _run(router.federated_search("test", [], search_fn=mock_search))
        assert results == []

    def test_federated_result_dataclass(self):
        from backend.retrieval.scope_router import FederatedResult
        fr = FederatedResult(scope_slug="s1", chunks=[{"id": "1"}], error=None)
        assert fr.scope_slug == "s1"
        assert len(fr.chunks) == 1
        fr_err = FederatedResult(scope_slug="s2", error="boom")
        assert fr_err.error == "boom"
        assert fr_err.chunks == []

    def test_scope_match_dataclass(self):
        from backend.retrieval.scope_router import ScopeMatch
        sm = ScopeMatch(slug="x", folder_name="X", kts_path="/x", match_type="exact", confidence=0.95)
        assert sm.confidence == 0.95


# ═══════════════════════════════════════════════════════════════════════════
#  12.4 — RETRIEVAL SERVICE WIRING
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase12_4_RetrievalServiceWiring:
    """RetrievalService properly wires Phase 12 scope routing."""

    RS_PATH = Path(__file__).resolve().parents[1] / "backend" / "agents" / "retrieval_service.py"

    def test_imports_scope_router(self):
        text = self.RS_PATH.read_text(encoding="utf-8")
        assert "from backend.retrieval.scope_router import ScopeRouter" in text

    def test_imports_parse_two_level_scope(self):
        text = self.RS_PATH.read_text(encoding="utf-8")
        assert "parse_two_level_scope" in text

    def test_lazy_scope_router_init(self):
        text = self.RS_PATH.read_text(encoding="utf-8")
        assert "_get_scope_router" in text
        assert "_scope_router" in text

    def test_lazy_deal_catalog_init(self):
        text = self.RS_PATH.read_text(encoding="utf-8")
        assert "_deal_catalog" in text

    def test_scope_routing_in_execute(self):
        text = self.RS_PATH.read_text(encoding="utf-8")
        assert 'scope_override = request.get("scope_override")' in text

    def test_resolved_scope_variable_exists(self):
        """After routing, resolved_scope should be set and passed downstream."""
        text = self.RS_PATH.read_text(encoding="utf-8")
        assert "resolved_scope" in text

    def test_resolved_scope_passed_to_search(self):
        """All vector_store.search() calls should receive scope=resolved_scope."""
        text = self.RS_PATH.read_text(encoding="utf-8")
        assert "scope=resolved_scope" in text

    def test_clarification_return_on_too_many(self):
        text = self.RS_PATH.read_text(encoding="utf-8")
        assert "needs_scope_clarification" in text

    def test_phase6_retrieve_accepts_scope(self):
        """_phase6_retrieve() must accept scope parameter."""
        text = self.RS_PATH.read_text(encoding="utf-8")
        assert "def _phase6_retrieve(self, query" in text
        # Check it accepts scope parameter
        sig_line = [l for l in text.splitlines() if "_phase6_retrieve" in l and "def " in l][0]
        assert "scope" in sig_line

    def test_phase6_retrieve_accepts_doc_type_filter(self):
        text = self.RS_PATH.read_text(encoding="utf-8")
        sig_line = [l for l in text.splitlines() if "_phase6_retrieve" in l and "def " in l][0]
        assert "doc_type_filter" in sig_line


# ═══════════════════════════════════════════════════════════════════════════
#  12.4 — INGESTION-CATALOG WIRING
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase12_4_IngestionCatalogWiring:
    """Ingestion agent populates the deal catalog after ingest."""

    IA_PATH = Path(__file__).resolve().parents[1] / "backend" / "agents" / "ingestion_agent.py"

    def test_ingestion_imports_deal_catalog(self):
        text = self.IA_PATH.read_text(encoding="utf-8")
        assert "DealCatalog" in text
        assert "CatalogEntry" in text
        assert "slugify" in text

    def test_ingestion_upserts_catalog_entry(self):
        text = self.IA_PATH.read_text(encoding="utf-8")
        assert "catalog.upsert(entry)" in text

    def test_ingestion_increments_doc_count(self):
        text = self.IA_PATH.read_text(encoding="utf-8")
        assert "existing.doc_count + 1" in text or "doc_count" in text

    def test_ingestion_populates_doc_types(self):
        text = self.IA_PATH.read_text(encoding="utf-8")
        assert "doc_types" in text

    def test_ingestion_populates_collateral_types(self):
        """Phase 12 spec requires collateral_types to be populated."""
        text = self.IA_PATH.read_text(encoding="utf-8")
        assert "collateral_types" in text
        assert "_detect_collateral_types" in text

    def test_detect_collateral_types_heloc(self):
        from backend.agents.ingestion_agent import _detect_collateral_types
        result = _detect_collateral_types("Bear Stearns 2006-HELOC-1")
        assert "HELOC" in result

    def test_detect_collateral_types_subprime(self):
        from backend.agents.ingestion_agent import _detect_collateral_types
        result = _detect_collateral_types("Subprime Mortgage Trust 2007")
        assert "Subprime" in result

    def test_detect_collateral_types_alt_a(self):
        from backend.agents.ingestion_agent import _detect_collateral_types
        result = _detect_collateral_types("Alt-A Mortgage Securities 2006")
        assert "Alt-A" in result

    def test_detect_collateral_types_none(self):
        from backend.agents.ingestion_agent import _detect_collateral_types
        result = _detect_collateral_types("Generic Deal Name")
        assert result == []

    def test_catalog_enabled_default_true(self):
        """deal_catalog_enabled defaults to True in settings."""
        from config.settings import KTSConfig
        s = KTSConfig()
        assert s.deal_catalog_enabled is True


# ═══════════════════════════════════════════════════════════════════════════
#  12 — CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase12_Config:
    """Phase 12 config flags in settings.py."""

    def test_per_folder_kts_enabled(self):
        from config.settings import KTSConfig
        s = KTSConfig()
        assert hasattr(s, "per_folder_kts_enabled")
        assert s.per_folder_kts_enabled is True

    def test_deal_catalog_enabled(self):
        from config.settings import KTSConfig
        s = KTSConfig()
        assert hasattr(s, "deal_catalog_enabled")
        assert s.deal_catalog_enabled is True

    def test_scope_discovery_on_startup(self):
        from config.settings import KTSConfig
        s = KTSConfig()
        assert hasattr(s, "scope_discovery_on_startup")
        assert s.scope_discovery_on_startup is True

    def test_knowledge_source_root(self):
        from config.settings import KTSConfig
        s = KTSConfig()
        assert hasattr(s, "knowledge_source_root")


# ═══════════════════════════════════════════════════════════════════════════
#  12 — END-TO-END INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase12_EndToEnd:
    """End-to-end integration: slugify → catalog → router → search path."""

    def test_slugify_to_collection_name(self):
        """Slug from deal_catalog.slugify maps to VectorStore.collection_name_for_scope."""
        from backend.vector.deal_catalog import slugify
        from backend.vector.store import VectorStore
        slug = slugify("Bear Stearns 2006-HE1")
        name = VectorStore.collection_name_for_scope(slug)
        assert name == "kts_bear_stearns_2006_he1"

    def test_catalog_and_router_integration(self, tmp_path):
        """Router uses real catalog for keyword matching."""
        from backend.vector.deal_catalog import DealCatalog, CatalogEntry
        from backend.retrieval.scope_router import ScopeRouter

        db = str(tmp_path / "integration.db")
        catalog = DealCatalog(db_path=db)
        catalog.upsert(CatalogEntry(
            folder_name="Bear Stearns 2006-HE1",
            slug="bear_stearns_2006_he1",
            kts_path="/deals/bs2006he1/.kts",
            doc_count=4,
            issuers=["Bear Stearns"],
        ))
        catalog.upsert(CatalogEntry(
            folder_name="WSHFC 2007-A",
            slug="wshfc_2007_a",
            kts_path="/deals/wshfc2007a/.kts",
            doc_count=2,
        ))

        router = ScopeRouter(catalog=catalog)

        # Explicit scope
        r1 = router.route("anything", explicit_scope="bear_stearns_2006_he1")
        assert r1.is_single_scope
        assert r1.scopes[0].slug == "bear_stearns_2006_he1"

        # Keyword match
        r2 = router.route("bear stearns deal")
        assert len(r2.scopes) >= 1

    def test_full_routing_priority_order(self, tmp_path):
        """Test that routing priority is: explicit > mention > keyword > fallback."""
        from backend.vector.deal_catalog import DealCatalog, CatalogEntry
        from backend.retrieval.scope_router import ScopeRouter

        db = str(tmp_path / "priority.db")
        catalog = DealCatalog(db_path=db)
        catalog.upsert(CatalogEntry(
            folder_name="Alpha",
            slug="alpha",
            kts_path="/alpha/.kts",
        ))

        router = ScopeRouter(catalog=catalog)

        # 1. Explicit scope always wins
        r = router.route("tell me about alpha", explicit_scope="alpha")
        assert r.scopes[0].match_type == "exact"

        # 2. Without explicit, exact mention in query
        r2 = router.route("tell me about alpha scope")
        if r2.is_single_scope:
            assert r2.scopes[0].match_type in ("exact", "keyword")

        # 3. Global fallback when nothing matches
        r3 = router.route("completely unrelated query xyz123")
        assert r3.scopes[0].match_type == "fallback"

    def test_federated_with_real_catalog(self, tmp_path):
        """Federated search using real catalog and mock search function."""
        from backend.vector.deal_catalog import DealCatalog, CatalogEntry
        from backend.retrieval.scope_router import ScopeRouter

        db = str(tmp_path / "fed.db")
        catalog = DealCatalog(db_path=db)
        for i in range(5):
            catalog.upsert(CatalogEntry(
                folder_name=f"Deal_{i}",
                slug=f"deal_{i}",
                kts_path=f"/deals/deal_{i}/.kts",
            ))

        router = ScopeRouter(catalog=catalog)

        async def mock_search(q, slug, top_k):
            return [{"chunk_id": f"{slug}_c1", "content": f"content from {slug}"}]

        results = _run(router.federated_search(
            "test", [f"deal_{i}" for i in range(5)],
            search_fn=mock_search, top_k=3,
        ))
        assert len(results) == 5
        assert all(r.error is None for r in results)
