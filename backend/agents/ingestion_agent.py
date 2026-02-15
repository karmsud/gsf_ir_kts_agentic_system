from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.common.models import AgentResult, IngestedDocument
from backend.common.text_utils import clean_text
from backend.ingestion import (
    convert_docx, convert_html, convert_pdf, convert_pptx, convert_json, 
    extract_json_metadata, extract_image_refs,
    convert_png, convert_yaml, convert_ini, convert_csv
)
from backend.vector import VectorStore, chunk_document
from .base_agent import AgentBase


class IngestionAgent(AgentBase):
    agent_name = "ingestion-agent"

    def __init__(self, config):
        super().__init__(config)
        self.vector_store = VectorStore(config.chroma_persist_dir)

    def _convert(self, file_path: Path, images_dir: str | None = None) -> tuple[str, list[str]]:
        extension = file_path.suffix.lower()
        if extension in {".md", ".txt"}:
            return file_path.read_text(encoding="utf-8", errors="ignore"), []
        if extension in {".htm", ".html"}:
            return convert_html(str(file_path))
        if extension == ".docx":
            return convert_docx(str(file_path), images_dir=images_dir)
        if extension == ".pdf":
            return convert_pdf(str(file_path), images_dir=images_dir)
        if extension == ".pptx":
            return convert_pptx(str(file_path), images_dir=images_dir)
        if extension == ".json":
            return convert_json(str(file_path))
        if extension == ".png":
            return convert_png(str(file_path))
        if extension in {".yaml", ".yml"}:
            return convert_yaml(str(file_path))
        if extension == ".ini":
            return convert_ini(str(file_path))
        if extension == ".csv":
            return convert_csv(str(file_path))
        raise ValueError(f"Unsupported extension: {extension}")

    def execute(self, request: dict) -> AgentResult:
        import shutil
        import tempfile
        
        source_path = Path(request["path"]).resolve()
        if not source_path.exists() or not source_path.is_file():
            return AgentResult(success=False, confidence=0.1, data={"error": f"file_not_found:{source_path}"}, reasoning="Source file not found.")

        provided_doc_id = request.get("doc_id")
        # Legacy fallback provided for robustness, but caller should ideally provide stable ID
        doc_id = provided_doc_id or f"doc_{abs(hash(str(source_path))) % 10_000_000:07d}"

        # Atomic Write Strategy
        # 1. Prepare Staging (must exist before _convert so images can be extracted into it)
        staging_dir = Path(self.config.knowledge_base_path) / "staging" / doc_id
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        staging_dir.mkdir(parents=True, exist_ok=True)

        final_doc_dir = Path(self.config.knowledge_base_path) / "documents" / doc_id
        final_images_dir = final_doc_dir / "images"
        staging_images_dir = staging_dir / "images"
        staging_images_dir.mkdir(parents=True, exist_ok=True)

        try:
            raw_text, raw_image_refs = self._convert(source_path, images_dir=str(staging_images_dir))
        except Exception as exc:
            return AgentResult(success=False, confidence=0.2, data={"error": str(exc)}, reasoning="Document conversion failed.")

        text = clean_text(raw_text)
        if not text:
            return AgentResult(success=False, confidence=0.3, data={"error": "empty_document"}, reasoning="Extracted text is empty.")

        content_path = staging_dir / "content.md"
        content_path.write_text(text, encoding="utf-8")

        # Enrich metadata
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
        
        if json_metadata:
            metadata["error_codes"] = json_metadata.get("error_codes", [])
            metadata["categories"] = json_metadata.get("categories", [])
        
        metadata_path = staging_dir / "metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        # Combine embedded images (extracted by converters into staging_images_dir)
        # with any external image references resolved from the source document
        image_paths = list(raw_image_refs)
        external_refs = extract_image_refs(str(source_path), raw_image_refs)
        # Deduplicate by resolved path (converters and extractor may return same files)
        seen = {str(Path(p).resolve()) for p in image_paths}
        for ref in external_refs:
            resolved = str(Path(ref).resolve())
            if resolved not in seen:
                image_paths.append(ref)
                seen.add(resolved)

        # 2. Versioning (Backup Old)
        if final_doc_dir.exists():
            current_version = 0
            try:
                old_meta = json.loads((final_doc_dir / "metadata.json").read_text(encoding="utf-8"))
                current_version = old_meta.get("version", 0)
            except:
                pass
            
            version_backup_dir = Path(self.config.knowledge_base_path) / "versions" / doc_id / f"v{current_version}"
            version_backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy active to backup
            for f in final_doc_dir.glob("*"):
                if f.is_file():
                    shutil.copy2(f, version_backup_dir)
        
        # 3. Swap (Commit Storage)
        final_doc_dir.parent.mkdir(parents=True, exist_ok=True)
        # Remove partial final dir if exists? No, that deletes history if we didn't version.
        # But we want to overwrite 'current'.
        # CopyTree from staging to final, overwriting.
        if final_doc_dir.exists():
             shutil.rmtree(final_doc_dir) # Safe because we versioned above
        
        shutil.move(str(staging_dir), str(final_doc_dir))

        # Remap image paths from staging to final location
        staging_prefix = str(staging_dir)
        final_prefix = str(final_doc_dir)
        image_paths = [
            p.replace(staging_prefix, final_prefix) if p.startswith(staging_prefix) else p
            for p in image_paths
        ]

        # 4. Vector Store (Transaction)
        # Delete OLD chunks first to prevent phantom artifacts
        self.vector_store.delete_doc_chunks(doc_id)
        
        chunks = chunk_document(
            doc_id=doc_id,
            source_path=str(source_path),
            text=text,
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
        )
        self.vector_store.upsert_chunks(chunks)

        ingested = IngestedDocument(
            doc_id=doc_id,
            title=metadata["title"],
            source_path=str(source_path),
            extension=source_path.suffix.lower(),
            content_path=str(final_doc_dir / "content.md"),
            metadata_path=str(final_doc_dir / "metadata.json"),
            images_dir=str(final_images_dir),
            extracted_text=text,
            image_paths=image_paths,
            chunk_count=len(chunks),
            word_count=metadata["word_count"],
            version=metadata["version"],
        )

        confidence = 0.95 if text else 0.5
        return self.quality_check(
            AgentResult(
                success=True,
                confidence=confidence,
                data={"document": ingested, "chunk_count": len(chunks), "word_count": metadata["word_count"], "extracted_image_count": len(image_paths)},
                reasoning="Ingested source document into local knowledge base and vector index.",
            )
        )
