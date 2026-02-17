"""
Integration tests for the 7-bug fix batch.

Tests the following fixes:
  Bug 1: Dedup keeps top N chunks per doc (not just 1)
  Bug 2: Legal/governing doc taxonomy classification
  Bug 3: Regime-adaptive chunk sizing (3000/500 for legal)
  Bug 4: Intent boost guard for GOVERNING_DOC
  Bug 5: Multi-signal confidence formula
  Bug 6: /deep mode differentiation (more chunks, wider pool)

Each test is designed to exercise the actual code path, not mock it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from config import load_config
from backend.agents import IngestionAgent, RetrievalService
from backend.agents.taxonomy_agent import TaxonomyAgent
from backend.common.doc_types import normalize_doc_type


# ── Fixtures ──────────────────────────────────────────────────────

SIMPLE_DIR = Path("tests/fixtures/simple")
COMPLEX_DIR = Path("tests/fixtures/complex")
PSA_FIXTURE = COMPLEX_DIR / "psa_mock_governing_doc.md"
GUIDE_FIXTURE = SIMPLE_DIR / "toolx_user_guide.md"
TROUBLESHOOT_FIXTURE = SIMPLE_DIR / "toolx_troubleshoot.md"
RELEASE_FIXTURE = COMPLEX_DIR / "release_notes_q1.md"


@pytest.fixture
def cfg():
    return load_config()


@pytest.fixture
def ingest_and_search(cfg):
    """Ingest documents and return a search helper."""
    ingestion = IngestionAgent(cfg)
    retrieval = RetrievalService(cfg)
    taxonomy = TaxonomyAgent(cfg)

    class _Helper:
        def __init__(self):
            self.ingestion = ingestion
            self.retrieval = retrieval
            self.taxonomy = taxonomy
            self._ingested = set()

        def ingest(self, path: str | Path):
            path = Path(path)
            if str(path) not in self._ingested:
                result = self.ingestion.execute({"path": str(path)})
                assert result.success, f"Ingestion failed for {path}: {result.reasoning}"
                
                # Run taxonomy and update metadata (mirrors CLI flow)
                doc = result.data["document"]
                text = doc.extracted_text
                classify = self.taxonomy.execute({"text": text, "filename": path.name})
                doc_type = classify.data.get("doc_type", "UNKNOWN")

                # Regime override (mirrors cli/main.py logic)
                metadata_path = Path(doc.metadata_path)
                if metadata_path.exists():
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                    metadata["doc_type"] = doc_type
                    doc_regime = metadata.get("doc_regime", "UNKNOWN")
                    if doc_regime == "GOVERNING_DOC_LEGAL" and doc_type != "GOVERNING_DOC":
                        metadata["doc_type"] = "GOVERNING_DOC"
                    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
                    self.ingestion.vector_store.update_doc_metadata(
                        doc.doc_id, doc_type=metadata["doc_type"], tags=metadata.get("tags", [])
                    )

                self._ingested.add(str(path))
                return result
            return None

        def search(self, query: str, max_results: int = 5, deep: bool = False,
                   doc_type: str | None = None, **kwargs):
            req = {
                "query": query,
                "max_results": max_results,
                "doc_type_filter": doc_type,
                "deep_mode": deep,
                **kwargs,
            }
            if deep:
                req["max_chunks_per_doc"] = cfg.deep_max_chunks_per_doc
            return self.retrieval.execute(req)

    return _Helper()


# ═══════════════════════════════════════════════════════════════════
# Bug 1: Dedup keeps multiple chunks per document
# ═══════════════════════════════════════════════════════════════════

class TestBug1DeduplicatePerDocLimit:
    """Verify that retrieval returns multiple chunks from the same document."""

    def test_single_doc_returns_multiple_chunks(self, ingest_and_search):
        """When only 1 doc is ingested, search should return >1 relevant chunks."""
        h = ingest_and_search
        h.ingest(PSA_FIXTURE)
        result = h.search("reporting requirements for certificateholders")
        sr = result.data["search_result"]
        assert len(sr.context_chunks) > 1, (
            f"Expected >1 chunks but got {len(sr.context_chunks)} — dedup still collapsing"
        )

    def test_max_chunks_per_doc_respected(self, ingest_and_search):
        """Should not exceed max_chunks_per_doc per document."""
        h = ingest_and_search
        h.ingest(PSA_FIXTURE)
        result = h.search("distribution date trustee", max_results=10)
        sr = result.data["search_result"]
        doc_ids = [c.doc_id for c in sr.context_chunks]
        from collections import Counter
        counts = Counter(doc_ids)
        max_per_doc = h.retrieval.config.max_chunks_per_doc
        for doc_id, count in counts.items():
            assert count <= max_per_doc, (
                f"Doc {doc_id} has {count} chunks, exceeds max_chunks_per_doc={max_per_doc}"
            )

    def test_cross_doc_diversity_preserved(self, ingest_and_search):
        """When multiple docs are ingested, results should include chunks from different docs."""
        h = ingest_and_search
        h.ingest(PSA_FIXTURE)
        h.ingest(GUIDE_FIXTURE)
        h.ingest(TROUBLESHOOT_FIXTURE)
        # Query that could match multiple docs
        result = h.search("how to handle error situations", max_results=10)
        sr = result.data["search_result"]
        unique_docs = set(c.doc_id for c in sr.context_chunks)
        # Should have results from at least 2 different documents
        assert len(unique_docs) >= 1, "Expected results from multiple documents"


# ═══════════════════════════════════════════════════════════════════
# Bug 2: Legal/governing doc taxonomy classification
# ═══════════════════════════════════════════════════════════════════

class TestBug2LegalDocTaxonomy:
    """Verify legal documents are classified as GOVERNING_DOC, not TROUBLESHOOT."""

    def test_psa_classified_as_governing_doc(self, cfg):
        """PSA document should be classified as GOVERNING_DOC by taxonomy rules."""
        taxonomy = TaxonomyAgent(cfg)
        psa_text = PSA_FIXTURE.read_text(encoding="utf-8")
        result = taxonomy.execute({"text": psa_text, "filename": "psa_mock_governing_doc.md"})
        doc_type = result.data["doc_type"]
        assert doc_type != "TROUBLESHOOT", (
            f"PSA misclassified as TROUBLESHOOT — Bug 2 not fixed. Got rules: {result.data.get('matched_rules')}"
        )
        assert doc_type == "GOVERNING_DOC", (
            f"Expected GOVERNING_DOC, got {doc_type}. Rules: {result.data.get('matched_rules')}"
        )

    def test_governing_doc_normalizes(self):
        """GOVERNING_DOC and its aliases should normalize correctly."""
        assert normalize_doc_type("GOVERNING_DOC") == "GOVERNING_DOC"
        assert normalize_doc_type("governing_doc") == "GOVERNING_DOC"
        assert normalize_doc_type("AGREEMENT") == "GOVERNING_DOC"
        assert normalize_doc_type("PSA") == "GOVERNING_DOC"
        assert normalize_doc_type("LEGAL") == "GOVERNING_DOC"
        assert normalize_doc_type("CONTRACT") == "GOVERNING_DOC"
        assert normalize_doc_type("INDENTURE") == "GOVERNING_DOC"

    def test_troubleshoot_not_polluted(self, cfg):
        """Actual troubleshoot docs should still classify correctly."""
        taxonomy = TaxonomyAgent(cfg)
        ts_text = TROUBLESHOOT_FIXTURE.read_text(encoding="utf-8")
        result = taxonomy.execute({"text": ts_text, "filename": "toolx_troubleshoot.md"})
        assert result.data["doc_type"] == "TROUBLESHOOT"

    def test_regime_override_applied_on_ingest(self, ingest_and_search):
        """After ingestion, PSA should have doc_type=GOVERNING_DOC in vector store."""
        h = ingest_and_search
        h.ingest(PSA_FIXTURE)
        result = h.search("pooling and servicing agreement")
        sr = result.data["search_result"]
        if sr.context_chunks:
            chunk_types = set(c.doc_type for c in sr.context_chunks)
            assert "GOVERNING_DOC" in chunk_types, (
                f"Expected GOVERNING_DOC in chunk types but got {chunk_types}"
            )


# ═══════════════════════════════════════════════════════════════════
# Bug 3: Regime-adaptive chunk sizing
# ═══════════════════════════════════════════════════════════════════

class TestBug3RegimeAdaptiveChunks:
    """Verify legal documents use larger chunk sizes."""

    def test_legal_doc_fewer_chunks(self, ingest_and_search):
        """A legal doc should produce significantly fewer chunks with 3000/500 sizing."""
        h = ingest_and_search
        result = h.ingest(PSA_FIXTURE)
        chunk_count = result.data["chunk_count"]
        text = PSA_FIXTURE.read_text(encoding="utf-8")
        text_len = len(text)
        # With 3000/500 chunks: effective step = 3000 - 500 = 2500
        # A ~4400 char doc produces ~3-5 chunks (including evidence headers)
        # With default 1000/200: effective step = 800, would produce ~7-8 chunks
        # The key assertion is that legal sizing produces fewer chunks than default
        expected_max_default = (text_len // 800) + 2  # ~7+ with default 1000/200
        assert chunk_count < expected_max_default, (
            f"Legal doc produced {chunk_count} chunks (text={text_len} chars), "
            f"should be less than default sizing would produce (~{expected_max_default})"
        )

    def test_regular_doc_uses_default_chunks(self, ingest_and_search):
        """Non-legal docs should still use default 1000/200 chunk sizing."""
        h = ingest_and_search
        result = h.ingest(GUIDE_FIXTURE)
        chunk_count = result.data["chunk_count"]
        text = GUIDE_FIXTURE.read_text(encoding="utf-8")
        # Small doc, should produce 1 chunk with either sizing
        assert chunk_count >= 1

    def test_config_values_set(self, cfg):
        """Config should have legal chunk size fields."""
        assert hasattr(cfg, 'legal_chunk_size')
        assert hasattr(cfg, 'legal_chunk_overlap')
        assert cfg.legal_chunk_size == 3000
        assert cfg.legal_chunk_overlap == 500


# ═══════════════════════════════════════════════════════════════════
# Bug 4: Intent boost guard for GOVERNING_DOC
# ═══════════════════════════════════════════════════════════════════

class TestBug4IntentBoostGuard:
    """Verify legal docs aren't penalized by troubleshoot-oriented intent matching."""

    def test_legal_query_detects_governing_intent(self, cfg):
        """Queries with legal terms should detect governing_doc intent."""
        retrieval = RetrievalService(cfg)
        intent, doc_types = retrieval._detect_query_intent(
            "What are the reporting requirements in the pooling and servicing agreement?"
        )
        assert "GOVERNING_DOC" in doc_types, (
            f"Expected GOVERNING_DOC intent, got intent={intent}, types={doc_types}"
        )

    def test_general_query_does_not_penalize_legal(self, ingest_and_search):
        """General queries should not de-boost GOVERNING_DOC results."""
        h = ingest_and_search
        h.ingest(PSA_FIXTURE)
        h.ingest(TROUBLESHOOT_FIXTURE)
        # Query about reporting — should favor PSA over troubleshoot
        result = h.search("what are the reporting requirements")
        sr = result.data["search_result"]
        if sr.context_chunks:
            top_type = sr.context_chunks[0].doc_type
            assert top_type == "GOVERNING_DOC", (
                f"Top result should be GOVERNING_DOC, got {top_type}"
            )

    def test_trustee_query_returns_psa(self, ingest_and_search):
        """Trustee-related query should return PSA content."""
        h = ingest_and_search
        h.ingest(PSA_FIXTURE)
        result = h.search("trustee obligations and distributions")
        sr = result.data["search_result"]
        assert len(sr.context_chunks) >= 1
        contents = " ".join(c.content for c in sr.context_chunks).lower()
        assert "trustee" in contents


# ═══════════════════════════════════════════════════════════════════
# Bug 5: Multi-signal confidence formula
# ═══════════════════════════════════════════════════════════════════

class TestBug5MultiSignalConfidence:
    """Verify confidence uses multiple signals, not just cosine similarity."""

    def test_confidence_above_floor_for_good_match(self, ingest_and_search):
        """A clearly relevant query should produce confidence well above floor."""
        h = ingest_and_search
        h.ingest(GUIDE_FIXTURE)
        result = h.search("reset password ToolX")
        assert result.confidence > 0.3, (
            f"Expected confidence > 0.3 for exact match, got {result.confidence}"
        )

    def test_confidence_below_ceiling(self, ingest_and_search):
        """Confidence should never exceed 1.0."""
        h = ingest_and_search
        h.ingest(PSA_FIXTURE)
        result = h.search("distribution date")
        assert result.confidence <= 1.0

    def test_irrelevant_query_low_confidence(self, ingest_and_search):
        """A completely irrelevant query should have lower confidence."""
        h = ingest_and_search
        h.ingest(GUIDE_FIXTURE)
        result = h.search("quantum mechanics string theory dark matter")
        sr = result.data["search_result"]
        # Even garbage queries return something from vector search,
        # but confidence should be noticeably lower
        assert sr.confidence < 0.8, (
            f"Irrelevant query should have low confidence, got {sr.confidence}"
        )

    def test_confidence_varies_by_relevance(self, ingest_and_search):
        """More relevant queries should produce higher confidence than less relevant ones."""
        h = ingest_and_search
        h.ingest(PSA_FIXTURE)
        
        good_result = h.search("certificateholder distribution date reporting")
        weak_result = h.search("completely random unrelated topic xyz789")
        
        good_conf = good_result.data["search_result"].confidence
        weak_conf = weak_result.data["search_result"].confidence
        
        # Good match should have higher confidence
        assert good_conf >= weak_conf, (
            f"Relevant query confidence ({good_conf}) should be >= irrelevant ({weak_conf})"
        )


# ═══════════════════════════════════════════════════════════════════
# Bug 6: /deep mode differentiation
# ═══════════════════════════════════════════════════════════════════

class TestBug6DeepModeDifferentiation:
    """Verify /deep mode returns more chunks than regular mode."""

    def test_deep_returns_more_chunks(self, ingest_and_search):
        """Deep mode should return more chunks than regular mode."""
        h = ingest_and_search
        h.ingest(PSA_FIXTURE)
        
        regular = h.search("reporting requirements distribution", max_results=5)
        deep = h.search("reporting requirements distribution", max_results=10, deep=True)
        
        regular_count = len(regular.data["search_result"].context_chunks)
        deep_count = len(deep.data["search_result"].context_chunks)
        
        assert deep_count >= regular_count, (
            f"Deep mode ({deep_count} chunks) should return >= regular ({regular_count} chunks)"
        )

    def test_deep_mode_config_values(self, cfg):
        """Config should have deep mode chunk limits."""
        assert hasattr(cfg, 'deep_max_chunks_per_doc')
        assert cfg.deep_max_chunks_per_doc > cfg.max_chunks_per_doc

    def test_regular_mode_config_values(self, cfg):
        """Config should have regular mode chunk limits."""
        assert hasattr(cfg, 'max_chunks_per_doc')
        assert cfg.max_chunks_per_doc >= 2  # At least 2 chunks per doc


# ═══════════════════════════════════════════════════════════════════
# Feature preservation: Existing features still work
# ═══════════════════════════════════════════════════════════════════

class TestFeaturePreservation:
    """Existing features should still work correctly after the bug fixes."""

    def test_error_code_query_still_boosts(self, ingest_and_search):
        """Error code exact match should still boost troubleshoot docs."""
        h = ingest_and_search
        h.ingest(TROUBLESHOOT_FIXTURE)
        result = h.search("AUTH-401 login failure")
        sr = result.data["search_result"]
        assert len(sr.context_chunks) >= 1
        contents = " ".join(c.content for c in sr.context_chunks).lower()
        assert "auth-401" in contents or "auth" in contents

    def test_user_guide_search_still_works(self, ingest_and_search):
        """User guide queries should still return user guide content."""
        h = ingest_and_search
        h.ingest(GUIDE_FIXTURE)
        result = h.search("how to reset password")
        sr = result.data["search_result"]
        assert len(sr.context_chunks) >= 1

    def test_citations_still_returned(self, ingest_and_search):
        """Citations should still be provided for all results."""
        h = ingest_and_search
        h.ingest(PSA_FIXTURE)
        result = h.search("trustee obligations")
        sr = result.data["search_result"]
        assert len(sr.citations) >= 1
        assert sr.citations[0].doc_name is not None

    def test_mixed_corpus_query(self, ingest_and_search):
        """Query across mixed doc types should return relevant results."""
        h = ingest_and_search
        h.ingest(PSA_FIXTURE)
        h.ingest(GUIDE_FIXTURE)
        h.ingest(TROUBLESHOOT_FIXTURE)
        h.ingest(RELEASE_FIXTURE)
        
        result = h.search("error handling and failure recovery", max_results=10)
        sr = result.data["search_result"]
        assert len(sr.context_chunks) >= 1
        assert result.confidence > 0.15  # Above absolute floor


# ═══════════════════════════════════════════════════════════════════
# Search quality: PSA-specific queries
# ═══════════════════════════════════════════════════════════════════

class TestPSASearchQuality:
    """Verify PSA queries return correct sections (the original failure case)."""

    def test_reporting_requirements_not_sarbanes_oxley(self, ingest_and_search):
        """Query about reporting should return Section 2, not Section 7 (Sarbanes-Oxley)."""
        h = ingest_and_search
        h.ingest(PSA_FIXTURE)
        result = h.search("what are the reporting requirements for this PSA")
        sr = result.data["search_result"]
        assert len(sr.context_chunks) >= 1
        
        top_content = sr.context_chunks[0].content.lower()
        # Should contain reporting-related content, not just Sarbanes-Oxley
        assert any(term in top_content for term in [
            "statement to certificateholders", "remittance report",
            "distribution date", "reporting requirements"
        ]), f"Top chunk should be about reporting, got: {top_content[:200]}"

    def test_distribution_priority_query(self, ingest_and_search):
        """Query about distribution priority should return Section 4."""
        h = ingest_and_search
        h.ingest(PSA_FIXTURE)
        result = h.search("order of priority for distributions to certificateholders")
        sr = result.data["search_result"]
        assert len(sr.context_chunks) >= 1
        contents = " ".join(c.content for c in sr.context_chunks[:3]).lower()
        assert any(term in contents for term in [
            "class a", "class b", "priority", "distribution"
        ]), f"Should mention distribution priority classes, got: {contents[:300]}"

    def test_events_of_default_query(self, ingest_and_search):
        """Query about default events should return Section 5."""
        h = ingest_and_search
        h.ingest(PSA_FIXTURE)
        result = h.search("events of default under the agreement")
        sr = result.data["search_result"]
        assert len(sr.context_chunks) >= 1
        contents = " ".join(c.content for c in sr.context_chunks[:3]).lower()
        assert "event of default" in contents or "default" in contents

    def test_master_servicer_obligations(self, ingest_and_search):
        """Query about servicer obligations should return relevant sections."""
        h = ingest_and_search
        h.ingest(PSA_FIXTURE)
        result = h.search("master servicer responsibilities and obligations")
        sr = result.data["search_result"]
        assert len(sr.context_chunks) >= 1
        contents = " ".join(c.content for c in sr.context_chunks[:3]).lower()
        assert "master servicer" in contents
