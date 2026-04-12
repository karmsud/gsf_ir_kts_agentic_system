"""
Vector-First Retrieval Strategy for Guide / Troubleshooting Documents.

Optimised for non-legal corpora where queries describe *symptoms* in natural
language rather than naming exact defined terms.  The strategy is:

1. **Vector-first**: Semantic similarity search across items + sections
   (no graph-scoping — queries are too fuzzy for TOC-style lookup)
2. **Graph expansion**: BFS from hit nodes following ERROR_CODE, TOOL, STEP,
   PROCEDURE, NEXT edges to surface related procedural content
3. **Error-code boost**: Exact error-code matches in query receive a
   significant additive score
4. **Cross-encoder rerank**: Final precision pass
5. **Step-sequence ordering**: Results within the same doc are re-sorted
   by chunk_index so procedural steps appear in order

This is the counterpart to :class:`HumanLikeRetriever` which uses a
graph-first strategy optimised for legal / governing documents.
"""

from __future__ import annotations

import logging
import math
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from backend.common.explainability import ExplainabilityLogger
from backend.retrieval.cross_encoder import rerank as cross_encoder_rerank
from backend.vector.dual_vector_store import DualVectorStore

logger = logging.getLogger(__name__)


# ── Configuration ─────────────────────────────────────────────

@dataclass
class GuideRetrievalConfig:
    """Configuration for vector-first guide retrieval."""

    # Vector search
    items_top_k: int = 60
    sections_top_k: int = 20

    # Graph expansion
    graph_expansion_enabled: bool = True
    bfs_depth: int = 4
    expansion_edge_types: Tuple[str, ...] = (
        "NEXT", "CONTAINS", "REFERENCES", "HAS_STEP",
        "HAS_RULE", "HAS_DEFINITION", "RELATES_TO",
    )
    max_expansion_nodes: int = 15

    # Error-code boosting
    error_code_boost: float = 0.35

    # Cross-encoder
    use_cross_encoder: bool = True

    # Step-sequence ordering
    step_sequence_ordering: bool = True

    # Query processing
    enable_query_decomposition: bool = True

    # Result limits
    min_confidence: float = 0.5


# ── Result ────────────────────────────────────────────────────

@dataclass
class GuideRetrievalResult:
    results: List[Dict[str, Any]]
    confidence: float
    trace: Any
    strategy: str = "vector_first_guide"


# ── Retriever ─────────────────────────────────────────────────

class GuideRetriever:
    """
    Vector-first retrieval strategy for guide / troubleshooting docs.

    Flow:
        1. (Optional) Decompose compound queries
        2. Vector search across items + sections (global, no graph scoping)
        3. Deduplicate & merge
        4. Graph BFS expansion from seed hits → ERROR_CODE / TOOL / STEP nodes
        5. Error-code exact-match boost
        6. Cross-encoder rerank
        7. Keyword-match rerank (same as HumanLikeRetriever)
        8. Step-sequence ordering within same document
        9. Confidence derivation
    """

    def __init__(
        self,
        dual_store: DualVectorStore,
        graph: nx.DiGraph,
        config: Optional[GuideRetrievalConfig] = None,
    ) -> None:
        self.dual_store = dual_store
        self.graph = graph
        self.config = config or GuideRetrievalConfig()

        # Pre-index error-code and tool nodes for fast lookup
        self._error_code_nodes: Dict[str, str] = {}   # code_lower → node_id
        self._tool_nodes: Dict[str, str] = {}          # tool_lower → node_id
        self._build_indexes()

    # ── Index building ────────────────────────────────────────

    def _build_indexes(self) -> None:
        if self.graph is None or self.graph.number_of_nodes() == 0:
            return
        for node_id, data in self.graph.nodes(data=True):
            ntype = (data.get("type") or "").upper()
            name = (data.get("name") or data.get("surface_form") or "").lower()
            if ntype == "ERROR_CODE" and name:
                self._error_code_nodes[name] = node_id
            elif ntype == "TOOL" and name:
                self._tool_nodes[name] = node_id
        logger.debug(
            "[GuideRetriever] Indexed %d error codes, %d tools",
            len(self._error_code_nodes), len(self._tool_nodes),
        )

    # ── Query helpers ─────────────────────────────────────────

    _ERROR_CODE_RE = re.compile(
        r'\bERR-[A-Z]+-\d{3}\b'
        r'|\bHTTP\s*\d{3}\b'
        r'|\b[A-Z]+\d{3,4}\b',
        re.IGNORECASE,
    )

    def _extract_error_codes(self, text: str) -> List[str]:
        return [m.upper() for m in self._ERROR_CODE_RE.findall(text)]

    @staticmethod
    def _extract_keywords(query: str) -> List[str]:
        stop = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "for", "of", "to", "in", "on", "at", "by", "with", "from",
            "what", "how", "when", "where", "why", "which", "who",
            "does", "do", "did", "will", "would", "could", "should",
            "and", "or", "but", "not", "if", "then", "than",
        }
        return [w for w in re.findall(r'\b[a-zA-Z]{3,}\b', query.lower()) if w not in stop]

    def _decompose_query(self, query: str) -> List[str]:
        """Split compound queries on 'and'/'or' if both parts are substantial."""
        subs = [query]
        if re.search(r'\band\b|\bor\b', query, re.I):
            parts = re.split(r'\s+(?:and|or)\s+', query, flags=re.I)
            if len(parts) > 1 and all(len(p.strip()) > 3 for p in parts):
                subs = [p.strip() for p in parts if p.strip()]
        return subs[:4]

    # ── Graph expansion ───────────────────────────────────────

    def _expand_from_seeds(
        self,
        seed_ids: List[str],
        seen: Set[str],
        xlog: ExplainabilityLogger,
    ) -> List[Dict[str, Any]]:
        """BFS from seed hit node IDs; return neighbouring ITEM/SECTION nodes."""
        if not self.config.graph_expansion_enabled or self.graph is None:
            return []

        candidates: List[Dict[str, Any]] = []
        allowed_edges = set(self.config.expansion_edge_types)

        for seed in seed_ids:
            if seed not in self.graph:
                continue
            # BFS up to configured depth
            visited: Set[str] = {seed}
            frontier = [seed]
            for _depth in range(self.config.bfs_depth):
                next_frontier: List[str] = []
                for nid in frontier:
                    for _, nbr, edata in self.graph.edges(nid, data=True):
                        etype = (edata.get("type") or edata.get("edge_type") or "").upper()
                        if etype not in allowed_edges:
                            continue
                        if nbr in visited or nbr in seen:
                            continue
                        visited.add(nbr)
                        next_frontier.append(nbr)

                        nd = self.graph.nodes.get(nbr, {})
                        ntype = (nd.get("type") or "").upper()
                        if ntype not in ("ITEM", "SECTION"):
                            continue

                        candidates.append({
                            "id": nbr,
                            "text": nd.get("text", nd.get("heading", "")),
                            "similarity": 0.25,  # base for graph-expanded
                            "source": "graph_expansion",
                            "metadata": {
                                "item_type": nd.get("item_type", ntype),
                                "section_number": nd.get("section_number", ""),
                                "document_id": nd.get("document_id", nd.get("doc_id", "")),
                                "source_path": nd.get("source_path", ""),
                                "chunk_index": nd.get("chunk_index", 0),
                            },
                            "_expansion_edge": etype,
                        })

                        if len(candidates) >= self.config.max_expansion_nodes:
                            break
                    if len(candidates) >= self.config.max_expansion_nodes:
                        break
                frontier = next_frontier
                if len(candidates) >= self.config.max_expansion_nodes:
                    break

        xlog.step(
            "graph_expansion",
            f"BFS from {len(seed_ids)} seeds → {len(candidates)} new candidates",
            detail={
                "depth": self.config.bfs_depth,
                "allowed_edges": list(allowed_edges),
            },
            why="Graph expansion follows NEXT/STEP/ERROR_CODE edges for procedural content",
        )
        return candidates

    # ── Error-code boosting ───────────────────────────────────

    def _apply_error_code_boost(
        self,
        query: str,
        results: List[Dict[str, Any]],
        xlog: ExplainabilityLogger,
    ) -> List[Dict[str, Any]]:
        """Additive boost for chunks containing exact error codes from the query."""
        query_codes = self._extract_error_codes(query)
        if not query_codes:
            return results

        boosted_count = 0
        for r in results:
            text = (r.get("text") or r.get("content") or "").upper()
            if any(code in text for code in query_codes):
                r["similarity"] = r.get("similarity", 0.0) + self.config.error_code_boost
                r["_error_code_boosted"] = True
                boosted_count += 1

        xlog.step(
            "error_code_boost",
            f"Boosted {boosted_count}/{len(results)} results for codes {query_codes}",
            detail={"codes": query_codes, "boost": self.config.error_code_boost},
            why="Exact error-code match is a high-precision signal for troubleshooting",
        )
        return results

    # ── Keyword-match reranking (shared logic with HumanLike) ─

    def _keyword_boost_rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        xlog: ExplainabilityLogger,
    ) -> List[Dict[str, Any]]:
        """Promote chunks with high keyword overlap with the query."""
        if not results:
            return results

        stopwords = {
            "the", "a", "an", "is", "are", "was", "were", "what", "which",
            "how", "when", "where", "who", "why", "does", "do", "did", "can",
            "could", "should", "would", "in", "on", "at", "to", "for", "of",
            "with", "by", "from", "as", "or", "and", "not", "be", "been",
            "this", "that", "it", "its", "i", "my", "me", "we", "our",
            "you", "your", "many", "much", "used", "available",
        }
        query_lower = query.lower()
        query_words = [
            w for w in re.findall(r'\b[\w\-\.]+\b', query_lower)
            if w not in stopwords and len(w) > 1
        ]
        error_codes = re.findall(r'[A-Z]{2,}[\-_][A-Z0-9\-_]+', query, re.I)
        priority_terms = [t.lower() for t in error_codes]

        for r in results:
            text = (r.get("text") or r.get("content") or "").lower()
            ce_score = r.get("cross_encoder_score")
            if ce_score is not None:
                base_score = 1.0 / (1.0 + math.exp(-ce_score))
            else:
                base_score = r.get("similarity", 0.5)

            matched = sum(1 for w in query_words if w in text)
            keyword_overlap = matched / max(len(query_words), 1)

            priority_boost = sum(0.25 for pt in priority_terms if pt in text)

            keyword_multiplier = 1.0 + keyword_overlap * 0.55
            r["_final_score"] = base_score * keyword_multiplier + min(priority_boost, 0.5)

        results.sort(key=lambda r: r.get("_final_score", 0), reverse=True)

        xlog.step(
            "keyword_boost",
            f"Keyword-boost reranked {len(results)} results",
            detail={"query_terms": query_words[:10], "priority_terms": priority_terms},
            why="Keyword overlap promotes specific detail chunks over overviews",
        )
        return results

    # ── Step-sequence ordering ────────────────────────────────

    def _apply_step_ordering(
        self,
        results: List[Dict[str, Any]],
        xlog: ExplainabilityLogger,
    ) -> List[Dict[str, Any]]:
        """
        Within results from the same document, re-order by chunk_index
        so procedural steps appear in their natural reading order.
        Group by doc_id → sort chunks within each group by chunk_index →
        interleave back preserving cross-document rank.
        """
        if not self.config.step_sequence_ordering or len(results) <= 1:
            return results

        # Bucket by document
        from collections import OrderedDict
        doc_buckets: OrderedDict[str, List[Dict]] = OrderedDict()
        for r in results:
            meta = r.get("metadata", {})
            doc_id = (
                meta.get("document_id") or meta.get("doc_id")
                or r.get("document_id") or r.get("doc_id") or ""
            )
            doc_buckets.setdefault(doc_id, []).append(r)

        # Sort each bucket by chunk_index
        reordered_count = 0
        for doc_id, bucket in doc_buckets.items():
            if len(bucket) > 1:
                bucket.sort(key=lambda r: (
                    r.get("metadata", {}).get("chunk_index", 0)
                    if isinstance(r.get("metadata"), dict) else 0
                ))
                reordered_count += 1

        # Rebuild list: take first item from each bucket in order, then second, etc.
        ordered: List[Dict] = []
        iterators = [iter(b) for b in doc_buckets.values()]
        while iterators:
            next_round = []
            for it in iterators:
                item = next(it, None)
                if item is not None:
                    ordered.append(item)
                    next_round.append(it)
            iterators = next_round

        if reordered_count:
            xlog.step(
                "step_ordering",
                f"Re-ordered chunks in {reordered_count} documents by step sequence",
                detail={"total_results": len(ordered)},
                why="Procedural docs read best when steps appear in original order",
            )

        return ordered

    # ══════════════════════════════════════════════════════════════
    # MAIN RETRIEVAL FLOW
    # ══════════════════════════════════════════════════════════════

    def retrieve(
        self,
        query: str,
        *,
        max_results: int = 10,
    ) -> GuideRetrievalResult:
        """
        Vector-first retrieval flow for guide / troubleshooting docs.

        Steps:
            1. Decompose compound queries
            2. Vector search (items + sections, global — no graph scoping)
            3. Deduplicate & merge with RRF if multiple sub-queries
            4. Graph BFS expansion from top seed hits
            5. Error-code exact-match boost
            6. Cross-encoder rerank
            7. Keyword-match rerank
            8. Step-sequence ordering
            9. Confidence derivation
        """
        start_time = time.perf_counter()
        xlog = ExplainabilityLogger(
            "guide_retrieval",
            doc_id=f"query:{query[:50]}",
            verbose=True,
        )
        xlog.step(
            "start",
            f"Guide (vector-first) retrieval started: '{query}'",
            detail={"max_results": max_results, "strategy": "vector_first_guide"},
            why="Vector-first strategy optimised for symptom-based natural-language queries",
        )

        # ── Step 1: Decompose ────────────────────────────────────
        if self.config.enable_query_decomposition:
            sub_queries = self._decompose_query(query)
            xlog.step(
                "decomposition",
                f"Decomposed into {len(sub_queries)} sub-queries",
                detail={"sub_queries": sub_queries},
                why="Compound queries benefit from separate retrieval + fusion",
            )
        else:
            sub_queries = [query]

        # ── Step 2: Vector search ────────────────────────────────
        all_result_sets: List[List[Dict]] = []
        for sq in sub_queries:
            items = self.dual_store.search_items(sq, top_k=self.config.items_top_k)
            sections = self.dual_store.search_sections(sq, top_k=self.config.sections_top_k)
            combined = items + sections
            if combined:
                all_result_sets.append(combined)

        xlog.step(
            "vector_search",
            f"Vector search: {len(sub_queries)} queries → {sum(len(rs) for rs in all_result_sets)} raw hits",
            detail={
                "items_top_k": self.config.items_top_k,
                "sections_top_k": self.config.sections_top_k,
            },
            why="Semantic similarity is the primary signal for guide-style queries",
        )

        # ── Step 3: RRF merge + dedup ────────────────────────────
        if len(all_result_sets) > 1:
            merged = self._rrf_merge(all_result_sets)
        elif all_result_sets:
            merged = all_result_sets[0]
        else:
            merged = []

        # deduplicate
        seen_ids: Set[str] = set()
        deduped: List[Dict] = []
        for r in merged:
            rid = r.get("id", "")
            if rid and rid in seen_ids:
                continue
            if rid:
                seen_ids.add(rid)
            deduped.append(r)
        merged = deduped[:max_results * 3]

        # ── Step 4: Graph BFS expansion ──────────────────────────
        seed_ids = [
            r.get("id", "") for r in merged[:5]
            if r.get("id", "") and self.graph is not None and r.get("id", "") in self.graph
        ]
        if seed_ids:
            expanded = self._expand_from_seeds(seed_ids, seen_ids, xlog)
            merged.extend(expanded)

        # ── Step 5: Error-code boost ─────────────────────────────
        merged = self._apply_error_code_boost(query, merged, xlog)

        # ── Step 6: Cross-encoder rerank ─────────────────────────
        if self.config.use_cross_encoder and merged:
            merged = cross_encoder_rerank(query, merged, content_key="text")
            merged.sort(key=lambda r: r.get("cross_encoder_score", 0), reverse=True)
            xlog.step(
                "cross_encoder",
                f"Cross-encoder reranked {len(merged)} results",
                detail={
                    "top_score": round(merged[0].get("cross_encoder_score", 0), 4) if merged else 0,
                },
                why="Cross-encoder provides high-precision semantic matching",
            )

        # ── Step 7: Keyword-match rerank ─────────────────────────
        merged = self._keyword_boost_rerank(query, merged, xlog)

        # ── Step 8: Step-sequence ordering ───────────────────────
        merged = self._apply_step_ordering(merged, xlog)

        # ── Step 9: Trim & confidence ────────────────────────────
        final = merged[:max_results]

        if final:
            top_ce = final[0].get("cross_encoder_score")
            if top_ce is not None:
                confidence = 1.0 / (1.0 + math.exp(-top_ce))
            else:
                confidence = final[0].get("similarity", 0.0)
        else:
            confidence = 0.0

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        xlog.step(
            "complete",
            f"Guide retrieval complete: {len(final)} results, confidence={confidence:.3f}",
            detail={"elapsed_ms": round(elapsed_ms, 2), "confidence": round(confidence, 4)},
            why="Vector-first guide retrieval complete",
        )

        trace_data = xlog.done()
        return GuideRetrievalResult(
            results=final,
            confidence=confidence,
            trace=trace_data.get("steps", []),
            strategy="vector_first_guide",
        )

    # ── RRF ───────────────────────────────────────────────────

    @staticmethod
    def _rrf_merge(
        result_sets: List[List[Dict[str, Any]]],
        k: int = 60,
    ) -> List[Dict[str, Any]]:
        scores: Dict[str, float] = {}
        best: Dict[str, Dict] = {}
        for rset in result_sets:
            for rank, r in enumerate(rset):
                rid = r.get("id", str(id(r)))
                scores[rid] = scores.get(rid, 0) + 1 / (k + rank + 1)
                if rid not in best:
                    best[rid] = r
        ordered = sorted(scores, key=scores.get, reverse=True)  # type: ignore[arg-type]
        return [best[rid] for rid in ordered]
