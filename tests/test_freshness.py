from pathlib import Path

from config import load_config
from backend.agents import FreshnessAgent, IngestionAgent


def test_freshness_reports_counts():
    cfg = load_config()
    ingestion = IngestionAgent(cfg)
    ingestion.execute({"path": str(Path("tests/fixtures/simple/toolx_user_guide.md"))})

    result = FreshnessAgent(cfg).execute({})
    report = result.data["freshness_report"]

    assert result.success
    assert report.total_documents >= 1
