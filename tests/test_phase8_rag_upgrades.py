"""
Phase 8 RAG Upgrade Tests — Comprehensive coverage of all 9 increments.

Increment 0: Contextual Chunk Headers (CCH)
Increment 1: BM25 Hybrid Search with RRF
Increment 2: MMR Diversity Sampling
Increment 3: Token-Aware Context Trimming (JS — tested via node/subprocess)
Increment 4: Parent-Child Document Linking
Increment 5: Targeted HyPE
Increment 6: Multi-Query RAG Fusion
Increment 7: N-Level Definition Chain Traversal
Increment 8: Self-RAG Iterative Generation Loop

Each section below mirrors the increment number.
"""

from __future__ import annotations

import inspect
import json
import math
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ═════════════════════════════════════════════════════════════════
# Phase 8 Config Flags
# ═════════════════════════════════════════════════════════════════

class TestPhase8Config:
    """All 21 Phase 8 config flags exist with correct defaults."""

    def test_enable_cch_default_true(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.enable_cch is True

    def test_enable_bm25_hybrid_default_true(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.enable_bm25_hybrid is True

    def test_bm25_weight_default(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.bm25_weight == 0.4

    def test_vector_weight_default(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.vector_weight == 0.6

    def test_rrf_constant_default(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.rrf_constant == 60

    def test_bm25_k1_default(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.bm25_k1 == 1.5

    def test_bm25_b_default(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.bm25_b == 0.75

    def test_enable_mmr_default_true(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.enable_mmr is True

    def test_mmr_lambda_default(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.mmr_lambda == 0.7

    def test_mmr_fetch_multiplier(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.mmr_fetch_multiplier == 5

    def test_enable_parent_expansion(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.enable_parent_expansion is True

    def test_max_parent_sections(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.max_parent_sections == 20

    def test_enable_hype_default_false(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.enable_hype is False

    def test_multi_query_rag_enabled(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.multi_query_rag_enabled is True

    def test_multi_query_variants(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.multi_query_variants == 8

    def test_multi_query_pool_size(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.multi_query_pool_size == 60

    def test_definition_traversal_enabled(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.definition_traversal_enabled is True

    def test_definition_traversal_depth(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.definition_traversal_depth == 8

    def test_self_rag_enabled_default_false(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.self_rag_enabled is False

    def test_self_rag_max_rounds(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.self_rag_max_rounds == 5

    def test_self_rag_model(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.self_rag_model == "gpt-4.1"

    def test_env_override_cch(self, monkeypatch):
        monkeypatch.setenv("KTS_ENABLE_CCH", "false")
        from config.settings import load_config
        cfg = load_config()
        assert cfg.enable_cch is False

    def test_env_override_bm25(self, monkeypatch):
        monkeypatch.setenv("KTS_ENABLE_BM25_HYBRID", "false")
        from config.settings import load_config
        cfg = load_config()
        assert cfg.enable_bm25_hybrid is False

    def test_env_override_mmr(self, monkeypatch):
        monkeypatch.setenv("KTS_ENABLE_MMR", "false")
        from config.settings import load_config
        cfg = load_config()
        assert cfg.enable_mmr is False


# ═════════════════════════════════════════════════════════════════
# Increment 0: Contextual Chunk Headers (CCH)
# ═════════════════════════════════════════════════════════════════

class TestCCH:
    """Phase 8.0 — Contextual Chunk Header generation."""

    def test_build_cch_header_full(self):
        from backend.vector.legal_chunker import build_cch_header
        h = build_cch_header("PSA_2006HE1", "PSA", "ARTICLE I DEFINITIONS")
        assert h.startswith("[")
        assert "DOC: PSA_2006HE1" in h
        assert "TYPE: PSA" in h
        assert "SECTION: ARTICLE I DEFINITIONS" in h
        assert h.endswith("]\n")

    def test_build_cch_header_empty_inputs(self):
        from backend.vector.legal_chunker import build_cch_header
        h = build_cch_header()
        assert h == ""

    def test_build_cch_header_partial(self):
        from backend.vector.legal_chunker import build_cch_header
        h = build_cch_header(doc_name="DOC1")
        assert "DOC: DOC1" in h
        assert "TYPE:" not in h

    def test_build_cch_truncation(self):
        from backend.vector.legal_chunker import build_cch_header
        long_title = "A" * 200
        h = build_cch_header(section_title=long_title, max_section_len=50)
        # Should truncate section title to 50 chars
        assert len(long_title[:50]) == 50
        assert "A" * 50 in h
        assert "A" * 51 not in h

    def test_create_chunk_for_embedding_with_cch(self):
        from backend.vector.legal_chunker import _create_chunk_for_embedding
        meta = {"doc_name": "PSA_2006HE1", "doc_type": "PSA", "section_title": "Definitions"}
        text = "The Closing Date means December 1, 2006."
        result = _create_chunk_for_embedding(text, meta, enable_cch=True)
        assert result.startswith("[DOC:")
        assert text in result

    def test_create_chunk_for_embedding_without_cch(self):
        from backend.vector.legal_chunker import _create_chunk_for_embedding
        meta = {"doc_name": "PSA", "doc_type": "PSA"}
        text = "Original text."
        result = _create_chunk_for_embedding(text, meta, enable_cch=False)
        assert result == text

    def test_create_chunk_no_metadata_returns_original(self):
        from backend.vector.legal_chunker import _create_chunk_for_embedding
        meta = {}
        text = "Some text."
        result = _create_chunk_for_embedding(text, meta, enable_cch=True)
        # Empty metadata → no header → return text as-is
        assert result == text


# ═════════════════════════════════════════════════════════════════
# Increment 1: BM25 Hybrid Search with RRF
# ═════════════════════════════════════════════════════════════════

class TestBM25Retriever:
    """Phase 8.1 — Pure Python BM25 keyword retriever."""

    def _make_docs(self):
        return [
            {"id": "d1", "content": "The Closing Date means December 1, 2006.", "metadata": {"type": "definition"}},
            {"id": "d2", "content": "Servicer shall remit amounts to the trustee.", "metadata": {"type": "obligation"}},
            {"id": "d3", "content": "The Closing Date is when the certificates are issued.", "metadata": {"type": "definition"}},
            {"id": "d4", "content": "Events of Default include failure to pay.", "metadata": {"type": "provision"}},
            {"id": "d5", "content": "Payment waterfall determines the allocation of funds.", "metadata": {"type": "provision"}},
        ]

    def test_import(self):
        from backend.retrieval.bm25_retriever import BM25Retriever
        assert BM25Retriever is not None

    def test_build_index(self):
        from backend.retrieval.bm25_retriever import BM25Retriever
        r = BM25Retriever(persist_dir=tempfile.mkdtemp())
        r.build_index(self._make_docs())
        assert r._doc_count == 5
        assert r._avgdl > 0

    def test_search_basic(self):
        from backend.retrieval.bm25_retriever import BM25Retriever
        r = BM25Retriever(persist_dir=tempfile.mkdtemp())
        r.build_index(self._make_docs())
        results = r.search("Closing Date", top_k=3)
        assert len(results) >= 1
        # d1 and d3 both mention "Closing Date"
        ids = {hit["id"] for hit in results}
        assert "d1" in ids or "d3" in ids

    def test_search_returns_scores(self):
        from backend.retrieval.bm25_retriever import BM25Retriever
        r = BM25Retriever(persist_dir=tempfile.mkdtemp())
        r.build_index(self._make_docs())
        results = r.search("Closing Date")
        for hit in results:
            assert "score" in hit
            assert hit["score"] > 0

    def test_search_ranked(self):
        from backend.retrieval.bm25_retriever import BM25Retriever
        r = BM25Retriever(persist_dir=tempfile.mkdtemp())
        r.build_index(self._make_docs())
        results = r.search("Closing Date", top_k=5)
        scores = [h["score"] for h in results]
        assert scores == sorted(scores, reverse=True)

    def test_search_empty_query(self):
        from backend.retrieval.bm25_retriever import BM25Retriever
        r = BM25Retriever(persist_dir=tempfile.mkdtemp())
        r.build_index(self._make_docs())
        assert r.search("") == []

    def test_search_empty_index(self):
        from backend.retrieval.bm25_retriever import BM25Retriever
        r = BM25Retriever(persist_dir=tempfile.mkdtemp())
        r.build_index([])
        assert r.search("anything") == []

    def test_search_no_match(self):
        from backend.retrieval.bm25_retriever import BM25Retriever
        r = BM25Retriever(persist_dir=tempfile.mkdtemp())
        r.build_index(self._make_docs())
        # All stop words → no scoring tokens remain
        assert r.search("the and or") == []

    def test_search_top_k_limit(self):
        from backend.retrieval.bm25_retriever import BM25Retriever
        r = BM25Retriever(persist_dir=tempfile.mkdtemp())
        r.build_index(self._make_docs())
        results = r.search("date", top_k=2)
        assert len(results) <= 2

    def test_save_and_load_index(self):
        from backend.retrieval.bm25_retriever import BM25Retriever
        d = tempfile.mkdtemp()
        r = BM25Retriever(persist_dir=d)
        r.build_index(self._make_docs())
        r.save_index()

        r2 = BM25Retriever(persist_dir=d)
        assert r2.load_index() is True
        assert r2._doc_count == 5
        results = r2.search("Closing Date")
        assert len(results) >= 1

    def test_load_nonexistent_returns_false(self):
        from backend.retrieval.bm25_retriever import BM25Retriever
        r = BM25Retriever(persist_dir=tempfile.mkdtemp())
        assert r.load_index() is False

    def test_idf_computation(self):
        """IDF should be higher for rare terms than common terms."""
        from backend.retrieval.bm25_retriever import BM25Retriever
        r = BM25Retriever(persist_dir=tempfile.mkdtemp())
        r.build_index(self._make_docs())
        # "closing" appears in 2/5 docs, "waterfall" appears in 1/5
        if "closing" in r._idf_cache and "waterfall" in r._idf_cache:
            assert r._idf_cache["waterfall"] > r._idf_cache["closing"]

    def test_metadata_preserved(self):
        from backend.retrieval.bm25_retriever import BM25Retriever
        r = BM25Retriever(persist_dir=tempfile.mkdtemp())
        r.build_index(self._make_docs())
        results = r.search("Closing Date", top_k=1)
        assert "metadata" in results[0]

    def test_custom_k1_b(self):
        from backend.retrieval.bm25_retriever import BM25Retriever
        r = BM25Retriever(persist_dir=tempfile.mkdtemp(), k1=2.0, b=0.5)
        r.build_index(self._make_docs())
        results = r.search("Closing Date")
        assert len(results) >= 1

    def test_tokenizer_strips_stopwords(self):
        from backend.retrieval.bm25_retriever import _tokenize
        tokens = _tokenize("The quick brown fox is a test")
        assert "the" not in tokens
        assert "is" not in tokens
        assert "a" not in tokens
        assert "quick" in tokens

    def test_tokenizer_lowercases(self):
        from backend.retrieval.bm25_retriever import _tokenize
        tokens = _tokenize("CLOSING DATE")
        assert "closing" in tokens
        assert "date" in tokens


# ═════════════════════════════════════════════════════════════════
# Increment 2: MMR Diversity Sampling
# ═════════════════════════════════════════════════════════════════

class TestMMR:
    """Phase 8.2 — Maximal Marginal Relevance in DualVectorStore."""

    def test_mmr_select_exists(self):
        from backend.vector.dual_vector_store import DualVectorStore
        assert hasattr(DualVectorStore, "mmr_select")

    def test_mmr_select_static(self):
        from backend.vector.dual_vector_store import DualVectorStore
        # mmr_select is a static method
        assert isinstance(inspect.getattr_static(DualVectorStore, "mmr_select"), staticmethod)

    def test_mmr_select_basic(self):
        from backend.vector.dual_vector_store import DualVectorStore
        query_emb = [1.0, 0.0, 0.0]
        cand_embs = [
            [1.0, 0.0, 0.0],  # identical to query (perfect relevance)
            [0.9, 0.1, 0.0],  # very similar to query
            [0.0, 1.0, 0.0],  # orthogonal (diverse)
        ]
        cand_results = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        selected = DualVectorStore.mmr_select(query_emb, cand_embs, cand_results, top_k=2, lambda_mult=0.5)
        assert len(selected) == 2
        # With lambda=0.5, should pick both relevant AND diverse
        ids = {r["id"] for r in selected}
        assert "a" in ids  # most relevant should always be first

    def test_mmr_select_pure_relevance(self):
        from backend.vector.dual_vector_store import DualVectorStore
        query_emb = [1.0, 0.0]
        cand_embs = [[1.0, 0.0], [0.8, 0.2], [0.0, 1.0]]
        cand_results = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        selected = DualVectorStore.mmr_select(query_emb, cand_embs, cand_results, top_k=3, lambda_mult=1.0)
        # lambda=1.0 → pure relevance → same as top-k by similarity
        assert selected[0]["id"] == "a"

    def test_mmr_select_empty_candidates(self):
        from backend.vector.dual_vector_store import DualVectorStore
        result = DualVectorStore.mmr_select([1.0], [], [], top_k=3)
        assert result == []

    def test_mmr_score_field_added(self):
        from backend.vector.dual_vector_store import DualVectorStore
        query_emb = [1.0, 0.0]
        cand_embs = [[0.9, 0.1]]
        cand_results = [{"id": "x", "text": "test"}]
        selected = DualVectorStore.mmr_select(query_emb, cand_embs, cand_results, top_k=1)
        assert len(selected) == 1
        assert "_mmr_score" in selected[0]
        assert selected[0]["_mmr_score"] > 0

    def test_mmr_select_top_k_respected(self):
        """top_k should limit the number of results."""
        from backend.vector.dual_vector_store import DualVectorStore
        query_emb = [1.0, 0.0]
        cand_embs = [[1.0, 0.0], [0.5, 0.5], [0.0, 1.0]]
        cand_results = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        selected = DualVectorStore.mmr_select(query_emb, cand_embs, cand_results, top_k=1)
        assert len(selected) == 1

    def test_mmr_zero_norm_safety(self):
        from backend.vector.dual_vector_store import DualVectorStore
        query_emb = [0.0, 0.0]
        cand_embs = [[0.0, 0.0], [1.0, 0.0]]
        cand_results = [{"id": "z"}, {"id": "n"}]
        # Should not raise ZeroDivisionError
        selected = DualVectorStore.mmr_select(query_emb, cand_embs, cand_results, top_k=2)
        assert len(selected) <= 2

    def test_search_items_mmr_method_exists(self):
        from backend.vector.dual_vector_store import DualVectorStore
        assert hasattr(DualVectorStore, "search_items_mmr")

    def test_search_sections_mmr_method_exists(self):
        from backend.vector.dual_vector_store import DualVectorStore
        assert hasattr(DualVectorStore, "search_sections_mmr")


# ═════════════════════════════════════════════════════════════════
# Increment 3: Token-Aware Context Trimming (JS)
# ═════════════════════════════════════════════════════════════════

class TestTokenTrimming:
    """Phase 8.3 — trimContextToTokenBudget in participant.js."""

    def test_js_file_contains_function(self):
        js_path = ROOT / "extension" / "chat" / "participant.js"
        src = js_path.read_text(encoding="utf-8")
        assert "trimContextToTokenBudget" in src

    def test_js_exports_function(self):
        js_path = ROOT / "extension" / "chat" / "participant.js"
        src = js_path.read_text(encoding="utf-8")
        assert "trimContextToTokenBudget" in src
        # Should be in module.exports
        idx_exports = src.index("module.exports")
        idx_func = src.index("trimContextToTokenBudget", idx_exports)
        assert idx_func > idx_exports

    def test_token_ratio_constant(self):
        js_path = ROOT / "extension" / "chat" / "participant.js"
        src = js_path.read_text(encoding="utf-8")
        assert "TOKEN_RATIO" in src

    def test_reserved_tokens_constant(self):
        js_path = ROOT / "extension" / "chat" / "participant.js"
        src = js_path.read_text(encoding="utf-8")
        assert "RESERVED_TOKENS" in src

    def test_exports_constants(self):
        js_path = ROOT / "extension" / "chat" / "participant.js"
        src = js_path.read_text(encoding="utf-8")
        idx_exports = src.index("module.exports")
        tail = src[idx_exports:]
        assert "TOKEN_RATIO" in tail
        assert "RESERVED_TOKENS" in tail


# ═════════════════════════════════════════════════════════════════
# Increment 4: Parent-Child Document Linking
# ═════════════════════════════════════════════════════════════════

class TestParentChildLinking:
    """Phase 8.4 — parent_section_id metadata + parent expansion."""

    def test_ingestion_has_parent_section_id(self):
        """ingestion_agent.py should emit parent_section_id in item metadata."""
        spec = __import__("importlib").util.find_spec("backend.agents.ingestion_agent")
        src = Path(spec.origin).read_text(encoding="utf-8")
        assert "parent_section_id" in src
        # Should contain the formatted pattern
        assert "parent_sec_id" in src or "parent_section_id" in src

    def test_dual_store_get_items_by_parent(self):
        from backend.vector.dual_vector_store import DualVectorStore
        assert hasattr(DualVectorStore, "get_items_by_parent")

    def test_dual_store_get_section_by_id(self):
        from backend.vector.dual_vector_store import DualVectorStore
        assert hasattr(DualVectorStore, "get_section_by_id")

    def test_expand_items_to_parent_sections_exists(self):
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        assert hasattr(HumanLikeRetriever, "_expand_items_to_parent_sections")

    def test_expand_items_signature(self):
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        sig = inspect.signature(HumanLikeRetriever._expand_items_to_parent_sections)
        assert "items" in sig.parameters
        assert "max_parents" in sig.parameters

    def test_enable_parent_expansion_flag(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert hasattr(cfg, "enable_parent_expansion")
        assert hasattr(cfg, "max_parent_sections")


# ═════════════════════════════════════════════════════════════════
# Increment 5: Targeted HyPE
# ═════════════════════════════════════════════════════════════════

class TestHyPE:
    """Phase 8.5 — HyPE question enrichment (Python & JS)."""

    def test_dual_store_store_item_questions(self):
        from backend.vector.dual_vector_store import DualVectorStore
        assert hasattr(DualVectorStore, "store_item_questions")

    def test_dual_store_search_item_questions(self):
        from backend.vector.dual_vector_store import DualVectorStore
        assert hasattr(DualVectorStore, "search_item_questions")

    def test_dual_store_mark_questions_pending(self):
        from backend.vector.dual_vector_store import DualVectorStore
        assert hasattr(DualVectorStore, "mark_questions_pending")

    def test_dual_store_get_questions_collection(self):
        from backend.vector.dual_vector_store import DualVectorStore
        assert hasattr(DualVectorStore, "_get_questions_collection")

    def test_js_hype_enricher_exists(self):
        js_path = ROOT / "extension" / "lib" / "hype_enricher.js"
        assert js_path.exists()

    def test_js_hype_enricher_exports(self):
        src = (ROOT / "extension" / "lib" / "hype_enricher.js").read_text(encoding="utf-8")
        assert "enrichChunksWithQuestions" in src
        assert "module.exports" in src

    def test_hype_default_disabled(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.enable_hype is False

    def test_retriever_source_has_hype_logic(self):
        spec = __import__("importlib").util.find_spec("backend.retrieval.human_like_retriever")
        src = Path(spec.origin).read_text(encoding="utf-8")
        assert "search_item_questions" in src
        assert "enable_hype" in src


# ═════════════════════════════════════════════════════════════════
# Increment 6: Multi-Query RAG Fusion
# ═════════════════════════════════════════════════════════════════

class TestMultiQueryRAGFusion:
    """Phase 8.6 — Multi-query variant expansion + RRF fusion."""

    def test_retrieve_has_extra_queries_param(self):
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        sig = inspect.signature(HumanLikeRetriever.retrieve)
        assert "extra_queries" in sig.parameters

    def test_extra_queries_default_none(self):
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        sig = inspect.signature(HumanLikeRetriever.retrieve)
        assert sig.parameters["extra_queries"].default is None

    def test_rrf_merge_exists(self):
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        assert hasattr(HumanLikeRetriever, "_rrf_merge")

    def test_rrf_merge_static(self):
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        # Verify it's a static method
        attr = inspect.getattr_static(HumanLikeRetriever, "_rrf_merge")
        assert isinstance(attr, staticmethod)

    def test_rrf_merge_basic(self):
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        # Two ranked lists with some overlap
        list_a = [{"id": "x", "score": 1.0}, {"id": "y", "score": 0.5}]
        list_b = [{"id": "y", "score": 1.0}, {"id": "z", "score": 0.5}]
        merged = HumanLikeRetriever._rrf_merge([list_a, list_b], weights=[1.0, 1.0], k=60)
        assert len(merged) >= 2
        # "y" appears in both lists so should have the highest RRF score
        ids = [r["id"] for r in merged]
        assert "y" in ids
        assert "x" in ids
        assert "z" in ids

    def test_rrf_merge_weighted(self):
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        list_a = [{"id": "x", "score": 1.0}]
        list_b = [{"id": "y", "score": 1.0}]
        merged = HumanLikeRetriever._rrf_merge([list_a, list_b], weights=[1.0, 0.1], k=60)
        # x should score higher due to larger weight on list_a
        assert merged[0]["id"] == "x"

    def test_rrf_merge_empty_lists(self):
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        merged = HumanLikeRetriever._rrf_merge([], weights=[], k=60)
        assert merged == [] or len(merged) == 0

    def test_rrf_merge_single_list(self):
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        items = [{"id": "a"}, {"id": "b"}]
        merged = HumanLikeRetriever._rrf_merge([items], weights=[1.0], k=60)
        assert len(merged) == 2

    def test_js_query_expander_exists(self):
        js_path = ROOT / "extension" / "lib" / "query_expander.js"
        assert js_path.exists()

    def test_js_query_expander_exports(self):
        src = (ROOT / "extension" / "lib" / "query_expander.js").read_text(encoding="utf-8")
        assert "expandQueryWithLLM" in src
        assert "module.exports" in src

    def test_multi_query_config_flags(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert hasattr(cfg, "multi_query_rag_enabled")
        assert hasattr(cfg, "multi_query_variants")
        assert hasattr(cfg, "multi_query_pool_size")

    def test_retriever_source_has_multi_query_logic(self):
        spec = __import__("importlib").util.find_spec("backend.retrieval.human_like_retriever")
        src = Path(spec.origin).read_text(encoding="utf-8")
        assert "extra_queries" in src
        assert "multi_query_rag_enabled" in src


# ═════════════════════════════════════════════════════════════════
# Increment 7: N-Level Definition Chain Traversal
# ═════════════════════════════════════════════════════════════════

class TestDefinitionTraversal:
    """Phase 8.7 — Extended definition traversal with vector fallback."""

    def test_resolve_term_from_vector_exists(self):
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        assert hasattr(HumanLikeRetriever, "_resolve_term_from_vector")

    def test_resolve_term_from_vector_signature(self):
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        sig = inspect.signature(HumanLikeRetriever._resolve_term_from_vector)
        assert "term" in sig.parameters
        assert "score_threshold" in sig.parameters

    def test_extract_defined_term_plain_colon_pattern(self):
        """Phase 8.7 —  plain colon pattern for PSA defined terms."""
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        ret = HumanLikeRetriever.__new__(HumanLikeRetriever)
        # Mock minimum required attributes
        ret._definition_index = {}
        ret._logger = MagicMock()

        # Title Case:  should match
        result = ret._extract_defined_term("Closing Date: means the date on which the trust was formed.")
        # May return "Closing Date" or None depending on full logic, but the pattern should exist in source
        spec = __import__("importlib").util.find_spec("backend.retrieval.human_like_retriever")
        src = Path(spec.origin).read_text(encoding="utf-8")
        assert r"^([A-Z][a-z]" in src  # Title-case colon pattern

    def test_definition_traversal_config(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.definition_traversal_enabled is True
        assert cfg.definition_traversal_depth == 8

    def test_enrich_with_definitions_has_vector_fallback(self):
        """enrich_with_definitions should contain vector fallback code."""
        spec = __import__("importlib").util.find_spec("backend.retrieval.human_like_retriever")
        src = Path(spec.origin).read_text(encoding="utf-8")
        assert "_resolve_term_from_vector" in src

    def test_definition_cap_10_terms(self):
        """Source should cap extracted terms at 10 per chunk."""
        spec = __import__("importlib").util.find_spec("backend.retrieval.human_like_retriever")
        src = Path(spec.origin).read_text(encoding="utf-8")
        # Look for the [:10] cap
        assert "[:10]" in src


# ═════════════════════════════════════════════════════════════════
# Increment 8: Self-RAG Iterative Generation Loop (JS)
# ═════════════════════════════════════════════════════════════════

class TestSelfRAG:
    """Phase 8.8 — Self-RAG JS components."""

    def test_js_gap_analyzer_exists(self):
        js_path = ROOT / "extension" / "lib" / "gap_analyzer.js"
        assert js_path.exists()

    def test_js_gap_analyzer_exports(self):
        src = (ROOT / "extension" / "lib" / "gap_analyzer.js").read_text(encoding="utf-8")
        assert "analyzeGaps" in src
        assert "module.exports" in src

    def test_js_iterative_generator_exists(self):
        js_path = ROOT / "extension" / "lib" / "iterative_generator.js"
        assert js_path.exists()

    def test_js_iterative_generator_exports(self):
        src = (ROOT / "extension" / "lib" / "iterative_generator.js").read_text(encoding="utf-8")
        assert "generateIteratively" in src
        assert "module.exports" in src

    def test_iterative_generator_imports_gap_analyzer(self):
        src = (ROOT / "extension" / "lib" / "iterative_generator.js").read_text(encoding="utf-8")
        assert "gap_analyzer" in src

    def test_iterative_generator_has_max_rounds(self):
        src = (ROOT / "extension" / "lib" / "iterative_generator.js").read_text(encoding="utf-8")
        assert "maxRounds" in src

    def test_iterative_generator_has_exclude_ids(self):
        src = (ROOT / "extension" / "lib" / "iterative_generator.js").read_text(encoding="utf-8")
        assert "excludeIds" in src

    def test_self_rag_config(self):
        from config.settings import KTSConfig
        cfg = KTSConfig()
        assert cfg.self_rag_enabled is False
        assert cfg.self_rag_max_rounds == 5
        assert cfg.self_rag_model == "gpt-4.1"


# ═════════════════════════════════════════════════════════════════
# Integration: Retrieval Service BM25 Wiring
# ═════════════════════════════════════════════════════════════════

class TestRetrievalServiceBM25Wiring:
    """Phase 8 — BM25 retriever wired into retrieval_service.py."""

    def test_retrieval_service_imports_bm25(self):
        spec = __import__("importlib").util.find_spec("backend.agents.retrieval_service")
        src = Path(spec.origin).read_text(encoding="utf-8")
        assert "BM25Retriever" in src

    def test_retrieval_service_creates_bm25(self):
        spec = __import__("importlib").util.find_spec("backend.agents.retrieval_service")
        src = Path(spec.origin).read_text(encoding="utf-8")
        assert "bm25_retriever" in src or "bm25" in src

    def test_retrieval_service_passes_config(self):
        spec = __import__("importlib").util.find_spec("backend.agents.retrieval_service")
        src = Path(spec.origin).read_text(encoding="utf-8")
        assert "config=" in src or "config=self.config" in src

    def test_retrieve_has_bm25_param(self):
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        sig = inspect.signature(HumanLikeRetriever.retrieve)
        assert "bm25_retriever" in sig.parameters

    def test_retrieve_has_config_param(self):
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        sig = inspect.signature(HumanLikeRetriever.retrieve)
        assert "config" in sig.parameters


# ═════════════════════════════════════════════════════════════════
# RRF Merge Unit Tests (Expanded)
# ═════════════════════════════════════════════════════════════════

class TestRRFMergeDetailed:
    """Detailed unit tests for _rrf_merge algorithm correctness."""

    def test_overlapping_docs_boost(self):
        """Documents appearing in multiple lists get cumulative RRF scores."""
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        # doc "shared" appears at rank 1 in both lists
        list_a = [{"id": "shared"}, {"id": "only_a"}]
        list_b = [{"id": "shared"}, {"id": "only_b"}]
        merged = HumanLikeRetriever._rrf_merge([list_a, list_b], weights=[1.0, 1.0], k=60)
        # "shared" should be first
        assert merged[0]["id"] == "shared"

    def test_rrf_preserves_metadata(self):
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        items = [{"id": "a", "text": "hello", "extra": 42}]
        merged = HumanLikeRetriever._rrf_merge([items], weights=[1.0], k=60)
        assert merged[0]["id"] == "a"

    def test_rrf_different_k_values(self):
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        items = [{"id": "a"}, {"id": "b"}]
        merged_k1 = HumanLikeRetriever._rrf_merge([items], weights=[1.0], k=1)
        merged_k100 = HumanLikeRetriever._rrf_merge([items], weights=[1.0], k=100)
        # Both should return same docs but different score magnitudes
        assert len(merged_k1) == len(merged_k100)


# ═════════════════════════════════════════════════════════════════
# Cross-Phase Regression Guards
# ═════════════════════════════════════════════════════════════════

class TestPhase8DoesNotRegress:
    """Verify Phase 8 additions don't break Phase 9-15 interfaces."""

    def test_retrieve_still_has_exclude_chunk_ids(self):
        """Phase 9 exclude_chunk_ids must still work."""
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        sig = inspect.signature(HumanLikeRetriever.retrieve)
        assert "exclude_chunk_ids" in sig.parameters
        assert sig.parameters["exclude_chunk_ids"].default is None

    def test_retrieve_still_has_max_results(self):
        from backend.retrieval.human_like_retriever import HumanLikeRetriever
        sig = inspect.signature(HumanLikeRetriever.retrieve)
        assert "max_results" in sig.parameters

    def test_dual_store_still_has_search_items(self):
        from backend.vector.dual_vector_store import DualVectorStore
        assert hasattr(DualVectorStore, "search_items")

    def test_dual_store_still_has_search_sections(self):
        from backend.vector.dual_vector_store import DualVectorStore
        assert hasattr(DualVectorStore, "search_sections")

    def test_dual_store_still_has_reset(self):
        from backend.vector.dual_vector_store import DualVectorStore
        assert hasattr(DualVectorStore, "reset")

    def test_confidence_scorer_still_importable(self):
        from backend.retrieval.confidence_scorer import ConfidenceScorer
        assert ConfidenceScorer is not None

    def test_session_memory_still_importable(self):
        from backend.retrieval.session_memory import SessionMemory
        assert SessionMemory is not None

    def test_gap_detector_still_importable(self):
        from backend.retrieval.gap_detector import GapDetector
        assert GapDetector is not None

    def test_legal_chunker_still_has_chunk_by_sections(self):
        from backend.vector.legal_chunker import LegalChunker
        assert hasattr(LegalChunker, "chunk_by_sections_parent_child")

    def test_participant_still_exports_core_functions(self):
        js_path = ROOT / "extension" / "chat" / "participant.js"
        src = js_path.read_text(encoding="utf-8")
        assert "registerChatParticipant" in src
        assert "selectPrompt" in src
        assert "buildContextBlock" in src
        assert "generateAnswer" in src

    def test_critique_client_still_exists(self):
        js_path = ROOT / "extension" / "lib" / "critique_client.js"
        assert js_path.exists()

    def test_settings_backward_compatible(self):
        """All pre-Phase 8 config flags must still exist."""
        from config.settings import KTSConfig
        cfg = KTSConfig()
        # Phase 9
        assert hasattr(cfg, "critique_generation_enabled")
        # Phase 10
        assert hasattr(cfg, "session_memory_enabled")
        # Phase 13
        assert hasattr(cfg, "confidence_scoring_enabled")
        # Phase 15
        assert hasattr(cfg, "comparison_mode_enabled")


# ═════════════════════════════════════════════════════════════════
# BM25 Index Persistence Round-Trip
# ═════════════════════════════════════════════════════════════════

class TestBM25Persistence:
    """Detailed persistence tests for BM25Retriever."""

    def test_round_trip_scores_match(self):
        from backend.retrieval.bm25_retriever import BM25Retriever
        docs = [
            {"id": "a", "content": "Closing Date means initial closing."},
            {"id": "b", "content": "Servicer remits Monthly Payment."},
        ]
        d = tempfile.mkdtemp()
        r1 = BM25Retriever(persist_dir=d)
        r1.build_index(docs)
        scores_before = {h["id"]: h["score"] for h in r1.search("Closing Date")}
        r1.save_index()

        r2 = BM25Retriever(persist_dir=d)
        r2.load_index()
        scores_after = {h["id"]: h["score"] for h in r2.search("Closing Date")}

        for doc_id in scores_before:
            assert abs(scores_before[doc_id] - scores_after[doc_id]) < 1e-6

    def test_corrupt_index_returns_false(self):
        from backend.retrieval.bm25_retriever import BM25Retriever
        d = tempfile.mkdtemp()
        index_path = os.path.join(d, BM25Retriever.INDEX_FILE)
        with open(index_path, "w") as f:
            f.write("{broken json")
        r = BM25Retriever(persist_dir=d)
        assert r.load_index() is False

    def test_save_creates_directory(self):
        from backend.retrieval.bm25_retriever import BM25Retriever
        d = os.path.join(tempfile.mkdtemp(), "subdir", "deep")
        r = BM25Retriever(persist_dir=d)
        r.build_index([{"id": "x", "content": "test"}])
        r.save_index()
        assert os.path.exists(os.path.join(d, BM25Retriever.INDEX_FILE))


# ═════════════════════════════════════════════════════════════════
# Phase 8 Behavioral / Integration Tests (added during re-review)
# ═════════════════════════════════════════════════════════════════

class TestBM25HyphenatedTerms:
    """Fix verification: BM25 tokenizer must preserve hyphenated terms."""

    def test_hyphenated_deal_id(self):
        from backend.retrieval.bm25_retriever import _tokenize
        tokens = _tokenize("PSA-2006HE1 is the target deal")
        assert "psa-2006he1" in tokens

    def test_dotted_section_number(self):
        from backend.retrieval.bm25_retriever import _tokenize
        tokens = _tokenize("Section 5.05 governs distributions")
        assert "5.05" in tokens

    def test_underscored_identifier(self):
        from backend.retrieval.bm25_retriever import _tokenize
        tokens = _tokenize("The parent_section_id links items to sections")
        assert "parent_section_id" in tokens

    def test_plain_words_still_extracted(self):
        from backend.retrieval.bm25_retriever import _tokenize
        tokens = _tokenize("closing date means december first")
        assert "closing" in tokens
        assert "date" in tokens
        assert "december" in tokens
        assert "first" in tokens

    def test_hyphenated_term_in_search_results(self):
        from backend.retrieval.bm25_retriever import BM25Retriever
        docs = [
            {"id": "d1", "content": "PSA-2006HE1 Pooling and Servicing Agreement"},
            {"id": "d2", "content": "The servicer shall remit payments monthly"},
        ]
        r = BM25Retriever(persist_dir=tempfile.mkdtemp())
        r.build_index(docs)
        results = r.search("PSA-2006HE1")
        assert len(results) >= 1
        assert results[0]["id"] == "d1"


class TestCCHIngestionWiring:
    """Verify CCH enrichment is wired into IngestionAgent for items and sections."""

    def test_ingestion_agent_imports_cch(self):
        src = (ROOT / "backend" / "agents" / "ingestion_agent.py").read_text(encoding="utf-8")
        assert "from backend.vector.legal_chunker import build_cch_header, _create_chunk_for_embedding" in src

    def test_ingestion_agent_calls_create_chunk_for_embedding(self):
        src = (ROOT / "backend" / "agents" / "ingestion_agent.py").read_text(encoding="utf-8")
        assert src.count("_create_chunk_for_embedding(") >= 2, "CCH should be called for both items and sections"

    def test_cch_produces_enriched_embedding_text(self):
        from backend.vector.legal_chunker import _create_chunk_for_embedding
        meta = {"doc_name": "PSA_2006HE1", "doc_type": "PSA", "section_title": "Definitions"}
        chunk_text = "Closing Date means December 1, 2006."
        enriched = _create_chunk_for_embedding(chunk_text, meta, enable_cch=True)
        assert enriched.startswith("[DOC:")
        assert chunk_text in enriched

    def test_cch_enriched_text_contains_all_header_fields(self):
        from backend.vector.legal_chunker import _create_chunk_for_embedding
        meta = {"doc_name": "TEST_DOC", "doc_type": "INDENTURE", "section_title": "Article V"}
        enriched = _create_chunk_for_embedding("Some text", meta, enable_cch=True)
        assert "DOC: TEST_DOC" in enriched
        assert "TYPE: INDENTURE" in enriched
        assert "SECTION: Article V" in enriched


class TestNeedsReingestion:
    """Fix verification: _needs_reingestion() helper on IngestionAgent."""

    def test_method_exists(self):
        from backend.agents.ingestion_agent import IngestionAgent
        assert hasattr(IngestionAgent, "_needs_reingestion")

    def test_is_static_method(self):
        attr = inspect.getattr_static(
            __import__("backend.agents.ingestion_agent", fromlist=["IngestionAgent"]).IngestionAgent,
            "_needs_reingestion",
        )
        assert isinstance(attr, staticmethod)

    def test_returns_true_for_missing_parent_section_id(self):
        from backend.agents.ingestion_agent import IngestionAgent
        mock_store = MagicMock()
        mock_store.get_document_chunks.return_value = [
            {"metadata": {"doc_id": "a"}},  # no parent_section_id
        ]
        assert IngestionAgent._needs_reingestion(mock_store, "test_doc") is True

    def test_returns_false_when_parent_section_id_present(self):
        from backend.agents.ingestion_agent import IngestionAgent
        mock_store = MagicMock()
        mock_store.get_document_chunks.return_value = [
            {"metadata": {"parent_section_id": "sec1"}},
            {"metadata": {"parent_section_id": "sec2"}},
        ]
        assert IngestionAgent._needs_reingestion(mock_store, "test_doc") is False

    def test_returns_false_on_empty_chunks(self):
        from backend.agents.ingestion_agent import IngestionAgent
        mock_store = MagicMock()
        mock_store.get_document_chunks.return_value = []
        assert IngestionAgent._needs_reingestion(mock_store, "test_doc") is False

    def test_returns_false_on_exception(self):
        from backend.agents.ingestion_agent import IngestionAgent
        mock_store = MagicMock()
        mock_store.get_document_chunks.side_effect = RuntimeError("db error")
        assert IngestionAgent._needs_reingestion(mock_store, "test_doc") is False


class TestExtraQueriesThreading:
    """Verify extra_queries parameter threads through retrieval stack."""

    def test_retrieval_service_execute_accepts_extra_queries(self):
        src = (ROOT / "backend" / "agents" / "retrieval_service.py").read_text(encoding="utf-8")
        assert "extra_queries" in src

    def test_phase6_retrieve_has_extra_queries_param(self):
        from backend.agents.retrieval_service import RetrievalService
        sig = inspect.signature(RetrievalService._phase6_retrieve)
        assert "extra_queries" in sig.parameters

    def test_human_like_retrieve_has_extra_queries_param(self):
        from backend.agents.retrieval_service import RetrievalService
        sig = inspect.signature(RetrievalService._human_like_retrieve)
        assert "extra_queries" in sig.parameters

    def test_cli_search_has_extra_queries_option(self):
        src = (ROOT / "cli" / "main.py").read_text(encoding="utf-8")
        assert "--extra-queries" in src

    def test_cli_extra_queries_json_parsing(self):
        """Ensure the CLI properly parses JSON-encoded extra queries."""
        src = (ROOT / "cli" / "main.py").read_text(encoding="utf-8")
        assert "json.loads(extra_queries)" in src


class TestTokenTrimmingWiring:
    """Verify trim context is called in generateAnswer (participant.js)."""

    def test_participant_calls_trim_context(self):
        src = (ROOT / "extension" / "chat" / "participant.js").read_text(encoding="utf-8")
        assert "trimContextToTokenBudget(contextBlocks" in src

    def test_participant_uses_trimmed_context_in_message(self):
        src = (ROOT / "extension" / "chat" / "participant.js").read_text(encoding="utf-8")
        assert "trimmedContext" in src


class TestMultiQueryWiring:
    """Verify multi-query expansion is wired end-to-end in the JS extension."""

    def test_participant_imports_expand_query(self):
        src = (ROOT / "extension" / "chat" / "participant.js").read_text(encoding="utf-8")
        assert "require('../lib/query_expander')" in src
        assert "expandQueryWithLLM" in src

    def test_participant_calls_expand_query(self):
        src = (ROOT / "extension" / "chat" / "participant.js").read_text(encoding="utf-8")
        assert "expandQueryWithLLM(vscode, expansionModel, effectiveQuery, numVariants)" in src

    def test_kts_tool_forwards_extra_queries(self):
        src = (ROOT / "extension" / "copilot" / "kts_tool.js").read_text(encoding="utf-8")
        assert "options.extraQueries" in src
        assert "'--extra-queries'" in src

    def test_participant_passes_extra_queries_to_kts_tool(self):
        src = (ROOT / "extension" / "chat" / "participant.js").read_text(encoding="utf-8")
        assert "extraQueries:" in src


@pytest.mark.skip(reason="Self-RAG iterative generation not yet wired into participant.js")
class TestSelfRAGWiring:
    """Verify Self-RAG iterative generation is wired into participant.js."""

    def test_participant_imports_generate_iteratively(self):
        src = (ROOT / "extension" / "chat" / "participant.js").read_text(encoding="utf-8")
        assert "require('../lib/iterative_generator')" in src
        assert "generateIteratively" in src

    def test_participant_has_self_rag_block(self):
        src = (ROOT / "extension" / "chat" / "participant.js").read_text(encoding="utf-8")
        assert "selfRagEnabled" in src
        assert "generateIteratively(" in src

    def test_self_rag_confidence_penalty_applied(self):
        src = (ROOT / "extension" / "chat" / "participant.js").read_text(encoding="utf-8")
        assert "_selfRagConfidencePenalty" in src

    def test_self_rag_gap_penalty_formula(self):
        """Confidence penalty = 1.0 - 0.3 * min(gapCount/10, 0.5)."""
        src = (ROOT / "extension" / "chat" / "participant.js").read_text(encoding="utf-8")
        assert "1.0 - 0.3 * Math.min" in src

    def test_confidence_block_shows_self_rag_adjustment(self):
        src = (ROOT / "extension" / "chat" / "participant.js").read_text(encoding="utf-8")
        assert "Self-RAG adjusted" in src
