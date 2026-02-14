from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "cli.main", "freshness"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(result.stderr)
        raise SystemExit(result.returncode)
    print(json.dumps({"freshness_report": result.stdout.strip()}))


if __name__ == "__main__":
    main()
