"""
Phase 17 — Diff Engine

Compares retrieval results across two or more scopes, highlighting
specific differences in language, amounts, dates, and obligations.

Output format::

    {
        "query": "...",
        "diffs": [
            {
                "field": "Distribution Date timing",
                "values": {
                    "fin_deal1/PSA": "the 25th day of each month",
                    "fin_deal2/PSA": "the last business day of each month"
                },
                "diff_type": "value_difference",
                "significance": "high"
            }
        ],
        "common": [...],
        "summary": "..."
    }
"""
from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class DiffEngine:
    """Creates structured diffs between deal documents."""

    def __init__(self, *, config: Any = None) -> None:
        self.config = config
        self._similarity_threshold = getattr(
            config, "phase17_diff_similarity_threshold", 0.85
        ) if config else 0.85

    def diff(
        self,
        results_by_scope: Dict[str, List[dict]],
        query: str,
    ) -> dict:
        """Compute structured diff across scope results.

        Args:
            results_by_scope: Mapping of ``scope_slug → list[result_dict]``.
                Each result dict should contain at least ``text`` and
                optionally ``section_number``.
            query: Original user query for context.

        Returns:
            Structured diff dict with keys: ``query``, ``diffs``,
            ``common``, ``summary``, ``scope_count``.
        """
        scopes = list(results_by_scope.keys())
        if len(scopes) < 2:
            return {
                "query": query,
                "diffs": [],
                "common": [],
                "summary": "Need at least 2 scopes for diff.",
                "scope_count": len(scopes),
            }

        # Extract best matching text per scope
        scope_texts: Dict[str, str] = {}
        for scope, results in results_by_scope.items():
            texts = [r.get("text", "") for r in results if r.get("text")]
            scope_texts[scope] = texts[0] if texts else ""

        diffs: List[dict] = []
        common: List[dict] = []

        # Pairwise comparison
        for i in range(len(scopes)):
            for j in range(i + 1, len(scopes)):
                scope_a, scope_b = scopes[i], scopes[j]
                text_a = scope_texts.get(scope_a, "")
                text_b = scope_texts.get(scope_b, "")

                if not text_a or not text_b:
                    continue

                similarity = SequenceMatcher(None, text_a, text_b).ratio()

                if similarity >= self._similarity_threshold:
                    common.append({
                        "scopes": [scope_a, scope_b],
                        "similarity": round(similarity, 3),
                        "text_preview": text_a[:200],
                    })
                else:
                    # Identify specific differences
                    field_diffs = self._extract_field_diffs(text_a, text_b, scope_a, scope_b)
                    diffs.extend(field_diffs)

        # Generate summary
        summary = self._generate_summary(diffs, common, scopes, query)

        return {
            "query": query,
            "diffs": diffs,
            "common": common,
            "summary": summary,
            "scope_count": len(scopes),
        }

    def _extract_field_diffs(
        self,
        text_a: str,
        text_b: str,
        scope_a: str,
        scope_b: str,
    ) -> List[dict]:
        """Extract specific field-level diffs between two texts."""
        diffs: List[dict] = []

        # Date differences
        dates_a = set(re.findall(r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:day|business\s+day)\b", text_a, re.IGNORECASE))
        dates_b = set(re.findall(r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:day|business\s+day)\b", text_b, re.IGNORECASE))
        if dates_a != dates_b:
            diffs.append({
                "field": "Date/Timing",
                "values": {scope_a: ", ".join(dates_a) or "(none)", scope_b: ", ".join(dates_b) or "(none)"},
                "diff_type": "value_difference",
                "significance": "high",
            })

        # Amount differences (dollar amounts, percentages)
        amounts_a = set(re.findall(r"\$[\d,]+(?:\.\d+)?|\d+(?:\.\d+)?%", text_a))
        amounts_b = set(re.findall(r"\$[\d,]+(?:\.\d+)?|\d+(?:\.\d+)?%", text_b))
        if amounts_a != amounts_b:
            diffs.append({
                "field": "Amounts/Percentages",
                "values": {scope_a: ", ".join(amounts_a) or "(none)", scope_b: ", ".join(amounts_b) or "(none)"},
                "diff_type": "value_difference",
                "significance": "high",
            })

        # Overall text diff if specific fields didn't capture it
        if not diffs:
            similarity = SequenceMatcher(None, text_a, text_b).ratio()
            diffs.append({
                "field": "Language",
                "values": {scope_a: text_a[:300], scope_b: text_b[:300]},
                "diff_type": "text_difference",
                "significance": "medium" if similarity > 0.5 else "high",
            })

        return diffs

    @staticmethod
    def _generate_summary(
        diffs: List[dict],
        common: List[dict],
        scopes: List[str],
        query: str,
    ) -> str:
        """Generate a natural language summary of the diff results."""
        parts = [f'Comparison of "{query}" across {len(scopes)} scopes:']

        if common:
            parts.append(f"- {len(common)} aspect(s) are substantively similar")
        if diffs:
            high = sum(1 for d in diffs if d.get("significance") == "high")
            parts.append(f"- {len(diffs)} difference(s) found ({high} high significance)")
        if not diffs and not common:
            parts.append("- Insufficient data for comparison")

        return " ".join(parts)
