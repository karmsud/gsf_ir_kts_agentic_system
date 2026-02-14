from __future__ import annotations

from backend.common.models import AgentResult, LearningStep, TrainingPath
from backend.graph import GraphQueries, GraphStore
from .base_agent import AgentBase


class TrainingPathAgent(AgentBase):
    agent_name = "training-path-agent"

    def __init__(self, config):
        super().__init__(config)
        self.graph_store = GraphStore(config.graph_path)

    def execute(self, request: dict) -> AgentResult:
        topic = request["topic"]
        level = request.get("level", "beginner")
        max_steps = int(request.get("max_steps", 10))

        graph = self.graph_store.load()
        docs = GraphQueries.find_docs_for_topic(graph, topic)

        if level == "beginner":
            docs = [doc for doc in docs if doc.get("doc_type") not in {"RELEASE_NOTE"}]
        elif level == "advanced":
            docs = docs
        else:
            docs = docs

        docs = docs[:max_steps]

        steps: list[LearningStep] = []
        seen_doc_ids: set[str] = set()
        for index, doc in enumerate(docs):
            doc_id = doc["id"].split(":", maxsplit=1)[1]
            if doc_id in seen_doc_ids:
                continue
            seen_doc_ids.add(doc_id)
            estimated_time = int(max(5, len(str(doc.get("title", ""))) / 2))
            steps.append(
                LearningStep(
                    order=index + 1,
                    doc_id=doc_id,
                    doc_title=doc.get("title", "Untitled"),
                    doc_type=doc.get("doc_type", "UNKNOWN"),
                    estimated_time_minutes=estimated_time,
                    difficulty=level,
                    description=f"Read {doc.get('title', 'document')} for {topic}.",
                    prerequisites=[],
                )
            )

        total_time = sum(step.estimated_time_minutes for step in steps)
        coverage = min(1.0, len(steps) / max(1, max_steps))
        training_path = TrainingPath(topic=topic, level=level, steps=steps, total_time_minutes=total_time, coverage=coverage)
        confidence = 0.9 if steps else 0.4
        return self.quality_check(
            AgentResult(
                success=True,
                confidence=confidence,
                data={"training_path": training_path},
                reasoning="Generated training path from topic coverage edges.",
            )
        )
