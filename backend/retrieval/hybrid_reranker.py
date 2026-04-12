"""
Phase 6 Hybrid Re-ranker — combines content similarity, PageRank, and
graph proximity into a single score for item-level retrieval.

Formula:
    hybrid_score = w_content * content_sim
                 + w_pagerank * pagerank_norm
                 + w_proximity * graph_proximity
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

import networkx as nx

from backend.graph.pagerank import (
    compute_pagerank,
    get_node_neighbors,
    personalized_pagerank_for_query,
)

logger = logging.getLogger(__name__)


class HybridReranker:
    """
    Re-rank Phase 6 search results using three signals:
    1. Content similarity (from vector store)
    2. PageRank authority
    3. Graph proximity to seed hits
    """

    def __init__(
        self,
        *,
        content_weight: float = 0.6,
        pagerank_weight: float = 0.2,
        graph_proximity_weight: float = 0.2,
        pagerank_alpha: float = 0.85,
        bfs_depth_limit: int = 2,
    ) -> None:
        self.w_content = content_weight
        self.w_pagerank = pagerank_weight
        self.w_proximity = graph_proximity_weight
        self.pagerank_alpha = pagerank_alpha
        self.bfs_depth = bfs_depth_limit

    def rerank(
        self,
        results: List[Dict[str, Any]],
        G: nx.DiGraph,
        *,
        seed_node_ids: Optional[List[str]] = None,
        id_key: str = "id",
        score_key: str = "score",
    ) -> List[Dict[str, Any]]:
        """
        Rerank *results* using hybrid scoring.

        Each result dict must have *id_key* (graph node id) and
        *score_key* (vector similarity score).

        Returns results sorted by hybrid score (descending).
        """
        if not results:
            return results

        # -- PageRank -------------------------------------------------------
        if seed_node_ids:
            pr_scores = personalized_pagerank_for_query(
                G, seed_node_ids, alpha=self.pagerank_alpha
            )
        else:
            pr_scores = compute_pagerank(G, alpha=self.pagerank_alpha)

        # Normalize PageRank to [0, 1]
        max_pr = max(pr_scores.values()) if pr_scores else 1.0
        if max_pr == 0:
            max_pr = 1.0

        # -- Graph proximity -----------------------------------------------
        # Proximity = fraction of seed-set that can reach this node within bfs_depth
        proximity_cache: Dict[str, float] = {}
        if seed_node_ids:
            seed_neighborhoods: List[Set[str]] = []
            for seed in seed_node_ids:
                nbrs = get_node_neighbors(G, seed, depth_limit=self.bfs_depth)
                seed_neighborhoods.append(nbrs | {seed})

            for r in results:
                nid = r.get(id_key, "")
                if nid in proximity_cache:
                    continue
                reachable_count = sum(
                    1 for nbrs in seed_neighborhoods if nid in nbrs
                )
                proximity_cache[nid] = reachable_count / len(seed_node_ids)
        else:
            for r in results:
                proximity_cache[r.get(id_key, "")] = 0.0

        # -- Hybrid scoring ------------------------------------------------
        for r in results:
            nid = r.get(id_key, "")
            content_sim = float(r.get(score_key, 0.0))
            pr = pr_scores.get(nid, 0.0) / max_pr
            prox = proximity_cache.get(nid, 0.0)

            hybrid = (
                self.w_content * content_sim
                + self.w_pagerank * pr
                + self.w_proximity * prox
            )
            r["hybrid_score"] = hybrid
            r["_pr_norm"] = pr
            r["_proximity"] = prox

        results.sort(key=lambda r: r.get("hybrid_score", 0.0), reverse=True)

        logger.debug(
            "[Phase6-Rerank] top hybrid=%.4f (content=%.4f pr=%.4f prox=%.4f) for %s",
            results[0].get("hybrid_score", 0),
            float(results[0].get(score_key, 0)),
            results[0].get("_pr_norm", 0),
            results[0].get("_proximity", 0),
            results[0].get(id_key, "?"),
        )
        return results
