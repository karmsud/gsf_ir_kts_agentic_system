"""
Dual vector store implementation for Phase 6.

Manages two ChromaDB collections:
- items: Item-level (sentence granularity, 500-2K per doc)
- sections: Section-level (paragraph granularity, 50-150 per doc)

Both stores use the configured embedding provider (default: BGE ONNX INT8).
Falls back to MiniLM-L6-v2 for backward compatibility.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

from backend.extraction.item_extractor_base import Item

if TYPE_CHECKING:
    from backend.vector.embedding_provider import EmbeddingProvider

logger = logging.getLogger(__name__)


class DualVectorStore:
    """
    Dual vector store wrapper for item-level and section-level retrieval.

    Design:
    - Single ChromaDB PersistentClient with two collections
    - Configurable embedding provider (BGE ONNX INT8 or legacy MiniLM)
    - Unified query interface with store selection
    """

    INDEX_META_FILE = "_kts_phase6_index_meta.json"

    def __init__(
        self,
        persist_dir: str,
        embedding_provider: Optional["EmbeddingProvider"] = None
    ) -> None:
        """
        Initialize dual vector stores.

        Args:
            persist_dir: Directory for ChromaDB persistence
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
            from backend.vector.embedding_provider import ChromaEmbeddingAdapter
            self.ef = ChromaEmbeddingAdapter(embedding_provider)
            logger.info(f"[Phase6] DualVectorStore using provider: {embedding_provider.provider_id}")
        else:
            # Legacy fallback - deprecated, for dev/testing only
            logger.warning("[Phase6] DualVectorStore: No provider - using deprecated legacy mode")
            self.ef = embedding_functions.DefaultEmbeddingFunction()

        os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

        # Use resolved absolute path to avoid potential Rust binding path issues
        abs_path = str(self.persist_dir.resolve())
        self.client = chromadb.PersistentClient(
            path=abs_path,
            settings=Settings(anonymized_telemetry=False),
        )

        # Item-level collection (sentence granularity)
        self.item_collection = self.client.get_or_create_collection(
            name="kts_phase6_items",
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"},
        )

        # Section-level collection (paragraph granularity)
        self.section_collection = self.client.get_or_create_collection(
            name="kts_phase6_sections",
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"},
        )

        logger.info(
            f"[Phase6] DualVectorStore initialised: {persist_dir} "
            f"(items={self.item_collection.count()}, sections={self.section_collection.count()})"
        )
        
        # Write index metadata for compatibility tracking
        self._write_index_metadata()

    def _write_index_metadata(self) -> None:
        """Write index metadata for compatibility tracking."""
        meta_path = self.persist_dir / self.INDEX_META_FILE
        if self._embedding_provider:
            meta = {
                "provider_id": self._embedding_provider.provider_id,
                "dims": self._embedding_provider.dims,
                "model_hash": self._embedding_provider.model_hash,
            }
        else:
            meta = {
                "provider_id": "legacy_chroma_default",
                "dims": 384,
                "model_hash": "chromadb-default",
            }
        try:
            meta_path.write_text(json.dumps(meta, indent=2), encoding='utf-8')
        except Exception as e:
            logger.warning(f"Failed to write Phase6 index metadata: {e}")

    def embed_query(self, text: str) -> List[float]:
        """Embed a query using the configured provider (handles BGE query prefix)."""
        if self._embedding_provider:
            return self._embedding_provider.embed_query(text)
        embeddings = self.ef([text])
        return embeddings[0]

    # ── Item Store Operations ─────────────────────────────────────

    def add_items(self, items: list) -> None:
        """
        Add items to item-level vector store.

        Args:
            items: List of Item objects or dicts with keys: id, text, metadata
        """
        if not items:
            return

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for item in items:
            if isinstance(item, dict):
                # Dict-based input
                ids.append(item["id"])
                documents.append(item["text"])
                meta = dict(item.get("metadata", {}))
                metadatas.append(meta)
            else:
                # Item dataclass
                ids.append(item.id)
                documents.append(item.text)
                meta: dict[str, Any] = {
                    "item_type": item.item_type,
                    "document_id": item.document_id,
                    "section_number": item.section_number,
                    "section_heading": item.section_heading,
                    "section_index": item.section_index,
                    "item_index": item.item_index,
                }
                # Flatten safe metadata (ChromaDB requires scalar values)
                for k, v in item.metadata.items():
                    if isinstance(v, (str, int, float, bool)):
                        meta[k] = v
                    elif isinstance(v, list):
                        meta[k] = json.dumps(v)
                metadatas.append(meta)

        # Batch upsert in chunks of 500 (ChromaDB batch limit)
        batch_size = 500
        for start in range(0, len(ids), batch_size):
            end = start + batch_size
            self.item_collection.upsert(
                ids=ids[start:end],
                documents=documents[start:end],
                metadatas=metadatas[start:end],
            )

        logger.info(f"[Phase6] Upserted {len(items)} items into item store")

    def search_items(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search item-level vector store.

        Args:
            query: Query string
            top_k: Number of results to return
            filters: Optional metadata filters (e.g. {"item_type": "Definition"})

        Returns:
            List of result dicts with keys: id, text, similarity, metadata, type
        """
        where_arg = filters if filters else None

        results = self.item_collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where_arg,
            include=["documents", "metadatas", "distances"],
        )

        formatted: list[dict[str, Any]] = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                dist = results["distances"][0][i]
                score = 1.0 - dist  # Cosine distance → similarity
                formatted.append(
                    {
                        "id": results["ids"][0][i],
                        "text": results["documents"][0][i],
                        "similarity": score,
                        "metadata": results["metadatas"][0][i],
                        "type": "item",
                    }
                )
        return formatted

    # ── Section Store Operations ──────────────────────────────────

    def add_sections(self, sections: List[Dict[str, Any]]) -> None:
        """
        Add sections to section-level vector store.

        Args:
            sections: List of section dicts. Accepts either:
                - Full format: id, section_number, section_heading, section_text,
                  document_id, section_index, item_count, item_types
                - Simple format: id, text, metadata (dict with document_id etc.)
        """
        if not sections:
            return

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for sec in sections:
            ids.append(sec["id"])
            # Support both "section_text" (full) and "text" (simple) keys
            documents.append(sec.get("section_text", sec.get("text", "")))

            if "metadata" in sec:
                # Simple dict format: metadata is a sub-dict
                metadatas.append(dict(sec["metadata"]))
            else:
                # Full format: build metadata from top-level keys
                metadatas.append({
                    "section_number": sec.get("section_number", ""),
                    "section_heading": sec.get("section_heading", ""),
                    "document_id": sec.get("document_id", ""),
                    "section_index": sec.get("section_index", 0),
                    "item_count": sec.get("item_count", 0),
                    "item_types": ",".join(sec.get("item_types", [])),
                })

        batch_size = 500
        for start in range(0, len(ids), batch_size):
            end = start + batch_size
            self.section_collection.upsert(
                ids=ids[start:end],
                documents=documents[start:end],
                metadatas=metadatas[start:end],
            )

        logger.info(f"[Phase6] Upserted {len(sections)} sections into section store")

    def search_sections(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search section-level vector store.

        Args:
            query: Query string
            top_k: Number of results to return
            filters: Optional metadata filters

        Returns:
            List of result dicts with keys: id, text, similarity, metadata, type
        """
        where_arg = filters if filters else None

        results = self.section_collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where_arg,
            include=["documents", "metadatas", "distances"],
        )

        formatted: list[dict[str, Any]] = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                dist = results["distances"][0][i]
                score = 1.0 - dist
                formatted.append(
                    {
                        "id": results["ids"][0][i],
                        "text": results["documents"][0][i],
                        "similarity": score,
                        "metadata": results["metadatas"][0][i],
                        "type": "section",
                    }
                )
        return formatted

    # ── Unified Query Interface ───────────────────────────────────

    def search(
        self,
        query: str,
        store: str = "both",
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Unified search interface.

        Args:
            query: Query string
            store: "items", "sections", or "both" (default)
            top_k: Number of results
            filters: Optional metadata filters
        """
        if store == "items":
            return self.search_items(query, top_k, filters)
        elif store == "sections":
            return self.search_sections(query, top_k, filters)
        elif store == "both":
            items = self.search_items(query, top_k, filters)
            sections = self.search_sections(query, top_k, filters)
            combined = items + sections
            combined.sort(key=lambda r: r.get("similarity", 0), reverse=True)
            return combined[:top_k]
        else:
            raise ValueError(f"Invalid store: {store}. Must be 'items', 'sections', or 'both'")

    def get_by_id(self, item_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve item or section by ID.

        Args:
            item_id: Item or section ID

        Returns:
            Result dict or None if not found
        """
        # Try item collection first
        try:
            result = self.item_collection.get(ids=[item_id])
            if result["ids"]:
                return {
                    "id": result["ids"][0],
                    "text": result["documents"][0],
                    "metadata": result["metadatas"][0],
                    "type": "item",
                }
        except Exception:
            pass

        # Try section collection
        try:
            result = self.section_collection.get(ids=[item_id])
            if result["ids"]:
                return {
                    "id": result["ids"][0],
                    "text": result["documents"][0],
                    "metadata": result["metadatas"][0],
                    "type": "section",
                }
        except Exception:
            pass

        return None

    def delete_document(self, document_id: str) -> None:
        """Remove all items and sections for a document from both stores."""
        try:
            self.item_collection.delete(where={"document_id": document_id})
        except Exception:
            pass
        try:
            self.section_collection.delete(where={"document_id": document_id})
        except Exception:
            pass
        logger.info(f"[Phase6] Deleted document {document_id} from dual stores")

    def get_document_chunks(self, document_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve ALL item chunks belonging to a specific document.

        Args:
            document_id: The document identifier to fetch chunks for

        Returns:
            List of result dicts with keys: id, text, metadata, type
        """
        try:
            # Try "document_id" first (Phase 6 native), then "doc_id" (migrated)
            result = self.item_collection.get(
                where={"document_id": document_id},
                include=["documents", "metadatas"],
            )
            if not result["ids"]:
                result = self.item_collection.get(
                    where={"doc_id": document_id},
                    include=["documents", "metadatas"],
                )
            chunks: list[dict[str, Any]] = []
            if result["ids"]:
                for i in range(len(result["ids"])):
                    chunks.append({
                        "id": result["ids"][i],
                        "text": result["documents"][i],
                        "metadata": result["metadatas"][i],
                        "type": "item",
                    })
            return chunks
        except Exception as e:
            logger.warning(f"[Phase6] get_document_chunks failed for {document_id}: {e}")
            return []

    def reset(self) -> None:
        """Delete and re-create both collections."""
        self.client.delete_collection("kts_phase6_items")
        self.client.delete_collection("kts_phase6_sections")
        self.item_collection = self.client.get_or_create_collection(
            name="kts_phase6_items",
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"},
        )
        self.section_collection = self.client.get_or_create_collection(
            name="kts_phase6_sections",
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("[Phase6] Dual stores reset")

    # ─────────────────────────────────────────────────────────────
    # Phase 8.2 — MMR Diversity Sampling
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def mmr_select(
        query_embedding: list[float],
        candidate_embeddings: list[list[float]],
        candidate_results: list[dict],
        top_k: int = 10,
        lambda_mult: float = 0.7,
    ) -> list[dict]:
        """Maximal Marginal Relevance greedy selection.

        ``lambda_mult`` controls the trade-off:
        *  ``1.0`` → pure relevance (same as vanilla top-k)
        *  ``0.0`` → pure diversity (max dissimilarity to already-selected)

        Returns up to *top_k* results with new ``_mmr_score`` field.
        """
        import numpy as np

        if not candidate_results:
            return []

        q = np.asarray(query_embedding, dtype=np.float32)
        C = np.asarray(candidate_embeddings, dtype=np.float32)

        # Cosine similarity  (safe against zero-norm vectors)
        def _cos_sim(a: np.ndarray, b: np.ndarray) -> float:
            na, nb = np.linalg.norm(a), np.linalg.norm(b)
            if na == 0 or nb == 0:
                return 0.0
            return float(np.dot(a, b) / (na * nb))

        q_sims = [_cos_sim(q, C[i]) for i in range(len(C))]

        selected_idx: list[int] = []
        remaining = set(range(len(C)))

        for _ in range(min(top_k, len(C))):
            best_idx = -1
            best_score = -float("inf")

            for idx in remaining:
                relevance = q_sims[idx]

                # Max similarity to already-selected
                if selected_idx:
                    max_sim_to_selected = max(
                        _cos_sim(C[idx], C[s]) for s in selected_idx
                    )
                else:
                    max_sim_to_selected = 0.0

                mmr_score = lambda_mult * relevance - (1 - lambda_mult) * max_sim_to_selected

                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = idx

            if best_idx < 0:
                break
            selected_idx.append(best_idx)
            remaining.discard(best_idx)

        results: list[dict] = []
        for idx in selected_idx:
            r = dict(candidate_results[idx])
            r["_mmr_score"] = q_sims[idx]
            results.append(r)
        return results

    def search_items_mmr(
        self,
        query: str,
        top_k: int = 10,
        fetch_multiplier: int = 3,
        lambda_mult: float = 0.7,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Item search with MMR diversity re-ranking."""
        fetch_k = top_k * fetch_multiplier
        try:
            q_emb = self.embed_query(query)
            result = self.item_collection.query(
                query_embeddings=[q_emb],
                n_results=min(fetch_k, self.item_collection.count() or 1),
                include=["documents", "metadatas", "distances", "embeddings"],
                where=filters if filters else None,
            )
            if not result["ids"] or not result["ids"][0]:
                return []

            candidates: list[dict] = []
            embeddings: list[list[float]] = []
            for i in range(len(result["ids"][0])):
                candidates.append({
                    "id": result["ids"][0][i],
                    "text": result["documents"][0][i],
                    "similarity": 1.0 - result["distances"][0][i],
                    "metadata": result["metadatas"][0][i],
                    "type": "item",
                })
                embeddings.append(result["embeddings"][0][i])

            return self.mmr_select(q_emb, embeddings, candidates, top_k, lambda_mult)

        except Exception as exc:
            logger.warning("[Phase8] search_items_mmr fallback to vanilla: %s", exc)
            return self.search_items(query, top_k=top_k, filters=filters)

    def search_sections_mmr(
        self,
        query: str,
        top_k: int = 5,
        fetch_multiplier: int = 3,
        lambda_mult: float = 0.7,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Section search with MMR diversity re-ranking."""
        fetch_k = top_k * fetch_multiplier
        try:
            q_emb = self.embed_query(query)
            result = self.section_collection.query(
                query_embeddings=[q_emb],
                n_results=min(fetch_k, self.section_collection.count() or 1),
                include=["documents", "metadatas", "distances", "embeddings"],
                where=filters if filters else None,
            )
            if not result["ids"] or not result["ids"][0]:
                return []

            candidates: list[dict] = []
            embeddings: list[list[float]] = []
            for i in range(len(result["ids"][0])):
                candidates.append({
                    "id": result["ids"][0][i],
                    "text": result["documents"][0][i],
                    "similarity": 1.0 - result["distances"][0][i],
                    "metadata": result["metadatas"][0][i],
                    "type": "section",
                })
                embeddings.append(result["embeddings"][0][i])

            return self.mmr_select(q_emb, embeddings, candidates, top_k, lambda_mult)

        except Exception as exc:
            logger.warning("[Phase8] search_sections_mmr fallback to vanilla: %s", exc)
            return self.search_sections(query, top_k=top_k, filters=filters)

    # ─────────────────────────────────────────────────────────────
    # Phase 8.4 — Parent-Child Expansion helpers
    # ─────────────────────────────────────────────────────────────

    def get_items_by_parent(
        self,
        parent_section_id: str,
    ) -> List[Dict[str, Any]]:
        """Retrieve all items whose metadata contains the given parent_section_id."""
        try:
            result = self.item_collection.get(
                where={"parent_section_id": parent_section_id},
                include=["documents", "metadatas"],
            )
            items: list[dict] = []
            if result["ids"]:
                for i in range(len(result["ids"])):
                    items.append({
                        "id": result["ids"][i],
                        "text": result["documents"][i],
                        "metadata": result["metadatas"][i],
                        "type": "item",
                    })
            return items
        except Exception as exc:
            logger.warning("[Phase8] get_items_by_parent failed: %s", exc)
            return []

    def get_section_by_id(self, section_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single section by its ID."""
        try:
            result = self.section_collection.get(
                ids=[section_id],
                include=["documents", "metadatas"],
            )
            if result["ids"]:
                return {
                    "id": result["ids"][0],
                    "text": result["documents"][0],
                    "metadata": result["metadatas"][0],
                    "type": "section",
                }
            return None
        except Exception:
            return None

    # ─────────────────────────────────────────────────────────────
    # Phase 8.5 — HyPE (item_questions collection)
    # ─────────────────────────────────────────────────────────────

    def _get_questions_collection(self):
        """Lazy-create the ``kts_phase6_item_questions`` collection."""
        if not hasattr(self, "_questions_collection"):
            self._questions_collection = self.client.get_or_create_collection(
                name="kts_phase6_item_questions",
                embedding_function=self.ef,
                metadata={"hnsw:space": "cosine"},
            )
        return self._questions_collection

    def store_item_questions(
        self,
        chunk_id: str,
        questions: List[str],
    ) -> None:
        """Store generated hypothetical questions linked to *chunk_id*.

        Replaces any existing questions for *chunk_id* (idempotent).
        """
        coll = self._get_questions_collection()

        # Delete old questions for this chunk
        try:
            old = coll.get(where={"source_chunk_id": chunk_id})
            if old["ids"]:
                coll.delete(ids=old["ids"])
        except Exception:
            pass

        ids = [f"{chunk_id}_q{i}" for i in range(len(questions))]
        metas = [{"source_chunk_id": chunk_id, "question_index": i} for i in range(len(questions))]
        coll.add(ids=ids, documents=questions, metadatas=metas)

    def search_item_questions(
        self,
        query: str,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search the HyPE ``item_questions`` collection."""
        coll = self._get_questions_collection()
        if coll.count() == 0:
            return []
        try:
            result = coll.query(
                query_texts=[query],
                n_results=min(top_k, coll.count()),
                include=["documents", "metadatas", "distances"],
            )
            if not result["ids"] or not result["ids"][0]:
                return []

            results: list[dict] = []
            for i in range(len(result["ids"][0])):
                results.append({
                    "id": result["ids"][0][i],
                    "text": result["documents"][0][i],
                    "similarity": 1.0 - result["distances"][0][i],
                    "metadata": result["metadatas"][0][i],
                    "type": "question",
                })
            return results
        except Exception as exc:
            logger.warning("[Phase8] search_item_questions failed: %s", exc)
            return []

    def mark_questions_pending(self, chunk_id: str) -> None:
        """Flag a chunk as needing HyPE question enrichment (re-try later)."""
        try:
            self.item_collection.update(
                ids=[chunk_id],
                metadatas=[{"questions_pending": True}],
            )
        except Exception:
            pass

    def get_item_metadata(self, chunk_id: str) -> dict:
        """Return metadata dict for a single item."""
        try:
            result = self.item_collection.get(ids=[chunk_id], include=["metadatas"])
            if result["metadatas"]:
                return result["metadatas"][0]
        except Exception:
            pass
        return {}
