"""
Deal Comparator — Compare definitions, waterfall rules, accounts,
and other structural elements across two deals.

Ported from PayGen pipeline.skills.deal_comparator → backend.abs.skills
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from backend.abs.config.constants import COMPARISON_WEIGHTS


@dataclass
class SectionComparison:
    """Comparison of a single section between two deals."""
    section: str
    deal_a_count: int = 0
    deal_b_count: int = 0
    matched: int = 0
    only_in_a: list[str] = field(default_factory=list)
    only_in_b: list[str] = field(default_factory=list)
    similarity_score: float = 0.0
    details: list[dict] = field(default_factory=list)


@dataclass
class DealComparisonResult:
    """Full comparison of two deals."""
    deal_a_id: str
    deal_b_id: str
    overall_similarity: float  # 0.0 to 1.0
    section_comparisons: dict[str, SectionComparison] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "deal_a_id": self.deal_a_id,
            "deal_b_id": self.deal_b_id,
            "overall_similarity": round(self.overall_similarity, 4),
            "sections": {
                k: {
                    "section": v.section,
                    "deal_a_count": v.deal_a_count,
                    "deal_b_count": v.deal_b_count,
                    "matched": v.matched,
                    "only_in_a": v.only_in_a,
                    "only_in_b": v.only_in_b,
                    "similarity_score": round(v.similarity_score, 4),
                }
                for k, v in self.section_comparisons.items()
            },
            "summary": self.summary,
        }


def compare_deals(
    deal_a_extractions: dict[str, list[dict]],
    deal_b_extractions: dict[str, list[dict]],
    deal_a_id: str = "deal_a",
    deal_b_id: str = "deal_b",
    weights: Optional[dict[str, float]] = None,
) -> DealComparisonResult:
    """
    Compare two deals across all sections.

    Args:
        deal_a_extractions: Extractions from deal A
        deal_b_extractions: Extractions from deal B
        deal_a_id: Identifier for deal A
        deal_b_id: Identifier for deal B
        weights: Per-section weights for overall score (default: COMPARISON_WEIGHTS)

    Returns:
        DealComparisonResult with per-section and overall similarity
    """
    if weights is None:
        weights = COMPARISON_WEIGHTS

    result = DealComparisonResult(
        deal_a_id=deal_a_id,
        deal_b_id=deal_b_id,
        overall_similarity=0.0,
    )

    all_sections = set(deal_a_extractions.keys()) | set(deal_b_extractions.keys())

    weighted_sum = 0.0
    weight_sum = 0.0

    for section in sorted(all_sections):
        items_a = deal_a_extractions.get(section, [])
        items_b = deal_b_extractions.get(section, [])

        section_comp = _compare_section(section, items_a, items_b)
        result.section_comparisons[section] = section_comp

        w = weights.get(section, weights.get("default", 0.1))
        weighted_sum += section_comp.similarity_score * w
        weight_sum += w

    if weight_sum > 0:
        result.overall_similarity = weighted_sum / weight_sum

    # Summary
    high_sim = [s for s, c in result.section_comparisons.items() if c.similarity_score >= 0.8]
    low_sim = [s for s, c in result.section_comparisons.items() if c.similarity_score < 0.5]

    parts = [f"Overall similarity: {result.overall_similarity:.1%}"]
    if high_sim:
        parts.append(f"High similarity: {', '.join(high_sim)}")
    if low_sim:
        parts.append(f"Low similarity: {', '.join(low_sim)}")
    result.summary = "; ".join(parts)

    return result


def compare_definitions(
    defs_a: list[dict],
    defs_b: list[dict],
) -> SectionComparison:
    """Compare definitions between two deals."""
    return _compare_section("definitions", defs_a, defs_b, key_field="term")


def compare_waterfall(
    rules_a: list[dict],
    rules_b: list[dict],
) -> SectionComparison:
    """Compare waterfall rules between two deals."""
    return _compare_section("waterfall_rules", rules_a, rules_b, key_field="step")


def compare_accounts(
    accts_a: list[dict],
    accts_b: list[dict],
) -> SectionComparison:
    """Compare accounts between two deals."""
    return _compare_section("accounts", accts_a, accts_b, key_field="name")


def compare_classes(
    classes_a: list[dict],
    classes_b: list[dict],
) -> SectionComparison:
    """Compare classes between two deals."""
    return _compare_section("classes", classes_a, classes_b, key_field="name")


def similarity_score(
    deal_a_extractions: dict[str, list[dict]],
    deal_b_extractions: dict[str, list[dict]],
) -> float:
    """Quick overall similarity score without full comparison details."""
    result = compare_deals(deal_a_extractions, deal_b_extractions)
    return result.overall_similarity


def save_comparison(
    result: DealComparisonResult,
    output_path: Path,
) -> Path:
    """Save comparison result to JSON."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result.to_dict(), indent=2, default=str),
        encoding="utf-8",
    )
    return output_path


# ── Internal ──────────────────────────────────────────────────

def _compare_section(
    section: str,
    items_a: list[dict],
    items_b: list[dict],
    key_field: str = "id",
) -> SectionComparison:
    """Compare two lists of items from the same section type."""
    comp = SectionComparison(
        section=section,
        deal_a_count=len(items_a),
        deal_b_count=len(items_b),
    )

    if not items_a and not items_b:
        comp.similarity_score = 1.0
        return comp
    if not items_a or not items_b:
        comp.only_in_a = [_get_item_key(i, key_field, idx) for idx, i in enumerate(items_a)]
        comp.only_in_b = [_get_item_key(i, key_field, idx) for idx, i in enumerate(items_b)]
        comp.similarity_score = 0.0
        return comp

    # Build key maps
    map_a = {_get_item_key(i, key_field, idx): i for idx, i in enumerate(items_a)}
    map_b = {_get_item_key(i, key_field, idx): i for idx, i in enumerate(items_b)}

    keys_a = set(map_a.keys())
    keys_b = set(map_b.keys())

    common_keys = keys_a & keys_b
    comp.only_in_a = sorted(keys_a - keys_b)
    comp.only_in_b = sorted(keys_b - keys_a)

    # Compare common items
    matched = 0
    for key in sorted(common_keys):
        sim = _item_similarity(map_a[key], map_b[key])
        if sim >= 0.5:
            matched += 1
        comp.details.append({
            "key": key,
            "similarity": round(sim, 4),
            "fields_compared": len(set(map_a[key].keys()) | set(map_b[key].keys())),
        })

    comp.matched = matched

    # Overall section similarity
    total = len(keys_a | keys_b)
    if total > 0:
        jaccard = len(common_keys) / total
        field_sim = (
            sum(d["similarity"] for d in comp.details) / len(comp.details)
            if comp.details else 0.0
        )
        comp.similarity_score = (jaccard * 0.5) + (field_sim * 0.5)

    return comp


def _get_item_key(item: dict, key_field: str, index: int) -> str:
    """Get a unique key for an item."""
    val = item.get(key_field) or item.get("id") or item.get("name") or item.get("term")
    if val:
        return str(val)
    return f"item_{index}"


def _item_similarity(a: dict, b: dict) -> float:
    """Compute similarity between two items based on shared fields."""
    all_fields = set(a.keys()) | set(b.keys())
    all_fields -= {"id", "source_page", "source_line", "extraction_confidence"}

    if not all_fields:
        return 1.0

    matches = 0
    for field_name in all_fields:
        val_a = a.get(field_name)
        val_b = b.get(field_name)

        if val_a is None or val_b is None:
            continue

        str_a = str(val_a).strip().lower()
        str_b = str(val_b).strip().lower()

        if str_a == str_b:
            matches += 1
        elif _fuzzy_match(str_a, str_b):
            matches += 0.5

    return matches / len(all_fields)


def _fuzzy_match(a: str, b: str) -> bool:
    """Simple fuzzy matching — one string contains the other."""
    if not a or not b:
        return False
    return a in b or b in a
