from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.common.models import AgentResult, IngestedDocument
from backend.common.text_utils import clean_text
from backend.ingestion import convert_docx, convert_html, convert_pdf, convert_pptx, convert_json, extract_json_metadata, extract_image_refs
from backend.vector import VectorStore, chunk_document
from .base_agent import AgentBase


class IngestionAgent(AgentBase):
    agent_name = "ingestion-agent"

    def __init__(self, config):
        super().__init__(config)
        self.vector_store = VectorStore(config.chroma_persist_dir)

    def _convert(self, file_path: Path) -> tuple[str, list[str]]:
        extension = file_path.suffix.lower()
        if extension in {".md", ".txt"}:
            return file_path.read_text(encoding="utf-8", errors="ignore"), []
        if extension in {".htm", ".html"}:
            return convert_html(str(file_path))
        if extension == ".docx":
            return convert_docx(str(file_path))
        if extension == ".pdf":
            return convert_pdf(str(file_path))
        if extension == ".pptx":
            return convert_pptx(str(file_path))
        if extension == ".json":
            return convert_json(str(file_path))
        raise ValueError(f"Unsupported extension: {extension}")

    def execute(self, request: dict) -> AgentResult:
        source_path = Path(request["path"]).resolve()
        if not source_path.exists() or not source_path.is_file():
            return AgentResult(success=False, confidence=0.1, data={"error": f"file_not_found:{source_path}"}, reasoning="Source file not found.")

        provided_doc_id = request.get("doc_id")
        doc_id = provided_doc_id or f"doc_{abs(hash(str(source_path))) % 10_000_000:07d}"

        try:
            raw_text, raw_image_refs = self._convert(source_path)
        except Exception as exc:
            return AgentResult(success=False, confidence=0.2, data={"error": str(exc)}, reasoning="Document conversion failed.")

        text = clean_text(raw_text)
        if not text:
            return AgentResult(success=False, confidence=0.3, data={"error": "empty_document"}, reasoning="Extracted text is empty.")

        doc_dir = Path(self.config.knowledge_base_path) / "documents" / doc_id
        images_dir = doc_dir / "images"
        doc_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)

        content_path = doc_dir / "content.md"
        content_path.write_text(text, encoding="utf-8")

        # Enrich metadata for JSON reference catalogs
        json_metadata = {}
        if source_path.suffix.lower() == ".json":
            json_metadata = extract_json_metadata(str(source_path))
        
        metadata = {
            "doc_id": doc_id,
            "title": source_path.stem,
            "source_path": str(source_path),
            "extension": source_path.suffix.lower(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "modified_at": datetime.fromtimestamp(source_path.stat().st_mtime, tz=timezone.utc).isoformat(),
            "doc_type": json_metadata.get("doc_type", "UNKNOWN"),
            "tags": [],
            "tools": json_metadata.get("tool_names", []),
            "topics": [],
            "processes": [],
            "word_count": len(text.split()),
            "version": int(request.get("version", 1)),
        }
        
        # Add JSON-specific metadata
        if json_metadata:
            metadata["error_codes"] = json_metadata.get("error_codes", [])
            metadata["categories"] = json_metadata.get("categories", [])
        metadata_path = doc_dir / "metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        image_paths = extract_image_refs(str(source_path), raw_image_refs)

        ingested = IngestedDocument(
            doc_id=doc_id,
            title=metadata["title"],
            source_path=str(source_path),
            extension=source_path.suffix.lower(),
            content_path=str(content_path),
            metadata_path=str(metadata_path),
            images_dir=str(images_dir),
            extracted_text=text,
            image_paths=image_paths,
            chunk_count=0,
            word_count=metadata["word_count"],
            version=metadata["version"],
        )

        chunks = chunk_document(
            doc_id=doc_id,
            source_path=str(source_path),
            text=text,
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
        )
        self.vector_store.upsert_chunks(chunks)
        ingested.chunk_count = len(chunks)

        confidence = 0.95 if text else 0.5
        return self.quality_check(
            AgentResult(
                success=True,
                confidence=confidence,
                data={"document": ingested, "chunk_count": len(chunks), "word_count": metadata["word_count"]},
                reasoning="Ingested source document into local knowledge base and vector index.",
            )
        )
