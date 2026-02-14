from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from backend.common.hashing import sha256_file
from backend.common.manifest import ManifestStore
from backend.common.models import AgentResult, FileChange, FileInfo
from .base_agent import AgentBase


class CrawlerAgent(AgentBase):
    agent_name = "crawler-agent"

    def execute(self, request: dict) -> AgentResult:
        dry_run = bool(request.get("dry_run", False))
        force = bool(request.get("force", False))
        max_file_size_mb = int(request.get("max_file_size_mb", 100))
        paths = request.get("paths") or self.config.source_paths
        manifest = ManifestStore(self.config.manifest_path)
        known = manifest.load().get("files", {})

        current: dict[str, FileInfo] = {}
        changes = FileChange()

        for raw_path in paths:
            base = Path(raw_path)
            if not base.exists():
                changes.errors.append({"path": raw_path, "error": "path_not_found"})
                continue
            files = [p for p in base.rglob("*") if p.is_file() and p.suffix.lower() in self.config.supported_extensions]
            for file_path in files:
                try:
                    file_size = file_path.stat().st_size
                    if file_size > (max_file_size_mb * 1024 * 1024):
                        changes.warnings.append(f"skipped_large_file:{file_path}")
                        continue
                    info = FileInfo(
                        path=str(file_path.resolve()),
                        filename=file_path.name,
                        extension=file_path.suffix.lower(),
                        size_bytes=file_size,
                        modified_time=datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc).isoformat(),
                        hash=sha256_file(file_path),
                    )
                    current[info.path] = info
                except Exception as exc:
                    changes.errors.append({"path": str(file_path), "error": str(exc)})

        for path, info in current.items():
            if path not in known:
                changes.new_files.append(info)
            elif force or known[path].get("hash") != info.hash:
                info.doc_id = known[path].get("doc_id")
                changes.modified_files.append(info)
            else:
                changes.unchanged_files += 1

        for known_path in known:
            if known_path not in current:
                old = known[known_path]
                changes.deleted_files.append(
                    FileInfo(
                        path=known_path,
                        filename=old.get("filename", ""),
                        extension=old.get("extension", ""),
                        size_bytes=int(old.get("size_bytes", 0)),
                        modified_time=old.get("modified_time", ""),
                        hash=old.get("hash", ""),
                        doc_id=old.get("doc_id"),
                    )
                )

        if dry_run:
            changes.deleted_files = []

        result = self.quality_check(
            AgentResult(
                success=True,
                confidence=1.0 if not changes.errors else 0.8,
                data={"changes": changes, "dry_run": dry_run, "force": force},
                reasoning="Scanned configured source paths and detected file deltas.",
            )
        )
        return result
