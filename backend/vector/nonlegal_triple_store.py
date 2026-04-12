"""Phase 19.2 — Non-Legal Triple-Store Orchestrator.

Manages three completely separate ChromaDB collections for non-legal
(GENERIC_GUIDE) documents:

1. **Error-Boundary Store**    — one chunk per error entry
2. **Sentence Store**          — fine-grained 1-3 sentence chunks + parents
3. **Structure Store**         — heading-boundary chunks with breadcrumbs

At query time the orchestrator fans out to all three collections,
merges results, deduplicates by content similarity, and returns a
unified ranked list.

This class mirrors the API of ``DualVectorStore`` so the retrieval
service can use either interchangeably based on document regime.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import chromadb
from chromadb.config import Settings

from backend.common.models import TextChunk
from backend.vector.error_boundary_chunker import chunk_by_error_boundaries
from backend.vector.sentence_chunker import chunk_by_sentences
from backend.vector.structure_chunker import chunk_by_structure

if TYPE_CHECKING:
    from backend.vector.embedding_provider import EmbeddingProvider

logger = logging.getLogger(__name__)

# ── Collection names ────────────────────────────────────────────
COLL_ERROR_BOUNDARY = "kts_nonlegal_error_boundary"
COLL_SENTENCE       = "kts_nonlegal_sentences"
COLL_SENTENCE_PARENT = "kts_nonlegal_sentence_parents"
COLL_STRUCTURE      = "kts_nonlegal_structure"


class NonLegalTripleStore:
    """Triple vector store for non-legal / GENERIC_GUIDE documents.

    Provides the same external interface as ``DualVectorStore`` so the
    retrieval pipeline can use it as a drop-in replacement when the
    document regime is GENERIC_GUIDE.

    Parameters
    ----------
    persist_dir : str
        ChromaDB persistence directory (typically ``<scope>/chromadb``).
    embedding_provider : EmbeddingProvider | None
        Shared embedding provider (BGE ONNX INT8).
    """

    INDEX_META_FILE = "_kts_nonlegal_index_meta.json"

    def __init__(
        self,
        persist_dir: str,
        embedding_provider: Optional["EmbeddingProvider"] = None,
    ) -> None:
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._embedding_provider = embedding_provider

        # Resolve embedding function
        if embedding_provider is not None:
            from backend.vector.embedding_provider import ChromaEmbeddingAdapter
            self.ef = ChromaEmbeddingAdapter(embedding_provider)
            logger.info(
                f"[Phase19] NonLegalTripleStore using provider: "
                f"{embedding_provider.provider_id}"
            )
        else:
            from chromadb.utils import embedding_functions
            logger.warning(
                "[Phase19] NonLegalTripleStore: no provider — legacy fallback"
            )
            self.ef = embedding_functions.DefaultEmbeddingFunction()

        os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

        abs_path = str(self.persist_dir.resolve())
        self.client = chromadb.PersistentClient(
            path=abs_path,
            settings=Settings(anonymized_telemetry=False),
        )

        # ── Three primary collections ────────────────────────────
        self.error_boundary_col = self.client.get_or_create_collection(
            name=COLL_ERROR_BOUNDARY,
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"},
        )
        self.sentence_col = self.client.get_or_create_collection(
            name=COLL_SENTENCE,
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"},
        )
        self.sentence_parent_col = self.client.get_or_create_collection(
            name=COLL_SENTENCE_PARENT,
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"},
        )
        self.structure_col = self.client.get_or_create_collection(
            name=COLL_STRUCTURE,
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"},
        )

        logger.info(
            f"[Phase19] NonLegalTripleStore initialised: {persist_dir} "
            f"(errb={self.error_boundary_col.count()}, sent={self.sentence_col.count()}, "
            f"struct={self.structure_col.count()})"
        )
        self._write_index_metadata()

    # ── Index metadata ────────────────────────────────────────────

    def _write_index_metadata(self) -> None:
        meta_path = self.persist_dir / self.INDEX_META_FILE
        if self._embedding_provider:
            meta = {
                "provider_id": self._embedding_provider.provider_id,
                "dims": self._embedding_provider.dims,
                "model_hash": self._embedding_provider.model_hash,
                "store_type": "nonlegal_triple",
                "collections": [
                    COLL_ERROR_BOUNDARY,
                    COLL_SENTENCE,
                    COLL_SENTENCE_PARENT,
                    COLL_STRUCTURE,
                ],
            }
        else:
            meta = {
                "provider_id": "legacy_chroma_default",
                "dims": 384,
                "model_hash": "chromadb-default",
                "store_type": "nonlegal_triple",
            }
        try:
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to write NonLegal index metadata: {e}")

    def embed_query(self, text: str) -> List[float]:
        """Embed a query using the configured provider."""
        if self._embedding_provider:
            return self._embedding_provider.embed_query(text)
        embeddings = self.ef([text])
        return embeddings[0]

    # ── Ingestion ─────────────────────────────────────────────────

    def add_document(
        self,
        doc_id: str,
        source_path: str,
        text: str,
        *,
        error_boundary: bool = True,
        sentence: bool = True,
        structure: bool = True,
    ) -> Dict[str, int]:
        """Chunk a document with all three strategies and upsert.

        Parameters
        ----------
        doc_id : str
            Document identifier.
        source_path : str
            Source file path.
        text : str
            Full document text.
        error_boundary / sentence / structure : bool
            Toggle individual chunking strategies.

        Returns
        -------
        dict
            Counts: ``{"error_boundary": N, "sentence": N, "structure": N}``
        """
        counts: Dict[str, int] = {
            "error_boundary": 0,
            "sentence": 0,
            "sentence_parents": 0,
            "structure": 0,
        }

        if error_boundary:
            chunks = chunk_by_error_boundaries(doc_id, source_path, text)
            self._upsert_chunks(self.error_boundary_col, chunks)
            counts["error_boundary"] = len(chunks)

        if sentence:
            child_chunks, parent_records = chunk_by_sentences(
                doc_id, source_path, text,
            )
            self._upsert_chunks(self.sentence_col, child_chunks)
            self._upsert_parent_records(parent_records)
            counts["sentence"] = len(child_chunks)
            counts["sentence_parents"] = len(parent_records)

        if structure:
            chunks = chunk_by_structure(doc_id, source_path, text)
            self._upsert_chunks(self.structure_col, chunks)
            counts["structure"] = len(chunks)

        logger.info(
            f"[Phase19] add_document {doc_id}: errb={counts['error_boundary']}, "
            f"sent={counts['sentence']}(+{counts['sentence_parents']} parents), "
            f"struct={counts['structure']}"
        )
        return counts

    def _upsert_chunks(
        self,
        collection,
        chunks: List[TextChunk],
    ) -> None:
        """Upsert TextChunks into a ChromaDB collection."""
        if not chunks:
            return
        ids = [c.chunk_id for c in chunks]
        documents = [c.content for c in chunks]
        metadatas = []
        for c in chunks:
            meta: Dict[str, Any] = {
                "doc_id": c.doc_id,
                "source_path": c.source_path,
                "chunk_index": c.chunk_index,
                "doc_type": c.doc_type,
            }
            if c.entities:
                meta["entities"] = json.dumps(c.entities)
            if c.keyphrases:
                meta["keyphrases"] = json.dumps(c.keyphrases)
            metadatas.append(meta)

        batch_size = 500
        for start in range(0, len(ids), batch_size):
            end = start + batch_size
            collection.upsert(
                ids=ids[start:end],
                documents=documents[start:end],
                metadatas=metadatas[start:end],
            )

    def _upsert_parent_records(self, parents: List[Dict[str, Any]]) -> None:
        """Upsert parent context records from sentence chunker."""
        if not parents:
            return
        ids = [p["parent_id"] for p in parents]
        documents = [p.get("content") or p.get("text", "") for p in parents]
        metadatas = [
            {
                "doc_id": p["doc_id"],
                "source_path": p["source_path"],
                "child_ids": json.dumps(p.get("child_ids", [])),
            }
            for p in parents
        ]
        batch_size = 500
        for start in range(0, len(ids), batch_size):
            end = start + batch_size
            self.sentence_parent_col.upsert(
                ids=ids[start:end],
                documents=documents[start:end],
                metadatas=metadatas[start:end],
            )

    # ── Retrieval ─────────────────────────────────────────────────

    def search(
        self,
        query: str,
        store: str = "all",
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Unified search — fan-out to selected stores, merge, deduplicate.

        Parameters
        ----------
        query : str
            Search query.
        store : str
            ``"all"`` (default), ``"error_boundary"``, ``"sentence"``,
            ``"structure"``, or comma-separated combination.
        top_k : int
            Maximum results.
        filters : dict | None
            Optional metadata filters.

        Returns
        -------
        List[Dict[str, Any]]
            Ranked results with keys: id, text, similarity, metadata, type, store.
        """
        stores_to_query = self._resolve_stores(store)
        all_results: List[Dict[str, Any]] = []

        for store_name, collection in stores_to_query:
            results = self._query_collection(
                collection, query, top_k, filters, store_name,
            )
            all_results.extend(results)

        # Sort by similarity descending
        all_results.sort(key=lambda r: r.get("similarity", 0), reverse=True)

        # Deduplicate near-identical content
        deduped = self._deduplicate(all_results)

        return deduped[:top_k]

    def search_with_parent_expansion(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search sentence store and expand hits to parent context.

        Returns sentence-level hits with an additional ``parent_text``
        field containing the surrounding context window.
        """
        hits = self._query_collection(
            self.sentence_col, query, top_k, filters, "sentence",
        )
        for hit in hits:
            parent_id = hit["id"].replace("_sent_", "_sent_parent_")
            # Extract just the numeric suffix
            try:
                idx = int(hit["id"].rsplit("_", 1)[-1])
                parent_id = f"{hit['metadata'].get('doc_id', '')}_sent_parent_{idx:04d}"
            except (ValueError, IndexError):
                pass
            try:
                parent_result = self.sentence_parent_col.get(
                    ids=[parent_id],
                    include=["documents"],
                )
                if parent_result["ids"]:
                    hit["parent_text"] = parent_result["documents"][0]
            except Exception:
                pass
        return hits

    def _resolve_stores(
        self, store: str
    ) -> List[tuple]:
        """Resolve store selector to (name, collection) pairs."""
        mapping = {
            "error_boundary": ("error_boundary", self.error_boundary_col),
            "sentence": ("sentence", self.sentence_col),
            "structure": ("structure", self.structure_col),
        }
        if store == "all":
            return list(mapping.values())

        selected = []
        for s in store.split(","):
            s = s.strip()
            if s in mapping:
                selected.append(mapping[s])
        return selected or list(mapping.values())

    def _query_collection(
        self,
        collection,
        query: str,
        top_k: int,
        filters: Optional[Dict[str, Any]],
        store_name: str,
    ) -> List[Dict[str, Any]]:
        """Query a single ChromaDB collection."""
        where_arg = filters if filters else None
        try:
            results = collection.query(
                query_texts=[query],
                n_results=min(top_k, collection.count() or top_k),
                where=where_arg,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.warning(f"[Phase19] query failed on {store_name}: {e}")
            return []

        formatted: List[Dict[str, Any]] = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                dist = results["distances"][0][i]
                score = 1.0 - dist  # cosine distance → similarity
                formatted.append({
                    "id": results["ids"][0][i],
                    "text": results["documents"][0][i],
                    "similarity": score,
                    "metadata": results["metadatas"][0][i],
                    "type": "chunk",
                    "store": store_name,
                })
        return formatted

    @staticmethod
    def _deduplicate(
        results: List[Dict[str, Any]],
        overlap_ratio: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """Remove near-duplicate results based on token overlap.

        Uses a fast word-set Jaccard check rather than embedding distance
        so we don't need extra compute.
        """
        if not results:
            return results

        kept: List[Dict[str, Any]] = []
        kept_token_sets: List[set] = []

        for r in results:
            tokens = set(r.get("text", "").lower().split())
            if not tokens:
                continue
            is_dup = False
            for existing in kept_token_sets:
                intersection = tokens & existing
                union = tokens | existing
                if union and len(intersection) / len(union) >= overlap_ratio:
                    is_dup = True
                    break
            if not is_dup:
                kept.append(r)
                kept_token_sets.append(tokens)

        return kept

    # ── Document management ───────────────────────────────────────

    def delete_document(self, document_id: str) -> None:
        """Remove all chunks for a document from all stores."""
        for col_name, col in [
            ("error_boundary", self.error_boundary_col),
            ("sentence", self.sentence_col),
            ("sentence_parent", self.sentence_parent_col),
            ("structure", self.structure_col),
        ]:
            try:
                col.delete(where={"doc_id": document_id})
            except Exception:
                pass
        logger.info(f"[Phase19] Deleted document {document_id} from triple stores")

    def get_document_chunks(self, document_id: str) -> List[Dict[str, Any]]:
        """Retrieve all chunks for a document across all stores."""
        all_chunks: List[Dict[str, Any]] = []
        for col_name, col in [
            ("error_boundary", self.error_boundary_col),
            ("sentence", self.sentence_col),
            ("structure", self.structure_col),
        ]:
            try:
                result = col.get(
                    where={"doc_id": document_id},
                    include=["documents", "metadatas"],
                )
                if result["ids"]:
                    for i in range(len(result["ids"])):
                        all_chunks.append({
                            "id": result["ids"][i],
                            "text": result["documents"][i],
                            "metadata": result["metadatas"][i],
                            "type": "chunk",
                            "store": col_name,
                        })
            except Exception as e:
                logger.warning(
                    f"[Phase19] get_document_chunks({document_id}) "
                    f"failed on {col_name}: {e}"
                )
        return all_chunks

    def reset(self) -> None:
        """Delete and re-create all collections."""
        for name in [
            COLL_ERROR_BOUNDARY, COLL_SENTENCE,
            COLL_SENTENCE_PARENT, COLL_STRUCTURE,
        ]:
            try:
                self.client.delete_collection(name)
            except Exception:
                pass

        self.error_boundary_col = self.client.get_or_create_collection(
            name=COLL_ERROR_BOUNDARY,
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"},
        )
        self.sentence_col = self.client.get_or_create_collection(
            name=COLL_SENTENCE,
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"},
        )
        self.sentence_parent_col = self.client.get_or_create_collection(
            name=COLL_SENTENCE_PARENT,
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"},
        )
        self.structure_col = self.client.get_or_create_collection(
            name=COLL_STRUCTURE,
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("[Phase19] NonLegalTripleStore reset complete")

    def count(self) -> Dict[str, int]:
        """Return chunk counts per collection."""
        return {
            "error_boundary": self.error_boundary_col.count(),
            "sentence": self.sentence_col.count(),
            "sentence_parent": self.sentence_parent_col.count(),
            "structure": self.structure_col.count(),
        }
