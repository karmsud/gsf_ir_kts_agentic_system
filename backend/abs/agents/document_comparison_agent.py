"""
DocumentComparisonAgent — Track A: Document Intelligence + Ingestion

Compares the current deal's extractions against known portfolio deals
to surface structural similarities, anomalies, and potential issues.

No LLM / OpenAI dependency — all work is performed via the deterministic
deal_comparator and report_generator skill functions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.agents.base_agent import AgentBase
from backend.agents.agent_tools import ToolRegistry
from backend.common.confidence import ConfidenceScore, ConfidenceTier
from backend.abs.deal_scope import DealScope
from backend.abs.skills.deal_comparator import compare_deals, DealComparisonResult
from backend.abs.skills.report_generator import generate_report
from config import KTSConfig


class DocumentComparisonAgent(AgentBase):
    """
    Compare a deal against other portfolio deals.

    Responsibilities:
    1. Load current deal extractions from ``deal_path/extractions/``.
    2. Discover comparison deals from the portfolio directory.
    3. Run ``compare_deals()`` for each comparison pair.
    4. Score overall similarity and flag anomalies.
    5. Generate a Markdown comparison report via ``generate_report()``.
    """

    agent_name = "document_comparison"

    def __init__(
        self,
        config: KTSConfig,
        deal_scope: DealScope,
        tool_registry: ToolRegistry,
        llm_callable=None,
    ) -> None:
        super().__init__(config, deal_scope=deal_scope, tool_registry=tool_registry, llm_callable=llm_callable)

    # ------------------------------------------------------------------
    # Prompt structure
    # ------------------------------------------------------------------

    def _get_mission(self) -> str:
        return (
            "Compare the current deal against known portfolio deals to "
            "identify structural similarities, differences, and anomalies. "
            "Produce a comparison report that highlights sections that "
            "significantly deviate from portfolio norms."
        )

    def _get_actions(self) -> list[str]:
        return [
            "Load current deal extractions from deal_path/extractions/.",
            "Discover available comparison deals in the portfolio.",
            "Load extractions for each comparison deal.",
            "Run compare_deals() for each pair (current vs. comparison).",
            "Compute per-section and overall similarity scores.",
            "Identify anomalies: sections with unusually low similarity.",
            "Generate a Markdown comparison report.",
        ]

    def _get_output_spec(self) -> str:
        return (
            "dict with keys:\n"
            "  current_deal_id: str\n"
            "  comparisons: list[{\n"
            "    comparison_deal_id: str,\n"
            "    overall_similarity: float,\n"
            "    section_scores: dict[section, float],\n"
            "    only_in_current: dict[section, list[str]],\n"
            "    only_in_comparison: dict[section, list[str]],\n"
            "  }]\n"
            "  anomalies: list[{section, score, detail}]\n"
            "  report_path: str\n"
        )

    def _get_validation_rules(self) -> list[str]:
        return [
            "At least one comparison must be performed (if portfolio deals exist).",
            "Overall similarity must be between 0.0 and 1.0.",
            "Anomalies must reference a specific section and score.",
            "Report file must be written to deal_path/reports/.",
        ]

    # ------------------------------------------------------------------
    # Core execution
    # ------------------------------------------------------------------

    def _run(self, task: dict[str, Any]) -> dict[str, Any]:
        anomaly_threshold: float = task.get("anomaly_threshold", 0.50)

        current_extractions = self._load_extractions(self.deal_scope.deal_path)
        if not current_extractions:
            return {
                "current_deal_id": self.deal_scope.deal_id,
                "comparisons": [],
                "anomalies": [],
                "report_path": "",
                "error": "No extractions found for current deal.",
            }

        comp_deal_ids = self._resolve_comparison_deals(task)

        comparisons: list[dict[str, Any]] = []
        all_anomalies: list[dict[str, Any]] = []

        for comp_id in comp_deal_ids:
            comp_path = self.deal_scope.deals_root / comp_id
            if not comp_path.exists():
                continue

            comp_extractions = self._load_extractions(comp_path)
            if not comp_extractions:
                continue

            result: DealComparisonResult = compare_deals(
                deal_a_extractions=current_extractions,
                deal_b_extractions=comp_extractions,
                deal_a_id=self.deal_scope.deal_id,
                deal_b_id=comp_id,
            )

            section_scores: dict[str, float] = {}
            only_in_current: dict[str, list[str]] = {}
            only_in_comparison: dict[str, list[str]] = {}

            for sec_name, sec_comp in result.section_comparisons.items():
                section_scores[sec_name] = sec_comp.similarity_score

                if sec_comp.only_in_a:
                    only_in_current[sec_name] = sec_comp.only_in_a
                if sec_comp.only_in_b:
                    only_in_comparison[sec_name] = sec_comp.only_in_b

                if sec_comp.similarity_score < anomaly_threshold:
                    all_anomalies.append({
                        "section": sec_name,
                        "score": round(sec_comp.similarity_score, 4),
                        "comparison_deal": comp_id,
                        "detail": (
                            f"Section '{sec_name}' similarity "
                            f"({sec_comp.similarity_score:.2%}) is below "
                            f"threshold ({anomaly_threshold:.2%})."
                        ),
                    })

            comparisons.append({
                "comparison_deal_id": comp_id,
                "overall_similarity": round(result.overall_similarity, 4),
                "section_scores": {
                    k: round(v, 4) for k, v in section_scores.items()
                },
                "only_in_current": only_in_current,
                "only_in_comparison": only_in_comparison,
            })

        report_path = self._generate_report(comparisons, all_anomalies)

        return {
            "current_deal_id": self.deal_scope.deal_id,
            "comparisons": comparisons,
            "anomalies": all_anomalies,
            "report_path": str(report_path) if report_path else "",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_extractions(deal_path: Path) -> dict[str, list[dict]]:
        ext_dir = deal_path / "extractions"
        if not ext_dir.exists():
            return {}

        extractions: dict[str, list[dict]] = {}
        for json_file in sorted(ext_dir.glob("*.json")):
            section_name = json_file.stem
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    extractions[section_name] = data
                elif isinstance(data, dict) and "items" in data:
                    extractions[section_name] = data["items"]
                else:
                    extractions[section_name] = [data] if data else []
            except (json.JSONDecodeError, OSError):
                continue

        return extractions

    def _resolve_comparison_deals(self, task: dict[str, Any]) -> list[str]:
        if "comparison_deal_ids" in task and task["comparison_deal_ids"]:
            return list(task["comparison_deal_ids"])

        deals_root = self.deal_scope.deals_root
        if not deals_root.exists():
            return []

        return [
            d.name
            for d in sorted(deals_root.iterdir())
            if d.is_dir()
            and d.name != self.deal_scope.deal_id
            and (d / "extractions").exists()
        ]

    def _generate_report(
        self,
        comparisons: list[dict[str, Any]],
        anomalies: list[dict[str, Any]],
    ) -> Path | None:
        if not comparisons:
            return None

        report_dir = self.deal_scope.resolve("reports")
        report_data = {
            "current_deal_id": self.deal_scope.deal_id,
            "comparisons": comparisons,
            "anomalies": anomalies,
        }

        report_path = generate_report(
            report_type="comparison",
            data=report_data,
            output_dir=report_dir,
            deal_id=self.deal_scope.deal_id,
        )

        self._state["last_comparison_report"] = str(report_path)
        return report_path

    # ------------------------------------------------------------------
    # Quality gate overrides
    # ------------------------------------------------------------------

    def _score_completeness(self, result: Any, task: dict) -> float:
        comps = result.get("comparisons", [])
        expected = len(self._resolve_comparison_deals(task))
        if expected == 0:
            return 10.0
        ratio = len(comps) / expected
        return min(ratio * 10.0, 10.0)

    def _score_accuracy(self, result: Any, task: dict) -> float:
        comps = result.get("comparisons", [])
        if not comps:
            return 10.0
        for comp in comps:
            sim = comp.get("overall_similarity", -1)
            if not (0.0 <= sim <= 1.0):
                return 5.0
        return 10.0

    def _score_confidence(self, result: Any, task: dict[str, Any]) -> ConfidenceScore:
        comps = result.get("comparisons", [])
        if not comps:
            return ConfidenceScore(
                0.70, ConfidenceTier.MEDIUM,
                "No comparisons performed.",
            )
        avg_sim = sum(c["overall_similarity"] for c in comps) / len(comps)
        count_factor = min(len(comps) / 3, 1.0)
        value = round(min(0.60 + count_factor * 0.30 + avg_sim * 0.10, 1.0), 4)
        tier = self._categorize_confidence(value)
        return ConfidenceScore(
            value=value,
            tier=tier,
            reasoning=(
                f"Based on {len(comps)} comparisons with average similarity "
                f"{avg_sim:.2%}."
            ),
        )

    def _get_artifacts(self, result: Any) -> list[str]:
        report = result.get("report_path", "")
        return [report] if report else []
