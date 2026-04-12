"""
Phase 17.2 — Graph Partitioner

Partitions a deal-level graph into per-document sub-graphs based on
the ``doc_name_prefix`` attribute.  Also builds cross-document edges
in the deal graph.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Set

import networkx as nx

logger = logging.getLogger(__name__)


def partition_graph_by_document(
    deal_graph: nx.DiGraph,
    output_dir: str,
) -> Dict[str, int]:
    """
    Partition a deal-level graph into per-document sub-graphs.

    Args:
        deal_graph: The full deal graph with ``doc_name_prefix`` on all nodes.
        output_dir: Directory to write ``doc_graphs/`` into.

    Returns:
        Dict mapping ``doc_name_prefix`` → node count in sub-graph.
    """
    doc_graphs_dir = Path(output_dir) / "doc_graphs"
    doc_graphs_dir.mkdir(parents=True, exist_ok=True)

    # Group nodes by doc_name_prefix
    prefix_nodes: Dict[str, Set[str]] = {}
    for node_id, attrs in deal_graph.nodes(data=True):
        prefix = attrs.get("doc_name_prefix", "")
        if prefix:
            prefix_nodes.setdefault(prefix, set()).add(node_id)

    stats: Dict[str, int] = {}

    for prefix, node_ids in prefix_nodes.items():
        sub_graph = deal_graph.subgraph(node_ids).copy()
        out_path = doc_graphs_dir / f"{prefix}.json"
        _save_graph_json(sub_graph, out_path)
        stats[prefix] = len(node_ids)
        logger.info(
            "[Phase17] Doc graph %s: %d nodes, %d edges → %s",
            prefix,
            len(node_ids),
            sub_graph.number_of_edges(),
            out_path,
        )

    return stats


def add_cross_document_edges(deal_graph: nx.DiGraph) -> int:
    """
    Detect and add cross-document relationship edges.

    Cross-doc edges are identified when:

    1. A DEFINED_TERM node is DEFINED in doc A but REFERENCED in doc B
    2. An NER entity appears in multiple documents
    3. A concept keyword appears in multiple documents

    Returns:
        Count of cross-document edges added.
    """
    cross_edges_added = 0

    # Collect DEFINED_TERM / TERM nodes with their doc_name_prefix
    term_nodes: Dict[str, Dict[str, list]] = {}  # term_text → {prefix → [node_ids]}
    for node_id, attrs in deal_graph.nodes(data=True):
        node_type = attrs.get("type", "")
        prefix = attrs.get("doc_name_prefix", "")
        if not prefix:
            continue

        if node_type in ("DEFINED_TERM", "TERM"):
            label = attrs.get("surface_form", attrs.get("name", attrs.get("label", node_id)))
            term_nodes.setdefault(label, {}).setdefault(prefix, []).append(node_id)

    # Add CROSS_DOC_TERM edges for terms appearing in multiple docs
    for term_label, prefix_map in term_nodes.items():
        if len(prefix_map) < 2:
            continue
        prefixes = list(prefix_map.keys())
        for i in range(len(prefixes)):
            for j in range(i + 1, len(prefixes)):
                src_nodes = prefix_map[prefixes[i]]
                tgt_nodes = prefix_map[prefixes[j]]
                for src in src_nodes:
                    for tgt in tgt_nodes:
                        if not deal_graph.has_edge(src, tgt):
                            deal_graph.add_edge(
                                src,
                                tgt,
                                type="CROSS_DOC_TERM",
                                source_doc=prefixes[i],
                                target_doc=prefixes[j],
                                term=term_label,
                            )
                            cross_edges_added += 1

    # Collect NER entity nodes by entity name
    entity_nodes: Dict[str, Dict[str, list]] = {}
    for node_id, attrs in deal_graph.nodes(data=True):
        node_type = attrs.get("type", "")
        prefix = attrs.get("doc_name_prefix", "")
        if node_type in ("ENTITY", "NER_ENTITY") and prefix:
            name = attrs.get("surface_form", attrs.get("name", attrs.get("label", "")))
            if name:
                entity_nodes.setdefault(name, {}).setdefault(prefix, []).append(node_id)

    # Add CROSS_DOC_ENTITY edges
    for entity_name, prefix_map in entity_nodes.items():
        if len(prefix_map) < 2:
            continue
        prefixes = list(prefix_map.keys())
        for i in range(len(prefixes)):
            for j in range(i + 1, len(prefixes)):
                src = prefix_map[prefixes[i]][0]
                tgt = prefix_map[prefixes[j]][0]
                if not deal_graph.has_edge(src, tgt):
                    deal_graph.add_edge(
                        src,
                        tgt,
                        type="CROSS_DOC_ENTITY",
                        source_doc=prefixes[i],
                        target_doc=prefixes[j],
                        entity=entity_name,
                    )
                    cross_edges_added += 1

    logger.info("[Phase17] Added %d cross-document edges", cross_edges_added)
    return cross_edges_added


def _save_graph_json(G: nx.DiGraph, path: Path) -> None:
    """Save graph in the project's canonical JSON format."""
    nodes = {}
    for node_id, attrs in G.nodes(data=True):
        nodes[node_id] = {"id": node_id, **attrs}
    edges = []
    for src, tgt, attrs in G.edges(data=True):
        edges.append({"source": src, "target": tgt, **attrs})
    data = {"nodes": nodes, "edges": edges}
    if G.graph:
        data["graph"] = dict(G.graph)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
