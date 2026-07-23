"""
Hybrid Retrieval Engine — Graph + Dense Vector + Sparse BM25

Implements three-stage retrieval exclusively for financial and legal documents:

Stage 1 — Parallel Retrieval (three independent signals)
    ├─ Dense: ChromaDB cosine similarity (BGE ONNX INT8, 768-dim)
    ├─ Sparse: BM25 keyword search (Okapi BM25, domain-tuned stopwords)
    └─ Graph: Knowledge-graph entity expansion + neighbour retrieval

Stage 2 — Reciprocal Rank Fusion (RRF)
    All three ranked lists are merged via RRF(k=60) then domain-boosted:
    ├─ Financial/legal term score multiplier
    ├─ Section heading boost (waterfall, definitions, etc.)
    └─ Doc-regime weight (penalise off-domain documents)

Stage 3 — Cross-Encoder Reranking (optional)
    Top-N candidates are pairwise re-scored with an ONNX cross-encoder.

Usage::

    engine = HybridRetrievalEngine(config, vector_store, graph_store, bm25_retriever)
    results = engine.retrieve("What is the payment waterfall priority?", top_k=10)

Each result dict contains:
    {
        "chunk_id": str,
        "content": str,
        "score": float,          # final hybrid score (RRF + boosts)
        "rrf_score": float,      # raw RRF score before domain boosts
        "vector_rank": int|None,
        "bm25_rank": int|None,
        "graph_rank": int|None,
        "metadata": dict,
        "retrieval_signals": dict,   # explainability: which stages contributed
    }
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ── RRF constant (k=60 is the classic default) ─────────────────────────
_RRF_K = 60

# ── Graph traversal depth for entity expansion ─────────────────────────
_GRAPH_BFS_DEPTH = 2

# ── Maximum candidates from each stage before fusion ───────────────────
_STAGE_TOP_K_MULTIPLIER = 3  # retrieve 3× final top_k per stage


# ── Result dataclass ────────────────────────────────────────────────────

@dataclass
class HybridResult:
    chunk_id: str
    content: str
    score: float
    rrf_score: float = 0.0
    vector_rank: Optional[int] = None
    bm25_rank: Optional[int] = None
    graph_rank: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    retrieval_signals: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "score": self.score,
            "rrf_score": self.rrf_score,
            "vector_rank": self.vector_rank,
            "bm25_rank": self.bm25_rank,
            "graph_rank": self.graph_rank,
            "metadata": self.metadata,
            "retrieval_signals": self.retrieval_signals,
        }


# ── Engine ──────────────────────────────────────────────────────────────

class HybridRetrievalEngine:
    """
    Three-signal hybrid retrieval for financial and legal documents.

    Parameters
    ----------
    config : KTSConfig
        System configuration.
    vector_store : VectorStore
        ChromaDB-backed dense retrieval.
    graph_store : GraphStore | None
        NetworkX knowledge graph for entity expansion.
    bm25_retriever : BM25Retriever | None
        Pre-built BM25 index.  If None, sparse retrieval is skipped.
    cross_encoder_enabled : bool
        Whether to run Stage 3 cross-encoder reranking.
    vector_weight : float
        RRF score weight for dense vector signal (default 1.0).
    bm25_weight : float
        RRF score weight for BM25 signal (default 1.0).
    graph_weight : float
        RRF score weight for graph-expansion signal (default 0.6).
    """

    def __init__(
        self,
        config,
        vector_store,
        graph_store=None,
        bm25_retriever=None,
        *,
        cross_encoder_enabled: bool = True,
        vector_weight: float = 1.0,
        bm25_weight: float = 1.0,
        graph_weight: float = 0.6,
    ) -> None:
        self.config = config
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.bm25_retriever = bm25_retriever
        self.cross_encoder_enabled = cross_encoder_enabled
        self.w_vector = vector_weight
        self.w_bm25 = bm25_weight
        self.w_graph = graph_weight

        # Lazy-import domain module to avoid circular deps
        from backend.retrieval.financial_legal_domain import (
            detect_financial_intent,
            expand_financial_query,
            get_doc_regime_weight,
            score_section_boost,
            FINANCIAL_TERM_BOOSTS,
        )
        self._detect_intent = detect_financial_intent
        self._expand_query = expand_financial_query
        self._regime_weight = get_doc_regime_weight
        self._section_boost = score_section_boost
        self._term_boosts = FINANCIAL_TERM_BOOSTS

    # ── Public API ─────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 10,
        scope: Optional[str] = None,
        doc_type_filter: Optional[str] = None,
        include_graph: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Execute three-stage hybrid retrieval and return ranked results.

        Parameters
        ----------
        query : str
            Natural-language query (financial/legal domain).
        top_k : int
            Number of final results to return.
        scope : str | None
            Deal scope identifier for scoped vector collections.
        doc_type_filter : str | None
            Restrict to a specific document type.
        include_graph : bool
            Whether to include graph-expansion stage (disable if no graph).

        Returns
        -------
        List[Dict]
            Ranked list of result dicts (see module docstring for schema).
        """
        stage_k = max(top_k * _STAGE_TOP_K_MULTIPLIER, 20)

        # ── Domain intent detection ─────────────────────────────────
        intent, priority_doc_types = self._detect_intent(query)
        expanded_query = self._expand_query(query)

        logger.debug("[HybridEngine] query=%r intent=%s expanded=%r",
                     query, intent, expanded_query)

        # ── Stage 1a: Dense vector retrieval ───────────────────────
        vector_results = self._retrieve_vector(
            expanded_query, stage_k, scope=scope, doc_type_filter=doc_type_filter
        )

        # ── Stage 1b: BM25 sparse retrieval ────────────────────────
        bm25_results = self._retrieve_bm25(expanded_query, stage_k)

        # ── Stage 1c: Graph entity-expansion retrieval ─────────────
        graph_results: List[Dict[str, Any]] = []
        if include_graph and self.graph_store is not None:
            graph_results = self._retrieve_graph(query, stage_k, seed_ids=_extract_ids(vector_results))

        # ── Stage 2: Reciprocal Rank Fusion ────────────────────────
        fused = self._rrf_fuse(vector_results, bm25_results, graph_results)

        # ── Domain boosts (financial/legal signal amplification) ───
        boosted = self._apply_domain_boosts(fused, query, priority_doc_types)

        # ── Stage 3: Cross-encoder reranking (top candidates only) ─
        candidates = boosted[:min(top_k * 2, len(boosted))]
        if self.cross_encoder_enabled and len(candidates) > 1:
            candidates = self._cross_encoder_rerank(query, candidates)

        return [r.to_dict() for r in candidates[:top_k]]

    # ── Stage 1a: Dense Vector Retrieval ───────────────────────────────

    def _retrieve_vector(
        self,
        query: str,
        top_k: int,
        *,
        scope: Optional[str],
        doc_type_filter: Optional[str],
    ) -> List[Dict[str, Any]]:
        try:
            raw = self.vector_store.search(
                query,
                top_k=top_k,
                doc_type_filter=doc_type_filter,
                scope=scope,
            )
            return raw or []
        except Exception as exc:
            logger.warning("[HybridEngine] Vector retrieval failed: %s", exc)
            return []

    # ── Stage 1b: BM25 Sparse Retrieval ────────────────────────────────

    def _retrieve_bm25(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        if self.bm25_retriever is None:
            return []
        try:
            raw = self.bm25_retriever.search(query, top_k=top_k)
            return raw or []
        except Exception as exc:
            logger.warning("[HybridEngine] BM25 retrieval failed: %s", exc)
            return []

    # ── Stage 1c: Graph Entity-Expansion Retrieval ─────────────────────

    def _retrieve_graph(
        self,
        query: str,
        top_k: int,
        seed_ids: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Use the knowledge graph to expand retrieval.

        Strategy:
        1. Extract entity mentions from the query using the graph's node labels.
        2. For each matched entity node, BFS-traverse the graph up to depth 2.
        3. Collect all reachable DOCUMENT nodes.
        4. Return those document chunks that appear in the vector store.
        """
        try:
            G = self.graph_store.load()
        except Exception as exc:
            logger.warning("[HybridEngine] Graph load failed: %s", exc)
            return []

        if G is None or G.number_of_nodes() == 0:
            return []

        try:
            from backend.graph.pagerank import get_node_neighbors
        except ImportError:
            logger.debug("[HybridEngine] graph.pagerank not available, skipping graph stage")
            return []

        # ── Match query tokens to graph node labels ─────────────────
        query_tokens = set(query.lower().split())
        matched_nodes: List[str] = []
        for node_id, attrs in G.nodes(data=True):
            node_label = str(attrs.get("title", "")).lower()
            node_type = attrs.get("type", "")
            # Prioritise DEFINED_TERM and ENTITY nodes
            if node_type in {"DEFINED_TERM", "ENTITY", "KEYPHRASE", "TOPIC"}:
                for token in query_tokens:
                    if len(token) > 3 and token in node_label:
                        matched_nodes.append(node_id)
                        break

        if not matched_nodes:
            # Fall back to seed document nodes from vector results
            if seed_ids:
                matched_nodes = [f"doc:{sid}" for sid in list(seed_ids)[:5] if G.has_node(f"doc:{sid}")]

        if not matched_nodes:
            return []

        # ── BFS expand from matched nodes ────────────────────────────
        reachable_doc_nodes: Set[str] = set()
        for node in matched_nodes[:10]:  # cap seed set
            try:
                neighbours = get_node_neighbors(G, node, depth_limit=_GRAPH_BFS_DEPTH)
                for nbr in neighbours:
                    if G.nodes[nbr].get("type") == "DOCUMENT":
                        reachable_doc_nodes.add(nbr)
            except Exception:
                pass

        # ── Convert graph doc nodes → chunk results via vector store ─
        if not reachable_doc_nodes:
            return []

        graph_results: List[Dict[str, Any]] = []
        for doc_node_id in list(reachable_doc_nodes)[:top_k]:
            doc_id = doc_node_id.replace("doc:", "", 1)
            try:
                # Pull existing chunks from vector store for this doc
                chunks = self.vector_store.search(
                    "",  # empty query → we just want doc chunks
                    top_k=5,
                    doc_type_filter=None,
                    scope=None,
                    where={"doc_id": {"$eq": doc_id}},
                )
                for chunk in (chunks or []):
                    chunk["_from_graph"] = True
                    graph_results.append(chunk)
            except Exception:
                pass

        logger.debug("[HybridEngine] Graph stage: matched_nodes=%d reachable_docs=%d results=%d",
                     len(matched_nodes), len(reachable_doc_nodes), len(graph_results))
        return graph_results

    # ── Stage 2: Reciprocal Rank Fusion ────────────────────────────────

    def _rrf_fuse(
        self,
        vector_results: List[Dict[str, Any]],
        bm25_results: List[Dict[str, Any]],
        graph_results: List[Dict[str, Any]],
    ) -> List[HybridResult]:
        """
        Merge three ranked lists using Reciprocal Rank Fusion.

        RRF score: Σ  w_signal / (k + rank_in_signal)

        Returns a list of HybridResult sorted by descending RRF score.
        """
        # Index: chunk_id → HybridResult accumulator
        acc: Dict[str, HybridResult] = {}

        def _get_id(r: Dict[str, Any]) -> str:
            return str(r.get("chunk_id") or r.get("id") or r.get("_id") or "")

        def _get_content(r: Dict[str, Any]) -> str:
            return str(r.get("content") or r.get("document") or "")

        def _get_meta(r: Dict[str, Any]) -> Dict[str, Any]:
            return r.get("metadata") or {}

        # ── Vector contributions ────────────────────────────────────
        for rank, r in enumerate(vector_results, start=1):
            cid = _get_id(r)
            if not cid:
                continue
            rrf_contrib = self.w_vector / (_RRF_K + rank)
            if cid not in acc:
                acc[cid] = HybridResult(
                    chunk_id=cid,
                    content=_get_content(r),
                    score=0.0,
                    metadata=_get_meta(r),
                )
            acc[cid].rrf_score += rrf_contrib
            acc[cid].vector_rank = rank
            acc[cid].retrieval_signals["vector_score"] = r.get("score", 0.0)

        # ── BM25 contributions ──────────────────────────────────────
        for rank, r in enumerate(bm25_results, start=1):
            cid = _get_id(r)
            if not cid:
                continue
            rrf_contrib = self.w_bm25 / (_RRF_K + rank)
            if cid not in acc:
                acc[cid] = HybridResult(
                    chunk_id=cid,
                    content=_get_content(r),
                    score=0.0,
                    metadata=_get_meta(r),
                )
            acc[cid].rrf_score += rrf_contrib
            acc[cid].bm25_rank = rank
            acc[cid].retrieval_signals["bm25_score"] = r.get("score", 0.0)

        # ── Graph contributions ────────────────────────────────────
        for rank, r in enumerate(graph_results, start=1):
            cid = _get_id(r)
            if not cid:
                continue
            rrf_contrib = self.w_graph / (_RRF_K + rank)
            if cid not in acc:
                acc[cid] = HybridResult(
                    chunk_id=cid,
                    content=_get_content(r),
                    score=0.0,
                    metadata=_get_meta(r),
                )
            acc[cid].rrf_score += rrf_contrib
            acc[cid].graph_rank = rank
            acc[cid].retrieval_signals["graph_expanded"] = True

        # ── Sort by RRF score ─────────────────────────────────────
        fused = sorted(acc.values(), key=lambda x: x.rrf_score, reverse=True)

        # Copy rrf_score → score (will be further modified by domain boosts)
        for r in fused:
            r.score = r.rrf_score

        return fused

    # ── Domain Boosts ──────────────────────────────────────────────────

    def _apply_domain_boosts(
        self,
        results: List[HybridResult],
        query: str,
        priority_doc_types: List[str],
    ) -> List[HybridResult]:
        """
        Apply financial/legal domain-specific score multipliers:

        1. Document regime weight (financial/legal docs boosted, off-domain penalised)
        2. Section heading boost (waterfall, definitions, etc.)
        3. Term frequency boost for high-value financial terms in the chunk
        4. Priority doc-type boost when result matches expected intent type
        """
        query_lower = query.lower()

        # Pre-compute which high-value terms appear in the query
        query_term_hits = {
            term for term in self._term_boosts
            if term.replace("_", " ") in query_lower or term.replace("_", "") in query_lower
        }

        for r in results:
            meta = r.metadata
            doc_regime = meta.get("doc_regime") or meta.get("doc_type") or ""
            section_heading = meta.get("section_heading") or meta.get("section") or ""
            doc_type = meta.get("doc_type") or ""

            # 1. Regime weight
            regime_w = self._regime_weight(doc_regime)

            # 2. Section boost
            section_w = self._section_boost(section_heading)

            # 3. Term boost — count how many high-value financial terms appear
            #    in both the query AND the chunk content
            content_lower = r.content.lower()
            term_multiplier = 1.0
            term_hits_in_chunk: List[str] = []
            for term in query_term_hits:
                term_norm = term.replace("_", " ")
                if term_norm in content_lower:
                    term_multiplier = max(term_multiplier, self._term_boosts.get(term, 1.0))
                    term_hits_in_chunk.append(term)
            # Cap at 2.5 to prevent score explosion
            term_multiplier = min(term_multiplier, 2.5)

            # 4. Priority doc-type alignment
            intent_w = 1.2 if doc_type.upper() in [d.upper() for d in priority_doc_types] else 1.0

            final_score = r.rrf_score * regime_w * section_w * term_multiplier * intent_w
            r.score = final_score
            r.retrieval_signals.update({
                "regime_weight": regime_w,
                "section_boost": section_w,
                "term_multiplier": term_multiplier,
                "intent_weight": intent_w,
                "term_hits": term_hits_in_chunk,
            })

        # Re-sort after boosts
        results.sort(key=lambda x: x.score, reverse=True)
        return results

    # ── Stage 3: Cross-Encoder Reranking ───────────────────────────────

    def _cross_encoder_rerank(
        self,
        query: str,
        candidates: List[HybridResult],
    ) -> List[HybridResult]:
        """Optionally rerank top candidates with ONNX cross-encoder."""
        try:
            from backend.retrieval.cross_encoder import rerank as ce_rerank
            # cross_encoder.rerank expects list of {id, content} dicts
            raw = [{"id": r.chunk_id, "content": r.content, "metadata": r.metadata}
                   for r in candidates]
            reranked = ce_rerank(query, raw)

            # Map reranked order back to HybridResult objects
            id_to_result = {r.chunk_id: r for r in candidates}
            ordered: List[HybridResult] = []
            for item in reranked:
                cid = str(item.get("id") or item.get("chunk_id") or "")
                if cid in id_to_result:
                    r = id_to_result[cid]
                    ce_score = item.get("score", r.score)
                    # Blend: 60% cross-encoder, 40% hybrid
                    r.score = 0.6 * ce_score + 0.4 * r.score
                    r.retrieval_signals["cross_encoder_score"] = ce_score
                    ordered.append(r)

            # Append any candidates not in reranked output (shouldn't happen)
            seen = {r.chunk_id for r in ordered}
            for r in candidates:
                if r.chunk_id not in seen:
                    ordered.append(r)

            return ordered

        except Exception as exc:
            logger.debug("[HybridEngine] Cross-encoder reranking skipped: %s", exc)
            return candidates

    # ── BM25 Index Management ──────────────────────────────────────────

    def build_bm25_index(self, documents: List[Dict[str, Any]]) -> None:
        """(Re)build the BM25 index from a list of {id, content, metadata} dicts."""
        if self.bm25_retriever is None:
            logger.warning("[HybridEngine] No BM25 retriever configured")
            return
        self.bm25_retriever.build_index(documents)
        self.bm25_retriever.save_index()
        logger.info("[HybridEngine] BM25 index built: %d documents", len(documents))

    def load_or_build_bm25_index(self, get_all_chunks_fn) -> bool:
        """
        Load existing BM25 index from disk, or build from scratch.

        Parameters
        ----------
        get_all_chunks_fn : callable
            Zero-argument function that returns all chunks from the vector
            store as [{id, content, metadata}] when called.  Only invoked
            if the saved index is absent or stale.

        Returns
        -------
        bool
            True if BM25 is ready, False if unavailable.
        """
        if self.bm25_retriever is None:
            return False
        if self.bm25_retriever.load_index():
            logger.info("[HybridEngine] BM25 index loaded from disk")
            return True
        # Build from scratch
        try:
            docs = get_all_chunks_fn()
            if docs:
                self.build_bm25_index(docs)
                return True
            logger.warning("[HybridEngine] No documents available to build BM25 index")
            return False
        except Exception as exc:
            logger.warning("[HybridEngine] BM25 index build failed: %s", exc)
            return False


# ── Helpers ─────────────────────────────────────────────────────────────

def _extract_ids(results: List[Dict[str, Any]]) -> Set[str]:
    ids: Set[str] = set()
    for r in results:
        cid = r.get("chunk_id") or r.get("id") or ""
        if cid:
            ids.add(str(cid))
    return ids


def create_hybrid_engine(config, vector_store, graph_store=None) -> HybridRetrievalEngine:
    """
    Factory: create a HybridRetrievalEngine with auto-detected BM25 support.

    Loads the BM25 index if it exists on disk; otherwise leaves it None so
    the caller can build it post-ingestion via ``engine.build_bm25_index()``.
    """
    from backend.retrieval.bm25_retriever import BM25Retriever

    persist_dir = getattr(config, "knowledge_base_path", ".kts")
    bm25 = BM25Retriever(
        persist_dir=persist_dir,
        k1=getattr(config, "bm25_k1", 1.5),
        b=getattr(config, "bm25_b", 0.75),
    )
    # Try to load existing index; don't build here (caller owns lifecycle)
    if not bm25.load_index():
        logger.debug("[HybridEngine] BM25 index not found on disk; will build after ingestion")

    ce_enabled = getattr(config, "cross_encoder_enabled", True)

    return HybridRetrievalEngine(
        config=config,
        vector_store=vector_store,
        graph_store=graph_store,
        bm25_retriever=bm25,
        cross_encoder_enabled=ce_enabled,
        vector_weight=getattr(config, "hybrid_vector_weight", 1.0),
        bm25_weight=getattr(config, "hybrid_bm25_weight", 1.0),
        graph_weight=getattr(config, "hybrid_graph_weight", 0.6),
    )
