from __future__ import annotations

from config import KTSConfig
from .escalation import EscalationManager
from .models import AgentResult


class QualityGate:
    def __init__(self, config: KTSConfig):
        self.config = config

    def apply(self, result: AgentResult) -> AgentResult:
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
