"""
Phase 6 Iterative Multi-Hop Retrieval Orchestrator.

Implements convergent-loop retrieval with:
1. Query expansion (terms, synonyms, reformulations)
2. Dual vector search (items + sections)
3. Graph expansion (BFS from seed hits)
4. Hybrid re-ranking (content + PageRank + proximity)
5. Confidence targeting (loop until >= threshold)
6. Result filtering (only return high-confidence results)
7. Full explainability trace

Adapted from Neo4j design to use NetworkX/GraphStore.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Set

import networkx as nx

from backend.common.config_phase6 import Phase6Config
from backend.common.explainability import ExplainabilityLogger
from backend.graph.pagerank import get_node_neighbors
from backend.retrieval.hybrid_reranker import HybridReranker
from backend.vector.dual_vector_store import DualVectorStore

logger = logging.getLogger(__name__)


class IterativeOrchestrator:
    """
    Multi-hop iterative retrieval with query expansion and explainability.

    Usage::

        orch = IterativeOrchestrator(dual_store, graph, phase6_cfg, kb_path)
        results = orch.retrieve(query, max_results=10)
    """

    def __init__(
        self,
        dual_store: DualVectorStore,
        graph: nx.DiGraph,
        config: Phase6Config,
        kb_path: str = ".kts",
    ) -> None:
        self.dual_store = dual_store
        self.graph = graph
        self.config = config
        self.kb_path = kb_path
        self.reranker = HybridReranker(
            content_weight=config.content_weight,
            pagerank_weight=config.pagerank_weight,
            graph_proximity_weight=config.graph_proximity_weight,
            pagerank_alpha=config.pagerank_alpha,
            bfs_depth_limit=config.bfs_depth_limit,
        )

    # ── Query Expansion ───────────────────────────────────────────

    def _expand_query(self, query: str, xlog: ExplainabilityLogger) -> List[str]:
        """
        Generate query variations using term registry and domain synonyms.
        
        Returns list of queries: [original, reformulation_1, reformulation_2, ...]
        """
        queries = [query]
        
        try:
            from backend.retrieval.query_expander import QueryExpander
            expander = QueryExpander(kb_path=self.kb_path)
            
            # Get synonym expansion
            expanded = expander.expand(query, max_expansions=3, use_ner_entities=False)
            if expanded != query:
                queries.append(expanded)
            
            # Domain-specific reformulations
            reformulations = self._generate_reformulations(query)
            queries.extend(reformulations)
            
            # Deduplicate while preserving order
            seen: Set[str] = set()
            unique: List[str] = []
            for q in queries:
                q_lower = q.lower().strip()
                if q_lower not in seen:
                    seen.add(q_lower)
                    unique.append(q)
            
            xlog.step(
                "query_expansion",
                f"Expanded '{query}' into {len(unique)} variations",
                detail={"original": query, "variations": unique[1:] if len(unique) > 1 else []},
                why="Query expansion improves recall by searching for semantically equivalent phrasings"
            )
            
            return unique[:5]  # Cap at 5 variations
            
        except Exception as exc:
            xlog.warn("query_expansion", f"Query expansion failed: {exc}")
            return [query]

    def _generate_reformulations(self, query: str) -> List[str]:
        """Generate domain-specific query reformulations."""
        reformulations: List[str] = []
        query_lower = query.lower()
        
        # PSA/Legal domain reformulations
        legal_mappings = {
            "allocation": ["distribution", "apportionment"],
            "losses": ["realized losses", "shortfalls", "writedowns", "credit losses"],
            "certificate": ["note", "security", "interest"],
            "holder": ["owner", "investor", "beneficial owner"],
            "distribution": ["payment", "remittance", "distribution amount"],
            "servicer": ["master servicer", "loan servicer"],
            "trustee": ["indenture trustee", "owner trustee"],
            "pool": ["collateral", "underlying assets", "mortgage loans"],
        }
        
        for term, substitutes in legal_mappings.items():
            if term in query_lower:
                for sub in substitutes[:2]:  # Only first 2 to avoid explosion
                    reformulated = query_lower.replace(term, sub)
                    if reformulated != query_lower:
                        reformulations.append(reformulated)
        
        return reformulations[:3]  # Cap reformulations

    # ── Public API ────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        *,
        max_results: int = 10,
        doc_type_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run iterative retrieval with query expansion and explainability.

        Returns dict with keys:
            results: list[dict] — filtered high-confidence results
            iterations: int — number of iterations executed
            confidence: float — final top confidence score
            trace: dict — full explainability trace for VS Code output
            explanation: list[str] — step-by-step log (backwards compatible)
        """
        start_time = time.perf_counter()
        xlog = ExplainabilityLogger(
            "phase6_retrieval",
            doc_id=f"query:{query[:50]}",
            verbose=self.config.verbose_logging,
        )
        
        xlog.step(
            "start",
            f"Phase 6 iterative retrieval started for query: '{query}'",
            detail={"max_results": max_results, "target_confidence": self.config.min_confidence},
            why="Phase 6 uses multi-hop graph traversal to find semantically related content"
        )

        # ── Step 1: Query Expansion ───────────────────────────────
        expanded_queries = self._expand_query(query, xlog)

        prev_confidence = 0.0
        best_results: List[dict] = []
        seen_ids: Set[str] = set()
        seed_node_ids: List[str] = []
        iteration = 0
        confidence = 0.0
        top_score = 0.0
        avg_top5 = 0.0

        for iteration in range(1, self.config.max_iterations + 1):
            iter_start = time.perf_counter()
            
            xlog.step(
                f"iteration_{iteration}",
                f"Starting iteration {iteration}/{self.config.max_iterations}",
                detail={"seeds": len(seed_node_ids), "seen": len(seen_ids)},
                why="Each iteration expands the search graph to find more relevant content"
            )

            # ── Step 2: Vector Search ─────────────────────────────
            if iteration == 1:
                # Initial search: use all expanded queries
                all_item_hits: List[dict] = []
                all_section_hits: List[dict] = []
                
                for q in expanded_queries:
                    item_hits = self.dual_store.search_items(q, top_k=max_results * 3)
                    section_hits = self.dual_store.search_sections(q, top_k=max_results)
                    all_item_hits.extend(item_hits)
                    all_section_hits.extend(section_hits)
                
                candidates = self._merge_hits(all_item_hits, all_section_hits, seen_ids)
                
                xlog.step(
                    "dual_store_search",
                    f"Searched {len(expanded_queries)} query variations across items+sections",
                    detail={
                        "queries": expanded_queries,
                        "item_hits": len(all_item_hits),
                        "section_hits": len(all_section_hits),
                        "unique_candidates": len(candidates),
                    },
                    why="Dual store searches both fine-grained items (definitions, rules) and broader sections"
                )
            else:
                # Expansion search: BFS from seeds
                candidates = self._expand_from_graph(seed_node_ids, seen_ids, xlog)

            if not candidates:
                xlog.step(
                    "no_candidates",
                    "No new candidates found — stopping early",
                    detail={"iteration": iteration},
                    why="Graph expansion exhausted without finding new relevant nodes"
                )
                break

            # Track seen IDs
            for c in candidates:
                seen_ids.add(c.get("id", ""))

            # Combine with previous results
            combined = best_results + candidates

            # ── Step 3: Hybrid Re-ranking ─────────────────────────
            rerank_start = time.perf_counter()
            combined = self.reranker.rerank(
                combined,
                self.graph,
                seed_node_ids=seed_node_ids or None,
                id_key="id",
                score_key="similarity",
            )
            rerank_ms = (time.perf_counter() - rerank_start) * 1000

            xlog.step(
                "hybrid_rerank",
                f"Re-ranked {len(combined)} candidates using content+PageRank+proximity",
                detail={
                    "weights": {
                        "content": self.config.content_weight,
                        "pagerank": self.config.pagerank_weight,
                        "proximity": self.config.graph_proximity_weight,
                    },
                    "elapsed_ms": round(rerank_ms, 2),
                },
                why="Hybrid scoring combines semantic similarity with graph authority signals"
            )

            # ── Step 4: Select top results ────────────────────────
            best_results = combined[:max_results * 2]

            # ── Step 5: Compute confidence ────────────────────────
            # Use top-1 hybrid score directly (proven to reach 0.809 for exact matches)
            if best_results:
                top_score = best_results[0].get("hybrid_score", best_results[0].get("similarity", 0.0))
                confidence = top_score
            else:
                confidence = 0.0

            improvement = confidence - prev_confidence
            
            xlog.step(
                "confidence_check",
                f"Confidence: {confidence:.3f} (delta: {improvement:+.3f})",
                detail={
                    "top_score": round(top_score, 4) if best_results else 0,
                    "threshold": self.config.min_confidence,
                    "improvement": round(improvement, 4),
                },
                why="Confidence uses top-1 hybrid score for direct relevance measure"
            )

            # ── Step 6: Update seeds for next iteration ───────────
            seed_node_ids = [
                r.get("id", "") for r in best_results[:5] if r.get("id", "") in self.graph
            ]

            # ── Step 7: Convergence check ─────────────────────────
            if confidence >= self.config.min_confidence:
                xlog.step(
                    "converged",
                    f"Target confidence reached: {confidence:.3f} >= {self.config.min_confidence}",
                    detail={"final_iteration": iteration},
                    why="Search converged — sufficient confidence achieved"
                )
                break
                
            if iteration > 1 and improvement < self.config.min_improvement:
                xlog.step(
                    "converged_plateau",
                    f"Improvement plateau: {improvement:.4f} < {self.config.min_improvement}",
                    detail={"final_iteration": iteration},
                    why="Further iterations unlikely to improve results"
                )
                break

            prev_confidence = confidence
            iter_ms = (time.perf_counter() - iter_start) * 1000
            xlog.step(
                f"iteration_{iteration}_complete",
                f"Iteration {iteration} complete in {iter_ms:.1f}ms",
                detail={"candidates": len(candidates), "best_results": len(best_results)},
                why="Proceeding to next iteration for deeper graph exploration"
            )

        # ── Step 8: Filter by confidence threshold ────────────────
        threshold = getattr(self.config, 'result_threshold', 0.70)
        filtered_results: List[dict] = []
        
        for r in best_results[:max_results]:
            score = r.get("hybrid_score", r.get("similarity", 0.0))
            if score >= threshold:
                filtered_results.append(r)
        
        # If no results meet threshold, return best available with warning
        if not filtered_results and best_results:
            filtered_results = best_results[:2]  # At least return top 2
            xlog.warn(
                "threshold_fallback",
                f"No results met confidence threshold {threshold}. "
                f"Returning top {len(filtered_results)} results (best: {best_results[0].get('hybrid_score', 0):.3f})"
            )
        
        final_confidence = confidence if best_results else 0.0
        total_ms = (time.perf_counter() - start_time) * 1000
        
        # Build explainability trace
        trace = xlog.done(summary={
            "query": query,
            "expanded_queries": expanded_queries,
            "iterations": iteration,
            "final_confidence": round(final_confidence, 4),
            "results_before_filter": len(best_results),
            "results_after_filter": len(filtered_results),
            "threshold": threshold,
            "total_ms": round(total_ms, 2),
        })
        
        # Also build backwards-compatible explanation list
        explanation = [f"[{s.get('step', '')}] {s.get('description', s.get('warning', ''))}" for s in trace.get("steps", [])]

        return {
            "results": filtered_results,
            "iterations": iteration,
            "confidence": round(final_confidence, 4),
            "trace": trace,  # Full explainability for VS Code output
            "explanation": explanation,  # Backwards compatible
        }

    # ── Internal helpers ──────────────────────────────────────────

    def _merge_hits(
        self,
        item_hits: List[dict],
        section_hits: List[dict],
        seen: Set[str],
    ) -> List[dict]:
        """Merge item + section hits, deduplicating by id."""
        merged: List[dict] = []
        for hit in item_hits + section_hits:
            hit_id = hit.get("id", "")
            if hit_id and hit_id not in seen:
                merged.append(hit)
                seen.add(hit_id)
        # Sort by similarity score descending
        merged.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        return merged

    def _expand_from_graph(
        self,
        seed_ids: List[str],
        seen: Set[str],
        xlog: ExplainabilityLogger,
    ) -> List[dict]:
        """Expand from seeds using BFS; return unseen graph neighbors as candidates."""
        candidates: List[dict] = []
        edges_traversed = 0
        
        for seed_id in seed_ids:
            neighbors = get_node_neighbors(
                self.graph, seed_id, depth_limit=self.config.bfs_depth_limit
            )
            for nbr_id in neighbors:
                if nbr_id in seen:
                    continue
                if nbr_id not in self.graph:
                    continue
                    
                node_data = dict(self.graph.nodes[nbr_id])
                node_type = node_data.get("type", "")
                
                # Only include items and sections, not documents/metadata nodes
                if node_type not in {"ITEM", "SECTION"}:
                    continue
                    
                candidates.append({
                    "id": nbr_id,
                    "text": node_data.get("text", node_data.get("heading", "")),
                    "similarity": 0.3,  # base score for graph-expanded results
                    "source": "graph_expansion",
                    "item_type": node_data.get("item_type", node_type),
                    "section_number": node_data.get("section_number", ""),
                    "document_id": node_data.get("document_id", node_data.get("doc_id", "")),
                })
                seen.add(nbr_id)
                edges_traversed += 1
        
        xlog.step(
            "graph_expansion",
            f"BFS from {len(seed_ids)} seeds found {len(candidates)} new candidates",
            detail={
                "depth_limit": self.config.bfs_depth_limit,
                "edges_traversed": edges_traversed,
            },
            why="Graph expansion follows REFERENCES and HAS_* edges to related content"
        )
        
        return candidates
