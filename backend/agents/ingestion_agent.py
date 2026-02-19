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
from backend.common.doc_types import normalize_doc_type
from backend.vector import VectorStore, chunk_document
from backend.vector.legal_chunker import chunk_legal_document
from backend.vector.embedding_provider import get_embedding_provider
from .base_agent import AgentBase

logger = logging.getLogger(__name__)


class IngestionAgent(AgentBase):
    agent_name = "ingestion-agent"

    def __init__(self, config):
        super().__init__(config)
        # Initialize embedding provider from config (supports BGE ONNX or legacy MiniLM)
        self._embedding_provider = get_embedding_provider(config)
        self.vector_store = VectorStore(
            config.chroma_persist_dir,
            embedding_provider=self._embedding_provider
        )

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

    # ------------------------------------------------------------------
    # Phase 6 — Hierarchical item extraction + dual store + graph
    # ------------------------------------------------------------------
    def _run_phase6_pipeline(
        self,
        doc_id: str,
        doc_regime: str,
        text: str,
        source_path: Path,
    ) -> dict:
        """Run Phase 6 ingestion: extract items, build hierarchical graph,
        and populate the dual vector store.

        Returns stats dict or None on failure.
        """
        try:
            from backend.vector.legal_chunker import LegalChunker
            from backend.extraction.item_extractor_base import get_item_extractor
            from backend.vector.dual_vector_store import DualVectorStore
            from backend.graph.enhanced_graph_builder import EnhancedGraphBuilder
            from backend.graph.persistence import GraphStore

            verbose = getattr(self.config, 'phase6_verbose_logging', True)

            # Determine effective doc_type for extractor routing
            doc_type = doc_regime if doc_regime != "UNKNOWN" else "GENERIC"
            if verbose:
                logger.info("[Phase6] Starting hierarchical pipeline for %s (type=%s)", source_path.name, doc_type)

            # 1. Parse sections using LegalChunker's section parsing
            if verbose:
                logger.info("[Phase6] Step 1/4 — Parsing sections from document text")
            chunker = LegalChunker(
                min_chunk_size=getattr(self.config, 'legal_min_chunk_size', 500),
                max_chunk_size=getattr(self.config, 'legal_max_chunk_size', 5000),
            )
            raw_sections = chunker.extract_sections(text)
            if not raw_sections:
                # Fallback: treat entire document as one section
                raw_sections = []

            sections = []
            if raw_sections:
                for i, sec in enumerate(raw_sections):
                    sections.append({
                        "section_number": sec.number or str(i + 1),
                        "section_heading": sec.title or f"Section {i + 1}",
                        "section_text": sec.content or "",
                    })
            else:
                # No structured sections found — treat entire text as one section
                sections = [{"section_number": "1", "section_heading": source_path.stem, "section_text": text}]
            if verbose:
                logger.info("[Phase6] Found %d sections", len(sections))

            # 2. Build hierarchical graph (adds SECTION + ITEM nodes + typed edges)
            if verbose:
                logger.info("[Phase6] Step 2/4 — Building hierarchical graph")
            graph_store = GraphStore(self.config.graph_path)
            builder = EnhancedGraphBuilder(graph_store)
            graph_stats = builder.build_hierarchical_graph(
                document_id=doc_id,
                doc_type=doc_type,
                sections=sections,
                doc_metadata={"title": source_path.stem, "path": str(source_path)},
            )
            if verbose:
                logger.info("[Phase6] Graph: %s", graph_stats)

            # 3. Extract items and populate dual vector store
            if verbose:
                logger.info("[Phase6] Step 3/4 — Extracting items & populating dual vector store")
            chroma_dir = getattr(self.config, 'phase6_chroma_dir', '.kts/vectors/phase6')
            dual_store = DualVectorStore(chroma_dir, embedding_provider=self._embedding_provider)

            extractor = get_item_extractor(doc_type)
            all_items = []
            for idx, sec in enumerate(sections):
                items = extractor.extract_items(
                    section_text=sec["section_text"],
                    section_number=sec["section_number"],
                    section_heading=sec["section_heading"],
                    section_index=idx,
                    document_id=doc_id,
                )
                all_items.extend(items)

            # Upsert items to dual store
            if all_items:
                item_dicts = []
                for item in all_items:
                    item_dicts.append({
                        "id": item.id,
                        "text": item.text,
                        "metadata": {
                            "item_type": item.item_type,
                            "document_id": item.document_id,
                            "section_number": item.section_number,
                            "section_heading": item.section_heading,
                            "section_index": item.section_index,
                            "item_index": item.item_index,
                            "source_path": str(source_path),
                            "doc_type": normalize_doc_type(doc_regime),
                        },
                    })
                dual_store.add_items(item_dicts)
                if verbose:
                    logger.info("[Phase6] Added %d items to dual vector store", len(item_dicts))

            # Upsert sections to dual store
            section_dicts = []
            for idx, sec in enumerate(sections):
                section_dicts.append({
                    "id": f"sec:{doc_id}:{idx:04d}",
                    "text": sec["section_text"][:2000],  # truncate for embedding
                    "metadata": {
                        "section_number": sec["section_number"],
                        "section_heading": sec["section_heading"],
                        "document_id": doc_id,
                        "source_path": str(source_path),
                        "doc_type": normalize_doc_type(doc_regime),
                    },
                })
            dual_store.add_sections(section_dicts)
            if verbose:
                logger.info("[Phase6] Added %d sections to dual vector store", len(section_dicts))

            # 4. Summary
            stats = {
                "sections": len(sections),
                "items": len(all_items),
                "graph": graph_stats,
            }
            if verbose:
                logger.info("[Phase6] Step 4/4 — Complete: %s", stats)
            return stats

        except Exception as exc:
            logger.error("[Phase6] Pipeline failed: %s", exc, exc_info=True)
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
        import sys
        import tempfile
        from backend.common.explainability import ExplainabilityLogger

        def _progress(msg):
            """Emit progress to stderr so the extension output channel shows real-time updates."""
            print(f"[Ingestion] {msg}", file=sys.stderr, flush=True)

        source_path = Path(request["path"]).resolve()
        if not source_path.exists() or not source_path.is_file():
            return AgentResult(success=False, confidence=0.1, data={"error": f"file_not_found:{source_path}"}, reasoning="Source file not found.")

        # Detect large documents early for adaptive behavior
        file_size_mb = source_path.stat().st_size / (1024 * 1024)
        is_large_doc = file_size_mb > 20  # >20 MB = large document
        if is_large_doc:
            _progress(f"Large document detected: {source_path.name} ({file_size_mb:.1f} MB)")

        provided_doc_id = request.get("doc_id")
        doc_id = provided_doc_id or f"doc_{abs(hash(str(source_path))) % 10_000_000:07d}"

        # ── Explainability Logger ──────────────────────────────────
        xlog = ExplainabilityLogger("ingestion", doc_id=doc_id, verbose=getattr(self.config, 'phase6_verbose_logging', True))

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
            _progress(f"Step 1/6: Converting {source_path.suffix} document...")
            raw_text, raw_image_refs = self._convert(source_path, images_dir=str(staging_images_dir))
        except Exception as exc:
            return AgentResult(success=False, confidence=0.2, data={"error": str(exc)}, reasoning="Document conversion failed.")

        text = clean_text(raw_text)
        if not text:
            return AgentResult(success=False, confidence=0.3, data={"error": "empty_document"}, reasoning="Extracted text is empty.")

        text_len = len(text)
        word_count = len(text.split())
        _progress(f"Step 2/6: Extracted {word_count:,} words ({text_len:,} chars), {len(raw_image_refs)} images")

        xlog.step("convert", f"Converted {source_path.suffix} → plain text",
                  detail={"extension": source_path.suffix, "chars": len(text), "images": len(raw_image_refs)},
                  why="Extract machine-readable content from binary/markup format")

        content_path = staging_dir / "content.md"
        content_path.write_text(text, encoding="utf-8")

        # Enrich metadata
        json_metadata = {}
        if source_path.suffix.lower() == ".json":
            json_metadata = extract_json_metadata(str(source_path))
        
        # NER & Keyphrase Extraction (bundled spaCy model)
        ner_result = None
        if getattr(self.config, 'ner_enabled', True):
            _progress("Step 3/6: Running NER extraction...")
            ner_result = self._extract_ner(text)

        # ── Regime Classification (TD §2) ─────────────────────────
        doc_regime = "UNKNOWN"
        if getattr(self.config, 'regime_classifier_enabled', True):
            _progress("Step 3/6: Classifying document regime...")
            try:
                regime_result = RegimeClassifier.classify(text, filename=source_path.name)
                doc_regime = regime_result.regime
                logger.info("Regime classified: %s (score=%d) for %s", doc_regime, regime_result.score, source_path.name)
            except Exception as exc:
                logger.debug("Regime classification failed: %s", exc)

        xlog.step("classify", f"Document regime: {doc_regime}",
                  detail={"regime": doc_regime, "filename": source_path.name},
                  why="Route to domain-specific chunking and extraction strategies")

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
        
        _progress("Step 4/6: Chunking document...")
        
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

            # ── Large-doc adaptive chunk sizing ────────────────────
            # For documents >20 MB (extracted), use bigger chunks to reduce
            # embedding count and stay within reasonable time budgets.
            if is_large_doc and doc_regime != "GOVERNING_DOC_LEGAL":
                # Scale chunk size: 2K base, +500 per 10 MB, cap at 5K
                effective_chunk_size = min(2000 + int(file_size_mb / 10) * 500, 5000)
                effective_chunk_overlap = min(effective_chunk_size // 4, 500)
                _progress(f"Large-doc adaptive chunks: size={effective_chunk_size}, overlap={effective_chunk_overlap}")

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
        _progress(f"Step 4/6: Generated {len(chunks)} chunks")

        xlog.step("chunk", f"Generated {len(chunks)} chunks ({('semantic-legal' if use_legal_chunking else 'character-based')})",
                  detail={"chunk_count": len(chunks), "method": "semantic-legal" if use_legal_chunking else "character-based"},
                  why="Split document into retrieval-friendly segments preserving semantic boundaries")
        
        # Extract entities/keyphrases per-chunk if NER enabled
        if getattr(self.config, 'ner_enabled', True):
            _progress(f"Extracting NER for {len(chunks)} chunks...")
            for i, chunk in enumerate(chunks):
                chunk_ner = self._extract_ner(chunk.content, max_keyphrases=5)
                if chunk_ner:
                    chunk.entities = [
                        {"text": e.text, "label": e.label} for e in chunk_ner.entities
                    ]
                    chunk.keyphrases = [
                        {"text": k.text, "score": k.score} for k in chunk_ner.keyphrases
                    ]
                if (i + 1) % 50 == 0:
                    _progress(f"NER progress: {i + 1}/{len(chunks)} chunks")
        
        _progress(f"Step 5/6: Embedding and upserting {len(chunks)} chunks...")
        self.vector_store.upsert_chunks(chunks)
        _progress(f"Step 5/6: Upserted {len(chunks)} chunks to vector store")

        xlog.step("vector_upsert", f"Upserted {len(chunks)} chunks to vector store",
                  detail={"chunk_count": len(chunks)},
                  why="Index chunks for semantic similarity retrieval")

        # ── Phase 6: Hierarchical GraphRAG Pipeline (ALWAYS RUN) ───
        # Phase 6 is now the primary architecture — no conditional needed
        _progress("Step 6/6: Building hierarchical graph + dual vector store...")
        phase6_stats = self._run_phase6_pipeline(
            doc_id=doc_id,
            doc_regime=doc_regime,
            text=text,
            source_path=source_path,
        )
        if phase6_stats:
            xlog.step("phase6", "Hierarchical GraphRAG pipeline complete",
                      detail=phase6_stats,
                      why="Build item-level graph + dual vector store for multi-hop retrieval")

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

        xlog.done(summary={
            "doc_id": doc_id, "chunks": len(chunks),
            "words": metadata["word_count"], "images": len(image_paths),
            "regime": doc_regime, "phase6": bool(phase6_stats),
        })

        return self.quality_check(
            AgentResult(
                success=True,
                confidence=confidence,
                data={"document": ingested, "chunk_count": len(chunks), "word_count": metadata["word_count"], "extracted_image_count": len(image_paths)},
                reasoning="Ingested source document into local knowledge base and vector index.",
            )
        )
