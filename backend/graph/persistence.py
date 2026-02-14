from __future__ import annotations

import json
from pathlib import Path


class GraphStore:
    def __init__(self, graph_path: str):
        self.path = Path(graph_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save({"nodes": {}, "edges": []})

    def load(self) -> dict:
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save(self, graph_data: dict) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(graph_data, handle, indent=2)
