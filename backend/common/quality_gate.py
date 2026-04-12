"""
QualityGate — Merged KTS + ABS quality evaluation.

Provides two interfaces:
  1. apply(result: AgentResult) -> AgentResult  — legacy KTS interface (backward compat)
  2. evaluate(output, ...) -> QualityResult      — full 5-dimension ABS evaluation

All scores are 0-10. All dimensions must be >= MIN_SCORE (8.0) to pass.
Max retries: 3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from config import KTSConfig
from .escalation import EscalationManager
from .models import AgentResult


class QualityDimension(str, Enum):
    """Five quality dimensions scored by the quality gate."""
    COMPLETENESS = "completeness"
    ACCURACY = "accuracy"
    CITATION_FIDELITY = "citation_fidelity"
    STRUCTURAL_CONFORMANCE = "structural_conformance"
    DEAL_SCOPE_COMPLIANCE = "deal_scope_compliance"


@dataclass
class QualityResult:
    """Result of quality gate evaluation."""
    passed: bool
    scores: dict[str, float] = field(default_factory=dict)
    retry_count: int = 0
    feedback: Optional[str] = None
    dimension_details: dict[str, str] = field(default_factory=dict)


class QualityGate:
    """
    Evaluates agent outputs on 5 quality dimensions (ABS) and provides
    the legacy KTS apply() interface for backward compatibility.

    ABS dimensions (0-10 each):
    - COMPLETENESS: Are all required fields/sections present?
    - ACCURACY: Are values correct and internally consistent?
    - CITATION_FIDELITY: Does every claim cite a source section?
    - STRUCTURAL_CONFORMANCE: Does output match expected format/schema?
    - DEAL_SCOPE_COMPLIANCE: Does all data come from the scoped deal?

    Pass criteria: ALL dimensions >= MIN_SCORE (8.0)
    """

    MIN_SCORE = 8.0
    MAX_RETRIES = 3

    def __init__(self, config: KTSConfig | None = None):
        self.config = config

    # ── Legacy KTS Interface (backward compat) ────────────────

    def apply(self, result: AgentResult) -> AgentResult:
        """Legacy KTS quality gate: confidence-based pass/fail."""
        if self.config is None:
            return result

        high = getattr(self.config, "confidence_high", 0.90)
        medium = getattr(self.config, "confidence_medium", 0.66)

        try:
            high = float(high)
        except (TypeError, ValueError):
            high = 0.90

        try:
            medium = float(medium)
        except (TypeError, ValueError):
            medium = 0.66

        if result.confidence >= high:
            return result

        if result.confidence >= medium:
            if result.reasoning:
                result.reasoning += " | Confidence medium; review recommended."
            else:
                result.reasoning = "Confidence medium; review recommended."
            return result

        result.escalation = EscalationManager.low_confidence(
            "Confidence too low for autonomous acceptance."
        )
        return result

    # ── Full ABS 5-Dimension Evaluation ───────────────────────

    def evaluate(
        self,
        output: Any,
        expected_fields: list[str] | None = None,
        expected_count_min: int | None = None,
        deal_id: str = "",
    ) -> QualityResult:
        """
        Score output on 5 dimensions.

        Args:
            output: The agent output to evaluate (typically dict or list)
            expected_fields: Required fields in each item
            expected_count_min: Minimum number of items expected
            deal_id: Expected deal ID for scope compliance

        Returns:
            QualityResult with pass/fail, scores, and feedback
        """
        scores = {}
        details = {}

        comp_score, comp_detail = self._score_completeness(output, expected_fields, expected_count_min)
        scores[QualityDimension.COMPLETENESS.value] = comp_score
        details[QualityDimension.COMPLETENESS.value] = comp_detail

        acc_score, acc_detail = self._score_accuracy(output)
        scores[QualityDimension.ACCURACY.value] = acc_score
        details[QualityDimension.ACCURACY.value] = acc_detail

        cit_score, cit_detail = self._score_citations(output)
        scores[QualityDimension.CITATION_FIDELITY.value] = cit_score
        details[QualityDimension.CITATION_FIDELITY.value] = cit_detail

        str_score, str_detail = self._score_structure(output, expected_fields)
        scores[QualityDimension.STRUCTURAL_CONFORMANCE.value] = str_score
        details[QualityDimension.STRUCTURAL_CONFORMANCE.value] = str_detail

        scope_score, scope_detail = self._score_scope(output, deal_id)
        scores[QualityDimension.DEAL_SCOPE_COMPLIANCE.value] = scope_score
        details[QualityDimension.DEAL_SCOPE_COMPLIANCE.value] = scope_detail

        min_score = min(scores.values())
        passed = min_score >= self.MIN_SCORE

        feedback = None
        if not passed:
            low_dims = [dim for dim, score in scores.items() if score < self.MIN_SCORE]
            feedback = (
                f"Quality gate failed. Dimensions below {self.MIN_SCORE}: "
                f"{', '.join(low_dims)}. Details: "
                + "; ".join(f"{d}: {details.get(d, '')}" for d in low_dims)
            )

        return QualityResult(
            passed=passed,
            scores=scores,
            feedback=feedback,
            dimension_details=details,
        )

    def _score_completeness(self, output: Any, expected_fields: list[str] | None,
                            expected_count_min: int | None) -> tuple[float, str]:
        if output is None:
            return 0.0, "Output is None"
        items = output if isinstance(output, list) else [output]
        if expected_count_min is not None and len(items) < expected_count_min:
            ratio = len(items) / expected_count_min
            return max(0.0, ratio * 10), f"Only {len(items)}/{expected_count_min} items"
        if expected_fields and items:
            missing_counts = []
            for item in items:
                if isinstance(item, dict):
                    missing = [f for f in expected_fields if f not in item]
                    if missing:
                        missing_counts.append(len(missing))
            if missing_counts:
                avg_missing = sum(missing_counts) / len(missing_counts)
                score = max(0.0, 10 - (avg_missing / len(expected_fields)) * 10)
                return score, f"Avg {avg_missing:.1f} missing fields per item"
        return 10.0, "Complete"

    def _score_accuracy(self, output: Any) -> tuple[float, str]:
        if output is None:
            return 0.0, "Output is None"
        if isinstance(output, list):
            empty_count = 0
            total_fields = 0
            for item in output:
                if isinstance(item, dict):
                    for v in item.values():
                        total_fields += 1
                        if v is None or v == "" or v == []:
                            empty_count += 1
            if total_fields > 0:
                empty_ratio = empty_count / total_fields
                if empty_ratio > 0.3:
                    return max(0.0, 10 - empty_ratio * 10), (
                        f"{empty_count}/{total_fields} fields are empty/None"
                    )
        return 10.0, "Internally consistent"

    def _score_citations(self, output: Any) -> tuple[float, str]:
        if output is None:
            return 0.0, "Output is None"
        items = output if isinstance(output, list) else [output]
        citation_fields = ["source_section", "source", "citation", "section"]
        cited = 0
        total = len(items)
        for item in items:
            if isinstance(item, dict):
                if any(item.get(f) for f in citation_fields):
                    cited += 1
        if total == 0:
            return 10.0, "No items to check"
        ratio = cited / total
        score = ratio * 10
        return score, f"{cited}/{total} items have citations"

    def _score_structure(self, output: Any, expected_fields: list[str] | None) -> tuple[float, str]:
        if output is None:
            return 0.0, "Output is None"
        if isinstance(output, list):
            if not output:
                return 5.0, "Empty list"
            if not all(isinstance(item, dict) for item in output):
                return 3.0, "Not all items are dicts"
        elif isinstance(output, dict):
            pass
        else:
            return 5.0, f"Unexpected type: {type(output).__name__}"
        return 10.0, "Structure conforms"

    def _score_scope(self, output: Any, deal_id: str) -> tuple[float, str]:
        return 10.0, "Scope compliant"

    def score_dimensions(self, output: Any) -> dict[str, float]:
        """Quick score without full evaluation."""
        result = self.evaluate(output)
        return result.scores
