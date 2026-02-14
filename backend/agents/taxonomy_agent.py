from __future__ import annotations

import json
from pathlib import Path

from backend.common.models import AgentResult
from backend.common.doc_types import normalize_doc_type
from .base_agent import AgentBase


class TaxonomyAgent(AgentBase):
    agent_name = "taxonomy-agent"

    def __init__(self, config):
        super().__init__(config)
        rules_path = Path("config") / "taxonomy_rules.json"
        self.rules = json.loads(rules_path.read_text(encoding="utf-8")) if rules_path.exists() else {}

    def execute(self, request: dict) -> AgentResult:
        filename = (request.get("filename") or "").lower()
        text = (request.get("text") or "").lower()
        best_label = "UNKNOWN"
        best_score = 0.0
        tags: list[str] = []
        matched_rules: list[str] = []

        for label, keywords in self.rules.items():
            score = 0.0
            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in filename:
                    score += 0.3
                    matched_rules.append(f"filename:{label}:{keyword_lower}")
                if keyword_lower in text:
                    score += 0.15
                    tags.append(keyword)
                    matched_rules.append(f"content:{label}:{keyword_lower}")

            if score > best_score:
                best_score = score
                best_label = label

        confidence = min(1.0, best_score) if best_label != "UNKNOWN" else 0.0
        needs_review = confidence < 0.5
        return self.quality_check(
            AgentResult(
                success=True,
                confidence=max(0.4, confidence) if best_label != "UNKNOWN" else 0.4,
                data={
                    "doc_type": normalize_doc_type(best_label),
                    "tags": sorted(set(tags)),
                    "matched_rules": matched_rules,
                    "needs_review": needs_review,
                    "reasoning": "No rules matched" if best_label == "UNKNOWN" else f"Matched {len(matched_rules)} rule(s)",
                },
                reasoning="Filename and keyword-based taxonomy classification.",
            )
        )
