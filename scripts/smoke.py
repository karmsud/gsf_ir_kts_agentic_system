from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str]) -> None:
    cmd = [sys.executable, "-m", "cli.main", *args]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise SystemExit(result.returncode)
    print(f"$ {' '.join(args)}")
    print(result.stdout.strip())


def main() -> None:
    fixtures = ROOT / "tests" / "fixtures" / "simple"
    run(["crawl", "--paths", str(fixtures)])
    run(["ingest", "--paths", str(fixtures)])
    run(["search", "How do I reset password in ToolX?"])
    run(["training", "--topic", "onboarding"])
    run(["impact", "--entity", "ToolX"])
    run(["freshness"])
    print(json.dumps({"smoke": "passed"}))


if __name__ == "__main__":
    main()
