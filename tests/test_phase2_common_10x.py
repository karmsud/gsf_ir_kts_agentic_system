from __future__ import annotations

from pathlib import Path

import pytest

from backend.common.hashing import sha256_file
from backend.common.manifest import ManifestStore
from backend.common.models import AgentResult, FileInfo
from backend.common.quality_gate import QualityGate
from backend.common.text_utils import chunk_text, clean_text
from config import load_config


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a\r\nb", "a\nb"),
        ("a\n\n\n\nb", "a\n\nb"),
        ("  spaced  ", "spaced"),
        ("", ""),
        ("\n\nheader\n", "header"),
        ("line1\r\nline2\r\n", "line1\nline2"),
        ("A\n\n\n\n\nB", "A\n\nB"),
        ("x", "x"),
        (" x y ", "x y"),
        ("t\n\n\n\nz", "t\n\nz"),
    ],
)
def test_clean_text_10_cases(raw: str, expected: str):
    assert clean_text(raw) == expected


@pytest.mark.parametrize(
    ("text", "size", "overlap", "min_chunks"),
    [
        ("abc" * 100, 50, 10, 2),
        ("abc" * 20, 30, 5, 2),
        ("x" * 100, 25, 5, 4),
        ("x" * 10, 10, 0, 1),
        ("x" * 11, 10, 2, 2),
        ("", 10, 3, 0),
        ("sample" * 40, 60, 15, 3),
        ("sample" * 2, 100, 0, 1),
        ("a" * 300, 50, 49, 6),
        ("a" * 300, 50, 1000, 6),
    ],
)
def test_chunk_text_10_cases(text: str, size: int, overlap: int, min_chunks: int):
    chunks = chunk_text(text, size, overlap)
    assert len(chunks) >= min_chunks
    if chunks:
        assert len(chunks[0]) <= size


def test_hash_manifest_quality_gate_functions(tmp_path: Path):
    cfg = load_config()

    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_text("hello", encoding="utf-8")
    file_b.write_text("hello-world", encoding="utf-8")

    hash_a = sha256_file(file_a)
    hash_b = sha256_file(file_b)
    assert hash_a != hash_b

    manifest = ManifestStore(str(tmp_path / "manifest.json"))
    info = FileInfo(
        path=str(file_a),
        filename=file_a.name,
        extension=file_a.suffix,
        size_bytes=file_a.stat().st_size,
        modified_time="now",
        hash=hash_a,
    )
    manifest.upsert_files([info])
    assert str(file_a) in manifest.load()["files"]

    gate = QualityGate(cfg)
    high = gate.apply(AgentResult(success=True, confidence=0.95))
    med = gate.apply(AgentResult(success=True, confidence=0.7, reasoning="mid"))
    low = gate.apply(AgentResult(success=True, confidence=0.3))

    assert high.escalation is None
    assert "Confidence medium" in med.reasoning
    assert low.escalation is not None
