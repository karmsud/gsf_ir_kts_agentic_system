"""
Escalation management — merged KTS EscalationManager + ABS EscalationHandler.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .models import EscalationReport


# ── KTS Legacy Interface ──────────────────────────────────────

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


# ── ABS Escalation Types ─────────────────────────────────────

class ABSEscalationType(str, Enum):
    EXTRACTION_AMBIGUITY = "extraction_ambiguity"
    CONFIDENCE_LOW = "confidence_low"
    QUALITY_GATE_FAILURE = "quality_gate_failure"
    CONTRADICTORY_DATA = "contradictory_data"
    MISSING_DATA = "missing_data"
    SCOPE_VIOLATION = "scope_violation"


@dataclass
class ABSEscalationReport:
    """Structured escalation when an ABS agent is blocked."""
    escalation_type: ABSEscalationType
    agent: str
    deal_id: str
    context: str
    solutions_attempted: list[str] = field(default_factory=list)
    root_blocker: str = ""
    impact: str = ""
    recommended_action: str = ""

    def to_dict(self) -> dict:
        return {
            "escalation_type": self.escalation_type.value,
            "agent": self.agent,
            "deal_id": self.deal_id,
            "context": self.context,
            "solutions_attempted": self.solutions_attempted,
            "root_blocker": self.root_blocker,
            "impact": self.impact,
            "recommended_action": self.recommended_action,
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        }


class ABSEscalationHandler:
    """Manages ABS escalation reports — save/load from deal folder."""

    def create_report(
        self,
        escalation_type: ABSEscalationType,
        agent: str,
        deal_id: str,
        context: str,
        solutions_attempted: list[str] | None = None,
        root_blocker: str = "",
        impact: str = "",
        recommended_action: str = "",
    ) -> ABSEscalationReport:
        return ABSEscalationReport(
            escalation_type=escalation_type,
            agent=agent,
            deal_id=deal_id,
            context=context,
            solutions_attempted=solutions_attempted or [],
            root_blocker=root_blocker,
            impact=impact,
            recommended_action=recommended_action,
        )

    def save(self, report: ABSEscalationReport, deal_path: Path) -> Path:
        esc_dir = deal_path / "logs" / "escalations"
        esc_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"escalation_{report.agent}_{timestamp}.json"
        filepath = esc_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        return filepath

    def load_all(self, deal_path: Path) -> list[dict]:
        esc_dir = deal_path / "logs" / "escalations"
        if not esc_dir.exists():
            return []
        reports = []
        for fp in sorted(esc_dir.glob("escalation_*.json")):
            with open(fp, "r", encoding="utf-8") as f:
                reports.append(json.load(f))
        return reports

    def has_unresolved(self, deal_path: Path) -> bool:
        esc_dir = deal_path / "logs" / "escalations"
        if not esc_dir.exists():
            return False
        return any(esc_dir.glob("escalation_*.json"))
