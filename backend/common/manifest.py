from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .models import FileInfo


class ManifestStore:
    def __init__(self, manifest_path: str):
        self.path = Path(manifest_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save({"files": {}, "updated_at": None})

    def load(self) -> dict:
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save(self, data: dict) -> None:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)

    def upsert_files(self, infos: list[FileInfo]) -> None:
        manifest = self.load()
        files = manifest.setdefault("files", {})
        for info in infos:
            files[info.path] = asdict(info)
        self.save(manifest)

    def remove_paths(self, paths: list[str]) -> None:
        manifest = self.load()
        files = manifest.setdefault("files", {})
        for path in paths:
            files.pop(path, None)
        self.save(manifest)
