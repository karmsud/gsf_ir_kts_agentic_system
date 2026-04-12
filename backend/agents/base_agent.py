"""
AgentBase — Merged base class for KTS and ABS agents.

KTS agents: subclass, override execute(request) -> AgentResult
ABS agents: subclass, override _run(task) + 4 spec methods, call execute_abs(task) -> AgentOutput

Backward compatibility:
    - __init__(config) still works for existing KTS agents
    - execute(request) -> AgentResult still works
    - quality_check(result) still works
"""

from __future__ import annotations

import datetime
import json
from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.agents.agent_tools import ToolRegistry
from backend.common.confidence import ConfidenceTier, ConfidenceScore
from backend.common.escalation import ABSEscalationType, ABSEscalationReport
from backend.common.models import AgentResult
from backend.common.quality_gate import QualityDimension, QualityGate, QualityResult
from config import KTSConfig

# Lazy import to avoid circular dependency — only used by ABS agents
_DealScope = None
_StructuredErrorLogger = None
_EscalationRequired = None


def _lazy_abs_imports():
    global _DealScope, _StructuredErrorLogger, _EscalationRequired
    if _DealScope is None:
        from backend.abs.deal_scope import DealScope as _DS
        from backend.abs.errors import (
            EscalationRequired as _ER,
            StructuredErrorLogger as _SEL,
        )
        _DealScope = _DS
        _StructuredErrorLogger = _SEL
        _EscalationRequired = _ER


# ── ABS Agent Output ──────────────────────────────────────────


@dataclass
class AgentOutput:
    """Standardized output from an ABS agent."""
    agent_name: str
    deal_id: str
    result: Any
    quality: QualityResult
    confidence: ConfidenceScore
    artifacts_produced: list[str] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat()
    )


# ══════════════════════════════════════════════════════════════
# AgentBase — merged
# ══════════════════════════════════════════════════════════════


class AgentBase(ABC):
    """
    Merged base class for KTS and ABS agents.

    KTS agents:
        - Override execute(request: dict) -> AgentResult
        - Call quality_check(result) manually

    ABS agents:
        - Pass deal_scope and tool_registry to __init__
        - Override _run(task), _get_mission(), _get_actions(),
          _get_output_spec(), _get_validation_rules()
        - Call execute_abs(task) -> AgentOutput (has quality gate + retry)
    """

    agent_name: str = "base-agent"
    agent_version: str = "1.0.0"

    # ABS quality settings
    MAX_RETRIES = 3
    MIN_QUALITY_SCORE = 8.0

    def __init__(
        self,
        config: KTSConfig,
        *,
        deal_scope: Any | None = None,
        tool_registry: ToolRegistry | None = None,
        llm_callable: Any | None = None,
    ):
        self.config = config
        self.quality_gate = QualityGate(config)

        # ABS extensions (optional — only ABS agents set these)
        self.deal_scope = deal_scope
        self.tool_registry = tool_registry or ToolRegistry()
        self.error_logger: Any = None
        self._state: dict[str, Any] = {}
        self._llm = llm_callable  # Phase 22: optional LLM callable

        if deal_scope is not None:
            _lazy_abs_imports()
            self.error_logger = _StructuredErrorLogger(deal_scope.deal_path)

    # ── KTS Interface (backward compat) ──────────────────────

    def execute(self, request: dict) -> AgentResult:
        """
        Override for KTS agents.
        ABS agents override _run() instead and call execute_abs().
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement execute() or _run()"
        )

    def quality_check(self, result: AgentResult) -> AgentResult:
        """KTS backward-compatible quality check."""
        return self.quality_gate.apply(result)

    # ── ABS Interface ────────────────────────────────────────

    def execute_abs(self, task: dict[str, Any]) -> AgentOutput:
        """
        ABS execution with quality gate, retry loop, and confidence scoring.

        Args:
            task: Task-specific input dictionary

        Returns:
            AgentOutput with result, quality scores, and confidence

        Raises:
            EscalationRequired: if quality gate fails after max retries
        """
        _lazy_abs_imports()
        feedback: str | None = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                if feedback:
                    task["_quality_feedback"] = feedback
                raw_result = self._run(task)

                # Evaluate quality
                quality = self._evaluate_quality(raw_result, task)

                # Score confidence
                confidence = self._score_confidence(raw_result, task)

                if quality.passed:
                    output = AgentOutput(
                        agent_name=self.agent_name,
                        deal_id=self.deal_scope.deal_id if self.deal_scope else "",
                        result=raw_result,
                        quality=quality,
                        confidence=confidence,
                        artifacts_produced=self._get_artifacts(raw_result),
                    )
                    self._save_state()
                    return output

                # Quality gate failed — prepare feedback for retry
                feedback = quality.feedback
                quality.retry_count = attempt + 1

            except Exception as e:
                if self.error_logger:
                    self.error_logger.log_error(e)
                if attempt == self.MAX_RETRIES:
                    raise _EscalationRequired(
                        report=ABSEscalationReport(
                            escalation_type=ABSEscalationType.QUALITY_GATE_FAILURE,
                            agent=self.agent_name,
                            deal_id=self.deal_scope.deal_id if self.deal_scope else "",
                            context=str(e),
                            solutions_attempted=[
                                f"attempt_{i+1}" for i in range(attempt + 1)
                            ],
                            root_blocker=str(e),
                            impact="Agent blocked",
                            recommended_action="Manual review required",
                        ).to_dict()
                    )

        # Max retries exhausted
        raise _EscalationRequired(
            report=ABSEscalationReport(
                escalation_type=ABSEscalationType.QUALITY_GATE_FAILURE,
                agent=self.agent_name,
                deal_id=self.deal_scope.deal_id if self.deal_scope else "",
                context=f"Quality gate failed after {self.MAX_RETRIES} retries",
                solutions_attempted=[
                    f"attempt_{i+1}" for i in range(self.MAX_RETRIES + 1)
                ],
                root_blocker=feedback or "Unknown quality failure",
                impact="Agent output below quality threshold",
                recommended_action="Review agent output and quality criteria",
            ).to_dict()
        )

    # ── ABS Subclass Overrides ───────────────────────────────

    def _run(self, task: dict[str, Any]) -> Any:
        """ABS agents override this. Raw execution without quality gate."""
        raise NotImplementedError(f"{type(self).__name__} must implement _run()")

    def _get_mission(self) -> str:
        """Return the agent's mission statement. Override in ABS agents."""
        return ""

    def _get_actions(self) -> list[str]:
        """Return list of actions the agent performs. Override in ABS agents."""
        return []

    def _get_output_spec(self) -> str:
        """Return expected output format description. Override in ABS agents."""
        return ""

    def _get_validation_rules(self) -> list[str]:
        """Return validation criteria. Override in ABS agents."""
        return []

    # ── ABS Prompt Structure (Decision D11) ──────────────────

    @property
    def system_prompt(self) -> str:
        """Build the MISSION/CONTEXT/INPUTS/ACTIONS/OUTPUTS/VALIDATION prompt."""
        return self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        tools = self.tool_registry.get_tools(self.agent_name)
        tool_list = "\n".join(
            f"  - {t.name}: {t.description}" for t in tools
        )
        deal_id = self.deal_scope.deal_id if self.deal_scope else "N/A"
        deal_path = str(self.deal_scope.deal_path) if self.deal_scope else "N/A"
        return f"""MISSION:
{self._get_mission()}

CONTEXT:
Deal: {deal_id}
Deal Path: {deal_path}
Available Tools:
{tool_list}

INPUTS:
{{task}}

ACTIONS:
{chr(10).join(f'  {i+1}. {a}' for i, a in enumerate(self._get_actions()))}

OUTPUTS:
{self._get_output_spec()}

VALIDATION:
{chr(10).join(f'  - {r}' for r in self._get_validation_rules())}
"""

    # ── ABS Quality Gate ─────────────────────────────────────

    def _evaluate_quality(self, result: Any, task: dict[str, Any]) -> QualityResult:
        """
        Default quality evaluation. Subclasses can override for custom checks.
        Scores on 5 dimensions, all must be >= MIN_QUALITY_SCORE.
        """
        scores = {
            QualityDimension.COMPLETENESS.value: self._score_completeness(result, task),
            QualityDimension.ACCURACY.value: self._score_accuracy(result, task),
            QualityDimension.CITATION_FIDELITY.value: self._score_citations(result, task),
            QualityDimension.STRUCTURAL_CONFORMANCE.value: self._score_structure(result, task),
            QualityDimension.DEAL_SCOPE_COMPLIANCE.value: self._score_scope(result, task),
        }

        min_score = min(scores.values())
        passed = min_score >= self.MIN_QUALITY_SCORE

        feedback_text: str | None = None
        if not passed:
            low_dims = [
                dim for dim, score in scores.items()
                if score < self.MIN_QUALITY_SCORE
            ]
            feedback_text = (
                f"Quality gate failed. Low dimensions: {low_dims}. "
                f"Scores: {scores}. Improve these areas and retry."
            )

        return QualityResult(passed=passed, scores=scores, feedback=feedback_text)

    def _score_completeness(self, result: Any, task: dict) -> float:
        """Score completeness (0-10). Override in subclass."""
        return 8.0

    def _score_accuracy(self, result: Any, task: dict) -> float:
        """Score accuracy (0-10). Override in subclass."""
        return 8.0

    def _score_citations(self, result: Any, task: dict) -> float:
        """Score citation fidelity (0-10). Override in subclass."""
        return 8.0

    def _score_structure(self, result: Any, task: dict) -> float:
        """Score structural conformance (0-10). Override in subclass."""
        return 8.0

    def _score_scope(self, result: Any, task: dict) -> float:
        """Score deal scope compliance (0-10). Override in subclass."""
        return 10.0

    # ── ABS Confidence Scoring ───────────────────────────────

    def _score_confidence(self, result: Any, task: dict[str, Any]) -> ConfidenceScore:
        """Default confidence scoring. Subclasses can override."""
        value = 0.95
        tier = self._categorize_confidence(value)
        return ConfidenceScore(value=value, tier=tier, reasoning="Default confidence")

    @staticmethod
    def _categorize_confidence(score: float) -> ConfidenceTier:
        """Map numeric score to tier. Decision D7: 90/66/0."""
        if score >= 0.90:
            return ConfidenceTier.HIGH
        elif score >= 0.66:
            return ConfidenceTier.MEDIUM
        else:
            return ConfidenceTier.LOW

    # ── ABS State Persistence (Decision D12) ─────────────────

    def _load_state(self) -> dict[str, Any]:
        """Load agent state from deal folder."""
        if not self.deal_scope:
            return self._state
        state_path = self.deal_scope.resolve(f"logs/{self.agent_name}_state.json")
        if state_path.exists():
            with open(state_path, "r", encoding="utf-8") as f:
                self._state = json.load(f)
        return self._state

    def _save_state(self) -> None:
        """Save agent state to deal folder."""
        if not self.deal_scope:
            return
        state_path = self.deal_scope.resolve(f"logs/{self.agent_name}_state.json")
        state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state["last_updated"] = datetime.datetime.now(datetime.UTC).isoformat()
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, ensure_ascii=False, default=str)

    # ── ABS Artifacts ────────────────────────────────────────

    def _get_artifacts(self, result: Any) -> list[str]:
        """Return list of artifact paths produced. Override in subclass."""
        return []

    # ── ABS Tool Access ──────────────────────────────────────

    def use_tool(self, tool_name: str, **kwargs) -> Any:
        """Invoke a registered tool with access control."""
        return self.tool_registry.invoke(tool_name, self.agent_name, **kwargs)

    def available_tools(self) -> list[str]:
        """List tool names available to this agent."""
        return [t.name for t in self.tool_registry.get_tools(self.agent_name)]

    def __repr__(self) -> str:
        deal_id = self.deal_scope.deal_id if self.deal_scope else "N/A"
        return f"{type(self).__name__}({self.agent_name}, deal={deal_id})"
