"""
Graph builder adapter — bridges PayGen graph calls to KTS EnhancedGraphBuilder.

Phase 22 replacement for Phase 21 stub.

KTS APIs used:
    GraphStore(graph_path) → JSON-backed NetworkX persistence
    EnhancedGraphBuilder(store) → hierarchical graph builder with
        build_hierarchical_graph(doc_id, doc_type, sections)

Ported from PayGen pipeline.skills.graph_builder → backend.abs.skills
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import networkx as nx

from backend.abs.config.graph_schema import (
    ABS_NODE_TYPES,
    ABS_EDGE_TYPES,
    get_all_node_type_names,
)

logger = logging.getLogger(__name__)

# ── Lazy KTS infrastructure imports ──────────────────────────────

try:
    from backend.graph.persistence import GraphStore
    from backend.graph.enhanced_graph_builder import EnhancedGraphBuilder
    _HAS_GRAPH = True
except ImportError:
    _HAS_GRAPH = False
    logger.warning("KTS EnhancedGraphBuilder unavailable — graph ops will fail")


# ── Node Types (kept for backward compat with consuming agents) ──
NODE_TYPES = [
    "definition", "waterfall_rule", "account", "class",
    "trigger", "loss_allocation", "credit_enhancement",
]


# ── Public API ────────────────────────────────────────────────────


def build_graph(
    sections: list[dict],
    config=None,
    deal_id: str = "",
    doc_type: str = "psa",
) -> nx.DiGraph:
    """Build ABS knowledge graph using KTS's enhanced builder.

    Transforms PayGen's flat section format into KTS's typed format,
    then delegates to EnhancedGraphBuilder.

    Args:
        sections: PayGen-format section dicts with items.
        config: KTSConfig instance.
        deal_id: Deal identifier.
        doc_type: Document type for extractor routing.

    Returns:
        NetworkX DiGraph with ABS-typed nodes/edges.
    """
    if not _HAS_GRAPH:
        raise RuntimeError(
            "KTS EnhancedGraphBuilder not available. "
            "Ensure backend.graph.persistence and backend.graph.enhanced_graph_builder "
            "are importable."
        )

    if config is None:
        from config.settings import load_config
        config = load_config()

    graph_path = getattr(config, "graph_path", str(Path.cwd() / "knowledge_graph.json"))
    store = GraphStore(graph_path)
    builder = EnhancedGraphBuilder(store)

    # Transform PayGen sections to KTS format
    kts_sections = _transform_sections(sections)

    # Build via KTS builder
    document_id = deal_id or "abs_deal"
    stats = builder.build_hierarchical_graph(
        document_id=document_id,
        doc_type=doc_type,
        sections=kts_sections,
        doc_metadata={"abs_domain": True, "deal_id": deal_id},
        doc_name_prefix=f"abs_{deal_id}_" if deal_id else "abs_",
    )

    # Load the built graph
    graph = store.load()

    # Tag ABS nodes
    for node_id, data in graph.nodes(data=True):
        data["abs_domain"] = True

    # PageRank
    pagerank_enabled = getattr(config, "abs_graph_pagerank_enabled", True)
    if pagerank_enabled:
        _compute_pagerank(graph)

    node_count = graph.number_of_nodes()
    edge_count = graph.number_of_edges()
    logger.info(
        f"Built ABS graph: {node_count} nodes, {edge_count} edges "
        f"(stats: {stats})"
    )

    return graph


def _transform_sections(sections: list[dict]) -> list[dict]:
    """Transform PayGen section format to KTS format.

    PayGen:
        {"section_id": "5.02", "title": "...", "text": "...", "items": [...]}
    KTS (build_hierarchical_graph expects):
        {"section_number": "5.02", "section_heading": "...", "section_text": "..."}
    """
    kts_sections = []
    for s in sections:
        sid = s.get("section_id", s.get("section_number", "unknown"))
        title = s.get("title", s.get("section_heading", ""))
        text = s.get("text", s.get("section_text", ""))

        kts_sections.append({
            "section_number": sid,
            "section_heading": title,
            "section_text": text,
        })

    return kts_sections


def _classify_item_type(item: dict) -> str:
    """Map PayGen item type to ABS node type."""
    item_type = item.get("type", "").lower()
    mapping = {
        "definition": "abs_definition",
        "obligation": "abs_obligation",
        "rule": "abs_waterfall_rule",
        "waterfall": "abs_waterfall_rule",
        "account": "abs_account",
        "trigger": "abs_trigger",
        "event_of_default": "abs_trigger",
        "class": "abs_class",
    }
    return mapping.get(item_type, "abs_obligation")


def _compute_pagerank(graph: nx.DiGraph) -> None:
    """Compute and attach PageRank scores."""
    if graph.number_of_nodes() == 0:
        return
    try:
        ranks = nx.pagerank(graph, alpha=0.85, max_iter=100)
        for node_id, score in ranks.items():
            graph.nodes[node_id]["pagerank"] = score
        logger.debug(f"Computed PageRank for {len(ranks)} nodes")
    except nx.NetworkXError as exc:
        logger.warning(f"PageRank computation failed: {exc}")


def save_graph(graph: nx.DiGraph, path: Path) -> None:
    """Save graph to GraphML file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(graph, str(path))
    logger.info(f"Saved graph to {path}")


def load_graph(path: Path) -> Optional[nx.DiGraph]:
    """Load graph from GraphML file."""
    path = Path(path)
    if not path.exists():
        logger.warning(f"Graph file not found: {path}")
        return None
    graph = nx.read_graphml(str(path))
    logger.info(f"Loaded graph from {path}: {graph.number_of_nodes()} nodes")
    return graph


def get_neighbors(
    graph: nx.DiGraph,
    node_id: str,
    depth: int = 1,
    edge_types: Optional[set[str]] = None,
) -> list[tuple[str, dict]]:
    """Get neighboring nodes up to specified depth via BFS.

    Args:
        graph: The knowledge graph.
        node_id: Starting node.
        depth: BFS depth.
        edge_types: Optional filter for edge types.

    Returns:
        List of (node_id, node_data) tuples.
    """
    if node_id not in graph:
        return []

    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(node_id, 0)]
    results: list[tuple[str, dict]] = []

    while queue:
        current, d = queue.pop(0)
        if current in visited or d > depth:
            continue
        visited.add(current)

        if current != node_id:
            results.append((current, dict(graph.nodes[current])))

        for neighbor in graph.successors(current):
            edge_data = graph.edges[current, neighbor]
            if edge_types is None or edge_data.get("edge_type") in edge_types:
                queue.append((neighbor, d + 1))

    return results


def query_graph(
    G: nx.DiGraph,
    node_type: Optional[str] = None,
    node_id: Optional[str] = None,
) -> dict[str, Any]:
    """Query graph for structured information.

    Args:
        G: NetworkX DiGraph.
        node_type: Filter by node type.
        node_id: Look up specific node.

    Returns:
        Dict with matching nodes/data.
    """
    if node_id and node_id in G:
        return {"node": node_id, "data": dict(G.nodes[node_id]),
                "successors": list(G.successors(node_id)),
                "predecessors": list(G.predecessors(node_id))}

    if node_type:
        matches = [
            (nid, dict(data))
            for nid, data in G.nodes(data=True)
            if data.get("type") == node_type or data.get("node_type") == node_type
        ]
        return {"node_type": node_type, "count": len(matches), "nodes": matches}

    return {"total_nodes": G.number_of_nodes(), "total_edges": G.number_of_edges()}


def find_dependencies(G: nx.DiGraph, node_id: str) -> list[str]:
    """Get all transitive dependencies (ancestors) of a node."""
    if node_id not in G:
        return []
    return list(nx.ancestors(G, node_id))


def find_dependents(G: nx.DiGraph, node_id: str) -> list[str]:
    """Get all transitive dependents (descendants) of a node."""
    if node_id not in G:
        return []
    return list(nx.descendants(G, node_id))


def detect_cycles(G: nx.DiGraph) -> list[list[str]]:
    """Detect circular dependencies in the graph."""
    try:
        return list(nx.simple_cycles(G))
    except nx.NetworkXError:
        return []


def get_waterfall_order(G: nx.DiGraph) -> list[str]:
    """Get topologically sorted waterfall rules."""
    try:
        all_sorted = list(nx.topological_sort(G))
        return [
            n for n in all_sorted
            if G.nodes[n].get("type") in ("waterfall_rule", "abs_waterfall_rule")
            or G.nodes[n].get("node_type") in ("waterfall_rule", "abs_waterfall_rule")
        ]
    except nx.NetworkXUnfeasible:
        logger.warning("Graph has cycles — cannot determine waterfall order")
        return []
