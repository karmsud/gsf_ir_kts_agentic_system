from config import load_config
from backend.agents import TaxonomyAgent


def test_taxonomy_classifies_troubleshoot_content():
    cfg = load_config()
    agent = TaxonomyAgent(cfg)
    result = agent.execute({"text": "This guide helps fix error and troubleshoot login failure."})
    assert result.success
    assert result.data["doc_type"] in {"TROUBLESHOOT", "USER_GUIDE"}
