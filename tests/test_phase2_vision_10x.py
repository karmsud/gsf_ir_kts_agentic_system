from __future__ import annotations

from pathlib import Path

from backend.agents import VisionAgent
from config import load_config


def test_vision_10_scenarios(tmp_path: Path):
    cfg = load_config()
    cfg.knowledge_base_path = str(tmp_path / "kb")
    cfg.chroma_persist_dir = str(tmp_path / "kb" / "vectors" / "chroma")
    agent = VisionAgent(cfg)

    images = []
    for idx in range(1, 4):
        img = tmp_path / f"img_{idx}.png"
        img.write_bytes(b"fake")
        images.append(str(img))

    r1 = agent.execute({"operation": "initialize", "doc_id": "doc_v", "image_paths": images, "descriptions": {}})
    r2 = agent.execute({"operation": "status", "doc_id": "doc_v"})
    r3 = agent.execute({"operation": "list_pending", "doc_id": "doc_v"})
    r4 = agent.execute({"operation": "complete", "doc_id": "doc_v", "descriptions": {"img_001": "short"}})
    r5 = agent.execute({"operation": "complete", "doc_id": "doc_v", "descriptions": {"img_001": "ToolX dialog showing security panel and reset button."}})
    r6 = agent.execute({"operation": "status", "doc_id": "doc_v"})
    r7 = agent.execute({"operation": "complete", "doc_id": "doc_v", "descriptions": {"img_002": "ToolY dashboard screenshot with incident queue visible.", "img_003": "ToolZ onboarding flow screenshot with progress indicator."}})
    r8 = agent.execute({"operation": "status", "doc_id": "doc_v"})
    r9 = agent.execute({"operation": "list_pending", "doc_id": "doc_v"})
    r10 = agent.execute({"operation": "unknown", "doc_id": "doc_v"})

    assert r1.success
    assert r2.data["pending_count"] == 3
    assert r3.data["pending_count"] == 3
    assert not r4.success
    assert r5.success
    assert r6.data["described_count"] >= 1
    assert r7.success and len(r7.data["newly_indexed"]) == 2
    assert r8.data["pending_count"] == 0
    assert r9.data["pending_count"] == 0
    assert not r10.success
