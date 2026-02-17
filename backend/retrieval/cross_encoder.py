"""ONNX Cross-Encoder Re-ranker (Option Prod).

Loads a quantized ONNX cross-encoder model and re-scores
(query, passage) pairs for high-precision retrieval ranking.

The model file is provided by the gsf.kts-models-crossencoder
extension and its path is communicated via the
``KTS_CROSSENCODER_MODEL_PATH`` environment variable.

Gated behind ``config.cross_encoder_enabled``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy singleton — ONNX session is expensive; load once.
# ---------------------------------------------------------------------------
_session = None
_tokenizer = None


def _load_model(model_path: Optional[str] = None):
    """Load the ONNX cross-encoder model.

    Returns ``(session, tokenizer)`` or ``(None, None)`` on failure.
    """
    global _session, _tokenizer
    if _session is not None:
        return _session, _tokenizer

    model_path = model_path or os.environ.get("KTS_CROSSENCODER_MODEL_PATH")
    if not model_path:
        logger.debug("Cross-encoder disabled — KTS_CROSSENCODER_MODEL_PATH not set.")
        return None, None

    model_dir = Path(model_path)
    onnx_file = None
    tokenizer_dir = None

    if model_dir.is_file() and model_dir.suffix == ".onnx":
        onnx_file = model_dir
        tokenizer_dir = model_dir.parent
    elif model_dir.is_dir():
        # Look for .onnx file in directory
        candidates = list(model_dir.glob("*.onnx"))
        if candidates:
            onnx_file = candidates[0]
        tokenizer_dir = model_dir

    if not onnx_file or not onnx_file.exists():
        logger.warning("Cross-encoder ONNX file not found at %s", model_path)
        return None, None

    try:
        import onnxruntime as ort  # noqa: E402
        from tokenizers import Tokenizer  # noqa: E402

        # Load ONNX session with CPU execution provider
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.intra_op_num_threads = 2
        _session = ort.InferenceSession(
            str(onnx_file),
            sess_options=sess_options,
            providers=["CPUExecutionProvider"],
        )

        # Load tokenizer (HuggingFace tokenizers format — tokenizer.json)
        tokenizer_path = tokenizer_dir / "tokenizer.json"
        if tokenizer_path.exists():
            _tokenizer = Tokenizer.from_file(str(tokenizer_path))
        else:
            # Fallback: try to import transformers tokenizer
            logger.warning("tokenizer.json not found at %s — cross-encoder disabled", tokenizer_dir)
            _session = None
            return None, None

        logger.info("Cross-encoder ONNX model loaded from %s", onnx_file)
        return _session, _tokenizer

    except ImportError as exc:
        logger.warning("Cross-encoder dependencies unavailable: %s", exc)
        return None, None
    except Exception as exc:
        logger.warning("Failed to load cross-encoder model: %s", exc)
        return None, None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_pairs(
    query: str,
    passages: List[str],
    model_path: Optional[str] = None,
    max_length: int = 512,
) -> List[float]:
    """Score ``(query, passage)`` pairs using the ONNX cross-encoder.

    Returns a list of relevance scores (higher = more relevant), one per
    passage.  Returns empty list if the model is unavailable.

    Parameters
    ----------
    query : str
        The user query.
    passages : List[str]
        Document passages to score against the query.
    model_path : str | None
        Override path to the ONNX model directory.
    max_length : int
        Maximum token length for the cross-encoder input.
    """
    session, tokenizer = _load_model(model_path)
    if session is None or tokenizer is None:
        return []

    if not passages:
        return []

    try:
        import numpy as np  # noqa: E402  — available via onnxruntime

        scores = []
        # Process in small batches to limit memory
        batch_size = 16
        for i in range(0, len(passages), batch_size):
            batch = passages[i : i + batch_size]

            # Tokenize (query, passage) pairs
            input_ids_list = []
            attention_mask_list = []
            token_type_ids_list = []

            for passage in batch:
                encoding = tokenizer.encode(query, passage)
                ids = encoding.ids[:max_length]
                type_ids = encoding.type_ids[:max_length]
                attn = [1] * len(ids)

                # Pad to max_length
                pad_len = max_length - len(ids)
                ids = ids + [0] * pad_len
                type_ids = type_ids + [0] * pad_len
                attn = attn + [0] * pad_len

                input_ids_list.append(ids)
                attention_mask_list.append(attn)
                token_type_ids_list.append(type_ids)

            # Build numpy arrays
            input_ids = np.array(input_ids_list, dtype=np.int64)
            attention_mask = np.array(attention_mask_list, dtype=np.int64)
            token_type_ids = np.array(token_type_ids_list, dtype=np.int64)

            # Run inference
            input_names = [inp.name for inp in session.get_inputs()]
            feed = {}
            for name in input_names:
                if "input_ids" in name:
                    feed[name] = input_ids
                elif "attention_mask" in name:
                    feed[name] = attention_mask
                elif "token_type_ids" in name:
                    feed[name] = token_type_ids

            outputs = session.run(None, feed)
            logits = outputs[0]  # shape: (batch_size, 1) or (batch_size,)

            # Extract scores
            if logits.ndim == 2:
                batch_scores = logits[:, 0].tolist()
            else:
                batch_scores = logits.tolist()

            scores.extend(batch_scores)

        return scores

    except Exception as exc:
        logger.warning("Cross-encoder scoring failed: %s", exc)
        return []


def rerank(
    query: str,
    rows: List[Dict],
    model_path: Optional[str] = None,
    content_key: str = "content",
    score_key: str = "cross_encoder_score",
) -> List[Dict]:
    """Re-rank a list of search result dicts by cross-encoder score.

    Each dict gets a new key (*score_key*) with the cross-encoder score.
    The list is **not** sorted — the caller decides how to blend scores.

    Returns the same list (mutated) if scoring succeeds, or unmodified
    if the model is unavailable.
    """
    if not rows:
        return rows

    logger.info(f"Cross-encoder reranking {len(rows)} candidates...")
    
    passages = [str(row.get(content_key, "")) for row in rows]
    scores = score_pairs(query, passages, model_path=model_path)

    if not scores:
        logger.warning(f"Cross-encoder scoring returned no scores (model unavailable or failed)")
        return rows  # model unavailable — pass through

    logger.info(f"Cross-encoder computed {len(scores)} scores, top={max(scores):.3f}, min={min(scores):.3f}")
    
    for row, score in zip(rows, scores):
        row[score_key] = score

    return rows
