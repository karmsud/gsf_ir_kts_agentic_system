"""
Phase 8.1 — Pure-Python BM25 Keyword Retriever

Custom BM25 implementation (~150 lines) for hybrid search.
No external dependencies beyond the standard library + json.

BM25 Formula:
    score(q, d) = Σ IDF(t) × (tf(t,d) × (k1 + 1)) / (tf(t,d) + k1 × (1 - b + b × |d|/avgdl))

Where:
    IDF(t) = log((N - n(t) + 0.5) / (n(t) + 0.5) + 1)
    N = total documents, n(t) = documents containing term t
    tf(t,d) = frequency of term t in document d
    |d| = document length in tokens, avgdl = average document length
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Tokenisation ─────────────────────────────────────────────────
# Preserves hyphenated terms ("PSA-2006HE1") and section numbers ("5.05")
_SPLIT_RE = re.compile(r"[a-z0-9]+(?:[-._][a-z0-9]+)*", re.IGNORECASE)
_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "this", "that", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "do", "does",
    "did", "will", "would", "shall", "should", "may", "might", "can",
    "could", "not", "no", "so", "if", "as", "its", "such",
})


def _tokenize(text: str) -> List[str]:
    """Case-fold + strip punctuation + remove stop-words.

    Preserves hyphenated legal terms (e.g. ``psa-2006he1``) and section
    numbers (e.g. ``5.05``) as single tokens for accurate BM25 matching.
    """
    return [
        w for w in _SPLIT_RE.findall(text.lower())
        if w not in _STOP_WORDS and len(w) > 1
    ]


# ── BM25Retriever ────────────────────────────────────────────────

class BM25Retriever:
    """Okapi BM25 keyword retriever with JSON persistence.

    Usage::

        retriever = BM25Retriever(persist_dir="/path/to/.kts")
        retriever.build_index(documents)    # list of {id, content, metadata?}
        retriever.save_index()

        results = retriever.search("Closing Date", top_k=20)
        # → [{id, content, score, metadata}, ...]
    """

    INDEX_FILE = "_kts_bm25_index.json"

    def __init__(self, persist_dir: str, *, k1: float = 1.5, b: float = 0.75):
        self.persist_dir = persist_dir
        self.k1 = k1
        self.b = b

        # Built by build_index():
        self._doc_count: int = 0
        self._avgdl: float = 0.0
        self._doc_lengths: Dict[str, int] = {}          # doc_id → token count
        self._doc_tf: Dict[str, Dict[str, int]] = {}    # doc_id → {term: freq}
        self._inverted_index: Dict[str, set] = {}        # term → {doc_ids}
        self._idf_cache: Dict[str, float] = {}
        self._documents: Dict[str, Dict[str, Any]] = {}  # doc_id → {id, content, metadata}

    # ── Index construction ───────────────────────────────────────

    def build_index(self, documents: List[Dict[str, Any]]) -> None:
        """Build BM25 inverted index from a list of ``{id, content, metadata?}``."""
        self._documents.clear()
        self._doc_tf.clear()
        self._inverted_index.clear()
        self._doc_lengths.clear()
        self._idf_cache.clear()

        if not documents:
            self._doc_count = 0
            self._avgdl = 0.0
            return

        total_length = 0
        for doc in documents:
            doc_id = doc["id"]
            content = doc.get("content", "")
            tokens = _tokenize(content)
            tf = Counter(tokens)

            self._documents[doc_id] = doc
            self._doc_tf[doc_id] = dict(tf)
            self._doc_lengths[doc_id] = len(tokens)
            total_length += len(tokens)

            for term in tf:
                if term not in self._inverted_index:
                    self._inverted_index[term] = set()
                self._inverted_index[term].add(doc_id)

        self._doc_count = len(documents)
        self._avgdl = total_length / self._doc_count if self._doc_count else 0.0

        # Pre-compute IDF for every term
        for term, doc_ids in self._inverted_index.items():
            n = len(doc_ids)
            self._idf_cache[term] = math.log(
                (self._doc_count - n + 0.5) / (n + 0.5) + 1.0
            )

        logger.info(
            "[BM25] Index built: %d documents, %d unique terms",
            self._doc_count, len(self._inverted_index),
        )

    # ── Search ───────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        """Return top-*k* documents ranked by BM25 score."""
        if not query or not self._doc_count:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scores: Dict[str, float] = {}

        for term in query_tokens:
            if term not in self._inverted_index:
                continue
            idf = self._idf_cache[term]
            for doc_id in self._inverted_index[term]:
                tf = self._doc_tf[doc_id].get(term, 0)
                dl = self._doc_lengths[doc_id]
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (
                    1 - self.b + self.b * dl / self._avgdl
                )
                score = idf * numerator / denominator
                scores[doc_id] = scores.get(doc_id, 0.0) + score

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        results: List[Dict[str, Any]] = []
        for doc_id, score in ranked:
            doc = self._documents.get(doc_id, {})
            results.append({
                "id": doc_id,
                "content": doc.get("content", ""),
                "score": score,
                "metadata": doc.get("metadata", {}),
            })

        return results

    # ── Persistence ──────────────────────────────────────────────

    def save_index(self) -> None:
        """Persist BM25 index to JSON for fast reload."""
        os.makedirs(self.persist_dir, exist_ok=True)
        path = os.path.join(self.persist_dir, self.INDEX_FILE)

        data = {
            "doc_count": self._doc_count,
            "avgdl": self._avgdl,
            "doc_lengths": self._doc_lengths,
            "doc_tf": self._doc_tf,
            "inverted_index": {t: list(ids) for t, ids in self._inverted_index.items()},
            "idf_cache": self._idf_cache,
            "documents": self._documents,
        }

        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

        logger.info("[BM25] Index saved: %s", path)

    def load_index(self) -> bool:
        """Load a previously saved index.  Returns ``False`` if not found."""
        path = os.path.join(self.persist_dir, self.INDEX_FILE)
        if not os.path.exists(path):
            return False

        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)

            self._doc_count = data["doc_count"]
            self._avgdl = data["avgdl"]
            self._doc_lengths = data["doc_lengths"]
            self._doc_tf = data["doc_tf"]
            self._inverted_index = {
                t: set(ids) for t, ids in data["inverted_index"].items()
            }
            self._idf_cache = data["idf_cache"]
            self._documents = data.get("documents", {})

            logger.info(
                "[BM25] Index loaded: %d documents, %d unique terms",
                self._doc_count, len(self._inverted_index),
            )
            return True

        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("[BM25] Corrupt index file, rebuilding: %s", exc)
            return False
