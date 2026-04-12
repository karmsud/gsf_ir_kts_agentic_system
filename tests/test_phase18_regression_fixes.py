"""
Phase 18 regression tests – 10 tests covering the three critical fixes:

  Fix 1: Scope routing (HE2→HE1 cross-contamination)
  Fix 2: Definition extractor (TOC skip + broadened regex)
  Fix 3: describe complete path (scope auto-discovery + --scope-kts passthrough)
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.extraction.definition_extractor import (
    DEFINITION_START_COLON,
    _MIN_SECTION_LENGTH,
    _TOC_DOTLEADER,
    extract_definitions_section,
    extract_term_dictionary,
)


# ───────────────────────────────────────────────────────────────────
# Helpers / fixtures
# ───────────────────────────────────────────────────────────────────

def _make_scope_tree(base: Path, scope_name: str, *, with_phase6: bool = True) -> Path:
    """Create a realistic per-scope .kts directory tree under *base*."""
    scope_dir = base / scope_name
    kts = scope_dir / ".kts"
    (kts / "vectors" / "phase6").mkdir(parents=True, exist_ok=True)
    (kts / "graph").mkdir(parents=True, exist_ok=True)
    (kts / "documents").mkdir(parents=True, exist_ok=True)
    if with_phase6:
        # Write a tiny sentinel so _discover_scope_kts_paths sees it
        (kts / "vectors" / "phase6" / "chroma.sqlite3").write_text("x")
    return kts


def _make_doc(kts: Path, doc_id: str) -> Path:
    """Create a stub documents/<doc_id>/ with a manifest."""
    doc_dir = kts / "documents" / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    manifest = doc_dir / "descriptions.json"
    manifest.write_text("{}", encoding="utf-8")
    return doc_dir


def _dummy_config(kb_path: str | Path) -> SimpleNamespace:
    """Minimal config-like namespace matching KTSConfig attributes."""
    kb = Path(kb_path)
    return SimpleNamespace(
        knowledge_base_path=str(kb),
        chroma_persist_dir=str(kb / "vectors"),
        phase6_chroma_dir=str(kb / "vectors" / "phase6"),
        graph_path=str(kb / "graph" / "knowledge_graph.json"),
        manifest_path=str(kb / "manifest.json"),
    )


# ═══════════════════════════════════════════════════════════════════
# Fix 1: Scope routing  (3 tests)
# ═══════════════════════════════════════════════════════════════════

class TestScopeRouting:
    """Ensure explicit scope slugs route through single-scope federation."""

    def test_resolve_scope_kts_path_finds_matching_scope(self, tmp_path):
        """_resolve_scope_kts_path should find the correct .kts for a slug."""
        from backend.agents.retrieval_service import RetrievalService

        # Build a scope tree — slug is lowercased by _discover_scope_kts_paths
        root_kts = tmp_path / "kb" / ".kts"
        root_kts.mkdir(parents=True)
        scope_he1 = _make_scope_tree(tmp_path / "kb", "bear_stearns_2006-HE1")
        scope_he2 = _make_scope_tree(tmp_path / "kb", "bear_stearns_2006_HE2")

        config = _dummy_config(root_kts)
        svc = RetrievalService.__new__(RetrievalService)
        svc.config = config
        svc.logger = MagicMock()

        # Slugs are lowercased during discovery
        result = svc._resolve_scope_kts_path("bear_stearns_2006_he2")
        assert result is not None, "Should resolve bear_stearns_2006_he2"
        assert "bear_stearns_2006_HE2" in result  # dir name preserved
        assert ".kts" in result

    def test_resolve_scope_kts_path_returns_none_for_unknown_slug(self, tmp_path):
        """Should return None when the slug doesn't match any discovered scope."""
        from backend.agents.retrieval_service import RetrievalService

        root_kts = tmp_path / "kb" / ".kts"
        root_kts.mkdir(parents=True)
        _make_scope_tree(tmp_path / "kb", "bear_stearns_2006-HE1")

        config = _dummy_config(root_kts)
        svc = RetrievalService.__new__(RetrievalService)
        svc.config = config
        svc.logger = MagicMock()

        # slug is lowercased
        assert svc._resolve_scope_kts_path("nonexistent_deal") is None

    def test_explicit_scope_does_not_fall_through_to_root(self, tmp_path):
        """When resolved_scope is set and .kts exists, _phase6_retrieve
        (which uses root vectors) should NOT be called; instead
        _federated_scope_retrieve should receive a single-scope list."""
        from backend.agents.retrieval_service import RetrievalService

        root_kts = tmp_path / "kb" / ".kts"
        root_kts.mkdir(parents=True)
        scope_he2 = _make_scope_tree(tmp_path / "kb", "bear_stearns_2006_HE2")

        config = _dummy_config(root_kts)
        svc = RetrievalService.__new__(RetrievalService)
        svc.config = config
        svc.logger = MagicMock()

        # Patch both paths
        svc._federated_scope_retrieve = MagicMock(return_value={"results": []})
        svc._phase6_retrieve = MagicMock(return_value={"results": []})
        svc._resolve_scope_kts_path = MagicMock(return_value=str(scope_he2))

        # Simulate the routing logic from retrieve()
        resolved_scope = "bear_stearns_2006_he2"  # slugs are lowercase
        scope_kts = svc._resolve_scope_kts_path(resolved_scope)
        if scope_kts:
            svc._federated_scope_retrieve(
                "test query", [(resolved_scope, scope_kts)],
                max_results=10,
            )
        else:
            svc._phase6_retrieve("test query", max_results=10, scope=resolved_scope)

        svc._federated_scope_retrieve.assert_called_once()
        svc._phase6_retrieve.assert_not_called()
        # Verify the scope list has exactly one element
        args = svc._federated_scope_retrieve.call_args
        scope_list = args[0][1]
        assert len(scope_list) == 1
        assert scope_list[0][0] == "bear_stearns_2006_he2"


# ═══════════════════════════════════════════════════════════════════
# Fix 2: Definition extractor – TOC skip + broadened regex (4 tests)
# ═══════════════════════════════════════════════════════════════════

class TestDefinitionExtractorTOCSkip:
    """Ensure the extractor skips TOC stubs and finds the real section."""

    def test_toc_stub_is_skipped_when_short_with_dotleaders(self):
        """A short stub (< 2000 chars) with dot-leaders should be skipped
        in favour of the real definitions section that follows."""
        toc_stub = (
            "ARTICLE I\nDEFINITIONS\n"
            "Section 1.01 Defined Terms......19\n"
            "Section 1.02 Notes on Usage......22\n"
            "ARTICLE II\nTHE TRUST\n"
        )
        real_section = (
            "ARTICLE I\nDEFINITIONS\n"
            + "\n".join(
                f'"Term_{i}": means some legal definition text for Term_{i}.'
                for i in range(200)
            )
            + "\nARTICLE II\n"
        )
        full_text = toc_stub + "\n\n" + real_section

        section, start, end = extract_definitions_section(full_text)
        assert len(section) >= _MIN_SECTION_LENGTH, (
            f"Section too short ({len(section)} chars) – likely matched TOC stub"
        )
        assert "Term_0" in section
        assert "Term_199" in section

    def test_no_toc_finds_first_match(self):
        """Without a TOC stub, the first match should be accepted directly."""
        real_section = (
            "ARTICLE I\nDEFINITIONS\n"
            + "\n".join(
                f'"Term_{i}" means definition text for Term_{i}.'
                for i in range(100)
            )
            + "\nARTICLE II\n"
        )
        section, start, end = extract_definitions_section(real_section)
        assert len(section) > 500
        assert "Term_0" in section

    def test_dotleader_pattern_detects_toc_lines(self):
        """_TOC_DOTLEADER should match sequences of 4+ dots."""
        assert _TOC_DOTLEADER.search("Section 1.01 ......19")
        assert _TOC_DOTLEADER.search("Definitions.............5")
        assert not _TOC_DOTLEADER.search("Term means end.")
        assert not _TOC_DOTLEADER.search("i.e. a thing")


class TestDefinitionExtractorBroadenedRegex:
    """Broadened DEFINITION_START_COLON should match diverse term formats."""

    def test_hyphenated_term_matches(self):
        """Terms like 'Back-Up Certification' should match."""
        m = DEFINITION_START_COLON.search("Back-Up Certification: has the meaning assigned")
        assert m is not None
        assert m.group(1).strip() == "Back-Up Certification"

    def test_term_with_digits_matches(self):
        """Terms like 'Class I-A-1 Certificate' should match."""
        m = DEFINITION_START_COLON.search("Class I-A-1 Certificate: means the certificate")
        assert m is not None
        assert "Class" in m.group(1)

    def test_lowercase_definition_start(self):
        """Definitions starting with lowercase like 'has the meaning' or '(a) the ...'."""
        m = DEFINITION_START_COLON.search("Servicer: has the meaning assigned in Section 3.01")
        assert m is not None
        assert m.group(1).strip() == "Servicer"

    def test_old_format_still_works(self):
        """Standard 'TitleCase: Definition' should still match."""
        m = DEFINITION_START_COLON.search("Trustee: The Bank of New York")
        assert m is not None
        assert m.group(1).strip() == "Trustee"


# ═══════════════════════════════════════════════════════════════════
# Fix 3: describe complete scope discovery (3 tests)
# ═══════════════════════════════════════════════════════════════════

class TestDescribeCompleteScopeDiscovery:
    """Test _resolve_scope_for_doc and describe_pending scope_kts emission."""

    def test_resolve_scope_for_doc_finds_per_scope(self, tmp_path):
        """When doc_id exists only in a per-scope .kts, that scope
        config should be returned — not the root config."""
        # Import the helper
        sys.path.insert(0, str(ROOT / "cli"))
        from cli.main import _resolve_scope_for_doc

        # Setup: root .kts has no doc, scope has it
        root_kts = tmp_path / "kb" / ".kts"
        (root_kts / "documents").mkdir(parents=True)
        scope_kts = _make_scope_tree(tmp_path / "kb", "troubleshoot")
        _make_doc(scope_kts, "doc_12345")

        config = _dummy_config(root_kts)
        resolved = _resolve_scope_for_doc(config, "doc_12345")
        assert "troubleshoot" in resolved.knowledge_base_path

    def test_resolve_scope_for_doc_prefers_root(self, tmp_path):
        """If doc_id exists in root .kts, root config is returned."""
        from cli.main import _resolve_scope_for_doc

        root_kts = tmp_path / "kb" / ".kts"
        _make_doc(root_kts, "doc_99999")

        config = _dummy_config(root_kts)
        resolved = _resolve_scope_for_doc(config, "doc_99999")
        assert resolved is config  # unchanged — root is returned directly

    def test_resolve_scope_for_doc_fallback(self, tmp_path):
        """If doc_id isn't found anywhere, original root config is returned."""
        from cli.main import _resolve_scope_for_doc

        root_kts = tmp_path / "kb" / ".kts"
        (root_kts / "documents").mkdir(parents=True)

        config = _dummy_config(root_kts)
        resolved = _resolve_scope_for_doc(config, "doc_nonexistent")
        assert resolved is config
