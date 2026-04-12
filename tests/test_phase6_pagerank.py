"""
Phase 6 — PageRank & Hybrid Reranker tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.graph.pagerank import (
    compute_pagerank,
    get_node_neighbors,
    personalized_pagerank_for_query,
)
from backend.retrieval.hybrid_reranker import HybridReranker


# ── PageRank ─────────────────────────────────────────────────────

class TestPageRank:
    @pytest.fixture
    def simple_graph(self):
        G = nx.DiGraph()
        G.add_edge("A", "B", weight=1.0)
        G.add_edge("B", "C", weight=1.0)
        G.add_edge("C", "A", weight=1.0)
        G.add_edge("A", "D", weight=1.0)
        return G

    def test_basic_pagerank(self, simple_graph):
        scores = compute_pagerank(simple_graph)
        assert len(scores) == 4
        assert all(0 < s < 1 for s in scores.values())
        # A has more incoming edges → should rank higher
        assert scores["A"] > scores["D"]

    def test_empty_graph(self):
        G = nx.DiGraph()
        scores = compute_pagerank(G)
        assert scores == {}

    def test_personalized_pagerank(self, simple_graph):
        scores = personalized_pagerank_for_query(simple_graph, ["A"])
        assert scores["A"] > scores["D"]

    def test_personalized_empty_seeds(self, simple_graph):
        # Should fall back to standard pagerank
        scores = personalized_pagerank_for_query(simple_graph, [])
        assert len(scores) == 4

    def test_personalized_invalid_seeds(self, simple_graph):
        scores = personalized_pagerank_for_query(simple_graph, ["NONEXISTENT"])
        assert len(scores) == 4


class TestGetNodeNeighbors:
    @pytest.fixture
    def chain_graph(self):
        G = nx.DiGraph()
        G.add_edge("A", "B", type="CONTAINS", weight=1.0)
        G.add_edge("B", "C", type="NEXT", weight=0.8)
        G.add_edge("C", "D", type="NEXT", weight=0.8)
        G.add_edge("D", "E", type="NEXT", weight=0.8)
        return G

    def test_depth_1(self, chain_graph):
        nbrs = get_node_neighbors(chain_graph, "A", depth_limit=1)
        assert nbrs == {"B"}

    def test_depth_2(self, chain_graph):
        nbrs = get_node_neighbors(chain_graph, "A", depth_limit=2)
        assert nbrs == {"B", "C"}

    def test_depth_3(self, chain_graph):
        nbrs = get_node_neighbors(chain_graph, "A", depth_limit=3)
        assert nbrs == {"B", "C", "D"}

    def test_nonexistent_node(self, chain_graph):
        nbrs = get_node_neighbors(chain_graph, "Z", depth_limit=2)
        assert nbrs == set()

    def test_edge_type_filter(self, chain_graph):
        nbrs = get_node_neighbors(chain_graph, "A", depth_limit=3, edge_types={"CONTAINS"})
        assert nbrs == {"B"}  # Only CONTAINS edge, not NEXT

    def test_edge_type_filter_next(self, chain_graph):
        nbrs = get_node_neighbors(chain_graph, "B", depth_limit=2, edge_types={"NEXT"})
        assert nbrs == {"C", "D"}


# ── Hybrid Reranker ──────────────────────────────────────────────

class TestHybridReranker:
    @pytest.fixture
    def sample_graph(self):
        G = nx.DiGraph()
        G.add_node("item1", type="ITEM")
        G.add_node("item2", type="ITEM")
        G.add_node("item3", type="ITEM")
        G.add_edge("item1", "item2", type="REFERENCES", weight=0.5)
        G.add_edge("item2", "item3", type="NEXT", weight=0.8)
        return G

    @pytest.fixture
    def sample_results(self):
        return [
            {"id": "item1", "score": 0.9, "text": "First item"},
            {"id": "item2", "score": 0.7, "text": "Second item"},
            {"id": "item3", "score": 0.5, "text": "Third item"},
        ]

    def test_reranking_produces_hybrid_scores(self, sample_graph, sample_results):
        reranker = HybridReranker()
        ranked = reranker.rerank(sample_results, sample_graph)
        assert all("hybrid_score" in r for r in ranked)

    def test_reranking_preserves_results(self, sample_graph, sample_results):
        reranker = HybridReranker()
        ranked = reranker.rerank(sample_results, sample_graph)
        assert len(ranked) == 3

    def test_reranking_with_seeds(self, sample_graph, sample_results):
        reranker = HybridReranker()
        ranked = reranker.rerank(
            sample_results, sample_graph, seed_node_ids=["item1"]
        )
        assert all("hybrid_score" in r for r in ranked)
        # item2 is a neighbor of item1, so it should get proximity boost
        item2_result = next(r for r in ranked if r["id"] == "item2")
        assert item2_result["_proximity"] > 0

    def test_reranking_empty_results(self, sample_graph):
        reranker = HybridReranker()
        ranked = reranker.rerank([], sample_graph)
        assert ranked == []

    def test_reranking_sorted_descending(self, sample_graph, sample_results):
        reranker = HybridReranker()
        ranked = reranker.rerank(sample_results, sample_graph)
        scores = [r["hybrid_score"] for r in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_custom_weights(self, sample_graph, sample_results):
        reranker = HybridReranker(
            content_weight=0.8, pagerank_weight=0.1, graph_proximity_weight=0.1
        )
        ranked = reranker.rerank(sample_results, sample_graph)
        # Higher content weight → should closely follow original score order
        assert ranked[0]["id"] == "item1"
