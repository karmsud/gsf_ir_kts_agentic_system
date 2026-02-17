from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _clean_runtime_dirs(monkeypatch):
    runtime_dir = Path(tempfile.mkdtemp(prefix="kts_test_runtime_", dir=str(ROOT)))
    monkeypatch.setenv("KTS_KB_PATH", str(runtime_dir))

    for child in [runtime_dir / "documents", runtime_dir / "vectors", runtime_dir / "graph", runtime_dir / "logs"]:
        child.mkdir(parents=True, exist_ok=True)

    yield

    shutil.rmtree(runtime_dir, ignore_errors=True)
