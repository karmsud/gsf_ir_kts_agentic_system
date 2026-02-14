from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(args: list[str]) -> dict:
    result = subprocess.run([sys.executable, "-m", "cli.main", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip()) if result.stdout.strip() else {}


def test_cli_10_scenarios(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "d1.md").write_text("ToolX onboarding support", encoding="utf-8")
    (src / "d2.md").write_text("ToolX deployment process", encoding="utf-8")

    r1 = _run(["crawl", "--paths", str(src), "--dry-run"])
    r2 = _run(["crawl", "--paths", str(src)])
    r3 = _run(["ingest", "--paths", str(src)])
    r4 = _run(["search", "ToolX onboarding", "--max-results", "3"])
    r5 = _run(["search", "deployment", "--doc-type", "SOP"])
    r6 = _run(["training", "--topic", "onboarding", "--level", "beginner"])
    r7 = _run(["impact", "--entity", "ToolX"])
    r8 = _run(["freshness", "--scope", "all", "--threshold-days", "1"])
    r9 = _run(["status"])
    r10 = _run(["describe", "pending"])

    assert r1["dry_run"] is True
    assert r2["changes"]["new_files"] is not None
    assert r3["count"] >= 1
    assert "context_chunks" in r4
    assert "context_chunks" in r5
    assert "steps" in r6
    assert "direct_docs" in r7
    assert "total_documents" in r8
    assert "graph_nodes" in r9
    assert "documents" in r10
