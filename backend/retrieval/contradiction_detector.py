"""
Phase 15.2 — Contradiction Detection (Two-Deal).

Given the same concept from two scopes, detect binary contradictions
(inclusion/exclusion conflicts), not mere divergences.

Usage::

    detector = ContradictionDetector(llm_call_fn=my_llm)
    result = await detector.detect(
        concept="Servicer Advance",
        scope_a="bear_2006_HE1", definition_a="...",
        scope_b="bear_2006_HE2", definition_b="...",
    )
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Prompt ────────────────────────────────────────────────────

CONTRADICTION_PROMPT = """You are comparing how "{concept}" is defined in two legal documents.

Document A ({scope_a}):
{definition_a}

Document B ({scope_b}):
{definition_b}

Answer ONLY with a JSON object:
{{
  "contradicts": true or false,
  "contradiction_type": "inclusion/exclusion" or "scope" or "condition" or "party" or "amount" or null,
  "summary": "one sentence describing the contradiction, or null if none",
  "severity": "material" or "minor" or null
}}"""


# ── Data Structures ───────────────────────────────────────────

@dataclass
class ContradictionResult:
    """Result of a two-deal contradiction check."""

    concept: str
    scope_a: str
    scope_b: str
    contradicts: bool = False
    contradiction_type: Optional[str] = None  # inclusion/exclusion, scope, condition, party, amount
    summary: Optional[str] = None
    severity: Optional[str] = None  # material, minor
    raw_response: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "concept": self.concept,
            "scope_a": self.scope_a,
            "scope_b": self.scope_b,
            "contradicts": self.contradicts,
            "contradiction_type": self.contradiction_type,
            "summary": self.summary,
            "severity": self.severity,
        }


# ── Contradiction Detector ────────────────────────────────────

class ContradictionDetector:
    """
    Phase 15.2 — Pairwise contradiction detection between two deals.

    Focuses on binary-dimension conflicts (inclusion/exclusion),
    not mere wording differences.
    """

    def __init__(
        self,
        llm_call_fn=None,
        max_tokens: int = 500,
        temperature: float = 0.0,
    ) -> None:
        self.llm_call_fn = llm_call_fn
        self.max_tokens = max_tokens
        self.temperature = temperature

    async def detect(
        self,
        concept: str,
        scope_a: str,
        definition_a: str,
        scope_b: str,
        definition_b: str,
    ) -> ContradictionResult:
        """
        Detect contradictions between two definitions of the same concept.

        Returns a ContradictionResult with the assessment.
        """
        if self.llm_call_fn is None:
            return ContradictionResult(
                concept=concept, scope_a=scope_a, scope_b=scope_b,
                raw_response="No LLM available",
            )

        prompt = CONTRADICTION_PROMPT.format(
            concept=concept,
            scope_a=scope_a,
            definition_a=definition_a,
            scope_b=scope_b,
            definition_b=definition_b,
        )

        try:
            raw = await self.llm_call_fn(prompt, self.max_tokens, self.temperature)

            # Parse JSON response
            parsed = self._parse_json(raw)

            return ContradictionResult(
                concept=concept,
                scope_a=scope_a,
                scope_b=scope_b,
                contradicts=parsed.get("contradicts", False),
                contradiction_type=parsed.get("contradiction_type"),
                summary=parsed.get("summary"),
                severity=parsed.get("severity"),
                raw_response=raw.strip(),
            )

        except Exception as exc:
            logger.error("[ContradictionDetector] LLM call failed: %s", exc)
            return ContradictionResult(
                concept=concept, scope_a=scope_a, scope_b=scope_b,
                raw_response=f"Detection failed: {exc}",
            )

    async def detect_batch(
        self,
        concept: str,
        definitions: Dict[str, str],
    ) -> List[ContradictionResult]:
        """
        Compare all pairs of definitions for the same concept.

        Parameters
        ----------
        definitions : dict
            ``{scope_slug: definition_text}``

        Returns
        -------
        list[ContradictionResult]
            One per unique pair.
        """
        slugs = list(definitions.keys())
        results: List[ContradictionResult] = []

        for i in range(len(slugs)):
            for j in range(i + 1, len(slugs)):
                result = await self.detect(
                    concept=concept,
                    scope_a=slugs[i],
                    definition_a=definitions[slugs[i]],
                    scope_b=slugs[j],
                    definition_b=definitions[slugs[j]],
                )
                results.append(result)

        return results

    @staticmethod
    def _parse_json(raw: str) -> Dict[str, Any]:
        """Best-effort JSON parsing from LLM output."""
        raw = raw.strip()
        # Try direct parse first
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # Try extracting from markdown code block
        import re
        match = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass
        # Try finding first { ... }
        brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass
        return {"contradicts": False, "summary": "Failed to parse LLM response"}


# ── Intent Detection ──────────────────────────────────────────

CONTRADICTION_SIGNALS = [
    "contradict", "conflict", "agree", "disagree", "same",
    "different", "diverge", "consistent", "inconsistent",
    "match", "mismatch", "align",
]


def is_contradiction_query(query: str) -> bool:
    """Detect if a query is asking about contradictions between deals."""
    q = query.lower()
    return any(signal in q for signal in CONTRADICTION_SIGNALS)
