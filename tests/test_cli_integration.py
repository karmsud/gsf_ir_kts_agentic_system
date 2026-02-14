import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(args: list[str]) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    output = result.stdout.strip()
    return json.loads(output) if output else {}


def test_cli_end_to_end():
    fixtures = ROOT / "tests" / "fixtures" / "simple"
    run_cli(["crawl", "--paths", str(fixtures)])
    ingest_out = run_cli(["ingest", "--paths", str(fixtures)])
    assert ingest_out["count"] >= 1

    search_out = run_cli(["search", "reset password ToolX"])
    assert len(search_out["context_chunks"]) >= 1

    training_out = run_cli(["training", "--topic", "onboarding"])
    assert "steps" in training_out

    impact_out = run_cli(["impact", "--entity", "ToolX"])
    assert "direct_docs" in impact_out

    freshness_out = run_cli(["freshness"])
    assert freshness_out["total_documents"] >= 1
