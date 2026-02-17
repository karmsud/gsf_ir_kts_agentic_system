from __future__ import annotations

from backend.graph import GraphBuilder, GraphStore
from backend.common.models import AgentResult
from .base_agent import AgentBase


class GraphBuilderAgent(AgentBase):
    agent_name = "graph-builder-agent"

    def __init__(self, config):
        super().__init__(config)
        self.builder = GraphBuilder(GraphStore(config.graph_path))

    def execute(self, request: dict) -> AgentResult:
        doc = request["document"]
        metadata = request.get("metadata", {})
        graph = self.builder.upsert_document(doc, metadata)
        return self.quality_check(
            AgentResult(
                success=True,
                confidence=0.95,
                data={"graph_nodes": graph.number_of_nodes(), "graph_edges": graph.number_of_edges()},
                reasoning="Upserted document nodes and relationships in knowledge graph.",
            )
        )
