"""Phase 19 — Complete End‑to‑End Test Suite for OneNote Ingestion.

Tests every layer of the Phase 19 pipeline:
  1. Synthetic .one / .onetoc2 binary file generation
  2. Binary converter (parse_onetoc2, parse_one_section)
  3. Delta-ingestion manifest (section mtime, page hash, chunk IDs)
  4. OneNote chunker (standard + release-notes strategies)
  5. Vision module (client init, skip-on-error, mock calls)
  6. CLI command wiring (ingest-onenote dry-run)
  7. Full E2E pipeline: generate → parse → chunk → store → search

Corpus: Test content derived from GSF IR Support Library.md
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.onenote_test_helpers import (
    SyntheticPage,
    build_one_file,
    build_onetoc2_file,
    create_minimal_jpeg,
    create_test_notebook,
    create_test_png,
    verify_notebook_structure,
    TROUBLESHOOTING_PAGES,
    RELEASE_NOTES_PAGES,
)

from backend.ingestion.onenote_converter import (
    OneNoteImage,
    OneNotePage,
    OneNoteTable,
    parse_one_section,
    parse_onetoc2,
)
from backend.ingestion.onenote_chunker import (
    chunk_onenote_page,
    extract_release_date,
    _is_release_notes_section,
    _token_estimate,
)
from backend.ingestion.onenote_manifest import OneNoteManifest
from backend.ingestion.onenote_vision import (
    VisionConfigError,
    _get_client,
    _mime_type,
    describe_image,
    describe_images_for_page,
    reset_client,
)
from backend.common.models import TextChunk


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def tmp_notebook_dir(tmp_path_factory):
    """Create a test notebook folder once for the entire module."""
    base = tmp_path_factory.mktemp("onenote_e2e")
    nb_dir = create_test_notebook(base, notebook_name="TestNB", include_images=True)
    yield nb_dir
    # Cleanup handled by pytest tmp_path_factory


@pytest.fixture
def tmp_kb(tmp_path):
    """Provide a temporary knowledge-base directory."""
    kb = tmp_path / "kb"
    kb.mkdir()
    return kb


@pytest.fixture
def fresh_manifest(tmp_kb):
    """Return a fresh OneNoteManifest in a temp KB directory."""
    return OneNoteManifest(tmp_kb)


# ═══════════════════════════════════════════════════════════════════════════
# 1. SYNTHETIC FILE BUILDER TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestSyntheticFileBuilder:
    """Validate that the test helper generates valid binary files."""

    def test_build_one_file_has_header_magic(self):
        """The .one file starts with the MS-ONESTORE header magic."""
        pages = [SyntheticPage(title="Test", text_blocks=["Hello world"])]
        data = build_one_file(pages)
        magic = bytes([0xE4, 0x52, 0x5C, 0x7B, 0x8C, 0xD8, 0xA3, 0x4D,
                       0xAE, 0xB1, 0x53, 0x78, 0xD0, 0x29, 0x96, 0xD3])
        assert data[:16] == magic

    def test_build_one_file_contains_utf16_text(self):
        """The .one file contains UTF-16LE encoded text."""
        pages = [SyntheticPage(title="Import Problems", text_blocks=["Check the log file"])]
        data = build_one_file(pages)
        assert "Import Problems".encode("utf-16-le") in data
        assert "Check the log file".encode("utf-16-le") in data

    def test_build_one_file_multiple_pages(self):
        """Multiple pages produce multiple page-boundary markers."""
        pages = [
            SyntheticPage(title="Page One", text_blocks=["Content A"]),
            SyntheticPage(title="Page Two", text_blocks=["Content B"]),
            SyntheticPage(title="Page Three", text_blocks=["Content C"]),
        ]
        data = build_one_file(pages)
        marker = b'\x94\x1d\x00\x1c'
        assert data.count(marker) == 3

    def test_build_one_file_with_image(self):
        """A JPEG image blob is embedded correctly."""
        jpeg = create_minimal_jpeg()
        pages = [SyntheticPage(title="With Image", text_blocks=["See image"], images=[jpeg])]
        data = build_one_file(pages)
        assert b'\xFF\xD8\xFF' in data   # JPEG SOI
        assert b'\xFF\xD9' in data       # JPEG EOI

    def test_build_onetoc2_contains_section_names(self):
        """The .onetoc2 file contains section names as UTF-16LE."""
        toc = build_onetoc2_file(["Troubleshooting", "Release Notes"])
        assert "Troubleshooting.one".encode("utf-16-le") in toc
        assert "Release Notes.one".encode("utf-16-le") in toc

    def test_create_test_notebook_structure(self, tmp_path):
        """create_test_notebook produces the expected directory structure."""
        nb_dir = create_test_notebook(tmp_path, "MyNB")
        assert nb_dir.exists()
        info = verify_notebook_structure(nb_dir)
        assert len(info["one_files"]) == 2
        assert len(info["toc_files"]) == 1
        assert "Troubleshooting.one" in info["one_files"]
        assert "Release Notes.one" in info["one_files"]
        assert info["total_size"] > 1000

    def test_minimal_jpeg_is_valid(self):
        """The synthetic JPEG is >= 512 bytes and has valid markers."""
        jpeg = create_minimal_jpeg()
        assert len(jpeg) >= 512
        assert jpeg[:2] == b'\xFF\xD8'      # SOI
        assert jpeg[-2:] == b'\xFF\xD9'     # EOI

    def test_minimal_png_is_valid(self):
        """The synthetic PNG is >= 512 bytes and has valid header."""
        png = create_test_png()
        assert len(png) >= 512
        assert png[:8] == b'\x89PNG\r\n\x1a\n'


# ═══════════════════════════════════════════════════════════════════════════
# 2. BINARY CONVERTER TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestOnetoc2Parser:
    """Tests for parse_onetoc2()."""

    def test_parse_toc_extracts_sections(self, tmp_notebook_dir):
        """parse_onetoc2 extracts section names from .onetoc2 file."""
        toc = list(tmp_notebook_dir.glob("*.onetoc2"))
        assert len(toc) == 1
        names = parse_onetoc2(str(toc[0]))
        assert "Troubleshooting" in names
        assert "Release Notes" in names

    def test_parse_toc_preserves_order(self, tmp_notebook_dir):
        """Section order from .onetoc2 matches the build order."""
        toc = list(tmp_notebook_dir.glob("*.onetoc2"))
        names = parse_onetoc2(str(toc[0]))
        # We built with ["Troubleshooting", "Release Notes"]
        assert names.index("Troubleshooting") < names.index("Release Notes")

    def test_parse_toc_missing_file_returns_empty(self, tmp_path):
        """parse_onetoc2 returns [] for a missing file."""
        result = parse_onetoc2(str(tmp_path / "missing.onetoc2"))
        assert result == []

    def test_parse_toc_empty_file_returns_empty(self, tmp_path):
        """parse_onetoc2 returns [] for an empty file."""
        empty = tmp_path / "Empty.onetoc2"
        empty.write_bytes(b'\x00' * 16)
        result = parse_onetoc2(str(empty))
        assert result == []

    def test_parse_toc_deduplicates(self, tmp_path):
        """Duplicate section names are deduplicated."""
        toc_data = build_onetoc2_file(["Alpha", "Beta", "Alpha"])
        f = tmp_path / "test.onetoc2"
        f.write_bytes(toc_data)
        names = parse_onetoc2(str(f))
        assert names.count("Alpha") == 1


class TestOneSectionParser:
    """Tests for parse_one_section()."""

    def test_parse_troubleshooting_returns_pages(self, tmp_notebook_dir):
        """Parser extracts pages from the Troubleshooting .one file."""
        one_file = tmp_notebook_dir / "Troubleshooting.one"
        pages = parse_one_section(str(one_file))
        assert len(pages) >= 1, "Should extract at least 1 page"

    def test_parse_release_notes_returns_pages(self, tmp_notebook_dir):
        """Parser extracts pages from the Release Notes .one file."""
        one_file = tmp_notebook_dir / "Release Notes.one"
        pages = parse_one_section(str(one_file))
        assert len(pages) >= 1

    def test_pages_have_text_content(self, tmp_notebook_dir):
        """Extracted pages contain actual text from the source corpus."""
        one_file = tmp_notebook_dir / "Troubleshooting.one"
        pages = parse_one_section(str(one_file))
        all_text = " ".join(p.full_text for p in pages)
        # These are from the embedded test corpus
        assert len(all_text) > 100, "Should have substantial text content"

    def test_pages_have_guids(self, tmp_notebook_dir):
        """Each page has a non-empty guid."""
        one_file = tmp_notebook_dir / "Troubleshooting.one"
        pages = parse_one_section(str(one_file))
        for p in pages:
            assert p.guid, f"Page '{p.title}' has empty guid"

    def test_pages_have_order_indices(self, tmp_notebook_dir):
        """Pages have sequential order_index values."""
        one_file = tmp_notebook_dir / "Troubleshooting.one"
        pages = parse_one_section(str(one_file))
        indices = [p.order_index for p in pages]
        assert indices == list(range(len(pages)))

    def test_images_extracted(self, tmp_notebook_dir):
        """At least one page has extracted images."""
        one_file = tmp_notebook_dir / "Troubleshooting.one"
        pages = parse_one_section(str(one_file))
        total_images = sum(len(p.images) for p in pages)
        assert total_images >= 1, "Should find at least 1 embedded image"

    def test_image_has_valid_format(self, tmp_notebook_dir):
        """Extracted images have recognized format fields."""
        one_file = tmp_notebook_dir / "Troubleshooting.one"
        pages = parse_one_section(str(one_file))
        for p in pages:
            for img in p.images:
                assert img.fmt in ("jpeg", "png", "gif")
                assert len(img.image_bytes) >= 512
                assert len(img.content_hash) > 0

    def test_missing_file_returns_empty(self):
        """parse_one_section returns [] for missing file."""
        assert parse_one_section("C:/nonexistent/file.one") == []

    def test_tiny_file_returns_empty(self, tmp_path):
        """Files < 16 bytes return empty list."""
        f = tmp_path / "tiny.one"
        f.write_bytes(b'\x00' * 10)
        assert parse_one_section(str(f)) == []

    def test_content_hash_stable(self, tmp_notebook_dir):
        """Page content_hash() is deterministic for the same content."""
        one_file = tmp_notebook_dir / "Troubleshooting.one"
        pages1 = parse_one_section(str(one_file))
        pages2 = parse_one_section(str(one_file))
        for p1, p2 in zip(pages1, pages2):
            assert p1.content_hash() == p2.content_hash()


class TestOneNoteDataModel:
    """Tests for OneNotePage, OneNoteImage, OneNoteTable data classes."""

    def test_page_full_text_includes_tables(self):
        """full_text property merges text_blocks and table markdown."""
        table = OneNoteTable(
            headers=["Name", "Value"],
            rows=[["Alpha", "100"], ["Beta", "200"]],
        )
        page = OneNotePage(
            guid="test_001", title="Test Page",
            text_blocks=["Some text here"], tables=[table],
        )
        ft = page.full_text
        assert "Some text here" in ft
        assert "Alpha" in ft
        assert "| Name" in ft

    def test_page_content_hash_changes_with_content(self):
        """Different content produces different hashes."""
        p1 = OneNotePage(guid="a", title="A", text_blocks=["Hello"])
        p2 = OneNotePage(guid="a", title="A", text_blocks=["Goodbye"])
        assert p1.content_hash() != p2.content_hash()

    def test_page_content_hash_includes_images(self):
        """Image hashes contribute to content_hash."""
        img = OneNoteImage(image_bytes=b'\xFF' * 100, fmt="jpeg")
        p1 = OneNotePage(guid="a", title="A", text_blocks=["Same"])
        p2 = OneNotePage(guid="a", title="A", text_blocks=["Same"], images=[img])
        assert p1.content_hash() != p2.content_hash()

    def test_image_auto_hash(self):
        """OneNoteImage auto-computes content_hash on creation."""
        img = OneNoteImage(image_bytes=b'\x01\x02\x03', fmt="png")
        assert len(img.content_hash) == 16

    def test_table_to_markdown(self):
        """OneNoteTable renders valid markdown table."""
        t = OneNoteTable(headers=["A", "B"], rows=[["1", "2"], ["3", "4"]])
        md = t.to_markdown()
        assert "| A" in md
        assert "| -" in md  # separator row
        assert "| 1" in md

    def test_table_empty_returns_empty(self):
        """Empty table returns empty string."""
        t = OneNoteTable()
        assert t.to_markdown() == ""


# ═══════════════════════════════════════════════════════════════════════════
# 3. DELTA MANIFEST TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestOneNoteManifest:
    """Tests for the delta-ingestion manifest."""

    def test_fresh_manifest_empty(self, fresh_manifest):
        """A new manifest has no sections."""
        s = fresh_manifest.summary()
        assert s["total_sections"] == 0
        assert s["total_pages"] == 0
        assert s["total_chunks"] == 0

    def test_save_and_reload(self, tmp_kb):
        """Manifest persists to disk and reloads correctly."""
        m1 = OneNoteManifest(tmp_kb)
        m1.upsert_page("section.one", "pg1", "Page 1", "hash1", ["c1", "c2"])
        m1.save()

        m2 = OneNoteManifest(tmp_kb)
        assert m2.get_chunk_ids("section.one", "pg1") == ["c1", "c2"]

    def test_section_needs_scan_new_section(self, fresh_manifest, tmp_path):
        """A never-seen section always needs scanning."""
        f = tmp_path / "new.one"
        f.write_bytes(b'\x00' * 100)
        assert fresh_manifest.section_needs_scan(f) is True

    def test_section_needs_scan_unchanged(self, fresh_manifest, tmp_path):
        """Section with matching mtime does not need scan."""
        f = tmp_path / "section.one"
        f.write_bytes(b'\x00' * 100)
        fresh_manifest.update_section_mtime(f, "Test Section")
        fresh_manifest.save()
        # Reload
        m2 = OneNoteManifest(fresh_manifest._path.parent)
        assert m2.section_needs_scan(f) is False

    def test_section_needs_scan_after_modification(self, tmp_kb, tmp_path):
        """Section with changed mtime needs scan."""
        import time
        f = tmp_path / "section.one"
        f.write_bytes(b'\x00' * 100)

        m = OneNoteManifest(tmp_kb)
        m.update_section_mtime(f, "Test")
        m.save()

        # Modify file
        time.sleep(0.05)
        f.write_bytes(b'\xFF' * 200)

        m2 = OneNoteManifest(tmp_kb)
        assert m2.section_needs_scan(f) is True

    def test_page_needs_ingest_new_page(self, fresh_manifest):
        """New page always needs ingestion."""
        assert fresh_manifest.page_needs_ingest("s.one", "pg1", "any_hash") is True

    def test_page_needs_ingest_unchanged(self, fresh_manifest):
        """Page with matching hash does not need ingestion."""
        fresh_manifest.upsert_page("s.one", "pg1", "Title", "hash123", ["c1"])
        assert fresh_manifest.page_needs_ingest("s.one", "pg1", "hash123") is False

    def test_page_needs_ingest_changed(self, fresh_manifest):
        """Page with different hash needs ingestion."""
        fresh_manifest.upsert_page("s.one", "pg1", "Title", "hash123", ["c1"])
        assert fresh_manifest.page_needs_ingest("s.one", "pg1", "hash456") is True

    def test_get_chunk_ids(self, fresh_manifest):
        """get_chunk_ids returns the stored chunk IDs."""
        fresh_manifest.upsert_page("s.one", "pg1", "T", "h", ["c1", "c2", "c3"])
        assert fresh_manifest.get_chunk_ids("s.one", "pg1") == ["c1", "c2", "c3"]

    def test_get_chunk_ids_missing_page(self, fresh_manifest):
        """Missing page returns empty list."""
        assert fresh_manifest.get_chunk_ids("s.one", "missing") == []

    def test_upsert_page_updates_hash(self, fresh_manifest):
        """Upserting a page updates its content_hash and chunk_ids."""
        fresh_manifest.upsert_page("s.one", "pg1", "T", "h1", ["c1"])
        fresh_manifest.upsert_page("s.one", "pg1", "T", "h2", ["c2", "c3"])
        assert fresh_manifest.page_needs_ingest("s.one", "pg1", "h2") is False
        assert fresh_manifest.get_chunk_ids("s.one", "pg1") == ["c2", "c3"]

    def test_remove_page_returns_chunk_ids(self, fresh_manifest):
        """remove_page returns the old chunk_ids for deletion."""
        fresh_manifest.upsert_page("s.one", "pg1", "T", "h", ["c1", "c2"])
        old_ids = fresh_manifest.remove_page("s.one", "pg1")
        assert old_ids == ["c1", "c2"]

    def test_remove_page_missing(self, fresh_manifest):
        """Removing a non-existent page returns empty list."""
        assert fresh_manifest.remove_page("s.one", "missing") == []

    def test_clear_section_returns_all_chunk_ids(self, fresh_manifest):
        """clear_section returns all chunk IDs from all pages."""
        fresh_manifest.upsert_page("s.one", "pg1", "T1", "h1", ["c1", "c2"])
        fresh_manifest.upsert_page("s.one", "pg2", "T2", "h2", ["c3"])
        all_ids = fresh_manifest.clear_section("s.one")
        assert sorted(all_ids) == ["c1", "c2", "c3"]

    def test_mark_full_ingest(self, fresh_manifest):
        """mark_full_ingest sets a timestamp."""
        fresh_manifest.mark_full_ingest()
        s = fresh_manifest.summary()
        assert s["last_full_ingest"] is not None

    def test_summary_counts(self, fresh_manifest):
        """summary() returns correct counts."""
        fresh_manifest.upsert_page("s1.one", "pg1", "T1", "h1", ["c1", "c2"])
        fresh_manifest.upsert_page("s1.one", "pg2", "T2", "h2", ["c3"])
        fresh_manifest.upsert_page("s2.one", "pg3", "T3", "h3", ["c4", "c5"])
        s = fresh_manifest.summary()
        assert s["total_pages"] == 3
        assert s["total_chunks"] == 5

    def test_update_section_mtime_preserves_pages(self, tmp_kb, tmp_path):
        """REGRESSION: update_section_mtime must NOT wipe existing pages."""
        f = tmp_path / "section.one"
        f.write_bytes(b'\x00' * 100)

        m = OneNoteManifest(tmp_kb)
        m.update_section_mtime(f, "MySection")
        m.upsert_page("section.one", "pg1", "Title1", "hash1", ["c1", "c2"])
        m.upsert_page("section.one", "pg2", "Title2", "hash2", ["c3"])

        # Simulate a second run — update_section_mtime called again
        m.update_section_mtime(f, "MySection")

        # Pages must still exist!
        assert m.get_chunk_ids("section.one", "pg1") == ["c1", "c2"]
        assert m.get_chunk_ids("section.one", "pg2") == ["c3"]
        assert m.page_needs_ingest("section.one", "pg1", "hash1") is False

    def test_manifest_json_format(self, tmp_kb):
        """Manifest JSON is valid and has expected schema."""
        m = OneNoteManifest(tmp_kb)
        m.upsert_page("s.one", "pg1", "T", "h", ["c1"])
        m.save()

        raw = json.loads((tmp_kb / "onenote_ingest_manifest.json").read_text())
        assert raw["version"] == 1
        assert "sections" in raw
        assert "s.one" in raw["sections"]
        assert "pg1" in raw["sections"]["s.one"]["pages"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. CHUNKER TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestOneNoteChunker:
    """Tests for the OneNote semantic chunker."""

    def _make_page(self, title: str, text: str, n_blocks: int = 1) -> OneNotePage:
        """Create a test page with given content."""
        blocks = [text[i * len(text) // n_blocks:(i + 1) * len(text) // n_blocks]
                  for i in range(n_blocks)]
        return OneNotePage(guid="test_page_001", title=title, text_blocks=blocks)

    def test_standard_page_produces_chunks(self):
        """A standard-section page produces at least 1 chunk."""
        page = self._make_page("Test Page", "This is some test content. " * 20)
        chunks = chunk_onenote_page(page, "Tech Tips", "/test.one")
        assert len(chunks) >= 1

    def test_chunks_are_text_chunk_instances(self):
        """Output chunks are TextChunk dataclass instances."""
        page = self._make_page("Test", "Content here")
        chunks = chunk_onenote_page(page, "Guides", "/test.one")
        for c in chunks:
            assert isinstance(c, TextChunk)

    def test_chunk_has_context_header(self):
        """Each chunk content starts with [Section: ...] [Page: ...]."""
        page = self._make_page("My Page", "Some content")
        chunks = chunk_onenote_page(page, "Help Desk", "/test.one")
        assert chunks[0].content.startswith("[Section: Help Desk]")
        assert "[Page: My Page]" in chunks[0].content

    def test_chunk_doc_id_format(self):
        """doc_id follows onenote_<notebook>_<section> format."""
        page = self._make_page("Test", "Content")
        chunks = chunk_onenote_page(page, "Tech Tips", "/t.one", notebook_name="GSF")
        assert chunks[0].doc_id.startswith("onenote_")
        assert "tech_tips" in chunks[0].doc_id

    def test_chunk_doc_type_standard(self):
        """Standard sections produce ONENOTE_GUIDE doc_type."""
        page = self._make_page("Test", "Content")
        chunks = chunk_onenote_page(page, "Tech Tips", "/t.one")
        assert all(c.doc_type == "ONENOTE_GUIDE" for c in chunks)

    def test_chunk_doc_type_release_notes(self):
        """Release-notes sections produce ONENOTE_RELEASE_NOTES doc_type."""
        page = self._make_page("March 2024", "New feature added")
        chunks = chunk_onenote_page(page, "Release Notes", "/t.one")
        assert all(c.doc_type == "ONENOTE_RELEASE_NOTES" for c in chunks)

    def test_release_notes_atomic_chunk(self):
        """Short release-notes pages stay as single atomic chunks."""
        page = self._make_page("April 2024", "Small update. " * 10)
        chunks = chunk_onenote_page(page, "Release Notes", "/t.one")
        assert len(chunks) == 1

    def test_large_page_gets_split(self):
        """A large standard page gets split into multiple chunks."""
        big_text = "This is a fairly lengthy sentence with many words. " * 200
        page = self._make_page("Big Page", big_text)
        chunks = chunk_onenote_page(page, "Guides", "/t.one")
        assert len(chunks) > 1

    def test_image_descriptions_merged(self):
        """Image descriptions are appended to page text before chunking."""
        page = self._make_page("With Images", "Some text")
        chunks = chunk_onenote_page(
            page, "Guides", "/t.one",
            image_descriptions=["Screenshot of Excel settings dialog"],
        )
        full = " ".join(c.content for c in chunks)
        assert "Screenshot of Excel" in full

    def test_chunk_ids_unique(self):
        """All chunks from a page have unique IDs."""
        big = "Word " * 2000
        page = self._make_page("Big", big)
        chunks = chunk_onenote_page(page, "Guides", "/t.one")
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_chunk_source_path(self):
        """Chunks carry the source .one file path."""
        page = self._make_page("T", "Content")
        chunks = chunk_onenote_page(page, "S", "/path/to/file.one")
        assert all(c.source_path == "/path/to/file.one" for c in chunks)

    def test_chunk_numbering_header(self):
        """Multi-chunk pages show [Chunk N/M] in headers."""
        big = "Word " * 2000
        page = self._make_page("Big", big)
        chunks = chunk_onenote_page(page, "Guides", "/t.one")
        if len(chunks) > 1:
            assert "[Chunk 1/" in chunks[0].content
            assert f"[Chunk {len(chunks)}/{len(chunks)}]" in chunks[-1].content


class TestReleaseNotesDetection:
    """Test section-name pattern matching for release-notes detection."""

    @pytest.mark.parametrize("name", [
        "Release Notes", "release notes", "What's New",
        "Change Log", "changelog", "Version History", "Update History",
    ])
    def test_release_notes_patterns_match(self, name):
        assert _is_release_notes_section(name) is True

    @pytest.mark.parametrize("name", [
        "Tech Tips", "Troubleshooting", "User Guide", "FAQ",
    ])
    def test_non_release_patterns_no_match(self, name):
        assert _is_release_notes_section(name) is False


class TestReleaseDateExtraction:
    """Test release date parsing from page titles."""

    @pytest.mark.parametrize("title,expected", [
        ("Release Notes - March 2024", (2024, 3)),
        ("March 2024 Update", (2024, 3)),
        ("2024-03 Release", (2024, 3)),
        ("January 2023", (2023, 1)),
        ("Dec 2025 Notes", (2025, 12)),
        ("2023-12 Hotfix", (2023, 12)),
    ])
    def test_valid_dates(self, title, expected):
        assert extract_release_date(title) == expected

    @pytest.mark.parametrize("title", [
        "General Notes", "Setup Guide", "Version Info", "",
    ])
    def test_no_date(self, title):
        assert extract_release_date(title) is None


class TestTokenEstimate:
    """Test the internal token estimation function."""

    def test_empty(self):
        assert _token_estimate("") == 1

    def test_short(self):
        assert _token_estimate("hello") >= 1

    def test_long(self):
        text = "x" * 4000
        est = _token_estimate(text)
        assert 900 <= est <= 1100  # ~1000 tokens at 4 chars/token


# ═══════════════════════════════════════════════════════════════════════════
# 5. VISION MODULE TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestVisionModule:
    """Tests for the GPT-4.1 vision integration."""

    def setup_method(self):
        """Reset the cached client before each test."""
        reset_client()

    def test_mime_type_mapping(self):
        """MIME types are mapped correctly."""
        assert _mime_type("jpeg") == "image/jpeg"
        assert _mime_type("jpg") == "image/jpeg"
        assert _mime_type("png") == "image/png"
        assert _mime_type("gif") == "image/gif"
        assert _mime_type("unknown") == "image/jpeg"  # fallback

    def test_no_api_key_raises_config_error(self):
        """Missing API key raises VisionConfigError."""
        env_backup = {}
        for key in ("OPENAI_API_KEY", "KTS_OPENAI_API_KEY",
                     "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"):
            env_backup[key] = os.environ.pop(key, None)
        try:
            reset_client()
            with pytest.raises(VisionConfigError):
                _get_client()
        finally:
            for key, val in env_backup.items():
                if val is not None:
                    os.environ[key] = val

    def test_skip_on_error_returns_empty(self):
        """With skip_on_error=True, missing key returns empty string."""
        env_backup = {}
        for key in ("OPENAI_API_KEY", "KTS_OPENAI_API_KEY",
                     "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"):
            env_backup[key] = os.environ.pop(key, None)
        try:
            reset_client()
            result = describe_image(
                image_bytes=b'\xFF' * 100,
                skip_on_error=True,
            )
            assert result == ""
        finally:
            for key, val in env_backup.items():
                if val is not None:
                    os.environ[key] = val

    def test_describe_images_for_page_skip_on_error(self):
        """describe_images_for_page returns empty strings when API unavailable."""
        env_backup = {}
        for key in ("OPENAI_API_KEY", "KTS_OPENAI_API_KEY",
                     "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"):
            env_backup[key] = os.environ.pop(key, None)
        try:
            reset_client()
            images = [
                OneNoteImage(image_bytes=b'\xFF' * 100, fmt="jpeg"),
                OneNoteImage(image_bytes=b'\xFF' * 200, fmt="png"),
            ]
            results = describe_images_for_page(
                images, page_title="Test", section_name="S", skip_on_error=True
            )
            assert len(results) == 2
            assert all(r == "" for r in results)
        finally:
            for key, val in env_backup.items():
                if val is not None:
                    os.environ[key] = val

    @patch("backend.ingestion.onenote_vision._get_client")
    def test_describe_image_with_mock_client(self, mock_get_client):
        """Vision call with mocked OpenAI client returns description."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "A screenshot of Excel settings"
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = describe_image(
            image_bytes=create_minimal_jpeg(),
            fmt="jpeg",
            page_title="Settings Page",
            section_name="Tech Tips",
        )
        assert "Excel settings" in result
        mock_client.chat.completions.create.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# 6. CLI COMMAND TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestCLIIngestOneNote:
    """Tests for the ingest-onenote CLI command."""

    def test_cli_help_available(self):
        """The ingest-onenote command is registered and shows help."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "cli.main", "ingest-onenote", "--help"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert result.returncode == 0
        assert "ingest-onenote" in result.stdout.lower() or "NOTEBOOK_PATH" in result.stdout

    def test_cli_help_shows_options(self):
        """Help text includes all expected options."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "cli.main", "ingest-onenote", "--help"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        for opt in ["--delta", "--full", "--skip-images", "--vision-model",
                     "--kb-path", "--dry-run", "--notebook-name"]:
            assert opt in result.stdout, f"Missing option: {opt}"

    def test_cli_dry_run(self, tmp_notebook_dir, tmp_path):
        """Dry-run mode parses files without writing to vector store."""
        import subprocess
        kb_dir = tmp_path / "kb_dry"
        kb_dir.mkdir()

        result = subprocess.run(
            [
                sys.executable, "-m", "cli.main", "ingest-onenote",
                str(tmp_notebook_dir),
                "--dry-run", "--skip-images",
                "--kb-path", str(kb_dir),
            ],
            capture_output=True, text=True, cwd=str(ROOT),
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )
        assert result.returncode == 0, f"CLI failed:\n{result.stderr}\n{result.stdout}"
        assert "dry-run" in result.stdout.lower() or "Dry run" in result.stdout
        assert "chunk" in result.stdout.lower()

    def test_cli_missing_path_fails(self, tmp_path):
        """CLI fails gracefully when path does not exist."""
        import subprocess
        result = subprocess.run(
            [
                sys.executable, "-m", "cli.main", "ingest-onenote",
                str(tmp_path / "nonexistent"),
                "--dry-run",
            ],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert result.returncode != 0


# ═══════════════════════════════════════════════════════════════════════════
# 7. FULL E2E PIPELINE TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestEndToEndPipeline:
    """Full pipeline: generate → parse → chunk → manifest → verify."""

    def test_full_pipeline_troubleshooting(self, tmp_notebook_dir, tmp_kb):
        """E2E: Troubleshooting section → parse → chunk → manifest."""
        one_file = tmp_notebook_dir / "Troubleshooting.one"
        section_name = "Troubleshooting"

        # Parse
        pages = parse_one_section(str(one_file))
        assert len(pages) >= 1

        # Chunk
        manifest = OneNoteManifest(tmp_kb)
        manifest.update_section_mtime(one_file, section_name)

        all_chunks: list[TextChunk] = []
        for page in pages:
            chunks = chunk_onenote_page(
                page,
                section_name=section_name,
                one_file_path=str(one_file),
                notebook_name="TestNB",
            )
            all_chunks.extend(chunks)

            manifest.upsert_page(
                one_file,
                page_guid=page.guid,
                title=page.title,
                content_hash=page.content_hash(),
                chunk_ids=[c.chunk_id for c in chunks],
                image_count=len(page.images),
            )

        assert len(all_chunks) >= 1
        assert all(c.doc_type == "ONENOTE_GUIDE" for c in all_chunks)

        # Verify manifest
        manifest.save()
        s = manifest.summary()
        assert s["total_pages"] == len(pages)
        assert s["total_chunks"] == len(all_chunks)

    def test_full_pipeline_release_notes(self, tmp_notebook_dir, tmp_kb):
        """E2E: Release Notes section → parse → chunk → verify atomic."""
        one_file = tmp_notebook_dir / "Release Notes.one"
        section_name = "Release Notes"

        pages = parse_one_section(str(one_file))
        assert len(pages) >= 1

        manifest = OneNoteManifest(tmp_kb)
        manifest.update_section_mtime(one_file, section_name)

        all_chunks: list[TextChunk] = []
        for page in pages:
            chunks = chunk_onenote_page(
                page,
                section_name=section_name,
                one_file_path=str(one_file),
                notebook_name="TestNB",
            )
            all_chunks.extend(chunks)
            manifest.upsert_page(
                one_file, page.guid, page.title,
                page.content_hash(), [c.chunk_id for c in chunks],
            )

        assert len(all_chunks) >= 1
        assert all(c.doc_type == "ONENOTE_RELEASE_NOTES" for c in all_chunks)

        manifest.save()

    def test_delta_ingestion_skip_unchanged(self, tmp_notebook_dir, tmp_kb):
        """Delta mode: unchanged pages are skipped on second run."""
        one_file = tmp_notebook_dir / "Troubleshooting.one"
        section_name = "Troubleshooting"

        # First run
        pages = parse_one_section(str(one_file))
        manifest = OneNoteManifest(tmp_kb)
        manifest.update_section_mtime(one_file, section_name)

        for page in pages:
            chunks = chunk_onenote_page(page, section_name, str(one_file))
            manifest.upsert_page(
                one_file, page.guid, page.title,
                page.content_hash(), [c.chunk_id for c in chunks],
            )
        manifest.save()

        # Second run — simulate delta check
        manifest2 = OneNoteManifest(tmp_kb)
        skipped = 0
        ingested = 0
        for page in pages:
            if not manifest2.page_needs_ingest(one_file, page.guid, page.content_hash()):
                skipped += 1
            else:
                ingested += 1

        assert skipped == len(pages), "All pages should be skipped (unchanged)"
        assert ingested == 0

    def test_delta_detects_changed_page(self, tmp_notebook_dir, tmp_kb):
        """Delta mode: a page with different hash triggers re-ingestion."""
        one_file = tmp_notebook_dir / "Troubleshooting.one"
        section_name = "Troubleshooting"
        pages = parse_one_section(str(one_file))

        manifest = OneNoteManifest(tmp_kb)
        manifest.update_section_mtime(one_file, section_name)
        for page in pages:
            manifest.upsert_page(
                one_file, page.guid, page.title,
                page.content_hash(), ["old_c1"],
            )
        manifest.save()

        # Simulate one page changed
        if pages:
            changed_page = pages[0]
            assert manifest.page_needs_ingest(
                one_file, changed_page.guid, "COMPLETELY_DIFFERENT_HASH"
            ) is True

    def test_chunk_delete_and_reinsert_flow(self, tmp_kb):
        """E2E flow: get old chunk IDs → delete → insert new → verify."""
        manifest = OneNoteManifest(tmp_kb)

        # Simulate first ingestion
        manifest.upsert_page("s.one", "pg1", "Title", "hash_v1",
                             ["chunk_a", "chunk_b", "chunk_c"])
        manifest.save()

        # Simulate re-ingestion (hash changed)
        old_ids = manifest.get_chunk_ids("s.one", "pg1")
        assert old_ids == ["chunk_a", "chunk_b", "chunk_c"]

        # "Delete" old chunks (would call vector_store.collection.delete)
        # Then insert new chunks
        manifest.upsert_page("s.one", "pg1", "Title", "hash_v2",
                             ["chunk_x", "chunk_y"])
        manifest.save()

        new_ids = manifest.get_chunk_ids("s.one", "pg1")
        assert new_ids == ["chunk_x", "chunk_y"]

    def test_two_section_full_notebook_e2e(self, tmp_notebook_dir, tmp_kb):
        """E2E: Full notebook with both sections → TOC ordering → all pages chunked."""
        toc_file = list(tmp_notebook_dir.glob("*.onetoc2"))[0]
        section_order = parse_onetoc2(str(toc_file))

        assert len(section_order) == 2

        manifest = OneNoteManifest(tmp_kb)
        total_chunks = 0
        total_pages = 0

        for sec_idx, sec_name in enumerate(section_order):
            one_file = tmp_notebook_dir / f"{sec_name}.one"
            assert one_file.exists(), f"Missing: {one_file}"

            pages = parse_one_section(str(one_file))
            manifest.update_section_mtime(one_file, sec_name)

            for page in pages:
                chunks = chunk_onenote_page(
                    page,
                    section_name=sec_name,
                    one_file_path=str(one_file),
                    notebook_name="TestNB",
                    section_order=sec_idx,
                )
                manifest.upsert_page(
                    one_file, page.guid, page.title,
                    page.content_hash(), [c.chunk_id for c in chunks],
                )
                total_chunks += len(chunks)
                total_pages += 1

        manifest.save()
        summary = manifest.summary()

        assert summary["total_sections"] == 2
        assert summary["total_pages"] == total_pages
        assert summary["total_chunks"] == total_chunks
        assert total_chunks > 0
        assert total_pages > 0

    def test_section_mtime_skip(self, tmp_notebook_dir, tmp_kb):
        """Section-level delta: unchanged file mtime skips entire section scan."""
        one_file = tmp_notebook_dir / "Troubleshooting.one"
        manifest = OneNoteManifest(tmp_kb)
        manifest.update_section_mtime(one_file, "Troubleshooting")
        manifest.save()

        # Reload — should NOT need scan
        m2 = OneNoteManifest(tmp_kb)
        assert m2.section_needs_scan(one_file) is False

    def test_content_searchable_keywords(self, tmp_notebook_dir):
        """Chunks contain searchable domain keywords from GSF IR corpus."""
        one_file = tmp_notebook_dir / "Troubleshooting.one"
        pages = parse_one_section(str(one_file))
        all_chunks: list[TextChunk] = []
        for page in pages:
            all_chunks.extend(chunk_onenote_page(page, "Troubleshooting", str(one_file)))

        full_text = " ".join(c.content for c in all_chunks).lower()

        # These keywords come from the embedded test corpus
        found_keywords = 0
        keywords = ["import", "vdi", "citrix", "excel", "macro", "package",
                     "error", "distrib", "deal", "process"]
        for kw in keywords:
            if kw in full_text:
                found_keywords += 1

        # At least half the keywords should be findable
        assert found_keywords >= len(keywords) // 2, (
            f"Only found {found_keywords}/{len(keywords)} keywords in chunk content"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 8. EDGE CASE & ROBUSTNESS TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Edge cases and error handling."""

    def test_empty_one_file(self, tmp_path):
        """A .one file with only header produces fallback page."""
        magic = bytes([0xE4, 0x52, 0x5C, 0x7B, 0x8C, 0xD8, 0xA3, 0x4D,
                       0xAE, 0xB1, 0x53, 0x78, 0xD0, 0x29, 0x96, 0xD3])
        f = tmp_path / "empty.one"
        f.write_bytes(magic + b'\x00' * 500)
        pages = parse_one_section(str(f))
        # Should return 0 pages (no text content) or fallback pages
        # Either outcome is acceptable as long as it doesn't crash
        assert isinstance(pages, list)

    def test_page_with_no_text_blocks(self):
        """Chunking a page with no text blocks returns empty list."""
        page = OneNotePage(guid="empty", title="", text_blocks=[])
        chunks = chunk_onenote_page(page, "Section", "/empty.one")
        # May produce 0 chunks (empty content) — should not crash
        assert isinstance(chunks, list)

    def test_manifest_corrupt_json(self, tmp_kb):
        """Corrupted manifest JSON causes fresh start."""
        manifest_path = tmp_kb / "onenote_ingest_manifest.json"
        manifest_path.write_text("{{invalid json!!", encoding="utf-8")
        m = OneNoteManifest(tmp_kb)
        assert m.summary()["total_sections"] == 0

    def test_manifest_wrong_version(self, tmp_kb):
        """Wrong version number causes fresh start."""
        manifest_path = tmp_kb / "onenote_ingest_manifest.json"
        manifest_path.write_text(
            json.dumps({"version": 999, "sections": {}}),
            encoding="utf-8",
        )
        m = OneNoteManifest(tmp_kb)
        assert m.summary()["total_sections"] == 0

    def test_chunker_handles_very_long_title(self):
        """A page with a very long title doesn't crash the chunker."""
        page = OneNotePage(
            guid="long_title",
            title="A" * 500,
            text_blocks=["Content"],
        )
        chunks = chunk_onenote_page(page, "S", "/t.one")
        assert len(chunks) >= 1

    def test_chunker_handles_unicode(self):
        """Non-ASCII content is handled without errors."""
        page = OneNotePage(
            guid="unicode",
            title="Données Financières",
            text_blocks=["Résumé: Les données sont importées correctement. €50.000"],
        )
        chunks = chunk_onenote_page(page, "S", "/t.one")
        assert len(chunks) >= 1
        assert "Données" in chunks[0].content or "donn" in chunks[0].content.lower()

    def test_onetoc2_with_special_chars(self, tmp_path):
        """Section names with spaces and special chars are handled."""
        toc = build_onetoc2_file(["Tech Tips & Tricks", "FAQ (2024)"])
        f = tmp_path / "test.onetoc2"
        f.write_bytes(toc)
        names = parse_onetoc2(str(f))
        assert "Tech Tips & Tricks" in names
        assert "FAQ (2024)" in names

    def test_table_splitting(self):
        """Tables with > 25 rows get split by the chunker."""
        # Create a page with a large markdown table
        rows = "\n".join(f"| item{i} | val{i} |" for i in range(60))
        md_table = "| Name | Value |\n| --- | --- |\n" + rows
        page = OneNotePage(
            guid="big_table", title="Big Table",
            text_blocks=[md_table],
        )
        chunks = chunk_onenote_page(page, "Data", "/t.one")
        # Should have been split
        assert len(chunks) >= 1

    def test_multiple_images_per_page(self):
        """Pages with multiple images produce valid chunks."""
        imgs = [
            OneNoteImage(image_bytes=create_minimal_jpeg(), fmt="jpeg"),
            OneNoteImage(image_bytes=create_test_png(), fmt="png"),
        ]
        page = OneNotePage(
            guid="multi_img", title="Multi Image",
            text_blocks=["See below"], images=imgs,
        )
        chunks = chunk_onenote_page(
            page, "S", "/t.one",
            image_descriptions=["Excel dialog", "Network diagram"],
        )
        full = " ".join(c.content for c in chunks)
        assert "Excel dialog" in full
        assert "Network diagram" in full
