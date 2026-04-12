"""
Phase 17 — Aggregation Engine

Summarises patterns across multiple deals, detecting the common
pattern and flagging outliers.

Output format::

    {
        "query": "...",
        "pattern": "8 of 10 deals define Distribution Date as the 25th",
        "outliers": [
            {"deal": "bear_stearns_2006he3", "text": "last business day", "deviation": "timing"}
        ],
        "confidence": 0.92,
        "deal_count": 10,
        "summary": "..."
    }
"""
from __future__ import annotations

import logging
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class AggregationEngine:
    """Analyses results across N deals to find patterns and outliers."""

    def __init__(self, *, config: Any = None) -> None:
        self.config = config
        self._outlier_threshold = getattr(
            config, "phase17_aggregate_outlier_threshold", 0.70
        ) if config else 0.70

    def aggregate(
        self,
        results_by_scope: Dict[str, List[dict]],
        query: str,
    ) -> dict:
        """Find patterns and outliers across scope results.

        Args:
            results_by_scope: Mapping of ``scope_slug → list[result_dict]``.
            query: Original user query for context.

        Returns:
            Structured aggregation dict with keys: ``query``, ``pattern``,
            ``outliers``, ``confidence``, ``deal_count``, ``summary``.
        """
        scopes = list(results_by_scope.keys())
        deal_count = len(scopes)

        if deal_count < 2:
            return {
                "query": query,
                "pattern": "",
                "outliers": [],
                "confidence": 0.0,
                "deal_count": deal_count,
                "summary": "Need at least 2 scopes for aggregation.",
            }

        # Extract best matching text per scope
        scope_texts: Dict[str, str] = {}
        for scope, results in results_by_scope.items():
            texts = [r.get("text", "") for r in results if r.get("text")]
            scope_texts[scope] = texts[0] if texts else ""

        # Remove empty scopes
        scope_texts = {k: v for k, v in scope_texts.items() if v}
        if len(scope_texts) < 2:
            return {
                "query": query,
                "pattern": "",
                "outliers": [],
                "confidence": 0.0,
                "deal_count": deal_count,
                "summary": "Insufficient text results for aggregation.",
            }

        # Find majority pattern via pairwise similarity clustering
        pattern_text, pattern_scopes, outliers = self._cluster_texts(scope_texts)

        confidence = len(pattern_scopes) / len(scope_texts) if scope_texts else 0.0

        pattern_desc = (
            f"{len(pattern_scopes)} of {len(scope_texts)} deals share the common pattern"
        )

        summary = self._generate_summary(
            query, pattern_desc, pattern_text, outliers, len(scope_texts)
        )

        return {
            "query": query,
            "pattern": pattern_desc,
            "pattern_text": pattern_text[:500] if pattern_text else "",
            "pattern_scopes": pattern_scopes,
            "outliers": outliers,
            "confidence": round(confidence, 3),
            "deal_count": deal_count,
            "summary": summary,
        }

    def _cluster_texts(
        self,
        scope_texts: Dict[str, str],
    ) -> tuple[str, list[str], list[dict]]:
        """Cluster texts by similarity to find the majority pattern.

        Returns:
            Tuple of (pattern_text, pattern_scopes, outlier_dicts).
        """
        scopes = list(scope_texts.keys())
        texts = [scope_texts[s] for s in scopes]

        # Pairwise similarity matrix
        n = len(texts)
        sim_matrix: list[list[float]] = []
        for i in range(n):
            row = []
            for j in range(n):
                if i == j:
                    row.append(1.0)
                else:
                    row.append(SequenceMatcher(None, texts[i], texts[j]).ratio())
            sim_matrix.append(row)

        # Find the text that is most similar to all others (centroid)
        avg_sims = [sum(row) / n for row in sim_matrix]
        centroid_idx = max(range(n), key=lambda i: avg_sims[i])
        centroid_text = texts[centroid_idx]

        # Partition into pattern (similar to centroid) vs outliers
        pattern_scopes: list[str] = []
        outliers: list[dict] = []

        for i in range(n):
            sim_to_centroid = sim_matrix[centroid_idx][i]
            if sim_to_centroid >= self._outlier_threshold:
                pattern_scopes.append(scopes[i])
            else:
                outliers.append({
                    "deal": scopes[i],
                    "text": texts[i][:300],
                    "similarity_to_pattern": round(sim_to_centroid, 3),
                    "deviation": self._classify_deviation(centroid_text, texts[i]),
                })

        return centroid_text, pattern_scopes, outliers

    @staticmethod
    def _classify_deviation(pattern_text: str, outlier_text: str) -> str:
        """Classify the type of deviation between pattern and outlier."""
        import re

        # Check for amount differences
        pattern_amounts = set(re.findall(r"\$[\d,]+(?:\.\d+)?|\d+(?:\.\d+)?%", pattern_text))
        outlier_amounts = set(re.findall(r"\$[\d,]+(?:\.\d+)?|\d+(?:\.\d+)?%", outlier_text))
        if pattern_amounts != outlier_amounts:
            return "amount"

        # Check for date/timing differences
        pattern_dates = set(re.findall(r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:day|business\s+day)\b", pattern_text, re.IGNORECASE))
        outlier_dates = set(re.findall(r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:day|business\s+day)\b", outlier_text, re.IGNORECASE))
        if pattern_dates != outlier_dates:
            return "timing"

        # Check for terminology differences (defined terms in quotes)
        pattern_terms = set(re.findall(r'"([^"]+)"', pattern_text))
        outlier_terms = set(re.findall(r'"([^"]+)"', outlier_text))
        if pattern_terms != outlier_terms:
            return "terminology"

        return "language"

    @staticmethod
    def _generate_summary(
        query: str,
        pattern_desc: str,
        pattern_text: str,
        outliers: list[dict],
        total_count: int,
    ) -> str:
        """Generate a natural language summary of the aggregation."""
        parts = [f'Aggregation for "{query}" across {total_count} scopes:']
        parts.append(f"Pattern: {pattern_desc}.")

        if pattern_text:
            parts.append(f'Common text: "{pattern_text[:150]}..."')

        if outliers:
            deviation_types = Counter(o.get("deviation", "unknown") for o in outliers)
            dev_summary = ", ".join(f"{v} {k}" for k, v in deviation_types.items())
            parts.append(f"Outliers: {len(outliers)} ({dev_summary}).")
        else:
            parts.append("No outliers detected.")

        return " ".join(parts)
