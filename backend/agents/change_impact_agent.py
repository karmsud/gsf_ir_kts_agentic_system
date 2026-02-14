from __future__ import annotations

from backend.common.models import AgentResult, ImpactReport
from backend.graph import GraphQueries, GraphStore
from .base_agent import AgentBase


class ChangeImpactAgent(AgentBase):
    agent_name = "change-impact-agent"

    def __init__(self, config):
        super().__init__(config)
        self.graph_store = GraphStore(config.graph_path)

    def execute(self, request: dict) -> AgentResult:
        entity = request["entity"]
        entity_type = request.get("entity_type", "auto")
        graph = self.graph_store.load()
        direct_docs = GraphQueries.find_docs_for_tool(graph, entity)
        processes = GraphQueries.find_processes_for_tool(graph, entity)

        indirect_docs = []
        for process in processes:
            process_name = process.get("name", "")
            indirect_docs.extend(GraphQueries.find_docs_for_process(graph, process_name))

        dedup_indirect = {
            doc.get("id"): doc
            for doc in indirect_docs
            if doc.get("id") and doc.get("id") not in {d.get("id") for d in direct_docs}
        }

        severity = "low"
        total_impacted = len(direct_docs) + len(dedup_indirect)
        if total_impacted >= 6:
            severity = "high"
        elif total_impacted >= 3:
            severity = "medium"

        recommendations = []
        if total_impacted:
            recommendations.append("Review directly impacted documentation first.")
            if dedup_indirect:
                recommendations.append("Review process-dependent documentation for indirect impact.")
        else:
            recommendations.append("No impacted docs found; verify entity spelling and graph ingestion status.")

        report = ImpactReport(
            entity=entity,
            entity_type=entity_type,
            direct_docs=[{"id": doc.get("id", ""), "title": doc.get("title", "") } for doc in direct_docs],
            indirect_docs=[{"id": doc.get("id", ""), "title": doc.get("title", "") } for doc in dedup_indirect.values()],
            stale_images=[],
            affected_processes=[{"id": proc.get("id", ""), "name": proc.get("name", "") } for proc in processes],
            affected_training=[{"id": doc.get("id", ""), "title": doc.get("title", "") } for doc in direct_docs if doc.get("doc_type") == "TRAINING"],
            recommended_actions=recommendations,
            severity=severity,
        )

        confidence = 0.9 if direct_docs or dedup_indirect else 0.45
        return self.quality_check(
            AgentResult(
                success=True,
                confidence=confidence,
                data={"impact_report": report},
                reasoning="Computed direct and indirect impact for changed entity.",
            )
        )
