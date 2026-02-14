from __future__ import annotations

from backend.common.models import IngestedDocument
from .persistence import GraphStore


class GraphBuilder:
    def __init__(self, store: GraphStore):
        self.store = store

    def upsert_document(self, doc: IngestedDocument, metadata: dict) -> dict:
        graph = self.store.load()
        nodes = graph.setdefault("nodes", {})
        edges = graph.setdefault("edges", [])
        edge_keys = {(e.get("source"), e.get("target"), e.get("type")) for e in edges}

        def add_edge(source: str, target: str, edge_type: str) -> None:
            key = (source, target, edge_type)
            if key not in edge_keys:
                edges.append({"source": source, "target": target, "type": edge_type})
                edge_keys.add(key)

        doc_node_id = f"document:{doc.doc_id}"
        nodes[doc_node_id] = {
            "id": doc_node_id,
            "type": "DOCUMENT",
            "title": metadata.get("title", doc.doc_id),
            "doc_type": metadata.get("doc_type", "UNKNOWN"),
            "source_path": doc.source_path,
            "version": doc.version,
            "tags": metadata.get("tags", []),
        }

        for tool in metadata.get("tools", []):
            tool_id = f"tool:{tool}"
            nodes[tool_id] = {"id": tool_id, "type": "TOOL", "name": tool}
            add_edge(tool_id, doc_node_id, "DOCUMENTS")

        for topic in metadata.get("topics", []):
            topic_id = f"topic:{topic}"
            nodes[topic_id] = {"id": topic_id, "type": "TOPIC", "name": topic}
            add_edge(doc_node_id, topic_id, "COVERS_TOPIC")

        for process in metadata.get("processes", []):
            process_id = f"process:{process}"
            nodes[process_id] = {"id": process_id, "type": "PROCESS", "name": process}
            add_edge(process_id, doc_node_id, "DOCUMENTS")
            for tool in metadata.get("tools", []):
                tool_id = f"tool:{tool}"
                add_edge(tool_id, process_id, "MENTIONS")

        self.store.save(graph)
        return graph
