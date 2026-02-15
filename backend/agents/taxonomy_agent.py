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
        filename_stem = Path(filename).stem if filename else ""

        # PHASE 0: Extension-based deterministic classification
        extension = Path(filename).suffix.lower()
        ext_map = {
            ".yaml": "CONFIG",
            ".yml": "CONFIG",
            ".ini": "CONFIG",
            ".csv": "INCIDENT",
            ".png": "ASSET_IMAGE",
        }
        if extension in ext_map:
            best_label = ext_map[extension]
            best_score = 1.0
            matched_rules.append(f"extension_match:{best_label}:{extension}")
            # Skip subsequent phases if extension match found
            # But allow prefix rules to potentially override or add tags if needed?
            # User requirement: "Deterministic... minimal"
            # It's safer to return early or ensure score reflects high confidence.
    
        # PHASE 1: Filename prefix pattern matching (highest priority)
        # Only run if not already confidently classified by extension
        # if best_score < 1.0:
        #    filename_stem = Path(filename).stem if filename else ""
        prefix_rules = {
            "ARCH_": "ARCHITECTURE",
            "POSTMORTEM_": "INCIDENT",
            "INC-": "INCIDENT",
            "REF_": "REFERENCE",
            "LEGACY_": "TROUBLESHOOT",
            "DEPRECATED_": "RELEASE_NOTE",
        }
        
        for prefix, label in prefix_rules.items():
            if filename_stem.upper().startswith(prefix):
                best_label = label
                best_score = 1.0  # High confidence for prefix match
                matched_rules.append(f"filename_prefix:{label}:{prefix}")
                
                # Add ARCHIVED tag for LEGACY/DEPRECATED
                if prefix in ["LEGACY_", "DEPRECATED_"]:
                    tags.append("ARCHIVED")
                break
        
        # PHASE 2: Filename contains pattern matching (medium priority)
        if best_score < 1.0:
            contains_rules = {
                "glossary": "REFERENCE",
                "catalog": "REFERENCE",
                "_archived": "RELEASE_NOTE",
                "_old": "TROUBLESHOOT",
            }
            
            for pattern, label in contains_rules.items():
                if pattern in filename_stem:
                    best_label = label
                    best_score = 0.8  # Medium confidence for contains match
                    matched_rules.append(f"filename_contains:{label}:{pattern}")
                    
                    if pattern in ["_archived", "_old"]:
                        tags.append("ARCHIVED")
                    break

        # PHASE 3: Content-based keyword matching (original logic, lower priority)
        for label, keywords in self.rules.items():
            score = 0.0
            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in filename:
                    score += 0.3
                    matched_rules.append(f"filename_keyword:{label}:{keyword_lower}")
                if keyword_lower in text:
                    score += 0.15
                    tags.append(keyword)
                    matched_rules.append(f"content:{label}:{keyword_lower}")

            # Only override if no prefix/contains match or content match is stronger
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
                reasoning="Filename pattern and content-based taxonomy classification.",
            )
        )
