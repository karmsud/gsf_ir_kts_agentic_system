import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_smoke_script_runs():
    result = subprocess.run(
        [sys.executable, "scripts/smoke.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert '"smoke": "passed"' in result.stdout
