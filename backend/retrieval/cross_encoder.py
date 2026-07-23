"""Cross-Encoder Re-ranker for high-precision retrieval ranking.

Supports two backends:
1. ONNX model via KTS_CROSSENCODER_MODEL_PATH (production, bundled in VSIX)
2. sentence-transformers CrossEncoder (development, auto-downloads model)

Gated behind ``config.cross_encoder_enabled``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy singleton — model is expensive; load once.
# ---------------------------------------------------------------------------
_model: Any = None
_model_type: str = ""  # "onnx" or "sentence_transformers"


def _resolve_cross_encoder_path(explicit_path: Optional[str] = None) -> Optional[str]:
    """Resolve the cross-encoder ONNX model directory.

    Priority:
    1. Explicit path argument
    2. KTS_CROSSENCODER_MODEL_PATH environment variable
    3. PyInstaller bundle: _MEIPASS/models/cross-encoder
    4. Development: packaging/models/cross_encoder
    """
    import sys

    # 1. Explicit path
    if explicit_path:
        p = Path(explicit_path)
        if p.is_dir() and (p / "model.onnx").exists():
            return str(p)
        if p.is_file() and p.suffix == ".onnx":
            return str(p.parent)

    # 2. Environment variable
    env_path = os.environ.get("KTS_CROSSENCODER_MODEL_PATH")
    if env_path:
        p = Path(env_path)
        if p.is_dir() and (p / "model.onnx").exists():
            return str(p)
        if p.is_file() and p.suffix == ".onnx":
            return str(p.parent)

    # 3. PyInstaller frozen bundle
    if getattr(sys, 'frozen', False):
        bundle_dir = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        model_dir = bundle_dir / 'models' / 'cross-encoder'
        if (model_dir / "model.onnx").exists():
            return str(model_dir)

    # 4. Development mode fallback
    dev_paths = [
        Path(__file__).parent.parent.parent / 'packaging' / 'models' / 'cross-encoder',
        Path(__file__).parent.parent.parent / 'packaging' / 'models' / 'cross_encoder',
        Path(__file__).parent.parent.parent / 'assets' / 'models' / 'cross-encoder',
    ]
    for p in dev_paths:
        if p.exists() and (p / "model.onnx").exists():
            return str(p)

    return None


def _load_model(model_path: Optional[str] = None):
    """Load the cross-encoder model.

    Priority:
    1. ONNX model (bundled or via KTS_CROSSENCODER_MODEL_PATH)
    2. sentence-transformers CrossEncoder (auto-download, dev only)

    Returns ``(model, model_type)`` or ``(None, "")`` on failure.
    """
    global _model, _model_type
    if _model is not None:
        return _model, _model_type

    model_path = _resolve_cross_encoder_path(model_path)

    # Try ONNX first if path is provided
    if model_path:
        model_dir = Path(model_path)
        onnx_file = None
        tokenizer_dir = None

        if model_dir.is_file() and model_dir.suffix == ".onnx":
            onnx_file = model_dir
            tokenizer_dir = model_dir.parent
        elif model_dir.is_dir():
            candidates = list(model_dir.glob("*.onnx"))
            if candidates:
                onnx_file = candidates[0]
            tokenizer_dir = model_dir

        if onnx_file and onnx_file.exists():
            try:
                import onnxruntime as ort
                from tokenizers import Tokenizer

                sess_options = ort.SessionOptions()
                sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                sess_options.intra_op_num_threads = 2
                session = ort.InferenceSession(
                    str(onnx_file),
                    sess_options=sess_options,
                    providers=["CPUExecutionProvider"],
                )

                tokenizer_path = tokenizer_dir / "tokenizer.json"
                if tokenizer_path.exists():
                    tokenizer = Tokenizer.from_file(str(tokenizer_path))
                    _model = (session, tokenizer)
                    _model_type = "onnx"
                    logger.info("Cross-encoder ONNX model loaded from %s", onnx_file)
                    return _model, _model_type
            except Exception as exc:
                logger.debug("ONNX cross-encoder failed: %s", exc)

    # Fallback to sentence-transformers
    try:
        from sentence_transformers import CrossEncoder
        _model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        _model_type = "sentence_transformers"
        logger.info("Cross-encoder loaded via sentence-transformers (ms-marco-MiniLM-L-6-v2)")
        return _model, _model_type
    except ImportError:
        logger.debug("sentence-transformers not available for cross-encoder")
    except Exception as exc:
        logger.warning("Failed to load sentence-transformers cross-encoder: %s", exc)

    logger.debug("Cross-encoder unavailable — neither ONNX nor sentence-transformers")
    return None, ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_pairs(
    query: str,
    passages: List[str],
    model_path: Optional[str] = None,
    max_length: int = 512,
) -> List[float]:
    """Score ``(query, passage)`` pairs using the cross-encoder.

    Returns a list of relevance scores (higher = more relevant), one per
    passage.  Returns empty list if the model is unavailable.
    """
    model, model_type = _load_model(model_path)
    if model is None:
        return []

    if not passages:
        return []

    try:
        if model_type == "sentence_transformers":
            # sentence-transformers CrossEncoder
            pairs = [[query, p] for p in passages]
            scores = model.predict(pairs)
            return scores.tolist() if hasattr(scores, "tolist") else list(scores)

        elif model_type == "onnx":
            # ONNX backend
            import numpy as np
            session, tokenizer = model

            scores = []
            batch_size = 16
            for i in range(0, len(passages), batch_size):
                batch = passages[i : i + batch_size]

                input_ids_list = []
                attention_mask_list = []
                token_type_ids_list = []

                for passage in batch:
                    encoding = tokenizer.encode(query, passage)
                    ids = encoding.ids[:max_length]
                    type_ids = encoding.type_ids[:max_length]
                    attn = [1] * len(ids)

                    pad_len = max_length - len(ids)
                    ids = ids + [0] * pad_len
                    type_ids = type_ids + [0] * pad_len
                    attn = attn + [0] * pad_len

                    input_ids_list.append(ids)
                    attention_mask_list.append(attn)
                    token_type_ids_list.append(type_ids)

                input_ids = np.array(input_ids_list, dtype=np.int64)
                attention_mask = np.array(attention_mask_list, dtype=np.int64)
                token_type_ids = np.array(token_type_ids_list, dtype=np.int64)

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
                logits = outputs[0]

                if logits.ndim == 2:
                    batch_scores = logits[:, 0].tolist()
                else:
                    batch_scores = logits.tolist()

                scores.extend(batch_scores)

            return scores

    except Exception as exc:
        logger.warning("Cross-encoder scoring failed: %s", exc)
        return []

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
