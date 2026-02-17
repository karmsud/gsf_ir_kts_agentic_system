from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, List, Optional

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

from backend.common.models import TextChunk

logger = logging.getLogger(__name__)


class VectorStore:
    """Production Vector Store using ChromaDB (local persistence).
    
    Features:
    - Default Embedding: all-MiniLM-L6-v2 (via ONNX, bundled for offline use)
    - Semantic Search: Finding concepts, not just keywords
    - Persistence: Stores data in ./knowledge_base/vectors/chroma
    - Offline Support: Model bundled in PyInstaller executable
    """

    def __init__(self, persist_dir: str):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        
        # Set ChromaDB model cache to bundled location if running in PyInstaller
        if getattr(sys, 'frozen', False):
            # Running in PyInstaller bundle — redirect ChromaDB ONNX model path
            # to the bundled location inside _MEIPASS.
            bundle_dir = Path(sys._MEIPASS)
            model_cache = bundle_dir / 'chroma_models' / 'all-MiniLM-L6-v2'
            if model_cache.exists():
                # Monkey-patch the class-level DOWNLOAD_PATH so the model/tokenizer
                # properties load from the bundled directory instead of ~/.cache/
                from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
                ONNXMiniLM_L6_V2.DOWNLOAD_PATH = model_cache
                logger.info(f"Using bundled ChromaDB model from: {model_cache}")
            else:
                logger.warning(f"Bundled ChromaDB model not found at: {model_cache}")
        
        # Disable ChromaDB telemetry — avoids posthog import errors in
        # PyInstaller bundles and prevents phoning home from offline installs.
        os.environ.setdefault('ANONYMIZED_TELEMETRY', 'False')
        
        # Initialize ChromaDB in Persistent Mode
        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        
        # Use default optimized ONNX embedding function (all-MiniLM-L6-v2)
        # This handles tokenization and embedding locally.
        self.ef = embedding_functions.DefaultEmbeddingFunction()
        
        self.collection = self.client.get_or_create_collection(
            name="kts_knowledge_base",
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"}
        )

    # -------------------------------------------------------------------------
    # Core API
    # -------------------------------------------------------------------------

    def add_chunks(self, chunks: List[TextChunk]) -> None:
        """Add list of TextChunk objects to ChromaDB"""
        if not chunks:
            return

        # Prepare batch vectors
        ids = [c.chunk_id for c in chunks]
        documents = [c.content for c in chunks]
        
        # Convert dataclass to dict for metadata, ensuring only primitives
        metadatas = []
        for c in chunks:
            meta = {
                "doc_id": c.doc_id,
                "source_path": c.source_path,
                "chunk_index": c.chunk_index,
                "doc_type": "UNKNOWN" 
            }
            # Add any other fields from TextChunk if they exist and are primitives
            if hasattr(c, "is_image_desc") and c.is_image_desc:
                meta["is_image_desc"] = True
            if hasattr(c, "image_id") and c.image_id:
                meta["image_id"] = str(c.image_id)
            # Preserve entity metadata (serialize as JSON strings for ChromaDB)
            if hasattr(c, "entities") and c.entities:
                import json
                meta["entities"] = json.dumps(c.entities)
            if hasattr(c, "keyphrases") and c.keyphrases:
                import json
                meta["keyphrases"] = json.dumps(c.keyphrases)
            metadatas.append(meta)

        # Upsert into collection
        self.collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
        logger.info(f"Upserted {len(chunks)} chunks into VectorStore")

    def search(self, query: str, top_k: int = 5, doc_type_filter: str | None = None) -> List[dict]:
        """Perform Semantic Search"""
        where_clause = {}
        if doc_type_filter:
            where_clause["doc_type"] = doc_type_filter

        # If no filter, pass None to where
        where_arg = where_clause if where_clause else None

        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where_arg,
            include=["documents", "metadatas", "distances"]
        )
        
        # Flatten structure
        hits = []
        if results["ids"]:
            count = len(results["ids"][0])
            for i in range(count):
                dist = results["distances"][0][i]
                # Cosine distance to similarity: 1 - distance
                score = 1.0 - dist
                
                meta = results["metadatas"][0][i]
                hits.append({
                    "chunk_id": results["ids"][0][i],
                    "content": results["documents"][0][i],
                    **meta,
                    "score": score
                })
        
        return hits
        
    def delete_document(self, doc_id: str) -> None:
        """Remove all chunks for a specific document"""
        # Delete expects a where clause
        self.collection.delete(
            where={"doc_id": doc_id}
        )

    def reset_index(self) -> None:
        """Clear all data"""
        self.client.delete_collection("kts_knowledge_base")
        self.collection = self.client.create_collection(
            name="kts_knowledge_base",
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"}
        )

    # -------------------------------------------------------------------------
    # Legacy / Compatibility API (Aliases for existing Agents)
    # -------------------------------------------------------------------------
    
    def upsert_chunks(self, chunks: List[TextChunk]) -> None:
        """Alias for add_chunks for backward compatibility."""
        self.add_chunks(chunks)

    def delete_doc_chunks(self, doc_id: str) -> None:
        """Alias for delete_document."""
        self.delete_document(doc_id)
        
    def delete_doc(self, doc_id: str) -> None:
        """Alias for delete_document."""
        self.delete_document(doc_id)

    def prune_orphans(self, active_doc_ids: set[str]) -> int:
        """Removes chunks where doc_id is NOT in the active set."""
        # Note: Expensive operation in Chroma without proper support for extensive deletes.
        # We will iterate and delete in batches if needed.
        # For now, minimal implementation:
        try:
            full_scan = self.collection.get(include=["metadatas"])
            if not full_scan or not full_scan["ids"]:
                return 0
                
            ids_to_delete = []
            for i, meta in enumerate(full_scan["metadatas"]):
                if meta.get("doc_id") not in active_doc_ids:
                    ids_to_delete.append(full_scan["ids"][i])
            
            if ids_to_delete:
                self.collection.delete(ids=ids_to_delete)
                return len(ids_to_delete)
        except Exception as e:
            logger.warning(f"Failed to prune orphans: {e}")
        return 0

    def update_doc_metadata(self, doc_id: str, doc_type: str | None = None, tags: list[str] | None = None) -> None:
        """Update metadata for existing chunks of a document"""
        try:
            results = self.collection.get(where={"doc_id": doc_id}, include=["metadatas"])
            if not results["ids"]:
                return

            ids = results["ids"]
            old_metadatas = results["metadatas"]
            new_metadatas = []

            for meta in old_metadatas:
                new_meta = meta.copy()
                if doc_type:
                    new_meta["doc_type"] = doc_type
                # Note: Chroma metadata values must be str, int, float, bool. NOT lists.
                if tags:
                   # Convert tags list to comma-separated string
                   new_meta["tags"] = ",".join(tags)
                new_metadatas.append(new_meta)
                
            self.collection.update(
                ids=ids,
                metadatas=new_metadatas
            )
        except Exception as e:
            logger.error(f"Failed to update metadata for {doc_id}: {e}")

    def add_image_description(self, doc_id: str, source_path: str, image_id: str, description: str) -> None:
        """Add a specific image description chunk"""
        chunk_id = f"{doc_id}_img_{image_id}"
        meta = {
            "doc_id": doc_id,
            "source_path": source_path,
            "chunk_index": -1,
            "doc_type": "IMAGE_DESC",
            "is_image_desc": True,
            "image_id": str(image_id)
        }
        self.collection.upsert(
            ids=[chunk_id],
            documents=[description],
            metadatas=[meta]
        )

    # -------------------------------------------------------------------------
    # Legacy Test Compatibility API
    # -------------------------------------------------------------------------

    def _load(self) -> list[dict]:
        """Compatibility helper used by older tests."""
        results = self.collection.get(include=["documents", "metadatas"])
        rows: list[dict] = []
        ids = results.get("ids", [])
        docs = results.get("documents", [])
        metas = results.get("metadatas", [])
        for idx, chunk_id in enumerate(ids):
            meta = metas[idx] if idx < len(metas) else {}
            row = {
                "chunk_id": chunk_id,
                "content": docs[idx] if idx < len(docs) else "",
                **(meta or {}),
            }
            rows.append(row)
        return rows

    def _save(self, rows: list[dict]) -> None:
        """Compatibility helper used by older tests."""
        self.reset_index()
        if not rows:
            return
        ids = [str(r.get("chunk_id")) for r in rows]
        documents = [str(r.get("content", "")) for r in rows]
        metadatas = []
        for row in rows:
            metadata = {k: v for k, v in row.items() if k not in {"chunk_id", "content"}}
            if "doc_type" not in metadata:
                metadata["doc_type"] = "UNKNOWN"
            metadatas.append(metadata)
        self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
