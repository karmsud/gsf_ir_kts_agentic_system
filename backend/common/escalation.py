from __future__ import annotations

from .models import EscalationReport


class EscalationManager:
    @staticmethod
    def low_confidence(message: str, contacts: list[str] | None = None) -> EscalationReport:
        return EscalationReport(
            type="LOW_CONFIDENCE",
            severity="warning",
            message=message,
            suggested_contacts=contacts or [],
        )

    @staticmethod
    def agent_error(message: str, contacts: list[str] | None = None) -> EscalationReport:
        return EscalationReport(
            type="AGENT_ERROR",
            severity="critical",
            message=message,
            suggested_contacts=contacts or [],
        )
