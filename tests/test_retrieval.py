from pathlib import Path

from config import load_config
from backend.agents import IngestionAgent, RetrievalService


def test_retrieval_returns_context_after_ingest():
    cfg = load_config()
    ingestion = IngestionAgent(cfg)
    retrieval = RetrievalService(cfg)

    ingestion.execute({"path": str(Path("tests/fixtures/simple/toolx_user_guide.md"))})
    result = retrieval.execute({"query": "reset password ToolX", "max_results": 5})

    assert result.success
    search_result = result.data["search_result"]
    assert len(search_result.context_chunks) >= 1
    assert len(search_result.citations) >= 1
