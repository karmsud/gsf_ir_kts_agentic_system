from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _clean_runtime_dirs():
    kb = ROOT / "knowledge_base"
    if kb.exists():
        for child in [kb / "documents", kb / "vectors", kb / "graph"]:
            if child.exists():
                shutil.rmtree(child)
            child.mkdir(parents=True, exist_ok=True)
        manifest = kb / "manifest.json"
        if manifest.exists():
            manifest.unlink()
    yield
