"""
Embedding Provider Abstraction (Phase 5 WS-1)

Provides a clean interface for embedding operations, allowing:
- BGE ONNX INT8 (768-dim) as the primary provider
- Legacy ChromaDB DefaultEmbeddingFunction (MiniLM 384-dim) as fallback
- Future providers via the same interface

The provider abstraction handles model-specific concerns like:
- Query prefixes (BGE requires "Represent this sentence: " prefix)
- Batch processing for document embedding
- Model hash tracking for index compatibility
"""
from __future__ import annotations

import logging
import os
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from config.settings import KTSConfig

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    """Abstract embedding provider for KTS vector operations."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique string identifying this provider, e.g. 'bge_onnx_int8'."""

    @property
    @abstractmethod
    def dims(self) -> int:
        """Dimensionality of output vectors."""

    @property
    @abstractmethod
    def model_hash(self) -> str:
        """SHA-256 prefix of the model for index compatibility checks."""

    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of document chunks. No prefix added."""

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """Embed a single query string. Provider may add model-specific prefix."""

    def as_chroma_ef(self) -> "ChromaEmbeddingAdapter":
        """Return a ChromaDB-compatible EmbeddingFunction wrapper."""
        return ChromaEmbeddingAdapter(self)


class ChromaEmbeddingAdapter:
    """Adapts EmbeddingProvider to chromadb.api.types.EmbeddingFunction.
    
    ChromaDB calls __call__(input: List[str]) for both document ingestion
    and query embedding. We route through embed_documents() here since
    ChromaDB doesn't distinguish between them. For queries, VectorStore
    will call embed_query() directly and pass pre-computed vectors.
    """

    def __init__(self, provider: EmbeddingProvider):
        self._provider = provider

    def __call__(self, input: List[str]) -> List[List[float]]:
        # ChromaDB < 0.4.15 calls this for everything
        return self._provider.embed_documents(input)

    def embed_query(self, input: List[str]) -> List[List[float]]:
        # ChromaDB 1.0+ calls this for queries
        # Note: input is a list of strings [query], return list of vectors
        # Our provider.embed_query takes a single string, so we map it
        return [self._provider.embed_query(t) for t in input]

    def embed_documents(self, input: List[str]) -> List[List[float]]:
        # ChromaDB 1.0+ calls this for documents
        return self._provider.embed_documents(input)

    def name(self) -> str:
        """Return provider ID for ChromaDB compatibility."""
        return self._provider.provider_id


class LegacyChromaProvider(EmbeddingProvider):
    """Wraps chromadb.utils.embedding_functions.DefaultEmbeddingFunction
    (ONNXMiniLM_L6_V2, 384-dim) for rollback to Phase 4 behavior."""

    def __init__(self):
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        self._ef = DefaultEmbeddingFunction()
        self._hash = "legacy:minilm_l6_v2"
        logger.info("LegacyChromaProvider initialized (MiniLM-L6-V2, 384-dim)")

    @property
    def provider_id(self) -> str:
        return "legacy_chroma_default"

    @property
    def dims(self) -> int:
        return 384

    @property
    def model_hash(self) -> str:
        return self._hash

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._ef(texts)

    def embed_query(self, text: str) -> List[float]:
        return self._ef([text])[0]


def _resolve_bge_model_path(config_path: Optional[str] = None) -> Optional[Path]:
    """Resolve path to BGE ONNX INT8 model artifacts.
    
    Priority:
    1. Environment variable KTS_BGE_MODEL_PATH
    2. config.embed_model_path (passed via config_path)
    3. PyInstaller bundle: _MEIPASS/models/bge-base-en-v1.5/onnx-int8
    4. Development: packaging/models/bge
    """
    # 1. Explicit env var
    env_path = os.environ.get("KTS_BGE_MODEL_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists() and (p / "model.onnx").exists():
            return p
        logger.warning(f"KTS_BGE_MODEL_PATH={env_path} does not contain model.onnx")

    # 2. Config-specified path
    if config_path:
        p = Path(config_path)
        if p.exists() and (p / "model.onnx").exists():
            return p
        logger.warning(f"embed_model_path={config_path} does not contain model.onnx")

    # 3. PyInstaller frozen bundle
    if getattr(sys, 'frozen', False):
        bundle_dir = Path(sys._MEIPASS)
        model_path = bundle_dir / 'models' / 'bge-base-en-v1.5' / 'onnx-int8'
        if (model_path / "model.onnx").exists():
            return model_path

    # 4. Development mode
    dev_paths = [
        Path(__file__).parent.parent.parent / 'packaging' / 'models' / 'bge' / 'bge-base-en-v1.5' / 'onnx-int8',
        Path(__file__).parent.parent.parent / 'packaging' / 'models' / 'bge' / 'bge-base-en-v1.5-onnx-int8',
        Path(__file__).parent.parent.parent / 'packaging' / 'models' / 'bge',
        Path(__file__).parent.parent.parent / 'packaging' / 'models' / 'bge' / 'bge-base-en-v1.5' / 'onnx',
        Path(__file__).parent.parent.parent / 'assets' / 'models' / 'bge-base-en-v1.5' / 'onnx-int8',
    ]
    for p in dev_paths:
        if p.exists() and (p / "model.onnx").exists():
            return p

    return None


def get_embedding_provider(config: Optional["KTSConfig"] = None) -> EmbeddingProvider:
    """Factory function to get the configured embedding provider.
    
    Uses config.embed_provider to determine which provider to use:
    - 'bge_onnx_int8': BGE base en v1.5, ONNX INT8 quantized (768-dim) [default]
    - 'legacy_chroma_default': MiniLM-L6-V2 via ChromaDB (384-dim) [deprecated]
    
    Environment variable KTS_EMBED_PROVIDER can override config setting.
    
    NOTE: As of Phase 5 WS-1, BGE ONNX INT8 is the ONLY supported embedding model
    in production builds. Legacy provider kept only for development/testing.
    """
    # Determine provider selection
    provider_choice = os.environ.get("KTS_EMBED_PROVIDER", "").strip().lower()
    if not provider_choice and config:
        provider_choice = getattr(config, 'embed_provider', 'bge_onnx_int8')
    if not provider_choice:
        provider_choice = 'bge_onnx_int8'

    logger.info(f"Embedding provider selection: {provider_choice}")

    # Legacy provider - only for explicit request (dev/testing)
    if provider_choice == 'legacy_chroma_default':
        logger.warning("Using deprecated LegacyChromaProvider - not recommended for production")
        return LegacyChromaProvider()

    # BGE ONNX INT8 - default and required for production
    config_model_path = getattr(config, 'embed_model_path', '') if config else ''
    model_path = _resolve_bge_model_path(config_model_path or None)
    
    if not model_path:
        raise FileNotFoundError(
            "BGE ONNX INT8 model not found. This model is REQUIRED for KTS operation.\n"
            "Run: .\\scripts\\download_bge_model.ps1\n"
            "Or set KTS_BGE_MODEL_PATH environment variable."
        )
    
    try:
        from backend.vector.bge_onnx_provider import BgeOnnxInt8Provider
        provider = BgeOnnxInt8Provider(model_path)
        logger.info(f"Using BGE ONNX INT8 provider from: {model_path}")
        return provider
    except Exception as e:
        raise RuntimeError(f"Failed to load BGE ONNX INT8 provider: {e}") from e
