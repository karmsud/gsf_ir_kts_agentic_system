"""
Phase 13.1 — Confidence Scoring & Uncertainty Flags.

Classifies retrieval confidence from cross-encoder rerank scores and match
counts.  Every answer is tagged with a confidence tier so users can
distinguish high-precision direct matches from speculative inferences.

Tiers:
    HIGH        — ≥2 direct matches (rerank > 0.75) AND top score > 0.85
    MEDIUM      — top score in (0.65, 0.85]
    LOW         — top score in (0.45, 0.65]
    SPECULATIVE — top score ≤ 0.45 or no chunks
    NO_MATCH    — empty result set
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Confidence Tiers ──────────────────────────────────────────

class ConfidenceTier(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    SPECULATIVE = "SPECULATIVE"
    NO_MATCH = "NO_MATCH"


# ── Result ────────────────────────────────────────────────────

@dataclass
class ConfidenceResult:
    """Confidence assessment of a retrieval result set."""

    tier: ConfidenceTier
    top_score: float
    n_direct_matches: int
    score_spread: float
    display_text: str
    display_icon: str
    detail: str
    matched_sections: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tier": self.tier.value,
            "top_score": round(self.top_score, 4),
            "n_direct_matches": self.n_direct_matches,
            "score_spread": round(self.score_spread, 4),
            "display_text": self.display_text,
            "display_icon": self.display_icon,
            "detail": self.detail,
            "matched_sections": self.matched_sections,
        }


# ── Display Templates ─────────────────────────────────────────

_DISPLAY_TEMPLATES = {
    ConfidenceTier.HIGH: {
        "icon": "✅",
        "template": "Answer confidence: **High** — {n_direct} direct match(es){section_note}",
    },
    ConfidenceTier.MEDIUM: {
        "icon": "🔵",
        "template": "Answer confidence: **Medium** — found in context, no direct definition",
    },
    ConfidenceTier.LOW: {
        "icon": "⚠️",
        "template": "Answer confidence: **Low** — inferred from related clauses — verify manually",
    },
    ConfidenceTier.SPECULATIVE: {
        "icon": "🔴",
        "template": "Answer confidence: **Speculative** — not found directly; answer may be incomplete",
    },
    ConfidenceTier.NO_MATCH: {
        "icon": "❌",
        "template": "Answer confidence: **No Match** — no relevant content found",
    },
}


# ── Thresholds (configurable) ─────────────────────────────────

@dataclass
class ConfidenceThresholds:
    """Tunable thresholds for confidence classification."""

    high_top_score: float = 0.85
    high_min_direct: int = 2
    medium_min_score: float = 0.65
    low_min_score: float = 0.45
    direct_match_threshold: float = 0.75


# ── Scorer ────────────────────────────────────────────────────

class ConfidenceScorer:
    """
    Classify retrieval confidence from rerank scores.

    Usage::

        scorer = ConfidenceScorer()
        result = scorer.score(top_chunks)
        # result.tier == ConfidenceTier.HIGH
        # result.display_text == "Answer confidence: **High** — 3 direct matches in Section 1.01"
    """

    def __init__(self, thresholds: Optional[ConfidenceThresholds] = None) -> None:
        self.thresholds = thresholds or ConfidenceThresholds()

    def score(
        self,
        top_chunks: List[Dict[str, Any]],
        *,
        score_key: str = "rerank_score",
        fallback_score_key: str = "cross_encoder_score",
        section_key: str = "section",
    ) -> ConfidenceResult:
        """
        Classify confidence from a list of result chunks.

        Each chunk dict should contain a ``rerank_score`` (or
        ``cross_encoder_score``) float.  Optionally a ``section``
        string for HIGH-tier display.
        """
        if not top_chunks:
            return self._build_result(ConfidenceTier.NO_MATCH, 0.0, 0, 0.0, [])

        # Extract scores
        scores = []
        for c in top_chunks:
            s = c.get(score_key)
            if s is None:
                s = c.get(fallback_score_key)
            if s is None:
                # Try to normalise cross-encoder logits
                raw = c.get("_final_score") or c.get("similarity") or 0.0
                s = float(raw)
            else:
                s = float(s)
            scores.append(s)

        top_score = max(scores) if scores else 0.0
        score_spread = (scores[0] - scores[-1]) if len(scores) > 1 else 0.0

        # Direct match count
        n_direct = sum(1 for s in scores if s > self.thresholds.direct_match_threshold)

        # Collect matched sections
        sections: List[str] = []
        for c in top_chunks:
            sec = c.get(section_key) or c.get("metadata", {}).get("section_number", "")
            if sec and sec not in sections:
                sections.append(sec)

        # Classify
        tier = self._classify(top_score, n_direct)

        return self._build_result(tier, top_score, n_direct, score_spread, sections)

    def _classify(self, top_score: float, n_direct: int) -> ConfidenceTier:
        t = self.thresholds
        if n_direct >= t.high_min_direct and top_score > t.high_top_score:
            return ConfidenceTier.HIGH
        if top_score > t.medium_min_score:
            return ConfidenceTier.MEDIUM
        if top_score > t.low_min_score:
            return ConfidenceTier.LOW
        return ConfidenceTier.SPECULATIVE

    @staticmethod
    def _build_result(
        tier: ConfidenceTier,
        top_score: float,
        n_direct: int,
        score_spread: float,
        sections: List[str],
    ) -> ConfidenceResult:
        tmpl = _DISPLAY_TEMPLATES[tier]
        icon = tmpl["icon"]

        section_note = ""
        if sections and tier == ConfidenceTier.HIGH:
            section_note = f" in {', '.join(sections[:3])}"

        display = f"{icon} " + tmpl["template"].format(
            n_direct=n_direct,
            section_note=section_note,
        )

        detail = (
            f"top_score={top_score:.3f}, "
            f"direct_matches={n_direct}, "
            f"spread={score_spread:.3f}"
        )

        return ConfidenceResult(
            tier=tier,
            top_score=top_score,
            n_direct_matches=n_direct,
            score_spread=score_spread,
            display_text=display,
            display_icon=icon,
            detail=detail,
            matched_sections=sections[:5],
        )
