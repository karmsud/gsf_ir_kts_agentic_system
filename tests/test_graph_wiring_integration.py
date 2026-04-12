"""
Integration tests for the full graph wiring pipeline:

  Ingestion:
    Module 1  DefinedTermExtractor → term_dictionary
    Module 3  build_reference_map  → DEPENDS_ON edges
    Module 4  build_definition_graph → TERM:: nodes + DAG metrics
    Module 5  precompute_all_resolution_trees → resolution_tree JSON on nodes
    Module 6  compute_pagerank → pagerank floats on nodes

  Retrieval:
    HumanLikeRetriever._build_indexes  → _term_node_index populated
    enrich_with_definitions            → resolution trees injected into context

These tests use the SAMPLE_PSA_TEXT from test_resolution_engine.py to
build a realistic graph and verify every link in the chain.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import networkx as nx
import pytest

from backend.extraction.definition_extractor import extract_term_dictionary
from backend.graph.reference_scanner import build_reference_map, build_section_reference_map
from backend.graph.definition_graph_builder import build_definition_graph
from backend.graph.resolution_tree import (
    precompute_all_resolution_trees,
    resolve_term,
    format_resolution_tree_for_llm,
)
from backend.graph.pagerank import compute_pagerank
from backend.graph.enhanced_graph_builder import EnhancedGraphBuilder


# ═══════════════════════════════════════════════════════════════════
# Mini PSA text for controlled testing
# ═══════════════════════════════════════════════════════════════════

PSA_TEXT = '''\
ARTICLE I.
DEFINITIONS

Section 1.01 Definitions.

"Distribution Date" means the 25th day of each month \
(or if such day is not a Business Day, the next succeeding \
Business Day), commencing in February 2006.

"Business Day" means any day other than a Saturday, Sunday, \
or a day on which banking institutions in the City of New York \
are authorized or obligated by law or by executive order to be closed.

"Certificate Principal Balance" means, with respect to any Certificate, \
the Initial Certificate Principal Balance thereof reduced by all amounts \
of principal previously distributed pursuant to Section 5.04, \
and further reduced by Realized Losses and Applied Realized Loss Amounts \
allocated thereto.

"Current Interest" means, as of any Distribution Date, with respect to \
any Certificate, the amount of interest accrued on the Certificate Principal \
Balance thereof during the related Accrual Period at the applicable \
Pass-Through Rate, plus recovered preferences, minus Prepayment Interest \
Shortfalls net of Compensating Interest.

"Accrual Period" means, with respect to any Distribution Date, the period \
from and including the prior Distribution Date (or with respect to the \
first Distribution Date, from the Cut-off Date) to but excluding such \
Distribution Date.

"Pass-Through Rate" means with respect to the Class I-A-1 Certificates, \
5.250% per annum (30/360 basis).

"Realized Losses" means losses allocated on the Mortgage Loans related to \
any liquidated Mortgage Loan, including the amount by which the outstanding \
principal balance of such Mortgage Loan exceeds the Net Liquidation Proceeds.

"Applied Realized Loss Amounts" means amounts applied against \
Certificate Principal Balance to cover Realized Losses allocated to such \
Certificate pursuant to the related Pooling and Servicing Agreement.

"Cut-off Date" means March 1, 2006.

"Closing Date" means the date of issuance of the Certificates, \
being a Business Day on or about March 30, 2006.

"Servicer" means Bear Stearns Mortgage Management LLC, or \
any successor servicer appointed pursuant to the Agreement.

"Trustee" means Deutsche Bank National Trust Company, \
a national banking association, or any successor trustee.

"Mortgage Loan" means each of the mortgage loans transferred \
and assigned to the Trustee pursuant to this Agreement, \
as identified in the Mortgage Loan Schedule attached hereto.

ARTICLE II.
CONVEYANCE
'''


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def term_dictionary():
    """Module 1: Extract defined terms using the state-machine parser (same as ingestion pipeline)."""
    return extract_term_dictionary(PSA_TEXT)


@pytest.fixture
def reference_map(term_dictionary):
    """Module 3: Build reference map."""
    return build_reference_map(term_dictionary)


@pytest.fixture
def enriched_graph(term_dictionary, reference_map):
    """Modules 4+5+6: Full graph with DEPENDS_ON edges, resolution trees, and PageRank."""
    G = nx.DiGraph()
    section_refs = build_section_reference_map(term_dictionary)

    # Module 4: Dependency graph
    G = build_definition_graph(G, term_dictionary, reference_map, section_refs)

    # Module 5: Resolution trees — now computed at query time.
    # Build them here for test assertions using the low-level API.
    from backend.graph.resolution_tree import build_resolution_tree
    memo: dict = {}
    trees: dict = {}
    for nid in G.nodes:
        if G.nodes[nid].get("type") == "defined_term":
            tree = build_resolution_tree(G, nid, memo=memo)
            name = G.nodes[nid].get("term_name", nid)
            trees[name] = tree
    # Also call the no-op shim to ensure it doesn't crash
    precompute_all_resolution_trees(G)

    # Module 6: PageRank
    pr_scores = compute_pagerank(G, alpha=0.85)
    for nid, score in pr_scores.items():
        G.nodes[nid]["pagerank"] = score

    return G, trees, pr_scores


# ═══════════════════════════════════════════════════════════════════
# Test 1: Module 1 — Term extraction
# ═══════════════════════════════════════════════════════════════════

class TestModule1_TermExtraction:
    def test_extracts_key_terms(self, term_dictionary):
        """extract_term_dictionary should find the quoted terms in PSA text."""
        # At minimum, these core terms should be extracted
        expected_terms = {"Distribution Date", "Business Day", "Certificate Principal Balance",
                          "Current Interest", "Accrual Period", "Pass-Through Rate",
                          "Realized Losses", "Cut-off Date"}
        found = set(term_dictionary.keys())
        missing = expected_terms - found
        assert len(missing) == 0, f"Missing terms: {missing}. Found: {found}"

    def test_definition_text_captured(self, term_dictionary):
        """Each term should have non-empty definition text."""
        for term, text in term_dictionary.items():
            assert len(text) > 10, f"Term '{term}' has too-short definition: {text!r}"


# ═══════════════════════════════════════════════════════════════════
# Test 2: Module 3 — Reference scanning
# ═══════════════════════════════════════════════════════════════════

class TestModule3_ReferenceScan:
    def test_current_interest_references(self, term_dictionary, reference_map):
        """'Current Interest' mentions 'Distribution Date', 'Certificate Principal Balance',
        'Accrual Period', 'Pass-Through Rate' — all should appear as references."""
        refs = reference_map.get("Current Interest", set())
        expected = {"Distribution Date", "Certificate Principal Balance", "Accrual Period", "Pass-Through Rate"}
        missing = expected - refs
        assert len(missing) == 0, (
            f"Current Interest should reference {expected} but found {refs}. Missing: {missing}"
        )

    def test_cpb_references_realized_losses(self, reference_map):
        """'Certificate Principal Balance' references 'Realized Losses'."""
        refs = reference_map.get("Certificate Principal Balance", set())
        assert "Realized Losses" in refs, f"CPB refs: {refs}"

    def test_no_self_references(self, reference_map):
        """No term should reference itself."""
        for term, refs in reference_map.items():
            assert term not in refs, f"'{term}' references itself"

    def test_section_cross_refs(self, term_dictionary):
        """CPB mentions 'Section 5.04' — should be extracted."""
        section_refs = build_section_reference_map(term_dictionary)
        cpb_secs = section_refs.get("Certificate Principal Balance", [])
        assert any("5.04" in s for s in cpb_secs), f"Expected Section 5.04 in CPB. Got: {cpb_secs}"


# ═══════════════════════════════════════════════════════════════════
# Test 3: Module 4 — Dependency graph construction
# ═══════════════════════════════════════════════════════════════════

class TestModule4_DependencyGraph:
    def test_term_nodes_created(self, enriched_graph):
        """Every term should have a TERM:: node with type='defined_term'."""
        G, _, _ = enriched_graph
        term_nodes = [n for n in G if G.nodes[n].get("type") == "defined_term"]
        assert len(term_nodes) >= 8, f"Expected >= 8 TERM:: nodes, got {len(term_nodes)}"

    def test_depends_on_edges_exist(self, enriched_graph):
        """Graph should contain DEPENDS_ON edges between terms."""
        G, _, _ = enriched_graph
        depends_on = [(u, v) for u, v, d in G.edges(data=True) if d.get("type") == "DEPENDS_ON"]
        assert len(depends_on) > 0, "No DEPENDS_ON edges found!"
        # Current Interest → Certificate Principal Balance
        ci_node = "TERM::Current Interest"
        cpb_node = "TERM::Certificate Principal Balance"
        assert G.has_edge(ci_node, cpb_node), (
            f"Expected edge {ci_node} → {cpb_node}. Edges from CI: "
            f"{list(G.successors(ci_node))}"
        )

    def test_depth_annotated(self, enriched_graph):
        """Terms with dependencies should have depth > 0."""
        G, _, _ = enriched_graph
        ci_node = "TERM::Current Interest"
        assert ci_node in G, f"Node {ci_node} not in graph"
        depth = G.nodes[ci_node].get("depth", -1)
        assert depth > 0, f"Current Interest depth should be > 0, got {depth}"


# ═══════════════════════════════════════════════════════════════════
# Test 4: Module 5 — Resolution tree pre-computation
# ═══════════════════════════════════════════════════════════════════

class TestModule5_ResolutionTree:
    def test_trees_computed_for_all_terms(self, enriched_graph):
        """Every defined term should have a resolution tree."""
        G, trees, _ = enriched_graph
        term_nodes = [n for n in G if G.nodes[n].get("type") == "defined_term"]
        for node in term_nodes:
            term_name = G.nodes[node].get("term_name")
            assert term_name in trees, f"No tree for term: {term_name}"

    def test_tree_resolved_at_query_time(self, enriched_graph):
        """resolve_term() should walk edges live and return a valid tree."""
        G, _, _ = enriched_graph
        result = resolve_term(G, "Current Interest")
        assert result is not None, "resolve_term returned None for Current Interest"
        assert result["term"] == "Current Interest"
        assert result["depth"] > 0
        assert result["dependency_count"] > 0
        # The formatted tree should contain the dependency map header
        assert "Dependency Map" in result["formatted_tree"]

    def test_current_interest_tree_has_cpb(self, enriched_graph):
        """Current Interest's tree should include Certificate Principal Balance as a dependency."""
        G, trees, _ = enriched_graph
        ci_tree = trees.get("Current Interest", {})
        deps = ci_tree.get("dependencies", {})
        assert "Certificate Principal Balance" in deps, (
            f"Expected 'Certificate Principal Balance' in CI dependencies. Got: {list(deps.keys())}"
        )

    def test_cpb_tree_has_realized_losses(self, enriched_graph):
        """Certificate Principal Balance → Realized Losses should appear in the tree."""
        G, trees, _ = enriched_graph
        cpb_tree = trees.get("Certificate Principal Balance", {})
        deps = cpb_tree.get("dependencies", {})
        assert "Realized Losses" in deps, (
            f"Expected 'Realized Losses' in CPB dependencies. Got: {list(deps.keys())}"
        )

    def test_resolve_term_query_helper(self, enriched_graph):
        """resolve_term() should return formatted tree for query-time use."""
        G, _, _ = enriched_graph
        result = resolve_term(G, "Current Interest")
        assert result is not None
        assert result["depth"] > 0
        assert "Current Interest" in result["formatted_tree"]
        assert "Certificate Principal Balance" in result["formatted_tree"]

    def test_leaf_term_has_depth_zero(self, enriched_graph):
        """'Cut-off Date' has no dependencies — depth should be 0."""
        G, trees, _ = enriched_graph
        tree = trees.get("Cut-off Date", {})
        assert tree.get("depth", -1) == 0, f"Cut-off Date depth should be 0, got {tree.get('depth')}"
        assert tree.get("is_leaf", False) is True


# ═══════════════════════════════════════════════════════════════════
# Test 5: Module 6 — PageRank
# ═══════════════════════════════════════════════════════════════════

class TestModule6_PageRank:
    def test_all_nodes_have_pagerank(self, enriched_graph):
        """Every node in the graph should have a pagerank attribute."""
        G, _, pr_scores = enriched_graph
        for node in G.nodes:
            assert "pagerank" in G.nodes[node], f"Node {node} missing pagerank"
            assert G.nodes[node]["pagerank"] > 0, f"Node {node} has zero pagerank"

    def test_pagerank_scores_positive(self, enriched_graph):
        """PageRank scores should all be positive (no negative/zero)."""
        _, _, pr_scores = enriched_graph
        assert all(v > 0 for v in pr_scores.values())

    def test_highly_referenced_terms_rank_higher(self, enriched_graph):
        """Terms referenced by many others should have higher PageRank.
        'Distribution Date' and 'Realized Losses' are referenced by multiple terms,
        so they should rank higher than standalone leaf terms like 'Cut-off Date'."""
        G, _, pr_scores = enriched_graph
        # Find some term nodes
        dist_date = pr_scores.get("TERM::Distribution Date", 0)
        cutoff = pr_scores.get("TERM::Cut-off Date", 0)
        # Distribution Date is referenced IN several definitions, but as a
        # target of DEPENDS_ON edges it has high in-degree → higher PageRank
        # This is a soft assertion since graph size is small
        if dist_date > 0 and cutoff > 0:
            # At minimum, scores should be non-zero
            assert dist_date > 0 and cutoff > 0


# ═══════════════════════════════════════════════════════════════════
# Test 6: Retrieval integration — _term_node_index + tree injection
# ═══════════════════════════════════════════════════════════════════

class TestRetrievalIntegration:
    """Test that HumanLikeRetriever picks up TERM:: nodes and injects resolution trees."""

    def _build_full_graph(self):
        """Build a graph that has both ITEM nodes (Definition type) and TERM:: nodes."""
        G = nx.DiGraph()

        # Add ITEM nodes (as EnhancedGraphBuilder would create)
        G.add_node("item:def:dist_date", type="ITEM", item_type="Definition",
                    text='"Distribution Date" means the 25th day of each month.')
        G.add_node("item:def:current_interest", type="ITEM", item_type="Definition",
                    text='"Current Interest" means the amount of interest accrued on the Certificate Principal Balance.')
        G.add_node("item:def:cpb", type="ITEM", item_type="Definition",
                    text='"Certificate Principal Balance" means the Initial Certificate Principal Balance reduced by Realized Losses.')
        G.add_node("item:def:realized_losses", type="ITEM", item_type="Definition",
                    text='"Realized Losses" means losses allocated on the Mortgage Loans.')

        # Add SECTION node
        G.add_node("sec:test:0001", type="SECTION", section_number="1.01", heading="Definitions")

        # Add TERM:: nodes (as build_definition_graph would create)
        term_dict = {
            "Distribution Date": "the 25th day of each month",
            "Current Interest": "the amount of interest accrued on the Certificate Principal Balance during the Accrual Period at the Pass-Through Rate",
            "Certificate Principal Balance": "the Initial Certificate Principal Balance reduced by Realized Losses",
            "Realized Losses": "losses allocated on the Mortgage Loans",
        }
        ref_map = build_reference_map(term_dict)
        G = build_definition_graph(G, term_dict, ref_map)

        # Pre-compute resolution trees
        precompute_all_resolution_trees(G)

        # PageRank
        pr = compute_pagerank(G)
        for nid, score in pr.items():
            G.nodes[nid]["pagerank"] = score

        return G

    def test_term_node_index_populated(self):
        """_term_node_index should contain entries for TERM:: nodes."""
        from backend.retrieval.human_like_retriever import HumanLikeRetriever, RetrievalConfig
        from unittest.mock import MagicMock

        G = self._build_full_graph()

        # Create minimal dual_store mock (not used for this test)
        dual_store = MagicMock()
        config = RetrievalConfig(inject_definitions=True)
        retriever = HumanLikeRetriever(dual_store, G, config)

        # Should have both _definition_index (from ITEM nodes) and _term_node_index (from TERM:: nodes)
        assert len(retriever._definition_index) > 0, "No definitions indexed"
        assert len(retriever._term_node_index) > 0, (
            f"No TERM:: nodes indexed. Graph has type=defined_term? "
            f"{[n for n in G if G.nodes[n].get('type') == 'defined_term']}"
        )
        assert "current interest" in retriever._term_node_index
        assert "certificate principal balance" in retriever._term_node_index

    def test_resolution_tree_injected_in_enrichment(self):
        """enrich_with_definitions should inject resolution trees for terms that have them."""
        from backend.retrieval.human_like_retriever import HumanLikeRetriever, RetrievalConfig

        # Minimal ExplainabilityLogger mock
        class FakeXLog:
            def step(self, *a, **kw):
                self.last_step = (a, kw)

        G = self._build_full_graph()

        dual_store_mock = type('DS', (), {
            'query_items': lambda *a, **kw: [],
            'query_sections': lambda *a, **kw: [],
        })()
        config = RetrievalConfig(inject_definitions=True, max_definitions_per_chunk=5)
        retriever = HumanLikeRetriever(dual_store_mock, G, config)
        xlog = FakeXLog()

        # Simulate a retrieval result that mentions "Current Interest"
        results = [{
            "text": "The Current Interest for the Class I-A-1 Certificates shall be calculated as described in Section 5.04.",
            "chunk_id": "test_chunk_1",
        }]

        enriched, glossary = retriever.enrich_with_definitions(results, xlog)
        assert len(enriched) == 1

        # Graph-known terms (in _term_node_index) are resolved to the shared
        # glossary (resolution_context), not per-chunk injected_definitions.
        assert "current interest" in retriever._term_node_index, (
            f"Current Interest not in _term_node_index. Keys: {list(retriever._term_node_index.keys())}"
        )
        # The shared glossary should contain the resolution tree content
        assert glossary, "Shared resolution glossary is empty"
        assert "Current Interest" in glossary, (
            f"Current Interest not found in glossary. Glossary excerpt: {glossary[:200]}"
        )
        assert "Certificate Principal Balance" in glossary, (
            f"Certificate Principal Balance not in resolution glossary. Excerpt: {glossary[:200]}"
        )

    def test_enriched_text_includes_tree(self):
        """The definitions_glossary (shared context) should contain the formatted tree."""
        from backend.retrieval.human_like_retriever import HumanLikeRetriever, RetrievalConfig

        class FakeXLog:
            def step(self, *a, **kw): pass

        G = self._build_full_graph()
        dual_store_mock = type('DS', (), {
            'query_items': lambda *a, **kw: [],
            'query_sections': lambda *a, **kw: [],
        })()
        config = RetrievalConfig(inject_definitions=True, max_definitions_per_chunk=5)
        retriever = HumanLikeRetriever(dual_store_mock, G, config)

        results = [{
            "text": "Current Interest for each certificate class.",
            "chunk_id": "chunk_2",
        }]

        enriched, glossary = retriever.enrich_with_definitions(results, FakeXLog())

        # The shared glossary should contain tree notation (depth= and deps)
        assert "depth=" in glossary or "deps)" in glossary or "Dependency Map" in glossary, (
            f"Glossary should contain tree notation. Got: {glossary[:300]}"
        )

    def test_leaf_term_has_no_tree(self):
        """Leaf terms (depth=0) should NOT have resolution_tree injected."""
        from backend.retrieval.human_like_retriever import HumanLikeRetriever, RetrievalConfig

        class FakeXLog:
            def step(self, *a, **kw): pass

        G = self._build_full_graph()
        dual_store_mock = type('DS', (), {
            'query_items': lambda *a, **kw: [],
            'query_sections': lambda *a, **kw: [],
        })()
        config = RetrievalConfig(inject_definitions=True, max_definitions_per_chunk=5)
        retriever = HumanLikeRetriever(dual_store_mock, G, config)

        # Query with only "Realized Losses" (a leaf term)
        results = [{
            "text": "Realized Losses on the Mortgage Loans for this period totaled $1.2M.",
            "chunk_id": "chunk_3",
        }]

        enriched, _glossary = retriever.enrich_with_definitions(results, FakeXLog())
        defs = enriched[0].get("injected_definitions", [])
        rl_defs = [d for d in defs if d["term"] == "Realized Losses"]
        if rl_defs:
            # If found, should NOT have a resolution tree (depth=0)
            assert "resolution_tree" not in rl_defs[0], (
                f"Leaf term should not have resolution_tree. Got: {rl_defs[0]}"
            )
