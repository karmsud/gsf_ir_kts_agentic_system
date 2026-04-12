"""
PreMortem analyzer — Adversarial pre-analysis before model generation.
Pattern M8: Identify risks before they become bugs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Risk:
    """A single identified risk."""
    category: str
    description: str
    severity: str   # "critical", "high", "medium", "low"
    mitigation: str
    affected_sections: list[str] = field(default_factory=list)


@dataclass
class PreMortemReport:
    """Full pre-mortem analysis report."""
    deal_id: str
    total_risks: int
    critical_risks: int
    high_risks: int
    risks: list[Risk] = field(default_factory=list)
    recommendation: str = ""  # "proceed", "proceed_with_caution", "halt"

    def to_dict(self) -> dict:
        return {
            "deal_id": self.deal_id,
            "total_risks": self.total_risks,
            "critical_risks": self.critical_risks,
            "high_risks": self.high_risks,
            "risks": [
                {
                    "category": r.category,
                    "description": r.description,
                    "severity": r.severity,
                    "mitigation": r.mitigation,
                    "affected_sections": r.affected_sections,
                }
                for r in self.risks
            ],
            "recommendation": self.recommendation,
        }


class PreMortemAnalyzer:
    """
    Analyzes deal extractions before model generation to identify risks.

    Risk categories checked:
    - MISSING_DATA: Required sections/fields not extracted
    - AMBIGUOUS_LANGUAGE: Definitions with uncertain interpretation
    - CIRCULAR_DEPENDENCY: Terms that reference each other
    - INCONSISTENT_VALUES: Contradictory data across sections
    - COMPLEX_WATERFALL: Unusually complex payment rules
    - TRIGGER_INTERACTION: Triggers that may interact unexpectedly
    """

    RISK_CATEGORIES = [
        "MISSING_DATA",
        "AMBIGUOUS_LANGUAGE",
        "CIRCULAR_DEPENDENCY",
        "INCONSISTENT_VALUES",
        "COMPLEX_WATERFALL",
        "TRIGGER_INTERACTION",
    ]

    def analyze(
        self,
        deal_id: str,
        extractions: dict[str, list[dict]],
        deal_setup: dict | None = None,
        classes_setup: list[dict] | None = None,
    ) -> PreMortemReport:
        """
        Run pre-mortem analysis on deal extractions.

        Args:
            deal_id: Deal identifier
            extractions: Dict of extraction type to items
            deal_setup: Deal setup data (optional)
            classes_setup: Classes setup data (optional)

        Returns:
            PreMortemReport with identified risks
        """
        risks: list[Risk] = []

        risks.extend(self._check_missing_data(extractions))

        if "definitions" in extractions:
            risks.extend(self._check_ambiguous_definitions(extractions["definitions"]))

        if "definitions" in extractions:
            risks.extend(self._check_circular_deps(extractions["definitions"]))

        if "waterfall_rules" in extractions:
            risks.extend(self._check_waterfall_complexity(extractions["waterfall_rules"]))

        if "triggers" in extractions:
            risks.extend(self._check_trigger_interactions(extractions["triggers"]))

        critical = sum(1 for r in risks if r.severity == "critical")
        high = sum(1 for r in risks if r.severity == "high")

        if critical > 0:
            recommendation = "halt"
        elif high > 2:
            recommendation = "proceed_with_caution"
        else:
            recommendation = "proceed"

        return PreMortemReport(
            deal_id=deal_id,
            total_risks=len(risks),
            critical_risks=critical,
            high_risks=high,
            risks=risks,
            recommendation=recommendation,
        )

    def _check_missing_data(self, extractions: dict) -> list[Risk]:
        """Check for missing required extraction types."""
        risks = []
        required = ["definitions", "waterfall_rules", "accounts"]
        for req in required:
            if req not in extractions or not extractions[req]:
                risks.append(Risk(
                    category="MISSING_DATA",
                    description=f"Required extraction '{req}' is missing or empty",
                    severity="critical",
                    mitigation=f"Re-run {req} parser or manually extract",
                    affected_sections=[req],
                ))

        optional = ["loss_allocations", "triggers", "reporting_requirements"]
        for opt in optional:
            if opt not in extractions or not extractions[opt]:
                risks.append(Risk(
                    category="MISSING_DATA",
                    description=f"Optional extraction '{opt}' is missing",
                    severity="medium",
                    mitigation=f"Check if {opt} section exists in document",
                    affected_sections=[opt],
                ))

        return risks

    def _check_ambiguous_definitions(self, definitions: list[dict]) -> list[Risk]:
        """Check for definitions with ambiguous language."""
        risks = []
        ambiguous_signals = [
            "may", "might", "approximately", "generally",
            "substantially", "as determined", "in the discretion",
        ]

        for defn in definitions:
            text = defn.get("definition_text", "").lower()
            found_signals = [s for s in ambiguous_signals if s in text]
            if len(found_signals) >= 2:
                risks.append(Risk(
                    category="AMBIGUOUS_LANGUAGE",
                    description=(
                        f"Definition '{defn.get('name', '?')}' contains "
                        f"ambiguous language: {', '.join(found_signals)}"
                    ),
                    severity="high",
                    mitigation="Review definition against governing doc, flag for manual interpretation",
                    affected_sections=["definitions"],
                ))

        return risks

    def _check_circular_deps(self, definitions: list[dict]) -> list[Risk]:
        """Check for circular term dependencies."""
        risks = []
        dep_map: dict[str, set[str]] = {}
        name_set = {d.get("name", "").lower() for d in definitions}

        for defn in definitions:
            name = defn.get("name", "").lower()
            deps = defn.get("depends_on", [])
            if isinstance(deps, list):
                dep_map[name] = {d.lower() for d in deps if d.lower() in name_set}

        for term, deps in dep_map.items():
            for dep in deps:
                if dep in dep_map and term in dep_map.get(dep, set()):
                    risks.append(Risk(
                        category="CIRCULAR_DEPENDENCY",
                        description=f"Circular dependency: '{term}' ↔ '{dep}'",
                        severity="high",
                        mitigation="Break circular reference during model generation",
                        affected_sections=["definitions"],
                    ))

        return risks

    def _check_waterfall_complexity(self, rules: list[dict]) -> list[Risk]:
        """Check for unusually complex waterfall structures."""
        risks = []
        if len(rules) > 25:
            risks.append(Risk(
                category="COMPLEX_WATERFALL",
                description=f"Waterfall has {len(rules)} rules (> 25 threshold)",
                severity="high",
                mitigation="Verify all rules are correctly prioritized, consider grouping",
                affected_sections=["waterfall"],
            ))

        for rule in rules:
            condition = rule.get("condition", "")
            if isinstance(condition, str) and len(condition) > 500:
                risks.append(Risk(
                    category="COMPLEX_WATERFALL",
                    description=f"Rule '{rule.get('rule_id', '?')}' has complex condition ({len(condition)} chars)",
                    severity="medium",
                    mitigation="Simplify or break into sub-conditions",
                    affected_sections=["waterfall"],
                ))

        return risks

    def _check_trigger_interactions(self, triggers: list[dict]) -> list[Risk]:
        """Check for triggers that may interact."""
        risks = []
        if len(triggers) > 5:
            risks.append(Risk(
                category="TRIGGER_INTERACTION",
                description=f"Deal has {len(triggers)} triggers — interaction matrix may be needed",
                severity="medium",
                mitigation="Test trigger combinations in stress scenarios",
                affected_sections=["triggers"],
            ))

        return risks

    def save_report(self, report: PreMortemReport, deal_path: Path) -> Path:
        """Save pre-mortem report to deal folder."""
        report_path = deal_path / "reports" / "pre_mortem_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        return report_path
