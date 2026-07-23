"""
Embedding abstraction for ABS retrieval.

Provides a uniform :class:`Embedder` interface with two implementations:

* :class:`BgeEmbedder` — production quality, wraps the bundled BGE ONNX INT8
  provider (768-dim). Used when the model files are present (in the frozen
  VSIX bundle they always are).
* :class:`HashEmbedder` — a dependency-free feature-hashing embedder used as a
  fallback when the ONNX model is unavailable (e.g. tests / dev). It produces
  deterministic, L2-normalised vectors so cosine similarity is meaningful even
  without the heavy model.

``get_default_embedder()`` auto-selects BGE when available, else the hash
embedder, so the system always runs out of the box.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from pathlib import Path
from typing import List, Optional, Protocol

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-z0-9]+(?:[-._][a-z0-9]+)*", re.IGNORECASE)


def _tokens(text: str) -> List[str]:
    return [w for w in _WORD_RE.findall((text or "").lower()) if len(w) > 1]


class Embedder(Protocol):
    """Minimal embedding interface used by the retrieval layer."""

    @property
    def dims(self) -> int: ...

    @property
    def provider_id(self) -> str: ...

    def embed_documents(self, texts: List[str]) -> List[List[float]]: ...

    def embed_query(self, text: str) -> List[float]: ...


class HashEmbedder:
    """Deterministic feature-hashing embedder (no external dependency)."""

    def __init__(self, dims: int = 256) -> None:
        self._dims = dims

    @property
    def dims(self) -> int:
        return self._dims

    @property
    def provider_id(self) -> str:
        return f"hash_{self._dims}"

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._embed(text)

    def _embed(self, text: str) -> List[float]:
        vec = [0.0] * self._dims
        for tok in _tokens(text):
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            idx = h % self._dims
            sign = 1.0 if (h >> 8) & 1 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class BgeEmbedder:
    """Production embedder backed by the bundled BGE ONNX INT8 provider."""

    def __init__(self, model_dir: Path) -> None:
        from backend.vector.bge_onnx_provider import BgeOnnxInt8Provider

        self._provider = BgeOnnxInt8Provider(model_dir)

    @property
    def dims(self) -> int:
        return self._provider.dims

    @property
    def provider_id(self) -> str:
        return self._provider.provider_id

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._provider.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        return self._provider.embed_query(text)


def locate_bge_model() -> Optional[Path]:
    """Search common locations for the bundled BGE ONNX model directory."""
    import sys

    candidates: List[Path] = []
    # Frozen bundle (_MEIPASS) and repo/dev layouts.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "models" / "bge-base-en-v1.5" / "onnx-int8")
    repo = Path(__file__).resolve().parents[3]
    candidates += [
        repo / "packaging" / "models" / "bge-base-en-v1.5" / "onnx-int8",
        repo / "packaging" / "models" / "bge" / "bge-base-en-v1.5" / "onnx-int8",
        repo / "knowledge_base" / "models" / "bge-base-en-v1.5" / "onnx-int8",
    ]
    for c in candidates:
        if (c / "model.onnx").exists():
            return c
    return None


def get_default_embedder(model_dir: Optional[Path] = None) -> Embedder:
    """Return BGE if the model is available, else the hash fallback."""
    try:
        path = Path(model_dir) if model_dir else locate_bge_model()
        if path and (path / "model.onnx").exists():
            logger.info("Using BgeEmbedder from %s", path)
            return BgeEmbedder(path)
    except Exception as exc:  # noqa: BLE001 - fall back gracefully
        logger.warning("BGE embedder unavailable (%s); using hash fallback.", exc)
    logger.info("Using HashEmbedder fallback (no BGE model found).")
    return HashEmbedder()


def cosine(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
