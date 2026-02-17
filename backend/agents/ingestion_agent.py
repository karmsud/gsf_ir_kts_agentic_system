from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend.common.models import AgentResult, IngestedDocument
from backend.common.text_utils import clean_text
# Import only core converters (no external dependencies)
from backend.ingestion import (
    convert_html, convert_json, 
    extract_json_metadata, extract_image_refs,
    convert_yaml, convert_ini, convert_csv
)
# Optional processors: docx, pptx, pdf, png require processor extensions
# NER extractor requires nlp processor extension
from backend.vector import VectorStore, chunk_document
from .base_agent import AgentBase

logger = logging.getLogger(__name__)


class IngestionAgent(AgentBase):
    agent_name = "ingestion-agent"

    def __init__(self, config):
        super().__init__(config)
        self.vector_store = VectorStore(config.chroma_persist_dir)
        
        # Check processor availability
        self._office_available = os.environ.get('KTS_OFFICE_PROCESSOR_PATH') is not None
        self._pdf_available = os.environ.get('KTS_PDF_PROCESSOR_PATH') is not None
        self._nlp_available = os.environ.get('KTS_NLP_PROCESSOR_PATH') is not None and \
                             os.environ.get('KTS_SPACY_MODEL_PATH') is not None
    
    def _load_office_converter(self, doc_type: str):
        """Dynamically load converter from office processor extension."""
        office_path = os.environ.get('KTS_OFFICE_PROCESSOR_PATH')
        if not office_path:
            return None
        
        # Add processor path to sys.path if not already there
        if office_path not in sys.path:
            sys.path.insert(0, office_path)
        
        try:
            if doc_type == 'docx':
                from converters.docx_converter import convert_docx
                return convert_docx
            elif doc_type == 'pptx':
                from converters.pptx_converter import convert_pptx
                return convert_pptx
        except ImportError as e:
            logger.error(f"Failed to load office converter: {e}")
            return None
    
    def _load_pdf_converter(self):
        """Dynamically load converter from PDF processor extension."""
        pdf_path = os.environ.get('KTS_PDF_PROCESSOR_PATH')
        if not pdf_path:
            return None
        
        if pdf_path not in sys.path:
            sys.path.insert(0, pdf_path)
        
        try:
            from converters.pdf_converter import convert_pdf
            return convert_pdf
        except ImportError as e:
            logger.error(f"Failed to load PDF converter: {e}")
            return None
    
    def _load_image_converter(self):
        """Dynamically load image converter (PNG) from office processor."""
        # Image processing uses PIL which is bundled with office processor
        office_path = os.environ.get('KTS_OFFICE_PROCESSOR_PATH')
        if not office_path:
            return None
        
        if office_path not in sys.path:
            sys.path.insert(0, office_path)
        
        try:
            from converters.png_converter import convert_png
            return convert_png
        except ImportError as e:
            logger.error(f"Failed to load image converter: {e}")
            return None
    
    def _extract_ner(self, text: str, max_keyphrases: int = None):
        """Extract entities and keyphrases using NLP processor if available."""
        if not self._nlp_available:
            return None
        
        nlp_path = os.environ.get('KTS_NLP_PROCESSOR_PATH')
        if nlp_path not in sys.path:
            sys.path.insert(0, nlp_path)
        
        try:
            from extractors.ner_extractor import extract_entities_and_keyphrases
            return extract_entities_and_keyphrases(text, max_keyphrases=max_keyphrases)
        except ImportError as e:
            logger.error(f"Failed to load NER extractor: {e}")
            return None

    def _convert(self, file_path: Path, images_dir: str | None = None) -> tuple[str, list[str]]:
        extension = file_path.suffix.lower()
        
        # Built-in converters (always available)
        if extension in {".md", ".txt"}:
            return file_path.read_text(encoding="utf-8", errors="ignore"), []
        if extension in {".htm", ".html"}:
            return convert_html(str(file_path))
        if extension == ".json":
            return convert_json(str(file_path))
        if extension in {".yaml", ".yml"}:
            return convert_yaml(str(file_path))
        if extension == ".ini":
            return convert_ini(str(file_path))
        if extension == ".csv":
            return convert_csv(str(file_path))
        
        # Office processor converters (optional)
        if extension in {".docx", ".doc"}:
            if not self._office_available:
                logger.warning(
                    f"Cannot process {extension} files - Office processor not installed. "
                    "Install 'kts-processors-office' extension to enable DOCX/PPTX support."
                )
                raise ValueError(f"Office processor required for {extension} files")
            converter = self._load_office_converter('docx')
            if not converter:
                raise ValueError(f"Failed to load DOCX converter")
            return converter(str(file_path), images_dir=images_dir)
        
        if extension == ".pptx":
            if not self._office_available:
                logger.warning(
                    "Cannot process PPTX files - Office processor not installed. "
                    "Install 'kts-processors-office' extension."
                )
                raise ValueError("Office processor required for PPTX files")
            converter = self._load_office_converter('pptx')
            if not converter:
                raise ValueError("Failed to load PPTX converter")
            return converter(str(file_path), images_dir=images_dir)
        
        # PDF processor converter (optional)
        if extension == ".pdf":
            if not self._pdf_available:
                logger.warning(
                    "Cannot process PDF files - PDF processor not installed. "
                    "Install 'kts-processors-pdf' extension to enable PDF support."
                )
                raise ValueError("PDF processor required for PDF files")
            converter = self._load_pdf_converter()
            if not converter:
                raise ValueError("Failed to load PDF converter")
            return converter(str(file_path), images_dir=images_dir)
        
        # Image converter (uses PIL from office processor)
        if extension == ".png":
            if not self._office_available:
                logger.warning(
                    "Cannot process PNG files - Office processor not installed. "
                    "Install 'kts-processors-office' extension (provides PIL/Pillow)."
                )
                raise ValueError("Office processor required for PNG files")
            converter = self._load_image_converter()
            if not converter:
                raise ValueError("Failed to load image converter")
            return converter(str(file_path))
        
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
        
        # NER & Keyphrase Extraction (if NLP processor available)
        ner_result = None
        if getattr(self.config, 'ner_enabled', False) and self._nlp_available:
            ner_result = self._extract_ner(text)

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

        # Attach NER results to metadata
        if ner_result and (ner_result.entities or ner_result.keyphrases):
            metadata["entities"] = [
                {"text": e.text, "label": e.label} for e in ner_result.entities
            ]
            metadata["keyphrases"] = [
                {"text": k.text, "score": k.score} for k in ner_result.keyphrases
            ]
        
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
        
        # Extract entities/keyphrases per-chunk if NER enabled and NLP processor available
        if getattr(self.config, 'ner_enabled', False) and self._nlp_available:
            logger.info(f"Extracting entities/keyphrases for {len(chunks)} chunks...")
            for chunk in chunks:
                ner_result = self._extract_ner(chunk.content, max_keyphrases=5)
                if ner_result:
                    chunk.entities = [
                        {"text": e.text, "label": e.label} for e in ner_result.entities
                    ]
                    chunk.keyphrases = [
                        {"text": k.text, "score": k.score} for k in ner_result.keyphrases
                    ]
        
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
