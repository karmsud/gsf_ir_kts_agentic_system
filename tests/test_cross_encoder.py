"""Unit tests for backend.retrieval.cross_encoder — ONNX cross-encoder re-ranking.

Tests both the *with-model* path (if ONNX model files exist) and the
*graceful-degradation* path (model absent → returns empty list / pass-through).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Reset global singletons between tests
import backend.retrieval.cross_encoder as ce_mod
from backend.retrieval.cross_encoder import rerank, score_pairs


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the lazy-loaded ONNX session/tokenizer between tests."""
    ce_mod._session = None
    ce_mod._tokenizer = None
    yield
    ce_mod._session = None
    ce_mod._tokenizer = None


# ---------------------------------------------------------------------------
# Graceful degradation (no model available)
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    def test_no_env_var_returns_empty_scores(self):
        """score_pairs returns [] when KTS_CROSSENCODER_MODEL_PATH is not set."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("KTS_CROSSENCODER_MODEL_PATH", None)
            result = score_pairs("What is a trustee?", ["The trustee manages assets."])
            assert result == []

    def test_invalid_path_returns_empty_scores(self):
        result = score_pairs(
            "What is a trustee?",
            ["The trustee manages assets."],
            model_path="/nonexistent/model",
        )
        assert result == []

    def test_empty_passages_returns_empty(self):
        result = score_pairs("query", [], model_path="/fake")
        assert result == []

    def test_rerank_passthrough_when_no_model(self):
        """rerank returns rows unmodified when model is unavailable."""
        rows = [
            {"content": "doc1 text", "score": 0.9},
            {"content": "doc2 text", "score": 0.7},
        ]
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("KTS_CROSSENCODER_MODEL_PATH", None)
            result = rerank("test query", rows)
            assert result == rows
            # Should NOT have cross_encoder_score key
            assert "cross_encoder_score" not in result[0]

    def test_rerank_empty_rows(self):
        result = rerank("query", [])
        assert result == []


# ---------------------------------------------------------------------------
# Mock-based tests (validate logic without real ONNX model)
# ---------------------------------------------------------------------------

class TestWithMockedModel:
    def _mock_load(self):
        """Set up mock ONNX session and tokenizer."""
        import types

        mock_session = MagicMock()
        # Simulate get_inputs returning named inputs
        inp_ids = MagicMock()
        inp_ids.name = "input_ids"
        inp_attn = MagicMock()
        inp_attn.name = "attention_mask"
        inp_type = MagicMock()
        inp_type.name = "token_type_ids"
        mock_session.get_inputs.return_value = [inp_ids, inp_attn, inp_type]

        mock_tokenizer = MagicMock()

        return mock_session, mock_tokenizer

    def test_score_pairs_returns_floats(self):
        """With a mocked model, score_pairs returns one float per passage."""
        import numpy as np

        mock_session, mock_tokenizer = self._mock_load()

        # Mock tokenizer.encode to return an encoding with ids and type_ids
        mock_encoding = MagicMock()
        mock_encoding.ids = list(range(10))
        mock_encoding.type_ids = [0] * 5 + [1] * 5
        mock_tokenizer.encode.return_value = mock_encoding

        # Mock session.run to return logits
        mock_session.run.return_value = [np.array([[3.2], [1.1], [-0.5]])]

        ce_mod._session = mock_session
        ce_mod._tokenizer = mock_tokenizer

        scores = score_pairs("test query", ["p1", "p2", "p3"])
        assert len(scores) == 3
        assert all(isinstance(s, float) for s in scores)
        assert scores[0] > scores[1] > scores[2]

    def test_rerank_adds_score_key(self):
        """rerank adds cross_encoder_score to each row dict."""
        import numpy as np

        mock_session, mock_tokenizer = self._mock_load()

        mock_encoding = MagicMock()
        mock_encoding.ids = list(range(10))
        mock_encoding.type_ids = [0] * 5 + [1] * 5
        mock_tokenizer.encode.return_value = mock_encoding

        mock_session.run.return_value = [np.array([[2.0], [5.0]])]

        ce_mod._session = mock_session
        ce_mod._tokenizer = mock_tokenizer

        rows = [
            {"content": "low relevance passage", "doc_id": "d1"},
            {"content": "high relevance passage", "doc_id": "d2"},
        ]

        result = rerank("test query", rows)
        assert len(result) == 2
        assert "cross_encoder_score" in result[0]
        assert "cross_encoder_score" in result[1]
        assert result[1]["cross_encoder_score"] > result[0]["cross_encoder_score"]

    def test_batch_processing(self):
        """Validates batching works for >16 passages."""
        import numpy as np

        mock_session, mock_tokenizer = self._mock_load()

        mock_encoding = MagicMock()
        mock_encoding.ids = list(range(10))
        mock_encoding.type_ids = [0] * 5 + [1] * 5
        mock_tokenizer.encode.return_value = mock_encoding

        # Return different shaped arrays for different batch sizes
        def mock_run(names, feed):
            batch_size = feed["input_ids"].shape[0]
            return [np.random.randn(batch_size, 1)]

        mock_session.run.side_effect = mock_run

        ce_mod._session = mock_session
        ce_mod._tokenizer = mock_tokenizer

        # 20 passages → should process in 2 batches (16 + 4)
        passages = [f"passage {i}" for i in range(20)]
        scores = score_pairs("test query", passages)
        assert len(scores) == 20

    def test_custom_score_key(self):
        """rerank supports custom score_key parameter."""
        import numpy as np

        mock_session, mock_tokenizer = self._mock_load()

        mock_encoding = MagicMock()
        mock_encoding.ids = list(range(10))
        mock_encoding.type_ids = [0] * 5 + [1] * 5
        mock_tokenizer.encode.return_value = mock_encoding

        mock_session.run.return_value = [np.array([[1.0]])]

        ce_mod._session = mock_session
        ce_mod._tokenizer = mock_tokenizer

        rows = [{"content": "text", "doc_id": "d1"}]
        result = rerank("query", rows, score_key="my_custom_score")
        assert "my_custom_score" in result[0]


# ---------------------------------------------------------------------------
# With real ONNX model (skipped if model files not present)
# ---------------------------------------------------------------------------

_CE_MODEL_PATH = os.environ.get("KTS_CROSSENCODER_MODEL_PATH", "")
_HAS_CE_MODEL = bool(_CE_MODEL_PATH) and Path(_CE_MODEL_PATH).exists()


@pytest.mark.skipif(not _HAS_CE_MODEL, reason="Cross-encoder ONNX model not available")
class TestWithRealModel:
    def test_score_pairs_real(self):
        scores = score_pairs(
            "What is the role of the trustee?",
            [
                "The Trustee shall hold legal title to the Trust Fund for the benefit of Certificateholders.",
                "The weather forecast for next week shows rain on Tuesday.",
            ],
            model_path=_CE_MODEL_PATH,
        )
        assert len(scores) == 2
        # Relevant passage should score higher
        assert scores[0] > scores[1], f"Expected relevant > irrelevant: {scores}"

    def test_rerank_real(self):
        rows = [
            {"content": "Python is a programming language.", "doc_id": "d1"},
            {"content": "The Servicer shall service and administer the Mortgage Loans.", "doc_id": "d2"},
        ]
        result = rerank("What are the servicer obligations?", rows, model_path=_CE_MODEL_PATH)
        assert "cross_encoder_score" in result[0]
        assert "cross_encoder_score" in result[1]
        # d2 should score higher for this query
        assert result[1]["cross_encoder_score"] > result[0]["cross_encoder_score"]
