"""
Stage 4: Knowledge Store Build — Chroma + NetworkX from deal data.

Builds vector store (Chroma) and knowledge graph (NetworkX) from
sections and structured extractions. Both stores are per-deal isolated.

Ported from PayGen pipeline.ingestion.knowledge_store → backend.abs.ingestion
Import rewrites:
  pipeline.embeddings.provider → graceful degradation (Phase 22 stub)
  pipeline.skills.embedder     → backend.abs.skills.embedder
  pipeline.config.pipeline_config → backend.abs.config.pipeline_config
  pipeline.skills.graph_builder   → backend.abs.skills.graph_builder
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# pipeline.embeddings.provider is NOT ported (Phase 22 dependency).
# Graceful degradation: stub functions used when unavailable.
try:
    from backend.abs.embeddings.provider import (
        resolve_vectorstore_runtime_dir,
        write_vectorstore_manifest,
    )
    _EMBEDDINGS_PROVIDER_AVAILABLE = True
except ImportError:
    _EMBEDDINGS_PROVIDER_AVAILABLE = False

    def resolve_vectorstore_runtime_dir(base_dir: Path) -> Path:
        """Stub: return base_dir / 'default' when provider unavailable."""
        runtime = Path(base_dir) / "default"
        runtime.mkdir(parents=True, exist_ok=True)
        return runtime

    def write_vectorstore_manifest(runtime_dir: Path) -> None:
        """Stub: no-op when provider unavailable."""
        pass

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeStoreResult:
    """Result of knowledge store construction."""
    vector_count: int
    graph_node_count: int
    graph_edge_count: int
    collection_name: str
    graph_path: Path
    chroma_path: Path
    embedded_sections: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "vector_count": self.vector_count,
            "graph_node_count": self.graph_node_count,
            "graph_edge_count": self.graph_edge_count,
            "collection_name": self.collection_name,
            "graph_path": str(self.graph_path),
            "chroma_path": str(self.chroma_path),
            "embedded_sections": self.embedded_sections,
            "errors": self.errors,
        }


def build_knowledge_store(
    sections_dir: Path,
    extractions_dir: Path,
    vectorstore_dir: Path,
    graph_dir: Path,
    deal_id: str,
    collection_name: Optional[str] = None,
) -> KnowledgeStoreResult:
    """
    Build both vector store and knowledge graph from deal data.

    Vector store:
    - Embeds section markdowns (chunked at ~1000 chars)
    - Embeds each definition as standalone chunk
    - Embeds each waterfall rule as standalone chunk
    - Per-deal Chroma collection

    Knowledge graph:
    - Nodes: definitions, waterfall rules, accounts, triggers, classes
    - Edges: references, dependencies, payments
    - Saved as JSON (primary) + pickle (optional)

    Args:
        sections_dir: Directory containing section .md files
        extractions_dir: Directory containing extraction .json files
        vectorstore_dir: Directory for Chroma persistent storage
        graph_dir: Directory for graph output
        deal_id: Deal identifier
        collection_name: Optional Chroma collection name (defaults to deal_id)

    Returns:
        KnowledgeStoreResult with statistics
    """
    sections_dir = Path(sections_dir)
    extractions_dir = Path(extractions_dir)
    vectorstore_dir = Path(vectorstore_dir)
    graph_dir = Path(graph_dir)

    vectorstore_dir.mkdir(parents=True, exist_ok=True)
    graph_dir.mkdir(parents=True, exist_ok=True)

    if collection_name is None:
        collection_name = deal_id.replace("-", "_").replace(" ", "_")
        if len(collection_name) < 3:
            collection_name += "_deal"

    runtime_vector_dir = resolve_vectorstore_runtime_dir(vectorstore_dir)

    result = KnowledgeStoreResult(
        vector_count=0,
        graph_node_count=0,
        graph_edge_count=0,
        collection_name=collection_name,
        graph_path=graph_dir / "deal_graph.json",
        chroma_path=runtime_vector_dir,
    )

    # ── Build Vector Store ────────────────────────────────────
    vector_count = _build_vector_store(
        sections_dir=sections_dir,
        extractions_dir=extractions_dir,
        chroma_path=runtime_vector_dir,
        collection_name=collection_name,
        deal_id=deal_id,
        result=result,
    )
    result.vector_count = vector_count

    try:
        write_vectorstore_manifest(runtime_vector_dir)
    except Exception as e:
        logger.warning("Vectorstore manifest write failed: %s", e)
        result.errors.append(f"Manifest write failed: {e}")

    # ── Build Knowledge Graph ─────────────────────────────────
    graph = _build_knowledge_graph(
        extractions_dir=extractions_dir,
        graph_dir=graph_dir,
        deal_id=deal_id,
    )
    if graph is not None:
        result.graph_node_count = graph.number_of_nodes()
        result.graph_edge_count = graph.number_of_edges()

    return result


def _build_vector_store(
    sections_dir: Path,
    extractions_dir: Path,
    chroma_path: Path,
    collection_name: str,
    deal_id: str,
    result: KnowledgeStoreResult,
) -> int:
    """Build Chroma vector store from sections and extractions."""
    total_vectors = 0

    try:
        from backend.abs.skills.embedder import chunk_text, embed, upsert_to_chroma
    except ImportError as e:
        result.errors.append(f"Embedder unavailable: {e}")
        return 0

    from backend.abs.config.pipeline_config import get_config
    cfg = get_config()

    # Embed section markdowns
    for section_file in sorted(sections_dir.glob("*.md")):
        section_name = section_file.stem
        text = section_file.read_text(encoding="utf-8")
        if not text.strip():
            continue

        try:
            chunks = chunk_text(
                text,
                max_chars=cfg.vectorstore.chunk_max_chars,
                overlap=cfg.vectorstore.chunk_overlap,
            )
            if not chunks:
                continue

            embeddings = embed(chunks)
            metadata = [
                {
                    "deal_id": deal_id,
                    "section_type": section_name,
                    "source_file": section_file.name,
                    "chunk_index": i,
                    "source_document": deal_id,
                }
                for i in range(len(chunks))
            ]

            count = upsert_to_chroma(
                chunks=chunks,
                embeddings=embeddings,
                collection_name=collection_name,
                metadata=metadata,
                chroma_path=chroma_path,
            )
            total_vectors += count
            result.embedded_sections.append(section_name)

        except Exception as e:
            logger.error(f"Embedding failed for section '{section_name}': {e}")
            result.errors.append(f"Embedding failed for '{section_name}': {e}")

    # Embed individual definitions as standalone chunks
    defs_path = extractions_dir / "definitions.json"
    if defs_path.exists():
        try:
            defs = json.loads(defs_path.read_text(encoding="utf-8"))
            total_vectors += _embed_items(
                items=defs,
                text_fields=["term", "definition"],
                item_type="definition",
                collection_name=collection_name,
                chroma_path=chroma_path,
                deal_id=deal_id,
            )
        except Exception as e:
            result.errors.append(f"Definition embedding failed: {e}")

    # Embed waterfall rules as standalone chunks
    rules_path = extractions_dir / "waterfall_rules.json"
    if rules_path.exists():
        try:
            rules = json.loads(rules_path.read_text(encoding="utf-8"))
            total_vectors += _embed_items(
                items=rules,
                text_fields=["rule_id", "description"],
                item_type="waterfall_rule",
                collection_name=collection_name,
                chroma_path=chroma_path,
                deal_id=deal_id,
            )
        except Exception as e:
            result.errors.append(f"Waterfall rule embedding failed: {e}")

    return total_vectors


def _embed_items(
    items: list[dict],
    text_fields: list[str],
    item_type: str,
    collection_name: str,
    chroma_path: Path,
    deal_id: str,
) -> int:
    """Embed a list of extracted items as individual chunks."""
    from backend.abs.skills.embedder import embed, upsert_to_chroma

    if not items:
        return 0

    texts: list[str] = []
    metadata_list: list[dict] = []

    for i, item in enumerate(items):
        # Compose text from specified fields
        parts = []
        for fld in text_fields:
            val = item.get(fld, "")
            if val:
                parts.append(str(val))
        text = " — ".join(parts)
        if not text.strip():
            continue

        texts.append(text)
        metadata_list.append({
            "deal_id": deal_id,
            "section_type": item_type,
            "source_file": f"{item_type}_{i}",
            "chunk_index": i,
            "source_document": deal_id,
        })

    if not texts:
        return 0

    embeddings = embed(texts)
    return upsert_to_chroma(
        chunks=texts,
        embeddings=embeddings,
        collection_name=collection_name,
        metadata=metadata_list,
        chroma_path=chroma_path,
    )


def _build_knowledge_graph(
    extractions_dir: Path,
    graph_dir: Path,
    deal_id: str,
):
    """Build NetworkX knowledge graph from extractions."""
    from backend.abs.skills.graph_builder import build_graph, save_graph

    # Load all available extractions
    extractions: dict[str, list[dict]] = {}
    for json_file in sorted(extractions_dir.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                extractions[json_file.stem] = data
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to load extraction '{json_file.name}': {e}")

    if not extractions:
        logger.warning("No extractions found for graph building")
        return None

    # Build graph
    graph = build_graph(extractions=extractions, deal_id=deal_id)

    # Save graph
    graph_path = graph_dir / "deal_graph.json"
    save_graph(graph, graph_path)

    # Also save as pickle for fast loading
    try:
        import pickle
        pickle_path = graph_dir / "deal_graph.pickle"
        with open(pickle_path, "wb") as f:
            pickle.dump(graph, f)
    except Exception as e:
        logger.warning(f"Pickle save skipped: {e}")

    return graph
