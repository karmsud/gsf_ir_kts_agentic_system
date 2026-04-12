"""
Phase 15.4 — Anomaly Scorer.

Computes an anomaly score for each clause against the market baseline corpus.
Anomalous clauses deviate from standard market language — flagged in /audit output.

Two signals:
  1. Semantic distance (cosine similarity to baseline standard_text)
  2. Deviation signal matching (keyword/pattern checks)

Usage::

    scorer = AnomalyScorer(baseline_corpus=corpus, embed_fn=my_embed)
    result = scorer.score("The Servicer shall not be obligated...",
                          clause_type="servicer_advance_definition",
                          deal_type="PSA_HELOC")
    if result.is_anomalous:
        print(result.format_flag())
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ── Data Structures ───────────────────────────────────────────

@dataclass
class AnomalyResult:
    """Result of anomaly scoring for a single clause."""

    score: float = 0.0          # 0 = identical to standard, 1 = completely different
    is_anomalous: bool = False
    severity: str = "standard"  # standard, low, medium, high
    deviation_signals: List[str] = field(default_factory=list)
    similarity_to_standard: float = 1.0
    clause_type: str = ""
    deal_type: str = ""

    def format_flag(self) -> str:
        """Format the anomaly result as a display flag."""
        if self.severity == "standard":
            return f"✅ Standard language (similarity: {self.similarity_to_standard:.2f})"

        if self.severity == "high":
            icon = "🔴"
            label = "Significant deviation"
        elif self.severity == "medium":
            icon = "⚠️"
            label = "Non-standard"
        else:  # low
            icon = "🔵"
            label = "Minor deviation"

        parts = [f"{icon} **{label}** (similarity: {self.similarity_to_standard:.2f} | Severity: {self.severity.title()})"]

        if self.deviation_signals:
            parts.append(f"Deviation signals: {', '.join(self.deviation_signals)}")

        return "\n".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "is_anomalous": self.is_anomalous,
            "severity": self.severity,
            "deviation_signals": self.deviation_signals,
            "similarity_to_standard": self.similarity_to_standard,
            "clause_type": self.clause_type,
            "deal_type": self.deal_type,
        }


# ── Anomaly Scorer ────────────────────────────────────────────

class AnomalyScorer:
    """
    Scores clauses against market baseline for anomaly detection.

    Parameters
    ----------
    baseline_corpus : BaselineCorpus
        The reference corpus of standard clause texts.
    embed_fn : callable, optional
        ``def embed_fn(text: str) -> np.ndarray`` — returns a 1D embedding vector.
    anomaly_threshold : float
        Score above which a clause is flagged as anomalous (default 0.35).
    high_severity_threshold : float
        Score above which a clause is flagged as high severity (default 0.6).
    """

    def __init__(
        self,
        baseline_corpus=None,
        embed_fn: Optional[Callable[[str], np.ndarray]] = None,
        anomaly_threshold: float = 0.35,
        high_severity_threshold: float = 0.6,
    ) -> None:
        self.baseline_corpus = baseline_corpus
        self.embed_fn = embed_fn
        self.anomaly_threshold = anomaly_threshold
        self.high_severity_threshold = high_severity_threshold

    def score(
        self,
        clause_text: str,
        clause_type: str,
        deal_type: str,
    ) -> AnomalyResult:
        """
        Score a clause against the market baseline.

        Returns an AnomalyResult with the anomaly assessment.
        """
        if self.baseline_corpus is None:
            return AnomalyResult(
                clause_type=clause_type,
                deal_type=deal_type,
            )

        baseline = self.baseline_corpus.get_baseline(clause_type, deal_type)
        if baseline is None:
            logger.debug(
                "[AnomalyScorer] No baseline for %s/%s — skipping",
                clause_type, deal_type,
            )
            return AnomalyResult(
                clause_type=clause_type,
                deal_type=deal_type,
            )

        # ── Semantic similarity ─────────────────────────────
        sim_score = self._compute_similarity(clause_text, baseline.standard_text)

        # ── Deviation signal detection ──────────────────────
        signals_found = self._check_deviation_signals(
            clause_text, baseline.deviation_signals
        )

        # ── Anomaly score: 1 - similarity + signal boost ────
        raw_anomaly = 1.0 - sim_score
        signal_boost = 0.15 * len(signals_found)
        anomaly_score = min(1.0, raw_anomaly + signal_boost)

        is_anomalous = anomaly_score > self.anomaly_threshold or len(signals_found) > 0

        # 4-tier severity: HIGH >0.60, MEDIUM >0.35, LOW >0.20, STANDARD ≤0.20
        if anomaly_score > self.high_severity_threshold:
            severity = "high"
        elif anomaly_score > self.anomaly_threshold:
            severity = "medium"
        elif anomaly_score > 0.20 or signals_found:
            severity = "low"
        else:
            severity = "standard"

        return AnomalyResult(
            score=anomaly_score,
            is_anomalous=is_anomalous,
            severity=severity,
            deviation_signals=signals_found,
            similarity_to_standard=sim_score,
            clause_type=clause_type,
            deal_type=deal_type,
        )

    def score_batch(
        self,
        clauses: List[Dict[str, str]],
        deal_type: str,
    ) -> List[AnomalyResult]:
        """
        Score multiple clauses.

        Parameters
        ----------
        clauses : list[dict]
            Each dict: ``{"text": str, "clause_type": str}``
        """
        return [
            self.score(
                clause_text=c["text"],
                clause_type=c["clause_type"],
                deal_type=deal_type,
            )
            for c in clauses
        ]

    # ── Internal Methods ────────────────────────────────────

    def _compute_similarity(self, text_a: str, text_b: str) -> float:
        """Compute cosine similarity between two texts."""
        if self.embed_fn is None:
            # Fallback: simple Jaccard similarity on words
            return self._jaccard_similarity(text_a, text_b)

        try:
            emb_a = self.embed_fn(text_a)
            emb_b = self.embed_fn(text_b)

            # Cosine similarity
            dot = np.dot(emb_a, emb_b)
            norm_a = np.linalg.norm(emb_a)
            norm_b = np.linalg.norm(emb_b)

            if norm_a == 0 or norm_b == 0:
                return 0.0

            return float(dot / (norm_a * norm_b))

        except Exception as exc:
            logger.warning("[AnomalyScorer] Embedding failed, using Jaccard: %s", exc)
            return self._jaccard_similarity(text_a, text_b)

    @staticmethod
    def _jaccard_similarity(text_a: str, text_b: str) -> float:
        """Simple word-level Jaccard similarity as embedding fallback."""
        words_a = set(text_a.lower().split())
        words_b = set(text_b.lower().split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)

    @staticmethod
    def _check_deviation_signals(
        text: str, signals: List[str]
    ) -> List[str]:
        """Check for deviation signal patterns in the clause text."""
        text_lower = text.lower()
        return [sig for sig in signals if sig.lower() in text_lower]
