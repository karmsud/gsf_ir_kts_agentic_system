"""Phase 19 — OneNote Delta-Ingestion Manifest.

Tracks which OneNote pages have been ingested and what content hashes
they held at ingestion time.  Enables delta ingestion: only changed or
new pages are re-processed; unchanged pages are skipped entirely.

Manifest file location
----------------------
``<knowledge_base_path>/onenote_ingest_manifest.json``

This lives *inside* the knowledge base directory (alongside chroma/,
graph/, etc.) so it travels with the KB and requires no write access
to the source network share.

Manifest JSON schema
--------------------
{
  "version": 1,
  "last_full_ingest": "<ISO-8601 or null>",
  "sections": {
    "<section_filename.one>": {
      "section_name": "<human name>",
      "file_modified_iso": "<ISO-8601>",
      "pages": {
        "<page_guid>": {
          "title": "<page title>",
          "content_hash": "<sha256 hex 32 chars>",
          "chunk_ids": ["chunk_id_1", "chunk_id_2", ...],
          "last_ingested_iso": "<ISO-8601>",
          "image_count": 0
        }
      }
    }
  }
}
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_MANIFEST_FILENAME = "onenote_ingest_manifest.json"
_SCHEMA_VERSION = 1


class OneNoteManifest:
    """Read / write / diff the OneNote ingestion manifest.

    Parameters
    ----------
    kb_path : str | Path
        Root of the knowledge base (e.g. ``.kts`` or ``knowledge_base``).
        The manifest is stored at ``<kb_path>/onenote_ingest_manifest.json``.
    """

    def __init__(self, kb_path: str | Path) -> None:
        self._path = Path(kb_path) / _MANIFEST_FILENAME
        self._data: dict = self._load()

    # ── Persistence ────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if raw.get("version") == _SCHEMA_VERSION:
                    return raw
                logger.warning(
                    "[Phase19] Manifest version mismatch at '%s' — starting fresh",
                    self._path,
                )
            except Exception as exc:
                logger.warning("[Phase19] Cannot read manifest '%s': %s — starting fresh", self._path, exc)
        return {"version": _SCHEMA_VERSION, "last_full_ingest": None, "sections": {}}

    def save(self) -> None:
        """Persist current manifest to disk (atomic write via temp file)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        tmp.replace(self._path)
        logger.debug("[Phase19] Manifest saved to '%s'", self._path)

    # ── Section helpers ────────────────────────────────────────────────────

    def _section_key(self, one_file: str | Path) -> str:
        """Normalise to basename only (e.g. 'Tech Tips.one')."""
        return Path(one_file).name

    def section_file_modified(self, one_file: str | Path) -> Optional[str]:
        """Return the last recorded file-modified ISO timestamp for *one_file*."""
        key = self._section_key(one_file)
        return self._data["sections"].get(key, {}).get("file_modified_iso")

    def section_needs_scan(self, one_file: str | Path) -> bool:
        """True if the .one file mtime differs from the recorded mtime.

        A section can be skipped entirely if its file has not changed since
        the last ingestion run.
        """
        key = self._section_key(one_file)
        recorded = self._data["sections"].get(key, {}).get("file_modified_iso")
        if recorded is None:
            return True  # never ingested

        try:
            current_mtime = datetime.fromtimestamp(
                Path(one_file).stat().st_mtime, tz=timezone.utc
            ).isoformat()
        except OSError:
            return True  # can't stat → assume changed

        return current_mtime != recorded

    def update_section_mtime(self, one_file: str | Path, section_name: str) -> None:
        """Store the current file mtime for *one_file*."""
        key = self._section_key(one_file)
        try:
            mtime = datetime.fromtimestamp(
                Path(one_file).stat().st_mtime, tz=timezone.utc
            ).isoformat()
        except OSError:
            mtime = _now_iso()
        section = self._data["sections"].setdefault(key, {})
        section["section_name"] = section_name
        section["file_modified_iso"] = mtime
        # Only initialise pages dict if absent — never wipe existing page data
        section.setdefault("pages", {})

    # ── Page diff helpers ──────────────────────────────────────────────────

    def page_needs_ingest(self, one_file: str | Path, page_guid: str, new_hash: str) -> bool:
        """True if *page_guid* is new or its content hash has changed."""
        key = self._section_key(one_file)
        pages = self._data["sections"].get(key, {}).get("pages", {})
        recorded_hash = pages.get(page_guid, {}).get("content_hash")
        return recorded_hash != new_hash

    def get_chunk_ids(self, one_file: str | Path, page_guid: str) -> list[str]:
        """Return the list of vector chunk IDs previously stored for *page_guid*."""
        key = self._section_key(one_file)
        return (
            self._data["sections"]
            .get(key, {})
            .get("pages", {})
            .get(page_guid, {})
            .get("chunk_ids", [])
        )

    def upsert_page(
        self,
        one_file: str | Path,
        page_guid: str,
        title: str,
        content_hash: str,
        chunk_ids: list[str],
        image_count: int = 0,
    ) -> None:
        """Record (or update) a successfully ingested page."""
        key = self._section_key(one_file)
        self._data["sections"].setdefault(key, {}).setdefault("pages", {})
        self._data["sections"][key]["pages"][page_guid] = {
            "title": title,
            "content_hash": content_hash,
            "chunk_ids": chunk_ids,
            "last_ingested_iso": _now_iso(),
            "image_count": image_count,
        }

    def remove_page(self, one_file: str | Path, page_guid: str) -> list[str]:
        """Remove a page entry and return its old chunk_ids (for deletion from vector store)."""
        key = self._section_key(one_file)
        pages = self._data["sections"].get(key, {}).get("pages", {})
        entry = pages.pop(page_guid, {})
        return entry.get("chunk_ids", [])

    def all_pages_for_section(self, one_file: str | Path) -> dict[str, dict]:
        """Return the pages dict for *one_file*."""
        key = self._section_key(one_file)
        return self._data["sections"].get(key, {}).get("pages", {})

    # ── Full-ingest helpers ────────────────────────────────────────────────

    def mark_full_ingest(self) -> None:
        """Record timestamp of a completed full ingestion run."""
        self._data["last_full_ingest"] = _now_iso()

    def clear_section(self, one_file: str | Path) -> list[str]:
        """Remove all page entries for *one_file*.

        Returns all chunk_ids that were tracked (so caller can delete them
        from the vector store before re-ingesting).
        """
        key = self._section_key(one_file)
        pages = self._data["sections"].pop(key, {}).get("pages", {})
        all_ids: list[str] = []
        for entry in pages.values():
            all_ids.extend(entry.get("chunk_ids", []))
        return all_ids

    # ── Reporting ──────────────────────────────────────────────────────────

    def summary(self) -> dict:
        """Return a human-readable summary of the manifest state."""
        sections_summary = {}
        total_pages = 0
        total_chunks = 0
        for sec_key, sec_data in self._data["sections"].items():
            pages = sec_data.get("pages", {})
            n_pages = len(pages)
            n_chunks = sum(len(p.get("chunk_ids", [])) for p in pages.values())
            total_pages += n_pages
            total_chunks += n_chunks
            sections_summary[sec_data.get("section_name", sec_key)] = {
                "pages": n_pages,
                "chunks": n_chunks,
                "file_modified": sec_data.get("file_modified_iso", "unknown"),
            }
        return {
            "manifest_path": str(self._path),
            "last_full_ingest": self._data.get("last_full_ingest"),
            "total_sections": len(self._data["sections"]),
            "total_pages": total_pages,
            "total_chunks": total_chunks,
            "sections": sections_summary,
        }


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
