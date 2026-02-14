from __future__ import annotations

from backend.common.doc_types import normalize_doc_type


class GraphQueries:
    @staticmethod
    def find_docs_for_tool(graph: dict, tool_name: str) -> list[dict]:
        tool_id = f"tool:{tool_name}"
        doc_ids = {
            edge["target"]
            for edge in graph.get("edges", [])
            if edge.get("source") == tool_id and edge.get("type") == "DOCUMENTS"
        }
        return [graph["nodes"][doc_id] for doc_id in doc_ids if doc_id in graph.get("nodes", {})]

    @staticmethod
    def find_processes_for_tool(graph: dict, tool_name: str) -> list[dict]:
        tool_id = f"tool:{tool_name}"
        process_ids = {
            edge["target"]
            for edge in graph.get("edges", [])
            if edge.get("source") == tool_id and edge.get("type") == "MENTIONS" and str(edge.get("target", "")).startswith("process:")
        }
        return [graph["nodes"][process_id] for process_id in process_ids if process_id in graph.get("nodes", {})]

    @staticmethod
    def find_docs_for_process(graph: dict, process_name: str) -> list[dict]:
        process_id = f"process:{process_name}"
        doc_ids = {
            edge["target"]
            for edge in graph.get("edges", [])
            if edge.get("source") == process_id and edge.get("type") == "DOCUMENTS"
        }
        return [graph["nodes"][doc_id] for doc_id in doc_ids if doc_id in graph.get("nodes", {})]

    @staticmethod
    def find_docs_for_topic(graph: dict, topic: str) -> list[dict]:
        topic_id = f"topic:{topic}"
        doc_ids = {
            edge["source"]
            for edge in graph.get("edges", [])
            if edge.get("target") == topic_id and edge.get("type") == "COVERS_TOPIC"
        }
        return [graph["nodes"][doc_id] for doc_id in doc_ids if doc_id in graph.get("nodes", {})]

    @staticmethod
    def doc_stats(graph: dict) -> dict:
        docs = [n for n in graph.get("nodes", {}).values() if n.get("type") == "DOCUMENT"]
        by_type: dict[str, int] = {}
        for doc in docs:
            doc_type = normalize_doc_type(doc.get("doc_type", "UNKNOWN"))
            by_type[doc_type] = by_type.get(doc_type, 0) + 1
        return {"documents": len(docs), "by_doc_type": by_type}
