from __future__ import annotations

import json
import logging
from pathlib import Path

import networkx as nx

logger = logging.getLogger(__name__)


class GraphStore:
    """Persistent knowledge-graph store backed by NetworkX DiGraph.

    On disk the graph is stored as JSON (NetworkX node-link format).
    In memory it is always materialised as an ``nx.DiGraph`` so every
    consumer gets O(1) adjacency look-ups, multi-hop traversal, and
    the full NetworkX algorithm suite for free.
    """

    def __init__(self, graph_path: str):
        self.path = Path(graph_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            # Bootstrap with an empty graph
            self._save_nx(nx.DiGraph())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> nx.DiGraph:
        """Deserialise the JSON file into an ``nx.DiGraph``."""
        with self.path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return self._dict_to_nx(raw)

    def save(self, graph: nx.DiGraph) -> None:
        """Persist an ``nx.DiGraph`` to JSON."""
        self._save_nx(graph)

    # ------------------------------------------------------------------
    # Legacy / migration helpers
    # ------------------------------------------------------------------

    def load_raw(self) -> dict:
        """Return the raw JSON dict (nodes/edges) for migration tooling."""
        with self.path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _save_nx(self, G: nx.DiGraph) -> None:
        data = self._nx_to_dict(G)
        with self.path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    @staticmethod
    def _nx_to_dict(G: nx.DiGraph) -> dict:
        """Convert an ``nx.DiGraph`` to the project's canonical JSON schema.

        Schema::

            {
              "nodes": { "<id>": {attr…}, … },
              "edges": [ {"source": …, "target": …, "type": …, …}, … ]
            }
        """
        nodes = {}
        for node_id, attrs in G.nodes(data=True):
            nodes[node_id] = {"id": node_id, **attrs}

        edges = []
        for src, tgt, attrs in G.edges(data=True):
            edges.append({"source": src, "target": tgt, **attrs})

        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def _dict_to_nx(raw: dict) -> nx.DiGraph:
        """Convert the canonical JSON dict back into an ``nx.DiGraph``."""
        G = nx.DiGraph()

        for node_id, attrs in raw.get("nodes", {}).items():
            clean = {k: v for k, v in attrs.items() if k != "id"}
            G.add_node(node_id, **clean)

        for edge in raw.get("edges", []):
            src = edge["source"]
            tgt = edge["target"]
            attrs = {k: v for k, v in edge.items() if k not in ("source", "target")}
            G.add_edge(src, tgt, **attrs)

        return G
