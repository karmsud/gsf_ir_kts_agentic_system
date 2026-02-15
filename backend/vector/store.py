from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from backend.common.models import TextChunk


class VectorStore:
    """Local fallback vector-like store using keyword overlap scoring.

    This keeps the system fully local and testable even if ChromaDB is unavailable.
    """

    def __init__(self, persist_dir: str):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.persist_dir / "chunks_index.json"
        if not self.index_file.exists():
            self._save([])

    def _load(self) -> list[dict]:
        with self.index_file.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _save(self, rows: list[dict]) -> None:
        with self.index_file.open("w", encoding="utf-8") as handle:
            json.dump(rows, handle, indent=2)

    def upsert_chunks(self, chunks: list[TextChunk]) -> None:
        rows = self._load()
        existing = {row["chunk_id"]: row for row in rows}
        for chunk in chunks:
            existing[chunk.chunk_id] = asdict(chunk)
        self._save(list(existing.values()))

    def delete_doc_chunks(self, doc_id: str) -> None:
        """Removes all chunks associated with a specific doc_id.
        Crucial for preventing 'phantom chunks' when a document shrinks.
        """
        rows = self._load()
        filtered = [row for row in rows if row.get("doc_id") != doc_id]
        self._save(filtered)

    def prune_orphans(self, active_doc_ids: set[str]) -> int:
        """Removes chunks where doc_id is NOT in the active set."""
        rows = self._load()
        original_count = len(rows)
        filtered = [row for row in rows if row.get("doc_id") in active_doc_ids]
        if len(filtered) < original_count:
            self._save(filtered)
        return original_count - len(filtered)

    def update_doc_metadata(self, doc_id: str, doc_type: str | None = None, tags: list[str] | None = None) -> None:
        rows = self._load()
        for row in rows:
            if row.get("doc_id") == doc_id:
                if doc_type is not None:
                    row["doc_type"] = doc_type
                if tags is not None:
                    row["tags"] = tags
        self._save(rows)

    def add_image_description(self, doc_id: str, source_path: str, image_id: str, description: str) -> None:
        rows = self._load()
        chunk_id = f"{doc_id}_img_{image_id}"
        payload = {
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "content": description,
            "source_path": source_path,
            "chunk_index": -1,
            "doc_type": "IMAGE_DESC",
            "is_image_desc": True,
            "image_id": image_id,
        }
        existing = {row["chunk_id"]: row for row in rows}
        existing[chunk_id] = payload
        self._save(list(existing.values()))

    def delete_doc(self, doc_id: str) -> None:
        rows = self._load()
        filtered = [row for row in rows if row.get("doc_id") != doc_id]
        self._save(filtered)

    def search(self, query: str, max_results: int = 5, doc_type_filter: str | None = None) -> list[dict]:
        query_tokens = set(re.findall(r"[A-Za-z0-9_\-]+", query.lower()))
        rows = self._load()
        scored: list[dict] = []
        for row in rows:
            if doc_type_filter and row.get("doc_type") != doc_type_filter:
                continue
            content_tokens = set(re.findall(r"[A-Za-z0-9_\-]+", row.get("content", "").lower()))
            overlap = len(query_tokens & content_tokens)
            if overlap == 0:
                continue
            score = overlap / max(1, len(query_tokens))
            scored.append({**row, "similarity": score})

        scored.sort(key=lambda item: item["similarity"], reverse=True)
        return scored[:max_results]
