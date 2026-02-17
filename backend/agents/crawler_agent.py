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
        missing_grace_scans = int(request.get("missing_grace_scans", 0))
        paths = request.get("paths") or self.config.source_paths
        manifest = ManifestStore(self.config.manifest_path)
        known = manifest.load().get("files", {})

        current_scan: dict[str, FileInfo] = {}
        changes = FileChange()

        # 1. Scan Files (Mark Phase)
        for raw_path in paths:
            base = Path(raw_path)
            if not base.exists():
                changes.errors.append({"path": raw_path, "error": "path_not_found"})
                continue
            
            # Dynamically skip the KB output directory (and legacy "knowledge_base")
            _kb_dir_name = Path(self.config.knowledge_base_path).name
            _skip_dirs = {_kb_dir_name, "knowledge_base", ".kts"}
            files = [
                p for p in base.rglob("*")
                if p.is_file()
                and p.suffix.lower() in self.config.supported_extensions
                and not _skip_dirs.intersection(p.parts)  # Skip KB index directories
            ]
            for file_path in files:
                abs_path = str(file_path.resolve())
                try:
                    file_size = file_path.stat().st_size
                    if file_size > (max_file_size_mb * 1024 * 1024):
                        changes.warnings.append(f"skipped_large_file:{file_path}")
                        continue
                    
                    file_hash = sha256_file(file_path)
                    
                    # Generate stable source_id from initial content hash if new
                    known_info = known.get(abs_path)
                    source_id = known_info.get("source_id") if known_info else f"src_{file_hash[:16]}"
                    if not source_id: # For migration of old manifest entries
                        source_id = f"src_{file_hash[:16]}"

                    info = FileInfo(
                        path=abs_path,
                        filename=file_path.name,
                        extension=file_path.suffix.lower(),
                        size_bytes=file_size,
                        modified_time=datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc).isoformat(),
                        hash=file_hash,
                        source_id=source_id,
                        status="active",
                        last_seen=datetime.now(timezone.utc).isoformat(),
                        retry_count=0
                    )
                    current_scan[abs_path] = info

                except Exception as exc:
                    # Robustness: Handle locked files
                    changes.errors.append({"path": abs_path, "error": str(exc)})
                    if abs_path in known:
                        # Keep existing entry but mark error
                        preserved = known[abs_path]
                        retry_count = preserved.get("retry_count", 0) + 1
                        info = FileInfo(
                            path=abs_path, # Preserve path
                            filename=preserved.get("filename", ""),
                            extension=preserved.get("extension", ""),
                            size_bytes=int(preserved.get("size_bytes", 0)),
                            modified_time=preserved.get("modified_time", ""),
                            hash=preserved.get("hash", ""),
                            doc_id=preserved.get("doc_id"),
                            source_id=preserved.get("source_id"),
                            status="error",
                            last_seen=preserved.get("last_seen"),
                            retry_count=retry_count
                        )
                        current_scan[abs_path] = info
        
        # 2. Identify Missing (Sweep Phase Setup)
        missing_paths = set(known.keys()) - set(current_scan.keys())
        potential_renames = {} # hash -> list[FileInfo]

        # 3. Process Changes
        for path, info in current_scan.items():
            if path in known:
                prev = known[path]
                info.doc_id = prev.get("doc_id")
                info.source_id = prev.get("source_id") or info.source_id # Persist source_id
                
                if info.status == "error":
                     # Don't re-ingest errors, just update manifest status
                     # We treat as 'unchanged' for diff purposes but will update manifest
                     pass 
                elif force or prev.get("hash") != info.hash:
                    changes.modified_files.append(info)
                else:
                    changes.unchanged_files += 1
            else:
                # Potential new file - buffer for rename check
                potential_renames.setdefault(info.hash, []).append(info)

        # 4. Handle Missing & Detect Renames
        for missing_path in missing_paths:
            old_info = known[missing_path]
            old_hash = old_info.get("hash")
            
            # Rename Heuristic: Exact content match
            if old_hash in potential_renames and potential_renames[old_hash]:
                # It's a MOVE!
                new_file_info = potential_renames[old_hash].pop(0) # Take one matching file
                
                # Transfer Identity
                new_file_info.doc_id = old_info.get("doc_id")
                new_file_info.source_id = old_info.get("source_id")
                new_file_info.versions = old_info.get("versions", [])
                
                # Report as New (with old ID) so it gets ingested/updated
                changes.new_files.append(new_file_info)
                
                # The old path is effectively deleted/superceded
                changes.deleted_files.append(
                    FileInfo(
                        path=missing_path,
                        filename=old_info.get("filename", ""),
                        extension=old_info.get("extension", ""),
                        size_bytes=old_info.get("size_bytes", 0),
                        modified_time=old_info.get("modified_time", ""),
                        hash=old_info.get("hash", ""),
                        doc_id=old_info.get("doc_id"),
                        status="deleted"
                    )
                )
            else:
                # True Missing
                # Grace Period Logic
                retry_count = old_info.get("retry_count", 0) + 1
                if retry_count > missing_grace_scans:
                    changes.deleted_files.append(
                        FileInfo(
                            path=missing_path,
                            filename=old_info.get("filename", ""),
                            extension=old_info.get("extension", ""),
                            size_bytes=old_info.get("size_bytes", 0),
                            modified_time=old_info.get("modified_time", ""),
                            hash=old_info.get("hash", ""),
                            doc_id=old_info.get("doc_id"),
                            status="deleted"
                        )
                    )
                else:
                    # Mark missing but keep in manifest (Soft Delete)
                    soft_deleted_info = FileInfo(
                        path=missing_path,
                        filename=old_info.get("filename", ""),
                        extension=old_info.get("extension", ""),
                        size_bytes=int(old_info.get("size_bytes", 0)),
                        modified_time=old_info.get("modified_time", ""),
                        hash=old_info.get("hash", ""),
                        doc_id=old_info.get("doc_id"),
                        source_id=old_info.get("source_id"),
                        status="missing",
                        last_seen=old_info.get("last_seen"),
                        retry_count=retry_count
                    )
                    changes.modified_files.append(soft_deleted_info)

        # Add remaining true new files
        for hash_val, infos in potential_renames.items():
            for info in infos:
                 if info not in changes.new_files:
                     changes.new_files.append(info)

        if dry_run:
            changes.deleted_files = []
            changes.modified_files = []
            changes.new_files = []

        result = self.quality_check(
            AgentResult(
                success=True,
                confidence=1.0 if not changes.errors else 0.8,
                data={"changes": changes, "dry_run": dry_run, "force": force},
                reasoning="Scanned configured source paths and detected file deltas.",
            )
        )
        return result
