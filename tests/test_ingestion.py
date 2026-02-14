from pathlib import Path

from config import load_config
from backend.agents import IngestionAgent


def test_ingestion_creates_content_and_chunks():
    cfg = load_config()
    agent = IngestionAgent(cfg)
    source = Path("tests/fixtures/simple/toolx_user_guide.md")
    result = agent.execute({"path": str(source)})
    document = result.data["document"]

    assert result.success
    assert Path(document.content_path).exists()
    assert result.data["chunk_count"] > 0
