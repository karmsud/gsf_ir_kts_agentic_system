"""
PageRank computation for Phase 6 graph-boosted retrieval.

Uses NetworkX's built-in ``pagerank`` function on the existing
GraphStore DiGraph.  Supports optional *personalization* to bias
scores toward nodes related to a query.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

import networkx as nx

logger = logging.getLogger(__name__)


def compute_pagerank(
    G: nx.DiGraph,
    *,
    alpha: float = 0.85,
    personalization: Optional[Dict[str, float]] = None,
    max_iter: int = 100,
    tol: float = 1e-6,
) -> Dict[str, float]:
    """
    Compute PageRank scores for all nodes in *G*.

    Args:
        G: NetworkX directed graph.
        alpha: Damping factor (default 0.85).
        personalization: Optional per-node bias dict.
        max_iter / tol: convergence parameters.

    Returns:
        Dict mapping node-id → PageRank score.
    """
    if len(G) == 0:
        return {}
    try:
        scores = nx.pagerank(
            G,
            alpha=alpha,
            personalization=personalization,
            max_iter=max_iter,
            tol=tol,
            weight="weight",
        )
        return scores
    except nx.PowerIterationFailedConvergence:
        logger.warning("[Phase6-PageRank] Failed to converge — returning uniform scores")
        n = len(G)
        return {node: 1.0 / n for node in G}


def personalized_pagerank_for_query(
    G: nx.DiGraph,
    seed_node_ids: List[str],
    *,
    alpha: float = 0.85,
) -> Dict[str, float]:
    """
    Compute *personalized* PageRank biased toward *seed_node_ids*.

    Teleport probability is concentrated on the seed nodes so that
    nodes reachable from the seeds are ranked highest.
    """
    if not seed_node_ids:
        return compute_pagerank(G, alpha=alpha)

    # Build personalization vector (uniform over seeds)
    valid_seeds = [nid for nid in seed_node_ids if nid in G]
    if not valid_seeds:
        return compute_pagerank(G, alpha=alpha)

    personalization = {nid: 1.0 / len(valid_seeds) for nid in valid_seeds}
    return compute_pagerank(G, alpha=alpha, personalization=personalization)


def get_node_neighbors(
    G: nx.DiGraph,
    node_id: str,
    *,
    depth_limit: int = 2,
    edge_types: Optional[Set[str]] = None,
) -> Set[str]:
    """
    BFS expansion from *node_id* up to *depth_limit* hops.

    Optionally filter to only traverse edges matching *edge_types*.
    Returns the set of reachable node ids (excluding *node_id* itself).
    """
    if node_id not in G:
        return set()

    if edge_types is None:
        # Simple BFS using built-in
        lengths = nx.single_source_shortest_path_length(G, node_id, cutoff=depth_limit)
        return set(lengths.keys()) - {node_id}

    # Manual BFS with edge-type filter
    visited: Set[str] = set()
    frontier: Set[str] = {node_id}
    for _ in range(depth_limit):
        next_frontier: Set[str] = set()
        for n in frontier:
            for _, target, data in G.edges(n, data=True):
                if target not in visited and target != node_id:
                    if data.get("type") in edge_types:
                        next_frontier.add(target)
        visited |= next_frontier
        frontier = next_frontier
        if not frontier:
            break
    return visited
