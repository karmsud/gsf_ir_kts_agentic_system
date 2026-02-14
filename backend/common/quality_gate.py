from __future__ import annotations

from config import KTSConfig
from .escalation import EscalationManager
from .models import AgentResult


class QualityGate:
    def __init__(self, config: KTSConfig):
        self.config = config

    def apply(self, result: AgentResult) -> AgentResult:
        if result.confidence >= self.config.confidence_high:
            return result

        if result.confidence >= self.config.confidence_medium:
            if result.reasoning:
                result.reasoning += " | Confidence medium; review recommended."
            else:
                result.reasoning = "Confidence medium; review recommended."
            return result

        result.escalation = EscalationManager.low_confidence(
            "Confidence too low for autonomous acceptance."
        )
        return result
