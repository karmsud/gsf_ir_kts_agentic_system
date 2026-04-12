"""
ConfidenceScorer — Confidence-based autonomy (Decision D7: 90/66/0).

≥ 90% → auto-proceed (HIGH)
66-89% → flag for review (MEDIUM)
< 66% → halt + escalate (LOW)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from backend.abs.config.constants import CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_LOW_THRESHOLD


class ConfidenceTier(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ConfidenceScore:
    """Confidence assessment for an output."""
    value: float          # 0.0 to 1.0
    tier: ConfidenceTier
    reasoning: str = ""
    factors: dict[str, float] | None = None


class ConfidenceScorer:
    """
    Scores confidence for agent outputs using multiple factors.

    Factors considered:
    - regex_match_rate: What fraction of items were matched by regex vs LLM fallback
    - cross_reference_rate: What fraction of items are cross-validated
    - coverage_rate: What fraction of expected output was actually produced
    - consistency_rate: Internal consistency of output

    Each factor produces a 0.0-1.0 score. Final score is weighted average.
    """

    HIGH_THRESHOLD = CONFIDENCE_HIGH_THRESHOLD  # 0.90
    LOW_THRESHOLD = CONFIDENCE_LOW_THRESHOLD    # 0.66

    DEFAULT_WEIGHTS = {
        "regex_match_rate": 0.25,
        "cross_reference_rate": 0.25,
        "coverage_rate": 0.30,
        "consistency_rate": 0.20,
    }

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights or self.DEFAULT_WEIGHTS

    def score(
        self,
        result: Any,
        context: dict[str, Any] | None = None,
    ) -> ConfidenceScore:
        """
        Compute confidence from result and context.

        Args:
            result: The output to score
            context: Optional context dict with factor values:
                - regex_match_rate: float (0-1)
                - cross_reference_rate: float (0-1)
                - coverage_rate: float (0-1)
                - consistency_rate: float (0-1)

        Returns:
            ConfidenceScore with value, tier, and reasoning
        """
        context = context or {}
        factors: dict[str, float] = {}

        # Compute each factor
        factors["regex_match_rate"] = context.get("regex_match_rate", self._default_regex_rate(result))
        factors["cross_reference_rate"] = context.get("cross_reference_rate", self._default_xref_rate(result))
        factors["coverage_rate"] = context.get("coverage_rate", self._default_coverage(result, context))
        factors["consistency_rate"] = context.get("consistency_rate", self._default_consistency(result))

        # Weighted average
        total_weight = sum(self.weights.get(k, 0) for k in factors)
        if total_weight == 0:
            value = 0.5
        else:
            value = sum(
                factors[k] * self.weights.get(k, 0) for k in factors
            ) / total_weight

        # Clamp to [0, 1]
        value = max(0.0, min(1.0, value))

        tier = self.categorize(value)

        # Build reasoning
        reasoning_parts = []
        for k, v in factors.items():
            reasoning_parts.append(f"{k}={v:.2f}")
        reasoning = ", ".join(reasoning_parts)

        return ConfidenceScore(
            value=value,
            tier=tier,
            reasoning=reasoning,
            factors=factors,
        )

    def categorize(self, score: float) -> ConfidenceTier:
        """Map numeric score to tier."""
        if score >= self.HIGH_THRESHOLD:
            return ConfidenceTier.HIGH
        elif score >= self.LOW_THRESHOLD:
            return ConfidenceTier.MEDIUM
        else:
            return ConfidenceTier.LOW

    # ---- Default factor computations ----

    def _default_regex_rate(self, result: Any) -> float:
        """Default regex match rate (assumes all regex matched)."""
        if result is None:
            return 0.0
        if isinstance(result, list) and len(result) == 0:
            return 0.0
        return 0.85  # Conservative default

    def _default_xref_rate(self, result: Any) -> float:
        """Default cross-reference rate."""
        if result is None:
            return 0.0
        if isinstance(result, list):
            if len(result) < 2:
                return 0.5
            return 0.80
        return 0.80

    def _default_coverage(self, result: Any, context: dict) -> float:
        """Default coverage rate."""
        expected = context.get("expected_count")
        if expected and isinstance(result, list):
            ratio = len(result) / expected
            return min(1.0, ratio)
        if isinstance(result, list) and len(result) > 0:
            return 0.85
        return 0.5

    def _default_consistency(self, result: Any) -> float:
        """Default internal consistency rate."""
        if result is None:
            return 0.0
        if isinstance(result, list):
            empty_count = 0
            total_fields = 0
            for item in result:
                if isinstance(item, dict):
                    for v in item.values():
                        total_fields += 1
                        if v is None or v == "" or v == []:
                            empty_count += 1
            if total_fields > 0:
                return 1.0 - (empty_count / total_fields)
        return 0.90
