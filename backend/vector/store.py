from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, List, Optional, TYPE_CHECKING

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

from backend.common.models import TextChunk

if TYPE_CHECKING:
    from backend.vector.embedding_provider import EmbeddingProvider

logger = logging.getLogger(__name__)


class VectorStore:
    """Production Vector Store using ChromaDB (local persistence).
    
    Features:
    - Configurable Embedding Provider: BGE ONNX INT8 (768-dim) or MiniLM-L6-v2 (384-dim)
    - Semantic Search: Finding concepts, not just keywords
    - Persistence: Stores data in ./knowledge_base/vectors/chroma
    - Offline Support: Models bundled in PyInstaller executable
    - Index Metadata: Tracks embedding model version for compatibility
    - Phase 12: Named Scoped Knowledge Spaces via per-folder collections
    """

    INDEX_META_FILE = "_kts_index_meta.json"

    # ── Phase 12.1: Collection naming constants ───────────────
    COLLECTION_PREFIX = "kts_"
    DEFAULT_COLLECTION = "kts_default"
    LEGACY_COLLECTION = "kts_knowledge_base"  # backward compat

    def __init__(
        self,
        persist_dir: str,
        embedding_provider: Optional["EmbeddingProvider"] = None
    ):
        """Initialize VectorStore with optional embedding provider.
        
        Args:
            persist_dir: Path to ChromaDB persistence directory
            embedding_provider: Optional EmbeddingProvider instance. If None,
                falls back to ChromaDB's default MiniLM-L6-v2.
                
        NOTE: As of Phase 5 WS-1, embedding_provider should ALWAYS be provided.
        The legacy fallback is deprecated and may be removed.
        """
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        
        # Store provider reference for embed_query access
        self._embedding_provider = embedding_provider
        
        # Resolve embedding function
        if embedding_provider is not None:
            # Use the configurable provider via adapter
            from backend.vector.embedding_provider import ChromaEmbeddingAdapter
            self.ef = ChromaEmbeddingAdapter(embedding_provider)
            logger.info(f"VectorStore using provider: {embedding_provider.provider_id} ({embedding_provider.dims}-dim)")
        else:
            # Legacy fallback - deprecated, for dev/testing only
            logger.warning("VectorStore: No embedding provider - using deprecated legacy mode")
            self.ef = embedding_functions.DefaultEmbeddingFunction()
        
        # Disable ChromaDB telemetry
        os.environ.setdefault('ANONYMIZED_TELEMETRY', 'False')
        
        # Initialize ChromaDB in Persistent Mode
        # Use resolved absolute path to avoid potential Rust binding path issues
        abs_path = str(self.persist_dir.resolve())
        # Explicitly set allow_reset=True to bypass potential strict mode checks in Rust bindings
        self.client = chromadb.PersistentClient(
            path=abs_path,
            settings=Settings(anonymized_telemetry=False, allow_reset=True),
        )
        
        self.collection = self.client.get_or_create_collection(
            name="kts_knowledge_base",
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"}
        )

        # Phase 13.3: Parent-chunk collection (stores full-section parents)
        # Parents are fetched by ID, never by similarity search.
        self._parent_collection = self.client.get_or_create_collection(
            name="kts_parent_chunks",
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"}
        )
        
        # Check and write index metadata for compatibility tracking
        self._handle_index_metadata()

    def _handle_index_metadata(self):
        """Check existing index metadata and handle model version changes."""
        meta_path = self.persist_dir / self.INDEX_META_FILE
        
        # Determine current provider info
        if self._embedding_provider:
            current_provider = self._embedding_provider.provider_id
            current_dims = self._embedding_provider.dims
            current_hash = self._embedding_provider.model_hash
        else:
            current_provider = "legacy_chroma_default"
            current_dims = 384
            current_hash = "chromadb-default"
        
        if meta_path.exists():
            try:
                existing = json.loads(meta_path.read_text(encoding='utf-8'))
                existing_provider = existing.get("provider_id", "unknown")
                existing_dims = existing.get("dims", 0)
                
                if existing_dims != current_dims:
                    logger.warning(
                        f"EMBEDDING DIMENSION MISMATCH: Index has {existing_dims}-dim "
                        f"vectors but current provider is {current_dims}-dim. "
                        f"Re-ingestion required for accurate search results."
                    )
                elif existing_provider != current_provider:
                    logger.info(
                        f"Embedding provider changed from {existing_provider} to {current_provider} "
                        f"(same dimensions). Results may vary slightly."
                    )
            except Exception as e:
                logger.warning(f"Failed to read index metadata: {e}")
        
        # Write/update metadata
        meta = {
            "provider_id": current_provider,
            "dims": current_dims,
            "model_hash": current_hash,
        }
        try:
            meta_path.write_text(json.dumps(meta, indent=2), encoding='utf-8')
        except Exception as e:
            logger.warning(f"Failed to write index metadata: {e}")

    def embed_query(self, text: str) -> List[float]:
        """Embed a query string using the configured provider.
        
        This method uses embed_query() on the provider, which handles
        any query-specific preprocessing (e.g., BGE query prefix).
        
        Args:
            text: Query string to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        if self._embedding_provider:
            return self._embedding_provider.embed_query(text)
        else:
            # Legacy: use ChromaDB's embedding function directly
            embeddings = self.ef([text])
            return embeddings[0]

    # -------------------------------------------------------------------------
    # Phase 12.1: Scoped Collection API
    # -------------------------------------------------------------------------

    @classmethod
    def collection_name_for_scope(cls, scope_slug: str) -> str:
        """Return the ChromaDB collection name for a given scope slug.

        - ``None`` / empty / ``"__global__"`` → ``kts_default``
        - any other slug          → ``kts_{slug}``
        """
        if not scope_slug or scope_slug == "__global__":
            return cls.DEFAULT_COLLECTION
        return f"{cls.COLLECTION_PREFIX}{scope_slug}"

    def get_or_create_scoped_collection(self, scope_slug: str):
        """Return (or create) a ChromaDB collection for *scope_slug*.

        Uses the naming convention ``kts_{slug}``.
        """
        name = self.collection_name_for_scope(scope_slug)
        return self.client.get_or_create_collection(
            name=name,
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"},
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
                "doc_type": getattr(c, "doc_type", "UNKNOWN"),
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
            # Phase 13.3: parent chunk linkage
            if hasattr(c, "parent_id") and c.parent_id:
                meta["parent_id"] = str(c.parent_id)
            metadatas.append(meta)

        # Upsert into collection
        self.collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
        logger.info(f"Upserted {len(chunks)} chunks into VectorStore")

    def search(self, query: str, top_k: int = 5, doc_type_filter: str | None = None, scope: str | None = None) -> List[dict]:
        """Perform Semantic Search.

        Parameters
        ----------
        query : str
            The search query text.
        top_k : int
            Maximum number of results to return.
        doc_type_filter : str | None
            Optional document type filter (Phase 12.3 two-level scope).
        scope : str | None
            Optional scope slug (Phase 12.1).  When provided, searches the
            named collection ``kts_{scope}`` instead of the default collection.
        """
        # Phase 12.1: Select the target collection based on scope
        if scope and scope != "__global__":
            target_collection = self.get_or_create_scoped_collection(scope)
            logger.debug("[Phase12] Scoped search: scope=%s, collection=%s", scope, target_collection.name)
        else:
            target_collection = self.collection

        where_clause = {}
        if doc_type_filter:
            where_clause["doc_type"] = doc_type_filter

        # If no filter, pass None to where
        where_arg = where_clause if where_clause else None

        results = target_collection.query(
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
    
    def get_chunks_by_indices(
        self, 
        doc_id: str, 
        start_index: int, 
        end_index: int
    ) -> List[dict]:
        """
        Retrieve chunks by document ID and index range.
        
        Used for context expansion: retrieve chunks before/after a hit chunk.
        
        Args:
            doc_id: Document identifier
            start_index: Starting chunk index (inclusive)
            end_index: Ending chunk index (inclusive)
        
        Returns:
            List of chunk dictionaries with content, metadata, chunk_index
        """
        if start_index < 0:
            start_index = 0
        
        # ChromaDB doesn't have native range queries on metadata,
        # so we need to get all chunks for doc and filter
        try:
            results = self.collection.get(
                where={"doc_id": doc_id},
                include=["documents", "metadatas"]
            )
            
            if not results or not results["ids"]:
                return []
            
            # Filter by chunk_index range
            chunks = []
            for i, chunk_id in enumerate(results["ids"]):
                meta = results["metadatas"][i]
                chunk_idx = int(meta.get("chunk_index", -1))
                
                if start_index <= chunk_idx <= end_index:
                    chunks.append({
                        "chunk_id": chunk_id,
                        "content": results["documents"][i],
                        **meta,
                        "chunk_index": chunk_idx,
                        "score": 0.0  # No score for direct retrieval
                    })
            
            # Sort by chunk_index to maintain document order
            chunks.sort(key=lambda x: x["chunk_index"])
            return chunks
            
        except Exception as e:
            logger.warning(f"Failed to retrieve chunks by indices for {doc_id}: {e}")
            return []
        
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
    # Phase 13.3: Parent Chunk API
    # -------------------------------------------------------------------------

    def add_parent_chunks(self, parents: List[dict]) -> None:
        """Store parent chunks for later ID-based retrieval.
        
        Each parent dict should contain:
            - parent_id (str): Unique parent ID
            - content (str): Full-section text
            - doc_id (str): Owning document
            - section (str, optional): Section number
            - child_ids (list[str], optional): IDs of child chunks
        """
        if not parents:
            return
        ids = [p["parent_id"] for p in parents]
        documents = [p["content"] for p in parents]
        metadatas = []
        for p in parents:
            meta = {
                "doc_id": p.get("doc_id", ""),
                "section": p.get("section", ""),
            }
            child_ids = p.get("child_ids", [])
            if child_ids:
                meta["child_ids"] = json.dumps(child_ids)
            metadatas.append(meta)
        self._parent_collection.upsert(
            ids=ids, documents=documents, metadatas=metadatas
        )
        logger.info(f"Upserted {len(parents)} parent chunks into parent store")

    def fetch_parent_chunks(self, parent_ids: List[str]) -> List[dict]:
        """Fetch parent chunks by their IDs (no similarity search).
        
        Returns list of dicts with parent_id, content, doc_id, section, child_ids.
        """
        if not parent_ids:
            return []
        # Deduplicate while preserving order
        seen = set()
        unique_ids = []
        for pid in parent_ids:
            if pid not in seen:
                seen.add(pid)
                unique_ids.append(pid)
        try:
            results = self._parent_collection.get(
                ids=unique_ids,
                include=["documents", "metadatas"]
            )
            if not results or not results["ids"]:
                return []
            parents = []
            for i, pid in enumerate(results["ids"]):
                meta = results["metadatas"][i] if i < len(results["metadatas"]) else {}
                child_ids_raw = meta.get("child_ids", "[]")
                try:
                    child_ids = json.loads(child_ids_raw) if isinstance(child_ids_raw, str) else []
                except (json.JSONDecodeError, TypeError):
                    child_ids = []
                parents.append({
                    "parent_id": pid,
                    "content": results["documents"][i] if i < len(results["documents"]) else "",
                    "doc_id": meta.get("doc_id", ""),
                    "section": meta.get("section", ""),
                    "child_ids": child_ids,
                })
            return parents
        except Exception as e:
            logger.warning(f"Failed to fetch parent chunks: {e}")
            return []

    def delete_parent_chunks(self, doc_id: str) -> None:
        """Remove all parent chunks for a document."""
        try:
            self._parent_collection.delete(where={"doc_id": doc_id})
        except Exception as e:
            logger.warning(f"Failed to delete parent chunks for {doc_id}: {e}")

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
