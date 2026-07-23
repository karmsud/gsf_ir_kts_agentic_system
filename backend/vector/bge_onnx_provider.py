"""
BGE ONNX INT8 Embedding Provider (Phase 5 WS-1)

BAAI/bge-base-en-v1.5 — ONNX INT8 quantized, 768-dimensional embeddings.

Key features:
- Query prefix: "Represent this sentence: " added for queries (not documents)
- Mean pooling over last hidden state + L2 normalization
- Batch processing for efficient document embedding
- HuggingFace `tokenizers` library for fast offline tokenization
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import List

import numpy as np

from backend.vector.embedding_provider import EmbeddingProvider

logger = logging.getLogger(__name__)


class BgeOnnxInt8Provider(EmbeddingProvider):
    """BAAI/bge-base-en-v1.5 — ONNX INT8 quantized, 768-dim.
    
    This model provides higher-quality embeddings than MiniLM-L6-V2 (384-dim)
    with better semantic understanding, particularly for legal/technical text.
    
    Model details:
    - Dimensions: 768
    - Max sequence length: 512 tokens
    - Size: ~110 MB (INT8 quantized)
    - Source: https://huggingface.co/BAAI/bge-base-en-v1.5
    """

    QUERY_PREFIX = "Represent this sentence: "
    MAX_SEQ_LEN = 512
    BATCH_SIZE = 32

    def __init__(self, model_dir: str | Path):
        """Initialize BGE provider with model directory.
        
        Args:
            model_dir: Path to directory containing model.onnx, tokenizer.json, vocab.txt
        """
        import onnxruntime as ort

        self._model_dir = Path(model_dir)
        self._validate_model_files()
        
        # Initialize ONNX Runtime session
        self._session = ort.InferenceSession(
            str(self._model_dir / "model.onnx"),
            providers=["CPUExecutionProvider"],
        )
        self._input_names = {i.name for i in self._session.get_inputs()}
        
        # Load tokenizer
        self._init_tokenizer()
        
        # Compute model hash for versioning
        self._hash = self._compute_model_hash()
        
        logger.info(f"BgeOnnxInt8Provider initialized: dims={self.dims}, hash={self._hash}")

    @property
    def provider_id(self) -> str:
        return "bge_onnx_int8"

    @property
    def dims(self) -> int:
        return 768

    @property
    def model_hash(self) -> str:
        return self._hash

    def embed_documents(self, texts: List[str], on_progress=None) -> List[List[float]]:
        """Embed a batch of document chunks without query prefix.

        Args:
            texts: Texts to embed.
            on_progress: Optional callable(done: int, total: int) called after
                each batch completes.  When provided the stderr fallback is
                suppressed so the caller owns progress reporting.
        """
        if not texts:
            return []

        import sys
        total = len(texts)
        show_stderr = on_progress is None and total > 100  # fallback for non-IPC callers

        all_vecs = []
        for i in range(0, total, self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]
            vecs = self._infer(batch)
            all_vecs.extend(vecs)
            done = min(i + self.BATCH_SIZE, total)
            if on_progress is not None:
                on_progress(done, total)
            elif show_stderr and ((i // self.BATCH_SIZE + 1) % 10 == 0 or done >= total):
                print(f"[Embedding] {done}/{total} chunks embedded ({done*100//total}%)", file=sys.stderr, flush=True)
        return all_vecs

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query string with BGE-specific prefix."""
        prefixed = f"{self.QUERY_PREFIX}{text}"
        return self._infer([prefixed])[0]

    def _infer(self, texts: List[str]) -> List[List[float]]:
        """Run ONNX inference on a batch of texts."""
        encoded = self._tokenize(texts)
        
        # Prepare inputs based on model requirements
        inputs = {
            "input_ids": encoded["input_ids"],
            "attention_mask": encoded["attention_mask"],
        }
        if "token_type_ids" in self._input_names:
            inputs["token_type_ids"] = encoded["token_type_ids"]

        # Run inference
        outputs = self._session.run(None, inputs)
        
        # Mean pooling over last hidden state
        hidden = outputs[0]  # (batch, seq_len, 768)
        mask = encoded["attention_mask"]
        mask_expanded = np.expand_dims(mask, axis=-1)  # (batch, seq_len, 1)
        
        # Mask-weighted sum
        summed = np.sum(hidden * mask_expanded, axis=1)
        counts = np.clip(mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
        pooled = summed / counts
        
        # L2 normalize
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        norms = np.clip(norms, a_min=1e-9, a_max=None)
        normalized = pooled / norms
        
        return normalized.tolist()

    def _init_tokenizer(self):
        """Initialize the HuggingFace tokenizer from bundled files."""
        from tokenizers import Tokenizer
        
        tokenizer_path = self._model_dir / "tokenizer.json"
        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self._tokenizer.enable_truncation(max_length=self.MAX_SEQ_LEN)
        self._tokenizer.enable_padding(pad_id=0, pad_token="[PAD]", length=None)

    def _tokenize(self, texts: List[str]) -> dict:
        """Tokenize a batch of texts into model inputs."""
        encodings = self._tokenizer.encode_batch(texts)
        max_len = max(len(e.ids) for e in encodings)

        input_ids = np.zeros((len(texts), max_len), dtype=np.int64)
        attention_mask = np.zeros((len(texts), max_len), dtype=np.int64)
        token_type_ids = np.zeros((len(texts), max_len), dtype=np.int64)

        for i, enc in enumerate(encodings):
            length = len(enc.ids)
            input_ids[i, :length] = enc.ids
            attention_mask[i, :length] = enc.attention_mask
            token_type_ids[i, :length] = enc.type_ids

        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        }

    def _validate_model_files(self):
        """Validate that all required model files exist."""
        required = ["model.onnx", "tokenizer.json"]
        missing = []
        for f in required:
            if not (self._model_dir / f).exists():
                missing.append(f)
        
        if missing:
            raise FileNotFoundError(
                f"Missing model files in {self._model_dir}: {missing}"
            )

    def _compute_model_hash(self) -> str:
        """Compute a hash of the ONNX model for version tracking."""
        h = hashlib.sha256()
        model_path = self._model_dir / "model.onnx"
        with open(model_path, "rb") as f:
            # Read first 1MB to avoid hashing entire large model
            chunk = f.read(1024 * 1024)
            h.update(chunk)
        return f"sha256:{h.hexdigest()[:16]}"
