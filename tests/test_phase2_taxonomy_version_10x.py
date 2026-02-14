from __future__ import annotations

import pytest

from backend.agents import TaxonomyAgent, VersionAgent
from config import load_config


@pytest.mark.parametrize(
    ("filename", "text", "expected"),
    [
        ("sop_deploy.md", "standard operating procedure step 1", "SOP"),
        ("user_guide.md", "how to use the tool", "USER_GUIDE"),
        ("release_notes.md", "release version changelog", "RELEASE_NOTE"),
        ("troubleshoot.md", "error fix broken fail", "TROUBLESHOOT"),
        ("training_deck.md", "training onboarding learn", "TRAINING"),
        ("misc.md", "random text", "UNKNOWN"),
        ("procedure.md", "step runbook", "SOP"),
        ("walkthrough.md", "tutorial guide", "USER_GUIDE"),
        ("incident.md", "issue troubleshoot", "TROUBLESHOOT"),
        ("course.md", "course onboarding", "TRAINING"),
    ],
)
def test_taxonomy_10_cases(filename: str, text: str, expected: str):
    cfg = load_config()
    agent = TaxonomyAgent(cfg)
    result = agent.execute({"filename": filename, "text": text})
    assert result.success
    assert result.data["doc_type"] == expected


def test_version_10_scenarios():
    cfg = load_config()
    agent = VersionAgent(cfg)

    cases = [
        ("# A\ntext", "# A\ntext"),
        ("# A\ntext", "# A\ntext2"),
        ("# A\ntext", "# A\ntext\n# B\nnew"),
        ("# A\ntext\n# B\nold", "# A\ntext"),
        ("# A\n![](a.png)", "# A\n![](a.png)\n![](b.png)"),
        ("# A\n![](a.png)", "# A\n"),
        ("", "# New\ncontent"),
        ("# Root\n", "# Root\nchanged\n# child\nmore"),
        ("# one\nA", "# one\nB"),
        ("# one\nA", "# one\nA\n# two\nB"),
    ]

    outputs = [agent.execute({"doc_id": f"d{idx}", "old_text": old, "new_text": new, "old_version": idx}) for idx, (old, new) in enumerate(cases, start=1)]

    assert len(outputs) == 10
    assert outputs[0].data["changed"] is False
    assert outputs[1].data["changed"] is True
    assert outputs[2].data["added_sections"]
    assert outputs[3].data["removed_sections"]
    assert outputs[4].data["added_images"]
    assert outputs[5].data["removed_images"]
    assert outputs[6].data["new_version"] == 8
    assert isinstance(outputs[7].data["changed_chunks"], list)
    assert "summary" in outputs[8].data
    assert outputs[9].success
