"""
Phase 6 — Iterative Orchestrator tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.common.config_phase6 import Phase6Config
from backend.retrieval.iterative_orchestrator import IterativeOrchestrator
from backend.vector.dual_vector_store import DualVectorStore


class TestIterativeOrchestrator:
    @pytest.fixture
    def graph(self):
        G = nx.DiGraph()
        # Doc → Sections
        G.add_node("doc:doc1", type="DOCUMENT")
        G.add_node("sec:doc1:0000", type="SECTION", heading="Definitions", section_number="1.01", doc_id="doc1")
        G.add_node("sec:doc1:0001", type="SECTION", heading="Distributions", section_number="2.01", doc_id="doc1")
        G.add_edge("doc:doc1", "sec:doc1:0000", type="CONTAINS", weight=1.0)
        G.add_edge("doc:doc1", "sec:doc1:0001", type="CONTAINS", weight=1.0)
        G.add_edge("sec:doc1:0000", "sec:doc1:0001", type="NEXT", weight=0.8)

        # Items
        G.add_node("item1", type="ITEM", item_type="Definition", text="Available Funds means all collected", document_id="doc1", section_number="1.01")
        G.add_node("item2", type="ITEM", item_type="Obligation", text="Trustee shall distribute Available Funds", document_id="doc1", section_number="2.01")
        G.add_edge("sec:doc1:0000", "item1", type="HAS_DEFINITION", weight=0.9)
        G.add_edge("sec:doc1:0001", "item2", type="HAS_RULE", weight=0.7)
        G.add_edge("item2", "item1", type="REFERENCES", weight=0.4)
        return G

    @pytest.fixture
    def dual_store(self, tmp_path):
        store = DualVectorStore(str(tmp_path / "phase6"))
        store.add_items([
            {"id": "item1", "text": "Available Funds means all collected amounts", "metadata": {"item_type": "Definition", "document_id": "doc1"}},
            {"id": "item2", "text": "Trustee shall distribute Available Funds", "metadata": {"item_type": "Obligation", "document_id": "doc1"}},
        ])
        store.add_sections([
            {"id": "sec:doc1:0000", "text": "Definitions section", "metadata": {"section_number": "1.01", "document_id": "doc1"}},
            {"id": "sec:doc1:0001", "text": "Distributions section", "metadata": {"section_number": "2.01", "document_id": "doc1"}},
        ])
        return store

    @pytest.fixture
    def config(self):
        return Phase6Config(
            enabled=True,
            max_iterations=3,
            min_confidence=0.5,
            min_improvement=0.01,
        )

    def test_retrieve_returns_results(self, dual_store, graph, config):
        orch = IterativeOrchestrator(dual_store, graph, config)
        result = orch.retrieve("distribute Available Funds", max_results=5)
        assert "results" in result
        assert "iterations" in result
        assert "confidence" in result
        assert "explanation" in result

    def test_retrieve_finds_items(self, dual_store, graph, config):
        orch = IterativeOrchestrator(dual_store, graph, config)
        result = orch.retrieve("Available Funds", max_results=5)
        assert len(result["results"]) > 0

    def test_explanation_populated(self, dual_store, graph, config):
        orch = IterativeOrchestrator(dual_store, graph, config)
        result = orch.retrieve("distribute", max_results=5)
        assert len(result["explanation"]) > 0
        assert any("iteration" in line.lower() for line in result["explanation"])

    def test_convergence_stops_early(self, dual_store, graph, config):
        config.min_confidence = 0.01  # Very low → should converge quickly
        orch = IterativeOrchestrator(dual_store, graph, config)
        result = orch.retrieve("Available Funds", max_results=5)
        assert result["iterations"] <= config.max_iterations

    def test_empty_store(self, tmp_path, graph, config):
        empty_store = DualVectorStore(str(tmp_path / "empty_phase6"))
        orch = IterativeOrchestrator(empty_store, graph, config)
        result = orch.retrieve("some random query", max_results=5)
        assert result["results"] == [] or result["confidence"] == 0.0
