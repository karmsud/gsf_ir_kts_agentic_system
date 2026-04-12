"""
Embedder adapter — bridges PayGen embedding calls to KTS EmbeddingProvider.

Phase 22 replacement for Phase 21 stub.
Preserves PayGen's function signatures for backward compatibility while
delegating to KTS's production-grade embedding infrastructure.

KTS APIs used:
    get_embedding_provider(config) → EmbeddingProvider (BGE ONNX INT8, 768-dim)
    LegalChunker(max_chunk_size=...) → heading-aware legal-doc chunker
    DualVectorStore(persist_dir, provider) → ChromaDB dual-collection store

Ported from PayGen pipeline.skills.embedder → backend.abs.skills
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any, Optional

from backend.abs.config.constants import (
    CHUNK_MAX_CHARS,
    CHUNK_OVERLAP,
)

logger = logging.getLogger(__name__)

# ── Lazy KTS infrastructure imports (graceful degradation) ────────

try:
    from backend.vector.embedding_provider import get_embedding_provider
    _HAS_EMBEDDING = True
except ImportError:
    _HAS_EMBEDDING = False
    logger.warning("KTS EmbeddingProvider unavailable — embed() will fail")

try:
    from backend.vector.legal_chunker import LegalChunker as _KTSLegalChunker
    _HAS_LEGAL_CHUNKER = True
except ImportError:
    _HAS_LEGAL_CHUNKER = False

try:
    from backend.vector.dual_vector_store import DualVectorStore
    _HAS_DUAL_STORE = True
except ImportError:
    _HAS_DUAL_STORE = False
    logger.warning("KTS DualVectorStore unavailable — embed_and_store() will fail")


# ── Singleton provider cache ──────────────────────────────────────
_provider = None


def _get_provider(config):
    """Lazy-init singleton embedding provider."""
    global _provider
    if _provider is None:
        if not _HAS_EMBEDDING:
            raise RuntimeError(
                "KTS EmbeddingProvider not available. "
                "Ensure backend.vector.embedding_provider is importable."
            )
        logger.info("Initializing EmbeddingProvider for ABS domain")
        _provider = get_embedding_provider(config)
    return _provider


def reset_provider() -> None:
    """Reset cached provider (for testing)."""
    global _provider
    _provider = None


# ── Public API ────────────────────────────────────────────────────


def chunk_text(
    text: str,
    max_chars: int = CHUNK_MAX_CHARS,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Split text into chunks.

    When KTS's LegalChunker is available, uses heading-aware legal-doc
    splitting.  Falls back to simple sentence-boundary splitting.

    Args:
        text: Input text to chunk.
        max_chars: Maximum characters per chunk (default from constants).
        overlap: Character overlap between chunks (default from constants).

    Returns:
        List of text chunks.
    """
    if not text or not text.strip():
        return []

    # Try KTS LegalChunker (heading-aware, superior for legal docs)
    if _HAS_LEGAL_CHUNKER:
        try:
            chunker = _KTSLegalChunker(
                min_chunk_size=max(200, overlap),
                max_chunk_size=max_chars,
                target_chunk_size=max_chars // 2,
            )
            sections = chunker.extract_sections(text)
            if sections:
                return [s.content for s in sections if s.content.strip()]
        except Exception as exc:
            logger.debug(f"LegalChunker failed, falling back to regex: {exc}")

    # Fallback: simple sentence-boundary splitting (original PayGen logic)
    return _regex_chunk(text, max_chars, overlap)


def _regex_chunk(text: str, max_chars: int, overlap: int) -> list[str]:
    """Simple regex-based sentence-boundary chunking (PayGen original)."""
    sentence_pattern = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')
    sentences = sentence_pattern.split(text.strip())

    if not sentences:
        return [text.strip()] if text.strip() else []

    chunks: list[str] = []
    current_chunk = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if current_chunk and len(current_chunk) + len(sentence) + 1 > max_chars:
            chunks.append(current_chunk.strip())
            if overlap > 0 and len(current_chunk) > overlap:
                current_chunk = current_chunk[-overlap:] + " " + sentence
            else:
                current_chunk = sentence
        else:
            current_chunk = (current_chunk + " " + sentence).strip() if current_chunk else sentence

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def embed(
    texts: list[str],
    config=None,
    model_name: str | None = None,
) -> list[list[float]]:
    """Embed texts using KTS's BGE ONNX INT8 provider.

    Args:
        texts: List of text strings to embed.
        config: KTSConfig instance. If None, uses default config.
        model_name: Ignored (kept for backward compat).

    Returns:
        List of 768-dimensional embedding vectors.
    """
    if not texts:
        return []

    if config is None:
        from config.settings import load_config
        config = load_config()

    provider = _get_provider(config)
    return provider.embed_documents(texts)


def embed_query(query: str, config=None) -> list[float]:
    """Embed a single query string.

    Uses the same provider but may apply different preprocessing
    for queries vs documents in the future.
    """
    if config is None:
        from config.settings import load_config
        config = load_config()

    provider = _get_provider(config)
    return provider.embed_query(query)


def embed_and_store(
    texts: list[str],
    metadatas: list[dict],
    collection_name: str,
    config=None,
    *,
    # Legacy signature compat
    text: str | None = None,
    chroma_path: Path | None = None,
    section_type: str = "",
    deal_id: str = "",
    source_file: str = "",
    model_name: str | None = None,
) -> int:
    """Embed texts and store in KTS DualVectorStore.

    Args:
        texts: Text content to embed and store.
        metadatas: Metadata dictionaries for each text.
        collection_name: Collection identifier (use ``abs_`` prefix).
        config: KTSConfig instance.

    Returns:
        Number of items stored.
    """
    # Handle legacy single-text call pattern
    if text is not None and not texts:
        texts_list = chunk_text(text)
        metadatas = [
            {"section_type": section_type, "deal_id": deal_id, "source_file": source_file}
            for _ in texts_list
        ]
        texts = texts_list

    if not texts:
        return 0

    if len(texts) != len(metadatas):
        raise ValueError(
            f"texts ({len(texts)}) and metadatas ({len(metadatas)}) must have same length"
        )

    if config is None:
        from config.settings import load_config
        config = load_config()

    if not _HAS_DUAL_STORE:
        raise RuntimeError(
            "KTS DualVectorStore not available. "
            "Ensure backend.vector.dual_vector_store is importable."
        )

    provider = _get_provider(config)
    persist_dir = getattr(config, "chroma_persist_dir", str(Path.cwd() / "chroma_db"))

    store = DualVectorStore(persist_dir, embedding_provider=provider)

    # Build item dicts for DualVectorStore.add_items()
    items = []
    for i, (txt, meta) in enumerate(zip(texts, metadatas)):
        item_id = hashlib.sha256(f"{collection_name}:{i}:{txt[:100]}".encode()).hexdigest()[:16]
        items.append({"id": item_id, "text": txt, "metadata": meta})

    store.add_items(items)

    logger.info(f"Stored {len(items)} items via DualVectorStore (collection context: '{collection_name}')")
    return len(items)
