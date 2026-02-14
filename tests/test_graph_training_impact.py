from pathlib import Path
import json

from config import load_config
from backend.agents import GraphBuilderAgent, IngestionAgent, TrainingPathAgent, ChangeImpactAgent


def test_training_and_impact_use_graph_relations():
    cfg = load_config()
    ingestion = IngestionAgent(cfg)
    graph_builder = GraphBuilderAgent(cfg)

    ingest_result = ingestion.execute({"path": str(Path("tests/fixtures/complex/enterprise_onboarding.md"))})
    document = ingest_result.data["document"]

    metadata_path = Path(document.metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["topics"] = ["onboarding"]
    metadata["tools"] = ["ToolX"]
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    graph_builder.execute({"document": document, "metadata": metadata})

    training = TrainingPathAgent(cfg).execute({"topic": "onboarding", "level": "beginner"})
    impact = ChangeImpactAgent(cfg).execute({"entity": "ToolX"})

    assert training.success
    assert len(training.data["training_path"].steps) >= 1
    assert impact.success
    assert len(impact.data["impact_report"].direct_docs) >= 1
