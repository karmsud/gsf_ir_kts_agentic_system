from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class KTSConfig:
    source_paths: list[str] = field(default_factory=list)
    supported_extensions: list[str] = field(
        default_factory=lambda: [
            ".docx",
            ".pdf",
            ".pptx",
            ".htm",
            ".html",
            ".md",
            ".txt",
            ".json",
            ".png",
            ".yaml",
            ".yml",
            ".ini",
            ".csv",
        ]
    )
    knowledge_base_path: str = "knowledge_base"
    chroma_persist_dir: str = "knowledge_base/vectors/chroma"
    graph_path: str = "knowledge_base/graph/knowledge_graph.json"
    manifest_path: str = "knowledge_base/manifest.json"
    chunk_size: int = 1000
    chunk_overlap: int = 200
    confidence_high: float = 0.90
    confidence_medium: float = 0.66
    stale_threshold_days: int = 180


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_config(root_dir: str | Path | None = None) -> KTSConfig:
    root = Path(root_dir or Path.cwd())
    paths_data = _read_json(root / "config" / "file_share_paths.json")
    
    # Allow override for testing isolation
    kb_path = os.environ.get("KTS_KB_PATH", "knowledge_base")
    
    cfg = KTSConfig(
        source_paths=paths_data.get("paths", []),
        knowledge_base_path=kb_path,
        chroma_persist_dir=f"{kb_path}/vectors/chroma",
        graph_path=f"{kb_path}/graph/knowledge_graph.json",
        manifest_path=f"{kb_path}/manifest.json"
    )
    return cfg
