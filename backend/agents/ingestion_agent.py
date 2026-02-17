from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend.common.models import AgentResult, IngestedDocument
from backend.common.text_utils import clean_text
# All converters are bundled in the self-contained build
from backend.ingestion import (
    convert_html, convert_json,
    extract_json_metadata, extract_image_refs,
    convert_yaml, convert_ini, convert_csv,
    convert_doc, convert_docx, convert_pdf, convert_pptx, convert_png,
    extract_entities_and_keyphrases,
)
from backend.ingestion.regime_classifier import RegimeClassifier
from backend.vector import VectorStore, chunk_document
from backend.vector.legal_chunker import chunk_legal_document
from .base_agent import AgentBase

logger = logging.getLogger(__name__)


class IngestionAgent(AgentBase):
    agent_name = "ingestion-agent"

    def __init__(self, config):
        super().__init__(config)
        self.vector_store = VectorStore(config.chroma_persist_dir)

    # ------------------------------------------------------------------
    # NER helper – uses bundled extract_entities_and_keyphrases directly
    # ------------------------------------------------------------------
    def _extract_ner(self, text: str, max_keyphrases: int = None):
        """Extract entities and keyphrases using bundled spaCy model."""
        try:
            return extract_entities_and_keyphrases(text, max_keyphrases=max_keyphrases)
        except Exception as e:
            logger.debug(f"NER extraction skipped: {e}")
            return None

    def _convert(self, file_path: Path, images_dir: str | None = None) -> tuple[str, list[str]]:
        extension = file_path.suffix.lower()

        # Plain-text / markup converters (always available)
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

        # DOCX (OOXML) — python-docx
        if extension == ".docx":
            return convert_docx(str(file_path), images_dir=images_dir)

        # DOC (legacy binary Word / OLE2) — custom parser via olefile
        if extension == ".doc":
            return convert_doc(str(file_path), images_dir=images_dir)

        # PPTX — python-pptx
        if extension == ".pptx":
            return convert_pptx(str(file_path), images_dir=images_dir)

        # PDF — PyMuPDF
        if extension == ".pdf":
            return convert_pdf(str(file_path), images_dir=images_dir)

        # PNG — asset metadata (no OCR)
        if extension == ".png":
            return convert_png(str(file_path))

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
        
        # NER & Keyphrase Extraction (bundled spaCy model)
        ner_result = None
        if getattr(self.config, 'ner_enabled', True):
            ner_result = self._extract_ner(text)

        # ── Regime Classification (TD §2) ─────────────────────────
        doc_regime = "UNKNOWN"
        if getattr(self.config, 'regime_classifier_enabled', True):
            try:
                regime_result = RegimeClassifier.classify(text, filename=source_path.name)
                doc_regime = regime_result.regime
                logger.info("Regime classified: %s (score=%d) for %s", doc_regime, regime_result.score, source_path.name)
            except Exception as exc:
                logger.debug("Regime classification failed: %s", exc)

        # ── Content-level date extraction (Gap 6) ──────────────────
        content_date = None
        try:
            import re as _re
            date_patterns = [
                r'(?:Last\s+Updated|Updated|Effective\s+Date|Date|Revision)[:\s]*'
                r'((?:January|February|March|April|May|June|July|August|September|October|November|December)'
                r'\s+\d{1,2},?\s+\d{4})',
                r'(?:Last\s+Updated|Updated|Effective\s+Date|Date|Revision)[:\s]*'
                r'(\d{4}-\d{2}-\d{2})',
                r'(?:Last\s+Updated|Updated|Effective\s+Date|Date|Revision)[:\s]*'
                r'(\d{1,2}/\d{1,2}/\d{4})',
            ]
            for pattern in date_patterns:
                m = _re.search(pattern, text[:5000], _re.IGNORECASE)
                if m:
                    content_date = m.group(1).strip()
                    break
        except Exception:
            pass

        metadata = {
            "doc_id": doc_id,
            "title": source_path.stem,
            "source_path": str(source_path),
            "extension": source_path.suffix.lower(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "modified_at": datetime.fromtimestamp(source_path.stat().st_mtime, tz=timezone.utc).isoformat(),
            "content_date": content_date,
            "doc_type": json_metadata.get("doc_type", "UNKNOWN"),
            "doc_regime": doc_regime,
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

        # 2. Versioning (Backup Old) — auto-increment version number
        if final_doc_dir.exists():
            current_version = 0
            try:
                old_meta = json.loads((final_doc_dir / "metadata.json").read_text(encoding="utf-8"))
                current_version = int(old_meta.get("version", 0))
            except Exception:
                pass
            
            version_backup_dir = Path(self.config.knowledge_base_path) / "versions" / doc_id / f"v{current_version}"
            version_backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy active to backup
            for f in final_doc_dir.glob("*"):
                if f.is_file():
                    shutil.copy2(f, version_backup_dir)
            
            # Auto-increment version for the new document
            metadata["version"] = current_version + 1
            # Re-write metadata to staging with updated version
            metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        
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
        
        # ── Intelligent Chunking Strategy ──────────────────────────
        # For legal/governing documents: use section-aware semantic chunking
        # to preserve document structure and reduce over-fragmentation.
        # For other documents: use traditional character-based chunking.
        
        use_legal_chunking = (
            doc_regime == "GOVERNING_DOC_LEGAL" and 
            getattr(self.config, 'section_aware_chunking_enabled', True)
        )
        
        if use_legal_chunking:
            # Semantic section-aware chunking for legal documents
            logger.info("Using legal semantic chunking for %s", source_path.name)
            chunks = chunk_legal_document(
                doc_id=doc_id,
                source_path=str(source_path),
                text=text,
                min_chunk_size=getattr(self.config, 'legal_min_chunk_size', 500),
                max_chunk_size=getattr(self.config, 'legal_max_chunk_size', 5000),
            )
        else:
            # Traditional character-based chunking
            # Regime-adaptive chunk sizing: legal docs use larger chunks even in fallback
            effective_chunk_size = self.config.chunk_size
            effective_chunk_overlap = self.config.chunk_overlap
            if doc_regime == "GOVERNING_DOC_LEGAL":
                effective_chunk_size = getattr(self.config, 'legal_chunk_size', 3000)
                effective_chunk_overlap = getattr(self.config, 'legal_chunk_overlap', 500)
                logger.info("Using legal chunk sizing: %d/%d for %s",
                            effective_chunk_size, effective_chunk_overlap, source_path.name)

            chunks = chunk_document(
                doc_id=doc_id,
                source_path=str(source_path),
                text=text,
                chunk_size=effective_chunk_size,
                chunk_overlap=effective_chunk_overlap,
            )
        
        logger.info("Generated %d chunks for %s (method=%s)", 
                    len(chunks), source_path.name, 
                    "semantic-legal" if use_legal_chunking else "character-based")
        
        # Extract entities/keyphrases per-chunk if NER enabled
        if getattr(self.config, 'ner_enabled', True):
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
