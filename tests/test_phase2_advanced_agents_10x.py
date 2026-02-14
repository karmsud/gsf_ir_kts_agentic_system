from __future__ import annotations

import json
from pathlib import Path

from backend.agents import ChangeImpactAgent, FreshnessAgent, GraphBuilderAgent, IngestionAgent, TrainingPathAgent
from config import load_config


def test_training_impact_freshness_10_scenarios(tmp_path: Path):
    cfg = load_config()
    cfg.knowledge_base_path = str(tmp_path / "kb")
    cfg.graph_path = str(tmp_path / "kb" / "graph" / "knowledge_graph.json")
    cfg.chroma_persist_dir = str(tmp_path / "kb" / "vectors" / "chroma")

    ingest = IngestionAgent(cfg)
    build = GraphBuilderAgent(cfg)

    for name, text, doc_type in [
        ("a.md", "ToolX onboarding support", "TRAINING"),
        ("b.md", "ToolX deployment process", "SOP"),
        ("c.md", "ToolY incident troubleshooting", "TROUBLESHOOT"),
    ]:
        source = tmp_path / name
        source.write_text(text, encoding="utf-8")
        result = ingest.execute({"path": str(source)})
        doc = result.data["document"]
        mpath = Path(doc.metadata_path)
        meta = json.loads(mpath.read_text(encoding="utf-8"))
        meta["doc_type"] = doc_type
        meta["tools"] = ["ToolX"] if "ToolX" in text else ["ToolY"]
        meta["topics"] = ["onboarding"] if "onboarding" in text else ["deployment"]
        meta["processes"] = ["DeployProcess"] if "deployment" in text else ["SupportProcess"]
        mpath.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        build.execute({"document": doc, "metadata": meta})

    train = TrainingPathAgent(cfg)
    impact = ChangeImpactAgent(cfg)
    fresh = FreshnessAgent(cfg)

    r1 = train.execute({"topic": "onboarding", "level": "beginner", "max_steps": 10})
    r2 = train.execute({"topic": "deployment", "level": "advanced", "max_steps": 1})
    r3 = train.execute({"topic": "missing-topic", "level": "beginner"})

    r4 = impact.execute({"entity": "ToolX"})
    r5 = impact.execute({"entity": "ToolY"})
    r6 = impact.execute({"entity": "NoSuchTool"})

    r7 = fresh.execute({"scope": "all"})
    r8 = fresh.execute({"scope": "TRAINING"})
    r9 = fresh.execute({"threshold_days": 0})
    r10 = fresh.execute({"include_images": False})

    assert r1.success and r1.data["training_path"].coverage >= 0.0
    assert len(r2.data["training_path"].steps) <= 1
    assert r3.data["training_path"].steps == []
    assert r4.data["impact_report"].severity in {"low", "medium", "high"}
    assert r5.success
    assert r6.success and r6.data["impact_report"].recommended_actions
    assert r7.data["freshness_report"].total_documents >= 1
    assert r8.success
    assert r9.success
    assert r10.success
