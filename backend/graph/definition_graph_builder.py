"""
Module 4: Dependency Graph Construction

Adds DEPENDS_ON edges to the existing NetworkX knowledge graph.
Validates DAG property. Computes topological sort and depth metrics.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

import networkx as nx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_definition_graph(
    graph: nx.DiGraph,
    term_dictionary: Dict[str, str],
    reference_map: Dict[str, Set[str]],
    section_references: Optional[Dict[str, List[str]]] = None,
) -> nx.DiGraph:
    """
    Add definition nodes and DEPENDS_ON edges to the knowledge graph.

    Args:
        graph: Existing NetworkX knowledge graph.
        term_dictionary: {term_name → definition_text} from Module 1.
        reference_map: {term_name → set of referenced terms} from Module 3.
        section_references: {term_name → list of section ids} from Module 3.

    Returns:
        Enhanced graph with DEPENDS_ON edges and depth annotations.
    """
    # 1. Upsert nodes for each defined term
    for term_name, definition_text in term_dictionary.items():
        node_id = f'TERM::{term_name}'

        if node_id not in graph:
            graph.add_node(node_id)

        graph.nodes[node_id].update({
            'type': 'defined_term',
            'term_name': term_name,
            'definition_text': definition_text,
            'text_length': len(definition_text),
        })

    # 2. Add DEPENDS_ON edges
    added_edges = 0
    for term_name, references in reference_map.items():
        source_id = f'TERM::{term_name}'
        for ref_term in references:
            target_id = f'TERM::{ref_term}'
            if target_id in graph:
                graph.add_edge(source_id, target_id, type='DEPENDS_ON')
                added_edges += 1

    # 3. Add CROSS_REF edges for section references
    if section_references:
        for term_name, sections in section_references.items():
            source_id = f'TERM::{term_name}'
            for section in sections:
                section_id = f'SECTION::{section}'
                if section_id in graph:
                    graph.add_edge(source_id, section_id, type='CROSS_REF')

    logger.info('Added %d DEPENDS_ON edges to knowledge graph.', added_edges)

    # 4. Validate & annotate
    _validate_and_annotate(graph, term_dictionary)

    return graph


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_depends_on_subgraph(graph: nx.DiGraph) -> nx.DiGraph:
    """Extract the subgraph containing only DEPENDS_ON edges."""
    depends_on_edges = [
        (u, v) for u, v, d in graph.edges(data=True)
        if d.get('type') == 'DEPENDS_ON'
    ]
    if not depends_on_edges:
        return nx.DiGraph()
    return graph.edge_subgraph(depends_on_edges).copy()


def _validate_and_annotate(
    graph: nx.DiGraph,
    term_dictionary: Dict[str, str],
) -> None:
    """Validate DAG property and compute depth / topo-order metrics."""
    term_nodes = [
        n for n in graph
        if graph.nodes[n].get('type') == 'defined_term'
    ]
    subgraph = _get_depends_on_subgraph(graph)

    # Cycle detection — use find_cycle (fast O(V+E)) instead of
    # simple_cycles which is exponential for dense legal-term graphs.
    has_cycles = False
    try:
        cycle_edges = nx.find_cycle(subgraph)
        has_cycles = True
        cycle_nodes = [u for u, v in cycle_edges]
        names = [graph.nodes[n].get('term_name', n) for n in cycle_nodes]
        logger.warning('Cycle detected in definition graph (sample): %s', ' → '.join(names[:10]))
        for node in cycle_nodes:
            graph.nodes[node]['has_cycle'] = True
    except nx.NetworkXNoCycle:
        logger.info('Definition graph is a valid DAG (no cycles).')

    # Depth & leaf annotation
    for node in term_nodes:
        if node not in subgraph:
            graph.nodes[node]['depth'] = 0
            graph.nodes[node]['is_leaf'] = True
            graph.nodes[node]['transitive_dep_count'] = 0
            continue

        descendants = nx.descendants(subgraph, node) if node in subgraph else set()
        graph.nodes[node]['transitive_dep_count'] = len(descendants)

        if not descendants:
            graph.nodes[node]['depth'] = 0
            graph.nodes[node]['is_leaf'] = True
        else:
            max_depth = 0
            for desc in descendants:
                try:
                    length = nx.shortest_path_length(subgraph, node, desc)
                    max_depth = max(max_depth, length)
                except nx.NetworkXNoPath:
                    pass
            graph.nodes[node]['depth'] = max_depth
            graph.nodes[node]['is_leaf'] = False

    # Topological sort (only if acyclic)
    if not has_cycles:
        try:
            topo_order = list(nx.topological_sort(subgraph))
            for i, node in enumerate(topo_order):
                graph.nodes[node]['topo_order'] = i
        except nx.NetworkXUnfeasible:
            logger.warning('Topological sort failed despite no simple cycles.')

    # Summary stats
    depths = [graph.nodes[n].get('depth', 0) for n in term_nodes]
    if depths:
        logger.info(
            'Graph stats: %d terms, max depth %d, avg depth %.1f.',
            len(term_nodes),
            max(depths),
            sum(depths) / len(depths),
        )
