from config import load_config
from backend.agents import CrawlerAgent


def test_crawler_detects_new_files():
    cfg = load_config()
    agent = CrawlerAgent(cfg)
    result = agent.execute({"paths": ["tests/fixtures/simple"]})
    changes = result.data["changes"]
    assert result.success
    assert len(changes.new_files) >= 2
