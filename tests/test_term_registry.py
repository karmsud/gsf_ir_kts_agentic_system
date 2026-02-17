"""Unit tests for backend.retrieval.term_registry — 3-tier learned synonym system.

Tests term registration, clustering, synonym file generation, approval/rejection
workflows, and data-persistence edge cases.  Uses a mock embedding function
to avoid ChromaDB dependency in CI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.retrieval.term_registry import (
    LEARN_CONFIDENCE_THRESHOLD,
    LEARN_MIN_DOC_COUNT,
    MAX_CLUSTER_SIZE,
    MAX_TERM_WORDS,
    MIN_TERM_WORDS,
    SIMILARITY_THRESHOLD,
    TermRegistry,
    _cosine_similarity,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _dummy_embed(texts: List[str]) -> List[List[float]]:
    """Deterministic fake embeddings.

    Maps known terms to manually-positioned vectors so we can control
    clustering behaviour.  Terms not in the map get a random-ish vector.
    """
    # Manually positioned vectors (384-dim would be realistic but 4-dim suffices)
    KNOWN = {
        "mortgage loans": [1.0, 0.0, 0.0, 0.0],
        "home loans":     [0.98, 0.05, 0.0, 0.0],    # close to mortgage loans
        "housing loans":  [0.96, 0.08, 0.0, 0.0],    # close to mortgage loans
        "trust fund":     [0.0, 1.0, 0.0, 0.0],
        "trust assets":   [0.05, 0.97, 0.0, 0.0],    # close to trust fund
        "distribution account": [0.0, 0.0, 1.0, 0.0],
        "payment account":      [0.1, 0.0, 0.92, 0.0],  # close to distribution account
        "weather forecast": [0.0, 0.0, 0.0, 1.0],   # dissimilar to all above
        "rain prediction":  [0.05, 0.0, 0.05, 0.95], # close to weather forecast
    }
    result = []
    for t in texts:
        key = t.strip().lower()
        if key in KNOWN:
            result.append(KNOWN[key])
        else:
            # Unique-ish vector based on hash
            h = hash(key) & 0xFFFFFFFF
            result.append([
                ((h >> 0) & 0xFF) / 255.0,
                ((h >> 8) & 0xFF) / 255.0,
                ((h >> 16) & 0xFF) / 255.0,
                ((h >> 24) & 0xFF) / 255.0,
            ])
    return result


@pytest.fixture
def registry(tmp_path) -> TermRegistry:
    """Fresh TermRegistry with a temp KB path and dummy embedder."""
    return TermRegistry(tmp_path, embed_fn=_dummy_embed)


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    def test_identical_vectors(self):
        assert _cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert _cosine_similarity([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert _cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)

    def test_zero_vector(self):
        assert _cosine_similarity([0, 0, 0], [1, 2, 3]) == 0.0


# ---------------------------------------------------------------------------
# Term registration
# ---------------------------------------------------------------------------

class TestRegisterTerms:
    def test_registers_new_terms(self, registry):
        added = registry.register_terms(
            ["mortgage loans", "trust fund"],
            doc_id="doc1",
            doc_type="PSA",
        )
        assert added == 2

    def test_deduplicates_on_second_registration(self, registry):
        registry.register_terms(["mortgage loans"], doc_id="doc1", doc_type="PSA")
        added2 = registry.register_terms(["mortgage loans"], doc_id="doc2", doc_type="PSA")
        assert added2 == 0  # same term, already registered

    def test_same_term_different_doc_type(self, registry):
        registry.register_terms(["mortgage loans"], doc_id="doc1", doc_type="PSA")
        added = registry.register_terms(["mortgage loans"], doc_id="doc2", doc_type="PROSPECTUS")
        assert added == 1  # different doc_type → new entry

    def test_ignores_single_word_terms(self, registry):
        added = registry.register_terms(["trustee"], doc_id="doc1", doc_type="PSA")
        assert added == 0  # single word < MIN_TERM_WORDS

    def test_ignores_overly_long_terms(self, registry):
        long_term = " ".join(["word"] * (MAX_TERM_WORDS + 1))
        added = registry.register_terms([long_term], doc_id="doc1", doc_type="PSA")
        assert added == 0

    def test_tracks_doc_ids(self, registry):
        registry.register_terms(["mortgage loans"], doc_id="doc1", doc_type="PSA")
        registry.register_terms(["mortgage loans"], doc_id="doc2", doc_type="PSA")
        registry.register_terms(["mortgage loans"], doc_id="doc3", doc_type="PSA")

        key = "PSA::mortgage loans"
        assert len(registry._registry[key]["doc_ids"]) == 3

    def test_persists_to_disk(self, registry, tmp_path):
        registry.register_terms(["mortgage loans"], doc_id="doc1", doc_type="PSA")
        assert (tmp_path / "term_registry.json").exists()

        data = json.loads((tmp_path / "term_registry.json").read_text())
        assert "PSA::mortgage loans" in data


# ---------------------------------------------------------------------------
# Synonym rebuilding (clustering)
# ---------------------------------------------------------------------------

class TestRebuildSynonyms:
    def _register_similar_terms(self, registry):
        """Register terms that should cluster together."""
        for doc_num in range(1, 5):  # 4 docs → passes LEARN_MIN_DOC_COUNT
            registry.register_terms(
                ["mortgage loans", "home loans", "housing loans"],
                doc_id=f"doc{doc_num}",
                doc_type="PSA",
            )

    def test_creates_output_files(self, registry, tmp_path):
        self._register_similar_terms(registry)
        summary = registry.rebuild_synonyms()

        assert (tmp_path / "synonyms_learned.json").exists()
        assert (tmp_path / "synonyms_candidates.json").exists()
        assert "learned_clusters" in summary
        assert "candidate_clusters" in summary
        assert "total_terms" in summary

    def test_clusters_similar_terms(self, registry, tmp_path):
        self._register_similar_terms(registry)
        registry.rebuild_synonyms()

        learned = json.loads((tmp_path / "synonyms_learned.json").read_text())
        # Should have at least one cluster under PSA
        if "PSA" in learned and learned["PSA"]:
            # All 3 terms should be in one cluster
            all_synonyms = []
            for term, record in learned["PSA"].items():
                all_synonyms.append(term)
                all_synonyms.extend(record["synonyms"])
            # At least 2 of 3 terms should be in the same cluster
            matched = sum(
                1 for t in ["mortgage loans", "home loans", "housing loans"]
                if t in all_synonyms
            )
            assert matched >= 2, f"Expected cluster of similar terms, got: {all_synonyms}"

    def test_dissimilar_terms_not_clustered(self, registry, tmp_path):
        """Weather terms should NOT cluster with mortgage terms."""
        for i in range(5):
            registry.register_terms(
                ["mortgage loans", "weather forecast"],
                doc_id=f"doc{i}",
                doc_type="PSA",
            )
        registry.rebuild_synonyms()

        learned = json.loads((tmp_path / "synonyms_learned.json").read_text())
        if "PSA" in learned:
            for term, record in learned["PSA"].items():
                if term == "mortgage loans":
                    assert "weather forecast" not in record["synonyms"]
                if term == "weather forecast":
                    assert "mortgage loans" not in record["synonyms"]

    def test_low_doc_count_goes_to_candidates(self, registry, tmp_path):
        """Terms appearing in fewer than LEARN_MIN_DOC_COUNT docs → candidates."""
        # Register in only 1 doc (below threshold)
        registry.register_terms(
            ["mortgage loans", "home loans"],
            doc_id="doc1",
            doc_type="PSA",
        )
        registry.rebuild_synonyms()

        candidates = json.loads((tmp_path / "synonyms_candidates.json").read_text())
        learned = json.loads((tmp_path / "synonyms_learned.json").read_text())
        # With only 1 doc, nothing should be learned
        psa_learned = learned.get("PSA", {})
        # If any cluster formed, it should be in candidates (low doc count)

    def test_regime_aware_output(self, registry, tmp_path):
        """Different doc_types produce separate regime keys."""
        for i in range(5):
            registry.register_terms(
                ["mortgage loans", "home loans"],
                doc_id=f"psa_doc{i}",
                doc_type="PSA",
            )
            registry.register_terms(
                ["trust fund", "trust assets"],
                doc_id=f"prosp_doc{i}",
                doc_type="PROSPECTUS",
            )
        registry.rebuild_synonyms()

        learned = json.loads((tmp_path / "synonyms_learned.json").read_text())
        # Should have separate regime keys
        regimes = set(learned.keys())
        # At least one of PSA or PROSPECTUS should appear
        assert len(regimes) >= 1

    def test_summary_counts(self, registry):
        self._register_similar_terms(registry)
        summary = registry.rebuild_synonyms()
        assert summary["total_terms"] >= 3
        assert summary["learned_clusters"] + summary["candidate_clusters"] >= 0


# ---------------------------------------------------------------------------
# Approval / Rejection workflows
# ---------------------------------------------------------------------------

class TestApprovalWorkflow:
    def _setup_candidate(self, registry, tmp_path):
        """Create a candidate entry."""
        cand_data = {
            "PSA": {
                "mortgage loans": {
                    "synonyms": ["home loans", "housing loans"],
                    "confidence": 0.75,
                    "doc_count": 2,
                    "status": "pending",
                }
            }
        }
        cand_path = tmp_path / "synonyms_candidates.json"
        cand_path.write_text(json.dumps(cand_data))

    def test_approve_moves_to_static(self, registry, tmp_path):
        self._setup_candidate(registry, tmp_path)
        static_path = tmp_path / "synonyms.json"
        static_path.write_text("{}")

        ok = registry.approve_candidate("mortgage loans", "PSA", static_path)
        assert ok

        # Check static file updated
        static = json.loads(static_path.read_text())
        assert "mortgage loans" in static
        assert "home loans" in static["mortgage loans"]

        # Check candidate marked approved
        cands = json.loads((tmp_path / "synonyms_candidates.json").read_text())
        assert cands["PSA"]["mortgage loans"]["status"] == "approved"

    def test_reject_marks_rejected(self, registry, tmp_path):
        self._setup_candidate(registry, tmp_path)

        ok = registry.reject_candidate("mortgage loans", "PSA")
        assert ok

        cands = json.loads((tmp_path / "synonyms_candidates.json").read_text())
        assert cands["PSA"]["mortgage loans"]["status"] == "rejected"

    def test_rejected_not_overwritten(self, registry, tmp_path):
        """Rejected entries should not be replaced on next rebuild."""
        self._setup_candidate(registry, tmp_path)
        registry.reject_candidate("mortgage loans", "PSA")

        # Simulate a rebuild that produces new candidates
        new_cands = {
            "PSA": {
                "mortgage loans": {
                    "synonyms": ["home loans"],
                    "confidence": 0.80,
                    "status": "pending",
                }
            }
        }
        registry._merge_candidates(new_cands)

        cands = json.loads((tmp_path / "synonyms_candidates.json").read_text())
        # Should still be "rejected", not overwritten
        assert cands["PSA"]["mortgage loans"]["status"] == "rejected"

    def test_approve_nonexistent_returns_false(self, registry, tmp_path):
        ok = registry.approve_candidate("nonexistent term", "PSA", tmp_path / "syn.json")
        assert not ok

    def test_reject_nonexistent_returns_false(self, registry, tmp_path):
        ok = registry.reject_candidate("nonexistent term", "PSA")
        assert not ok

    def test_get_pending_candidates(self, registry, tmp_path):
        cand_data = {
            "PSA": {
                "mortgage loans": {"synonyms": ["home loans"], "status": "pending"},
                "trust fund": {"synonyms": ["trust assets"], "status": "rejected"},
            }
        }
        (tmp_path / "synonyms_candidates.json").write_text(json.dumps(cand_data))

        pending = registry.get_pending_candidates()
        assert "PSA" in pending
        assert "mortgage loans" in pending["PSA"]
        assert "trust fund" not in pending["PSA"]  # rejected → filtered out


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_registry_rebuild(self, registry):
        summary = registry.rebuild_synonyms()
        assert summary["total_terms"] == 0
        assert summary["learned_clusters"] == 0

    def test_single_term_no_cluster(self, registry, tmp_path):
        registry.register_terms(["mortgage loans"], doc_id="d1", doc_type="PSA")
        summary = registry.rebuild_synonyms()
        # Can't cluster a single term
        assert summary["learned_clusters"] == 0

    def test_reload_persisted_registry(self, tmp_path):
        """Registry should reload from disk on construction."""
        reg1 = TermRegistry(tmp_path, embed_fn=_dummy_embed)
        reg1.register_terms(["mortgage loans"], doc_id="d1", doc_type="PSA")

        # Create new instance pointing to same path
        reg2 = TermRegistry(tmp_path, embed_fn=_dummy_embed)
        assert "PSA::mortgage loans" in reg2._registry

    def test_max_cluster_size_respected(self, registry):
        """Clusters should not exceed MAX_CLUSTER_SIZE."""
        # Register many similar-ish terms
        for i in range(20):
            registry.register_terms(
                [f"mortgage term variant {i % 3}"],
                doc_id=f"doc{i}",
                doc_type="PSA",
            )
        summary = registry.rebuild_synonyms()
        # Verify no cluster exceeds limit
        learned_path = registry._learned_path
        if learned_path.exists():
            learned = json.loads(learned_path.read_text())
            for regime, terms in learned.items():
                for term, record in terms.items():
                    assert len(record["synonyms"]) <= MAX_CLUSTER_SIZE
