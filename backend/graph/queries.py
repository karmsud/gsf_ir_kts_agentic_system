from __future__ import annotations

from typing import List

import networkx as nx

from backend.common.doc_types import normalize_doc_type


class GraphQueries:
    """Static query helpers that operate on an ``nx.DiGraph``.

    Edge types produced by GraphBuilder:
        DEFINES, MENTIONS, COVERS, ADDRESSES

    Node-id prefixes:
        doc:<id>, term:<id>, tool:<id>, topic:<id>, error:<id>
    """

    # ------------------------------------------------------------------
    # Tool queries
    # ------------------------------------------------------------------

    @staticmethod
    def find_docs_for_tool(G: nx.DiGraph, tool_name: str) -> List[dict]:
        """Return all DOCUMENT nodes that MENTION *tool_name*."""
        tool_id = f"tool:{tool_name.lower()}"
        if tool_id not in G:
            return []
        docs = []
        # Edges are doc→tool with type=MENTIONS, so tool is a successor target.
        # We need predecessors of the tool node.
        for pred in G.predecessors(tool_id):
            edge_data = G[pred][tool_id]
            if edge_data.get("type") == "MENTIONS" and G.nodes[pred].get("type") == "DOCUMENT":
                docs.append({"id": pred, **G.nodes[pred]})
        return docs

    @staticmethod
    def find_processes_for_tool(G: nx.DiGraph, tool_name: str) -> List[dict]:
        """Return process-type nodes connected to *tool_name* (if any)."""
        tool_id = f"tool:{tool_name.lower()}"
        if tool_id not in G:
            return []
        processes = []
        for nbr in G.predecessors(tool_id):
            if str(nbr).startswith("process:"):
                processes.append({"id": nbr, **G.nodes[nbr]})
        for nbr in G.successors(tool_id):
            if str(nbr).startswith("process:"):
                processes.append({"id": nbr, **G.nodes[nbr]})
        return processes

    # ------------------------------------------------------------------
    # Topic queries
    # ------------------------------------------------------------------

    @staticmethod
    def find_docs_for_topic(G: nx.DiGraph, topic: str) -> List[dict]:
        """Return all DOCUMENT nodes that COVER *topic*."""
        topic_id = f"topic:{topic.lower()}"
        if topic_id not in G:
            return []
        docs = []
        for pred in G.predecessors(topic_id):
            edge_data = G[pred][topic_id]
            if edge_data.get("type") == "COVERS" and G.nodes[pred].get("type") == "DOCUMENT":
                docs.append({"id": pred, **G.nodes[pred]})
        return docs

    # ------------------------------------------------------------------
    # Process queries (kept for backward compat — process nodes are rare)
    # ------------------------------------------------------------------

    @staticmethod
    def find_docs_for_process(G: nx.DiGraph, process_name: str) -> List[dict]:
        """Return DOCUMENT nodes linked to a process node."""
        process_id = f"process:{process_name.lower()}"
        if process_id not in G:
            return []
        docs = []
        for pred in G.predecessors(process_id):
            if G.nodes[pred].get("type") == "DOCUMENT":
                docs.append({"id": pred, **G.nodes[pred]})
        for succ in G.successors(process_id):
            if G.nodes[succ].get("type") == "DOCUMENT":
                docs.append({"id": succ, **G.nodes[succ]})
        return docs

    # ------------------------------------------------------------------
    # Error-code queries
    # ------------------------------------------------------------------

    @staticmethod
    def find_docs_for_error(G: nx.DiGraph, error_code: str) -> List[dict]:
        """Return all DOCUMENT nodes that ADDRESS *error_code*."""
        err_id = f"error:{error_code.upper()}"
        if err_id not in G:
            return []
        docs = []
        for pred in G.predecessors(err_id):
            edge_data = G[pred][err_id]
            if edge_data.get("type") == "ADDRESSES" and G.nodes[pred].get("type") == "DOCUMENT":
                docs.append({"id": pred, **G.nodes[pred]})
        return docs

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    @staticmethod
    def doc_stats(G: nx.DiGraph) -> dict:
        """Aggregate counts by doc_type."""
        docs = [
            attrs
            for _, attrs in G.nodes(data=True)
            if attrs.get("type") == "DOCUMENT"
        ]
        by_type: dict[str, int] = {}
        for doc in docs:
            dt = normalize_doc_type(doc.get("doc_type", "UNKNOWN"))
            by_type[dt] = by_type.get(dt, 0) + 1
        return {"documents": len(docs), "by_doc_type": by_type}

    # ------------------------------------------------------------------
    # Multi-hop helpers (new — leverage NetworkX)
    # ------------------------------------------------------------------

    @staticmethod
    def related_docs(G: nx.DiGraph, doc_id: str, max_hops: int = 2) -> List[dict]:
        """Find documents reachable within *max_hops* from *doc_id*."""
        doc_node = f"doc:{doc_id}" if not doc_id.startswith("doc:") else doc_id
        if doc_node not in G:
            return []

        # BFS up to max_hops on undirected view
        visited: set[str] = set()
        frontier = {doc_node}
        for _ in range(max_hops):
            next_frontier: set[str] = set()
            for n in frontier:
                for nbr in list(G.predecessors(n)) + list(G.successors(n)):
                    if nbr not in visited and nbr != doc_node:
                        next_frontier.add(nbr)
            visited |= next_frontier
            frontier = next_frontier

        # Filter to DOCUMENT nodes only
        results = []
        for n in visited:
            if G.nodes[n].get("type") == "DOCUMENT":
                results.append({"id": n, **G.nodes[n]})
        return results
