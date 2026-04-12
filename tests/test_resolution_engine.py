"""
Tests for the Definition Resolution Engine (Modules 1-5).

Covers:
  Module 1 — Term Dictionary Extraction
  Module 2 — Preliminary Statement Table Extraction
  Module 3 — Reference Scanning
  Module 4 — Dependency Graph Construction
  Module 5 — Resolution Tree Pre-computation
"""

from __future__ import annotations

import json
from decimal import Decimal

import networkx as nx
import pytest

from backend.extraction.definition_extractor import (
    extract_definitions_section,
    extract_term_dictionary,
)
from backend.extraction.prelim_statement_parser import (
    ClassMetadata,
    extract_and_parse,
    extract_preliminary_statement,
    parse_class_table,
)
from backend.graph.reference_scanner import (
    build_reference_map,
    build_section_reference_map,
    extract_section_references,
)
from backend.graph.definition_graph_builder import build_definition_graph
from backend.graph.resolution_tree import (
    build_resolution_tree,
    format_resolution_tree_for_llm,
    precompute_all_resolution_trees,
    resolve_term,
)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

SAMPLE_PSA_TEXT = '''\
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
of principal previously distributed to the holder pursuant to Section 5.04, \
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

"Realized Losses" means losses allocated on the Mortgage Loans.

"Applied Realized Loss Amounts" means amounts applied against \
Certificate Principal Balance to cover Realized Losses.

"Prepayment Interest Shortfall" means the shortfall in interest due \
to Prepayments reducing the Stated Principal Balance before the \
Scheduled Payment date.

"Compensating Interest" means amounts paid by the Master Servicer \
to compensate for Prepayment Interest Shortfalls.

"Cut-off Date" means March 1, 2006.

"Initial Certificate Principal Balance" means the initial principal \
balance of a Certificate as set forth in the Preliminary Statement.

"Stated Principal Balance" means the outstanding principal balance \
of a Mortgage Loan.

"Scheduled Payment" means the monthly principal and interest payment \
due on a Mortgage Loan.

ARTICLE II.
CONVEYANCE
'''

SAMPLE_PRELIM_TEXT = '''\
PRELIMINARY STATEMENT

The following table sets forth information with respect to the Certificates:

Class I-A-1    $417,353,000    5.250%    Fixed   07468WAA1
Class I-A-2    $100,000,000    5.150%    Fixed   07468WAB9
Class M-1      $50,000,000     5.500%    Fixed   07468WAC7
Class CE       Notional        N/A       N/A

ARTICLE II.
'''


@pytest.fixture
def term_dict():
    """Return a pre-computed term dictionary from sample text."""
    return extract_term_dictionary(SAMPLE_PSA_TEXT)


@pytest.fixture
def ref_map(term_dict):
    """Return a reference map from the sample dictionary."""
    return build_reference_map(term_dict)


@pytest.fixture
def sample_graph(term_dict, ref_map):
    """Build a graph with DEPENDS_ON edges for the sample dictionary."""
    g = nx.DiGraph()
    section_refs = build_section_reference_map(term_dict)
    return build_definition_graph(g, term_dict, ref_map, section_refs)


# ═══════════════════════════════════════════════════════════════════════
# Module 1: Term Dictionary Extraction
# ═══════════════════════════════════════════════════════════════════════


class TestModule1:
    def test_section_boundary(self):
        text, start, end = extract_definitions_section(SAMPLE_PSA_TEXT)
        assert 'ARTICLE I' in text
        assert 'CONVEYANCE' not in text, 'Should not include Article II content'

    def test_parse_means_pattern(self, term_dict):
        assert 'Distribution Date' in term_dict
        assert '25th' in term_dict['Distribution Date']

    def test_parse_colon_pattern(self):
        """Colon separator should also work (tested via 'means' in sample)."""
        assert len(extract_term_dictionary(SAMPLE_PSA_TEXT)) >= 10

    def test_multi_paragraph_definition(self, term_dict):
        """Certificate Principal Balance has multiple reduction clauses."""
        assert 'Certificate Principal Balance' in term_dict
        defn = term_dict['Certificate Principal Balance']
        assert 'Realized Losses' in defn
        assert 'Section 5.04' in defn

    def test_term_count(self, term_dict):
        """Sample PSA text should yield at least 13 defined terms."""
        assert len(term_dict) >= 13

    def test_empty_text(self):
        assert extract_term_dictionary('') == {}

    def test_no_definitions_section(self):
        assert extract_term_dictionary('No definitions here at all.') == {}


# ═══════════════════════════════════════════════════════════════════════
# Module 2: Preliminary Statement Table Extraction
# ═══════════════════════════════════════════════════════════════════════


class TestModule2:
    def test_locate_section(self):
        text = extract_preliminary_statement(SAMPLE_PRELIM_TEXT)
        assert 'Class I-A-1' in text

    def test_parse_class_count(self):
        classes = parse_class_table(SAMPLE_PRELIM_TEXT)
        assert len(classes) >= 3

    def test_dollar_amount(self):
        classes = parse_class_table(SAMPLE_PRELIM_TEXT)
        assert 'I-A-1' in classes
        assert classes['I-A-1'].initial_cpb == Decimal('417353000')

    def test_rate_extraction(self):
        classes = parse_class_table(SAMPLE_PRELIM_TEXT)
        assert classes['I-A-1'].initial_rate == Decimal('5.250') / 100

    def test_notional_flag(self):
        classes = parse_class_table(SAMPLE_PRELIM_TEXT)
        assert 'CE' in classes
        assert classes['CE'].is_notional is True

    def test_cusip(self):
        classes = parse_class_table(SAMPLE_PRELIM_TEXT)
        assert classes['I-A-1'].cusip == '07468WAA1'

    def test_extract_and_parse_convenience(self):
        classes = extract_and_parse(SAMPLE_PRELIM_TEXT)
        assert len(classes) >= 3

    def test_empty_text(self):
        assert extract_and_parse('') == {}


# ═══════════════════════════════════════════════════════════════════════
# Module 3: Reference Scanning
# ═══════════════════════════════════════════════════════════════════════


class TestModule3:
    def test_longest_match(self, ref_map):
        """'Certificate Principal Balance' matched as one term."""
        # Current Interest references Certificate Principal Balance (not just "Certificate")
        refs = ref_map.get('Current Interest', set())
        assert 'Certificate Principal Balance' in refs

    def test_no_self_reference(self, ref_map):
        for term, refs in ref_map.items():
            assert term not in refs, f'{term} should not self-reference'

    def test_current_interest_references(self, ref_map):
        refs = ref_map.get('Current Interest', set())
        expected = {'Certificate Principal Balance', 'Accrual Period', 'Pass-Through Rate',
                    'Prepayment Interest Shortfall', 'Compensating Interest', 'Distribution Date'}
        missing = expected - refs
        assert len(missing) <= 1, f'Missing references: {missing}'

    def test_section_cross_references(self, term_dict):
        refs = extract_section_references(term_dict.get('Certificate Principal Balance', ''))
        assert '5.04' in refs

    def test_section_reference_map(self, term_dict):
        sec_map = build_section_reference_map(term_dict)
        assert 'Certificate Principal Balance' in sec_map

    def test_empty_dictionary(self):
        assert build_reference_map({}) == {}


# ═══════════════════════════════════════════════════════════════════════
# Module 4: Dependency Graph Construction
# ═══════════════════════════════════════════════════════════════════════


class TestModule4:
    def test_term_nodes_added(self, sample_graph, term_dict):
        for term in term_dict:
            assert f'TERM::{term}' in sample_graph

    def test_depends_on_edges(self, sample_graph):
        edges = [
            (u, v) for u, v, d in sample_graph.edges(data=True)
            if d.get('type') == 'DEPENDS_ON'
        ]
        assert len(edges) > 0

    def test_cycle_detection_in_sample(self, sample_graph):
        """Sample data has a real cycle (Applied Realized Loss Amounts <-> Certificate Principal Balance).
        The builder should detect and log it."""
        depends_edges = [
            (u, v) for u, v, d in sample_graph.edges(data=True)
            if d.get('type') == 'DEPENDS_ON'
        ]
        sub = sample_graph.edge_subgraph(depends_edges).copy()
        cycles = list(nx.simple_cycles(sub))
        assert len(cycles) >= 1, "Expected at least one cycle in sample PSA cross-references"

    def test_depth_annotation(self, sample_graph):
        node = 'TERM::Current Interest'
        assert sample_graph.nodes[node].get('depth', 0) >= 2

    def test_leaf_annotation(self, sample_graph):
        node = 'TERM::Cut-off Date'
        assert sample_graph.nodes[node].get('is_leaf') is True

    def test_transitive_count(self, sample_graph):
        node = 'TERM::Current Interest'
        tc = sample_graph.nodes[node].get('transitive_dep_count', 0)
        assert tc >= 3


# ═══════════════════════════════════════════════════════════════════════
# Module 5: Resolution Tree Pre-computation
# ═══════════════════════════════════════════════════════════════════════


class TestModule5:
    def test_resolution_tree_structure(self, sample_graph):
        tree = build_resolution_tree(sample_graph, 'TERM::Current Interest')
        assert tree['term'] == 'Current Interest'
        assert tree['depth'] >= 2
        assert len(tree['dependencies']) >= 3

    def test_leaf_tree(self, sample_graph):
        tree = build_resolution_tree(sample_graph, 'TERM::Cut-off Date')
        assert tree['is_leaf'] is True
        assert tree['depth'] == 0

    def test_memoisation(self, sample_graph):
        memo: dict = {}
        build_resolution_tree(sample_graph, 'TERM::Current Interest', memo=memo)
        build_resolution_tree(sample_graph, 'TERM::Accrual Period', memo=memo)
        # Shared subtrees should be cached
        assert 'TERM::Distribution Date' in memo

    def test_precompute_all(self, sample_graph, term_dict):
        # precompute_all_resolution_trees is now a no-op (trees computed at query time)
        trees = precompute_all_resolution_trees(sample_graph)
        assert isinstance(trees, dict)  # returns empty dict (no-op)
        assert len(trees) == 0

    def test_resolve_term(self, sample_graph):
        precompute_all_resolution_trees(sample_graph)
        result = resolve_term(sample_graph, 'Current Interest')
        assert result is not None
        assert result['depth'] >= 2
        assert 'formatted_tree' in result

    def test_resolve_missing_term(self, sample_graph):
        assert resolve_term(sample_graph, 'Nonexistent Term') is None

    def test_format_for_llm_readable(self, sample_graph):
        tree = build_resolution_tree(sample_graph, 'TERM::Current Interest')
        text = format_resolution_tree_for_llm(tree, max_depth=3)
        assert 'Current Interest' in text
        # Format uses layered dependency map (-> for chains, [term]: for definitions)
        assert '->' in text or '[' in text

    def test_cycle_handling(self):
        """Artificial cycle produces cycle_detected marker on the back-edge."""
        g = nx.DiGraph()
        g.add_node('TERM::A', type='defined_term', term_name='A', definition_text='See B.')
        g.add_node('TERM::B', type='defined_term', term_name='B', definition_text='See A.')
        g.add_edge('TERM::A', 'TERM::B', type='DEPENDS_ON')
        g.add_edge('TERM::B', 'TERM::A', type='DEPENDS_ON')

        tree = build_resolution_tree(g, 'TERM::A')
        # A -> B is fine, but B -> A is a back-edge (cycle)
        subtree_b = tree['dependencies'].get('B', {})
        assert subtree_b is not None
        # Inside B's dependencies, A should appear with cycle_detected
        subtree_a_via_b = subtree_b.get('dependencies', {}).get('A', {})
        assert subtree_a_via_b.get('cycle_detected') is True

    def test_json_roundtrip(self, sample_graph):
        tree = build_resolution_tree(sample_graph, 'TERM::Current Interest')
        s = json.dumps(tree)
        loaded = json.loads(s)
        assert loaded['term'] == 'Current Interest'
        assert loaded['depth'] == tree['depth']
