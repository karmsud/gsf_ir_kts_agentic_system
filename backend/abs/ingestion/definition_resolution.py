"""Stage 3.5: Definition resolution artifacts.

Builds definition dependency artifacts from extracted definition JSON and
persists deterministic, deal-scoped outputs.

Ported from PayGen pipeline.ingestion.definition_resolution → backend.abs.ingestion
No import rewrites needed — fully self-contained (networkx is lazy-imported).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DefinitionResolutionResult:
    """Result summary for definition resolution artifact generation."""

    term_count: int
    edge_count: int
    graph_node_count: int
    graph_edge_count: int
    cycle_count: int
    term_dictionary_path: Path
    edge_path: Path
    graph_path: Path
    tree_path: Path
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "term_count": self.term_count,
            "edge_count": self.edge_count,
            "graph_node_count": self.graph_node_count,
            "graph_edge_count": self.graph_edge_count,
            "cycle_count": self.cycle_count,
            "term_dictionary_path": str(self.term_dictionary_path),
            "edge_path": str(self.edge_path),
            "graph_path": str(self.graph_path),
            "tree_path": str(self.tree_path),
            "warnings": self.warnings,
        }


def build_definition_resolution_artifacts(
    extractions_dir: Path,
    graph_dir: Path,
    deal_id: str,
    min_confidence: float = 0.5,
    max_depth: int = 12,
) -> DefinitionResolutionResult:
    """Build definition resolution artifacts from definitions extraction.

    Args:
        extractions_dir: Directory containing extraction JSON files.
        graph_dir: Directory for graph/resolution artifacts.
        deal_id: Deal identifier.
        min_confidence: Minimum confidence to persist dependency edges.
        max_depth: Maximum traversal depth for dependency tree expansion.

    Returns:
        DefinitionResolutionResult with artifact counts and paths.
    """
    extractions_dir = Path(extractions_dir)
    graph_dir = Path(graph_dir)
    graph_dir.mkdir(parents=True, exist_ok=True)

    term_dictionary_path = extractions_dir / "term_dictionary.json"
    edge_path = graph_dir / "definition_dep_edges.json"
    graph_path = graph_dir / "definition_dep_graph.json"
    tree_path = graph_dir / "definition_resolution_trees.json"

    defs_path = extractions_dir / "definitions.json"
    if not defs_path.exists():
        result = DefinitionResolutionResult(
            term_count=0,
            edge_count=0,
            graph_node_count=0,
            graph_edge_count=0,
            cycle_count=0,
            term_dictionary_path=term_dictionary_path,
            edge_path=edge_path,
            graph_path=graph_path,
            tree_path=tree_path,
            warnings=[f"Definitions extraction missing: {defs_path}"],
        )
        term_dictionary_path.write_text("[]", encoding="utf-8")
        edge_path.write_text("[]", encoding="utf-8")
        graph_path.write_text(json.dumps({"nodes": [], "edges": []}, indent=2), encoding="utf-8")
        tree_path.write_text("[]", encoding="utf-8")
        return result

    raw_defs = json.loads(defs_path.read_text(encoding="utf-8"))
    if not isinstance(raw_defs, list):
        raw_defs = []

    term_dict = _build_term_dictionary(raw_defs, deal_id)
    edges = _build_dep_edges(term_dict, min_confidence=min_confidence)

    graph = _build_dep_graph(term_dict, edges)
    trees, cycle_count = _build_resolution_trees(term_dict, graph, max_depth=max_depth)

    term_dictionary_path.write_text(
        json.dumps(term_dict, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    edge_path.write_text(json.dumps(edges, indent=2, ensure_ascii=False), encoding="utf-8")

    graph_payload = {
        "nodes": [
            {
                "id": n,
                **attrs,
            }
            for n, attrs in graph.nodes(data=True)
        ],
        "edges": [
            {
                "source": u,
                "target": v,
                **attrs,
            }
            for u, v, attrs in graph.edges(data=True)
        ],
    }
    graph_path.write_text(json.dumps(graph_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    tree_path.write_text(json.dumps(trees, indent=2, ensure_ascii=False), encoding="utf-8")

    return DefinitionResolutionResult(
        term_count=len(term_dict),
        edge_count=len(edges),
        graph_node_count=graph.number_of_nodes(),
        graph_edge_count=graph.number_of_edges(),
        cycle_count=cycle_count,
        term_dictionary_path=term_dictionary_path,
        edge_path=edge_path,
        graph_path=graph_path,
        tree_path=tree_path,
    )


def _build_term_dictionary(raw_defs: list[dict], deal_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()

    for idx, item in enumerate(raw_defs, start=1):
        term_name = str(
            item.get("name")
            or item.get("term")
            or item.get("defined_term")
            or ""
        ).strip()
        if not term_name:
            continue

        key = term_name.lower()
        if key in seen:
            continue
        seen.add(key)

        definition_text = str(
            item.get("definition_text")
            or item.get("definition")
            or item.get("description")
            or ""
        ).strip()

        term_id = str(item.get("external_id") or f"DEF-{deal_id}-{idx:03d}")
        records.append(
            {
                "term_id": term_id,
                "term_name": term_name,
                "definition_text": definition_text,
                "source_reference": item.get("source_section", "definitions"),
                "method": "extracted_definition",
                "confidence": 1.0,
            }
        )

    return records


def _build_dep_edges(
    term_dictionary: list[dict[str, Any]],
    min_confidence: float,
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    sorted_terms = sorted(term_dictionary, key=lambda t: len(t["term_name"]), reverse=True)

    for src in term_dictionary:
        src_name = src["term_name"]
        text = src.get("definition_text", "")
        if not text:
            continue

        for tgt in sorted_terms:
            if tgt["term_id"] == src["term_id"]:
                continue

            tgt_name = tgt["term_name"]
            pattern = re.compile(rf"\b{re.escape(tgt_name)}\b", re.IGNORECASE)
            matches = pattern.findall(text)
            if not matches:
                continue

            confidence = min(1.0, 0.4 + 0.15 * len(matches))
            if confidence < min_confidence:
                continue

            edges.append(
                {
                    "from_term_id": src["term_id"],
                    "from_term_name": src_name,
                    "to_term_id": tgt["term_id"],
                    "to_term_name": tgt_name,
                    "match_count": len(matches),
                    "confidence": round(confidence, 4),
                    "method": "regex_boundary",
                    "evidence": {
                        "matched_term": tgt_name,
                    },
                }
            )

    return edges


def _build_dep_graph(term_dictionary: list[dict[str, Any]], edges: list[dict[str, Any]]):
    import networkx as nx

    graph = nx.DiGraph()
    for term in term_dictionary:
        graph.add_node(
            term["term_id"],
            term_name=term["term_name"],
            source_reference=term.get("source_reference", "definitions"),
        )

    for edge in edges:
        graph.add_edge(
            edge["from_term_id"],
            edge["to_term_id"],
            confidence=edge["confidence"],
            method=edge["method"],
            match_count=edge["match_count"],
        )

    return graph


def _build_resolution_trees(
    term_dictionary: list[dict[str, Any]],
    graph,
    max_depth: int,
) -> tuple[list[dict[str, Any]], int]:
    import networkx as nx

    term_lookup = {t["term_id"]: t for t in term_dictionary}
    cycle_nodes: set[str] = set()
    if not nx.is_directed_acyclic_graph(graph):
        for cycle in nx.simple_cycles(graph):
            for node in cycle:
                cycle_nodes.add(node)

    trees: list[dict[str, Any]] = []

    for term in term_dictionary:
        term_id = term["term_id"]
        tree = _expand_tree(
            term_id=term_id,
            graph=graph,
            term_lookup=term_lookup,
            depth=0,
            max_depth=max_depth,
            seen_path=[],
        )
        tree["cycle_detected"] = term_id in cycle_nodes

        if not tree["cycle_detected"]:
            sub_nodes = _collect_nodes(tree)
            subgraph = graph.subgraph(sub_nodes).copy()
            try:
                tree["topological_order"] = list(nx.topological_sort(subgraph))
            except Exception:
                tree["topological_order"] = []
        else:
            tree["topological_order"] = []

        trees.append(tree)

    return trees, len(cycle_nodes)


def _expand_tree(
    term_id: str,
    graph,
    term_lookup: dict[str, dict[str, Any]],
    depth: int,
    max_depth: int,
    seen_path: list[str],
) -> dict[str, Any]:
    term = term_lookup.get(term_id, {})
    node = {
        "term_id": term_id,
        "term_name": term.get("term_name", term_id),
        "source_reference": term.get("source_reference", "definitions"),
        "depth": depth,
        "depends_on": [],
        "cycle_detected": term_id in seen_path,
    }

    if depth >= max_depth or node["cycle_detected"]:
        return node

    for dep_id in graph.successors(term_id):
        child = _expand_tree(
            term_id=dep_id,
            graph=graph,
            term_lookup=term_lookup,
            depth=depth + 1,
            max_depth=max_depth,
            seen_path=[*seen_path, term_id],
        )
        node["depends_on"].append(child)

    return node


def _collect_nodes(tree: dict[str, Any]) -> set[str]:
    nodes: set[str] = {tree["term_id"]}
    for child in tree.get("depends_on", []):
        nodes.update(_collect_nodes(child))
    return nodes
