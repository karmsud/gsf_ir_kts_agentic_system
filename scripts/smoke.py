"""Minimal smoke test — verifies core imports and config load."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure project root is on sys.path when invoked as `python scripts/smoke.py`
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main() -> None:
    errors: list[str] = []

    # 1. Core config imports
    try:
        from config.settings import KTSConfig, load_config  # noqa: F401
    except Exception as exc:
        errors.append(f"config import: {exc}")

    # 2. Backend core imports
    try:
        from backend.ingestion.regime_classifier import RegimeClassifier  # noqa: F401
        from backend.agents.retrieval_service import RetrievalService  # noqa: F401
    except Exception as exc:
        errors.append(f"backend import: {exc}")

    # 3. CLI import
    try:
        from cli.main import cli  # noqa: F401
    except Exception as exc:
        errors.append(f"cli import: {exc}")

    if errors:
        print(json.dumps({"smoke": "failed", "errors": errors}, indent=2))
        sys.exit(1)
    else:
        print(json.dumps({"smoke": "passed"}, indent=2))


if __name__ == "__main__":
    main()
