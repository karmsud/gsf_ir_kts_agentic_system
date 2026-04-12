"""
Stage 5: Governing Document Generation — Enhanced markdown from extractions.

Generates governing documents in the 4-layer format:
  Legal Text → Interpretation → Formula → Code Hint

When LLM is not available, uses deterministic template-based generation.

Ported from PayGen pipeline.ingestion.governing_doc_generator → backend.abs.ingestion
Import rewrite: pipeline.config.pipeline_config → backend.abs.config.pipeline_config
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class GoverningDocResult:
    """Result of governing document generation."""
    generated_docs: dict[str, Path]
    total_sections: int
    generation_method: str  # "template" or "llm"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "generated_docs": {k: str(v) for k, v in self.generated_docs.items()},
            "total_sections": self.total_sections,
            "generation_method": self.generation_method,
            "warnings": self.warnings,
        }


# Section number mapping for standard ordering — dynamically extended
_BASE_SECTION_NUMBERING = {
    "definitions": "01",
    "waterfall": "02",
    "loss_allocation": "03",
    "loss_allocations": "03",
    "triggers": "04",
    "accounts": "05",
    "collections": "06",
    "reporting_requirements": "07",
    "credit_enhancement": "08",
    "servicing": "09",
    "events_of_default": "10",
}

# Kept for backward compat — same as _BASE
SECTION_NUMBERING = dict(_BASE_SECTION_NUMBERING)


def _get_section_number(section_name: str, existing_numbers: set[str]) -> str:
    """Return a section number, auto-assigning new ones for unknown sections."""
    if section_name in _BASE_SECTION_NUMBERING:
        return _BASE_SECTION_NUMBERING[section_name]
    next_num = 11
    while f"{next_num:02d}" in existing_numbers:
        next_num += 1
    num = f"{next_num:02d}"
    _BASE_SECTION_NUMBERING[section_name] = num
    return num


def generate_governing_docs(
    extractions_dir: Path,
    sections_dir: Path,
    output_dir: Path,
    deal_id: str = "",
    use_llm: bool = False,
) -> GoverningDocResult:
    """
    Generate governing documents from extractions and sections.

    Each governing doc follows the 4-layer format:
    - Legal Text: Original text from the PSA
    - Interpretation: Plain-English explanation
    - Formula: Mathematical representation where applicable
    - Code Hint: Python pseudocode for implementation
    """
    extractions_dir = Path(extractions_dir)
    sections_dir = Path(sections_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine generation method from config
    generation_method = "template"
    if use_llm:
        try:
            from backend.abs.config.pipeline_config import get_config
            cfg = get_config()
            if cfg.extraction.is_llm:
                generation_method = "llm"
                logger.info("LLM generation enabled via config")
            else:
                logger.info("LLM requested but config extraction.mode=manual; using template")
        except Exception:
            logger.info("Config not available; using template generation")

    result = GoverningDocResult(
        generated_docs={},
        total_sections=0,
        generation_method=generation_method,
    )

    # Load all extractions
    extractions = _load_extractions(extractions_dir)

    # Specialized generators for known section types
    _specialized_generators = {
        "definitions": _generate_definitions_doc,
        "waterfall": _generate_waterfall_doc,
        "waterfall_rules": _generate_waterfall_doc,
        "loss_allocation": _generate_loss_allocation_doc,
        "loss_allocations": _generate_loss_allocation_doc,
        "triggers": _generate_triggers_doc,
        "accounts": _generate_accounts_doc,
        "collections": _generate_collections_doc,
        "reporting_requirements": _generate_reporting_doc,
        "credit_enhancement": _generate_credit_enhancement_doc,
        "servicing": _generate_servicing_doc,
        "events_of_default": _generate_events_of_default_doc,
    }

    # ── Dynamic section discovery ─────────────────────────────
    discovered_sections: set[str] = set()

    for name in extractions.keys():
        discovered_sections.add(name)

    for md_file in sorted(Path(sections_dir).glob("*.md")):
        stem = md_file.stem
        if stem not in ("preamble", "other", "full"):
            discovered_sections.add(stem)

    _alias_map = {
        "waterfall_rules": "waterfall",
        "loss_allocations": "loss_allocation",
    }
    _reverse_alias: dict[str, list[str]] = {}
    for raw, canon in _alias_map.items():
        _reverse_alias.setdefault(canon, []).append(raw)

    used_numbers: set[str] = set(_BASE_SECTION_NUMBERING.values())
    sections_to_generate: list[str] = []
    seen_canonical: set[str] = set()

    for raw_name in sorted(discovered_sections):
        canonical = _alias_map.get(raw_name, raw_name)
        if canonical not in seen_canonical:
            seen_canonical.add(canonical)
            sections_to_generate.append(raw_name)

    logger.info(
        f"[{deal_id}] Dynamic sections discovered: "
        f"{sorted(seen_canonical)} ({len(seen_canonical)} total)"
    )

    # Generate governing doc for every discovered section
    for raw_name in sections_to_generate:
        canonical = _alias_map.get(raw_name, raw_name)

        items = extractions.get(raw_name) or extractions.get(canonical)
        if not items:
            for alias in _reverse_alias.get(canonical, []):
                items = extractions.get(alias)
                if items:
                    break
        if not items:
            items = []

        section_text = _load_section_text(sections_dir, raw_name)
        if not section_text:
            section_text = _load_section_text(sections_dir, canonical)

        generator_fn = _specialized_generators.get(
            raw_name,
            _specialized_generators.get(canonical, None),
        )

        if generator_fn:
            content = generator_fn(
                items=items,
                section_text=section_text,
                deal_id=deal_id,
            )
        else:
            content = _generate_generic_doc(
                section_name=canonical,
                items=items,
                section_text=section_text,
                deal_id=deal_id,
            )

        if content:
            number = _get_section_number(canonical, used_numbers)
            used_numbers.add(number)
            filename = f"{number}_{canonical}.md"
            doc_path = output_dir / filename
            doc_path.write_text(content, encoding="utf-8")

            result.generated_docs[canonical] = doc_path
            result.total_sections += 1
        else:
            result.warnings.append(f"No content generated for section: {canonical}")

    return result


# ── Extraction Loading ────────────────────────────────────────

def _load_extractions(extractions_dir: Path) -> dict[str, list[dict]]:
    """Load all extraction JSON files."""
    extractions: dict[str, list[dict]] = {}
    for json_file in sorted(extractions_dir.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                extractions[json_file.stem] = data
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to load extraction '{json_file.name}': {e}")
    return extractions


def _load_section_text(sections_dir: Path, section_name: str) -> str:
    """Load original section markdown text."""
    candidates = [
        sections_dir / f"{section_name}.md",
        sections_dir / f"{section_name}s.md",
        sections_dir / f"{section_name.replace('_', '')}.md",
    ]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8")
    return ""


# ── Section Generators (4-Layer Format) ───────────────────────

def _generate_definitions_doc(
    items: list[dict],
    section_text: str,
    deal_id: str,
) -> str:
    """Generate definitions governing document."""
    timestamp = datetime.now(timezone.utc).isoformat()
    lines = [
        f"# Governing Document: Definitions",
        f"**Deal:** {deal_id}",
        f"**Generated:** {timestamp}",
        f"**Source:** Payment Source of Truth (PSA)",
        "",
        "---",
        "",
    ]

    if not items:
        lines.append("*No definitions extracted.*")
        return "\n".join(lines)

    categories: dict[str, list[dict]] = {}
    for item in items:
        cat = item.get("category", "other")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)

    for cat_name in sorted(categories.keys()):
        cat_items = categories[cat_name]
        lines.append(f"## {cat_name.replace('_', ' ').title()} Definitions")
        lines.append("")

        for item in cat_items:
            term = item.get("term", item.get("id", "Unknown"))
            definition = item.get("definition", "")
            source = item.get("source_section", "")
            value = item.get("value", "")
            formula = item.get("formula", "")
            dependencies = item.get("dependencies", [])

            lines.append(f"### DEF: {term}")
            lines.append("")
            lines.append(f"**Legal Text:**")
            lines.append(f"> {definition}")
            lines.append("")
            lines.append(f"**Interpretation:**")
            lines.append(f"The term \"{term}\" is defined in the governing documents as stated above.")
            if value:
                lines.append(f"The value associated with this term is: {value}")
            lines.append("")

            if formula:
                lines.append(f"**Formula:**")
                lines.append(f"```")
                lines.append(f"{formula}")
                lines.append(f"```")
                lines.append("")

            if dependencies:
                dep_str = ", ".join(str(d) for d in dependencies) if isinstance(dependencies, list) else str(dependencies)
                lines.append(f"**Dependencies:** {dep_str}")
                lines.append("")

            lines.append(f"**Code Hint:**")
            safe_term = term.lower().replace(" ", "_").replace("-", "_")
            lines.append(f"```python")
            if value:
                lines.append(f'{safe_term} = "{value}"  # {term}')
            else:
                lines.append(f'{safe_term} = None  # {term} — see definition above')
            lines.append(f"```")
            lines.append("")
            if source:
                lines.append(f"*Source: {source}*")
            lines.append("")

    return "\n".join(lines)


def _generate_waterfall_doc(
    items: list[dict],
    section_text: str,
    deal_id: str,
) -> str:
    """Generate waterfall governing document."""
    timestamp = datetime.now(timezone.utc).isoformat()
    lines = [
        f"# Governing Document: Payment Waterfall",
        f"**Deal:** {deal_id}",
        f"**Generated:** {timestamp}",
        f"**Source:** Payment Source of Truth (PSA)",
        "",
        "---",
        "",
        "## Distribution Priority",
        "",
    ]

    if not items:
        lines.append("*No waterfall rules extracted.*")
        return "\n".join(lines)

    sorted_items = sorted(items, key=lambda x: x.get("priority", 999))

    for i, item in enumerate(sorted_items, 1):
        rule_id = item.get("rule_id", item.get("id", f"RULE-{i:03d}"))
        desc = item.get("description", "")
        rule_type = item.get("rule_type", "other")
        pays_to = item.get("pays_to", [])
        conditions = item.get("conditions", [])
        depends_on = item.get("depends_on", [])
        source = item.get("source_section", "")

        lines.append(f"### Step {i}: {rule_id}")
        lines.append(f"**Type:** {rule_type}")
        lines.append("")

        lines.append(f"**Legal Text:**")
        lines.append(f"> {desc}")
        lines.append("")

        lines.append(f"**Interpretation:**")
        lines.append(f"Priority {i} in the waterfall. ")
        if pays_to:
            target_str = ", ".join(str(t) for t in pays_to) if isinstance(pays_to, list) else str(pays_to)
            lines.append(f"Pays to: {target_str}.")
        lines.append("")

        if conditions:
            cond_str = "; ".join(str(c) for c in conditions) if isinstance(conditions, list) else str(conditions)
            lines.append(f"**Conditions:** {cond_str}")
            lines.append("")

        lines.append(f"**Formula:**")
        lines.append(f"```")
        if rule_type == "interest":
            lines.append(f"amount = current_balance * coupon_rate / 12")
        elif rule_type == "principal":
            lines.append(f"amount = min(available_funds, scheduled_principal)")
        else:
            lines.append(f"amount = calculate_{rule_type}(available_funds)")
        lines.append(f"```")
        lines.append("")

        lines.append(f"**Code Hint:**")
        lines.append(f"```python")
        lines.append(f"# {rule_id}: {rule_type}")
        lines.append(f"def step_{i}_{rule_type}(available_funds, class_balances):")
        if rule_type == "interest":
            lines.append(f'    rate = class_balances["{pays_to[0] if pays_to else "target"}"]["coupon_rate"]')
            lines.append(f'    balance = class_balances["{pays_to[0] if pays_to else "target"}"]["current_balance"]')
            lines.append(f"    return min(balance * rate / 12, available_funds)")
        else:
            lines.append(f"    return min(available_funds, scheduled_amount)")
        lines.append(f"```")
        lines.append("")

        if depends_on:
            dep_str = ", ".join(str(d) for d in depends_on) if isinstance(depends_on, list) else str(depends_on)
            lines.append(f"**Depends On:** {dep_str}")
        if source:
            lines.append(f"*Source: {source}*")
        lines.append("")

    return "\n".join(lines)


def _generate_loss_allocation_doc(
    items: list[dict],
    section_text: str,
    deal_id: str,
) -> str:
    """Generate loss allocation governing document."""
    timestamp = datetime.now(timezone.utc).isoformat()
    lines = [
        f"# Governing Document: Loss Allocation",
        f"**Deal:** {deal_id}",
        f"**Generated:** {timestamp}",
        f"**Source:** Payment Source of Truth (PSA)",
        "",
        "---",
        "",
    ]

    if not items:
        lines.append("*No loss allocation rules extracted.*")
        return "\n".join(lines)

    for i, item in enumerate(items, 1):
        name = item.get("name", item.get("id", f"LOSS-{i:03d}"))
        desc = item.get("description", item.get("methodology", ""))
        source = item.get("source_section", "")

        lines.append(f"### {name}")
        lines.append("")
        lines.append(f"**Legal Text:**")
        lines.append(f"> {desc}")
        lines.append("")
        lines.append(f"**Interpretation:**")
        lines.append(f"This loss allocation rule determines how realized losses are distributed.")
        lines.append("")
        lines.append(f"**Formula:**")
        lines.append(f"```")
        lines.append(f"loss_allocated = min(realized_losses, current_balance)")
        lines.append(f"```")
        lines.append("")
        lines.append(f"**Code Hint:**")
        lines.append(f"```python")
        lines.append(f"def allocate_loss_{i}(losses, class_balances):")
        lines.append(f"    # Apply in reverse seniority order")
        lines.append(f"    for cls in reversed(sorted_classes):")
        lines.append(f"        alloc = min(losses, class_balances[cls])")
        lines.append(f"        class_balances[cls] -= alloc")
        lines.append(f"        losses -= alloc")
        lines.append(f"    return class_balances")
        lines.append(f"```")
        lines.append("")
        if source:
            lines.append(f"*Source: {source}*")
        lines.append("")

    return "\n".join(lines)


def _generate_triggers_doc(
    items: list[dict],
    section_text: str,
    deal_id: str,
) -> str:
    """Generate triggers governing document."""
    timestamp = datetime.now(timezone.utc).isoformat()
    lines = [
        f"# Governing Document: Performance Triggers",
        f"**Deal:** {deal_id}",
        f"**Generated:** {timestamp}",
        f"**Source:** Payment Source of Truth (PSA)",
        "",
        "---",
        "",
    ]

    if not items:
        lines.append("*No triggers extracted.*")
        return "\n".join(lines)

    for i, item in enumerate(items, 1):
        name = item.get("name", item.get("id", f"TRIG-{i:03d}"))
        condition = item.get("condition", item.get("description", ""))
        effect = item.get("effect", "")
        source = item.get("source_section", "")

        lines.append(f"### TRIG: {name}")
        lines.append("")
        lines.append(f"**Legal Text:**")
        lines.append(f"> {condition}")
        lines.append("")
        lines.append(f"**Interpretation:**")
        lines.append(f"This trigger evaluates a performance condition.")
        if effect:
            lines.append(f"When triggered, the effect is: {effect}")
        lines.append("")
        lines.append(f"**Formula:**")
        lines.append(f"```")
        lines.append(f"triggered = evaluate_condition(current_metrics)")
        lines.append(f"```")
        lines.append("")
        lines.append(f"**Code Hint:**")
        lines.append(f"```python")
        safe_name = name.lower().replace(" ", "_").replace("-", "_")
        lines.append(f"def check_{safe_name}(metrics):")
        lines.append(f"    # Evaluate: {condition[:80]}")
        lines.append(f"    return metrics.get('value', 0) > threshold")
        lines.append(f"```")
        lines.append("")
        if source:
            lines.append(f"*Source: {source}*")
        lines.append("")

    return "\n".join(lines)


def _generate_accounts_doc(
    items: list[dict],
    section_text: str,
    deal_id: str,
) -> str:
    """Generate accounts governing document."""
    timestamp = datetime.now(timezone.utc).isoformat()
    lines = [
        f"# Governing Document: Accounts",
        f"**Deal:** {deal_id}",
        f"**Generated:** {timestamp}",
        f"**Source:** Payment Source of Truth (PSA)",
        "",
        "---",
        "",
    ]

    if not items and not section_text.strip():
        lines.append("*No accounts extracted.*")
        return "\n".join(lines)

    if items:
        for i, item in enumerate(items, 1):
            name = item.get("account_name", item.get("name", item.get("id", f"ACC-{i:03d}")))
            purpose = item.get("purpose", item.get("description", ""))
            source = item.get("source_section", "")

            lines.append(f"### ACC: {name}")
            lines.append("")
            lines.append(f"**Legal Text:**")
            lines.append(f"> {purpose}")
            lines.append("")
            lines.append(f"**Interpretation:**")
            lines.append(f'The "{name}" is established per the governing documents for the purpose described above.')
            lines.append("")
            lines.append(f"**Code Hint:**")
            lines.append(f"```python")
            safe_name = name.lower().replace(" ", "_").replace("-", "_")
            lines.append(f'accounts["{safe_name}"] = {{"balance": 0.0, "purpose": "{purpose[:60]}"}}  # {name}')
            lines.append(f"```")
            lines.append("")
            if source:
                lines.append(f"*Source: {source}*")
            lines.append("")
    else:
        lines.append("## Accounts (from PSA text)")
        lines.append("")
        lines.append(f"**Legal Text:**")
        lines.append(f"> {section_text[:3000]}")
        lines.append("")

    return "\n".join(lines)


def _generate_collections_doc(
    items: list[dict],
    section_text: str,
    deal_id: str,
) -> str:
    """Generate collections governing document."""
    timestamp = datetime.now(timezone.utc).isoformat()
    lines = [
        f"# Governing Document: Collections",
        f"**Deal:** {deal_id}",
        f"**Generated:** {timestamp}",
        f"**Source:** Payment Source of Truth (PSA)",
        "",
        "---",
        "",
    ]

    if not items and not section_text.strip():
        lines.append("*No collections rules extracted.*")
        return "\n".join(lines)

    if items:
        for i, item in enumerate(items, 1):
            name = item.get("name", item.get("id", f"COL-{i:03d}"))
            desc = item.get("description", item.get("requirement", ""))
            source = item.get("source_section", "")

            lines.append(f"### COL: {name}")
            lines.append("")
            lines.append(f"**Legal Text:**")
            lines.append(f"> {desc}")
            lines.append("")
            lines.append(f"**Interpretation:**")
            lines.append(f"This collection rule governs how payments are collected and aggregated.")
            lines.append("")
            lines.append(f"**Code Hint:**")
            lines.append(f"```python")
            safe_name = name.lower().replace(" ", "_").replace("-", "_")
            lines.append(f"def collect_{safe_name}(receipts):")
            lines.append(f"    return sum(r['amount'] for r in receipts)")
            lines.append(f"```")
            lines.append("")
            if source:
                lines.append(f"*Source: {source}*")
            lines.append("")
    else:
        lines.append("## Collections (from PSA text)")
        lines.append("")
        lines.append(f"**Legal Text:**")
        lines.append(f"> {section_text[:3000]}")
        lines.append("")

    return "\n".join(lines)


def _generate_reporting_doc(
    items: list[dict],
    section_text: str,
    deal_id: str,
) -> str:
    """Generate reporting requirements governing document."""
    timestamp = datetime.now(timezone.utc).isoformat()
    lines = [
        f"# Governing Document: Reporting Requirements",
        f"**Deal:** {deal_id}",
        f"**Generated:** {timestamp}",
        f"**Source:** Payment Source of Truth (PSA)",
        "",
        "---",
        "",
    ]

    if not items and not section_text.strip():
        lines.append("*No reporting requirements extracted.*")
        return "\n".join(lines)

    if items:
        for i, item in enumerate(items, 1):
            req = item.get("requirement", item.get("description", item.get("name", f"RPT-{i:03d}")))
            source = item.get("source_section", "")

            lines.append(f"### RPT-{i:03d}")
            lines.append("")
            lines.append(f"**Legal Text:**")
            lines.append(f"> {req}")
            lines.append("")
            lines.append(f"**Interpretation:**")
            lines.append(f"The servicer/trustee is required to provide this reporting item per the PSA.")
            lines.append("")
            if source:
                lines.append(f"*Source: {source}*")
            lines.append("")
    else:
        lines.append("## Reporting Requirements (from PSA text)")
        lines.append("")
        lines.append(f"**Legal Text:**")
        lines.append(f"> {section_text[:3000]}")
        lines.append("")

    return "\n".join(lines)


def _generate_credit_enhancement_doc(
    items: list[dict],
    section_text: str,
    deal_id: str,
) -> str:
    """Generate credit enhancement governing document."""
    timestamp = datetime.now(timezone.utc).isoformat()
    lines = [
        f"# Governing Document: Credit Enhancement",
        f"**Deal:** {deal_id}",
        f"**Generated:** {timestamp}",
        f"**Source:** Payment Source of Truth (PSA)",
        "",
        "---",
        "",
    ]

    if not items and not section_text.strip():
        lines.append("*No credit enhancement provisions extracted.*")
        return "\n".join(lines)

    if items:
        for i, item in enumerate(items, 1):
            name = item.get("name", item.get("id", f"CE-{i:03d}"))
            desc = item.get("description", "")
            source = item.get("source_section", "")

            lines.append(f"### CE: {name}")
            lines.append("")
            lines.append(f"**Legal Text:**")
            lines.append(f"> {desc}")
            lines.append("")
            lines.append(f"**Interpretation:**")
            lines.append(f"This credit enhancement mechanism provides structural protection to senior classes.")
            lines.append("")
            lines.append(f"**Formula:**")
            lines.append(f"```")
            lines.append(f"enhancement_level = subordinate_balance / total_pool_balance")
            lines.append(f"```")
            lines.append("")
            if source:
                lines.append(f"*Source: {source}*")
            lines.append("")
    else:
        lines.append("## Credit Enhancement (from PSA text)")
        lines.append("")
        lines.append(f"**Legal Text:**")
        lines.append(f"> {section_text[:3000]}")
        lines.append("")

    return "\n".join(lines)


def _generate_servicing_doc(
    items: list[dict],
    section_text: str,
    deal_id: str,
) -> str:
    """Generate servicing governing document."""
    timestamp = datetime.now(timezone.utc).isoformat()
    lines = [
        f"# Governing Document: Servicing",
        f"**Deal:** {deal_id}",
        f"**Generated:** {timestamp}",
        f"**Source:** Payment Source of Truth (PSA)",
        "",
        "---",
        "",
    ]

    if not items and not section_text.strip():
        lines.append("*No servicing provisions extracted.*")
        return "\n".join(lines)

    if items:
        for i, item in enumerate(items, 1):
            name = item.get("name", item.get("id", f"SVC-{i:03d}"))
            desc = item.get("description", item.get("standard", ""))
            source = item.get("source_section", "")

            lines.append(f"### SVC: {name}")
            lines.append("")
            lines.append(f"**Legal Text:**")
            lines.append(f"> {desc}")
            lines.append("")
            lines.append(f"**Interpretation:**")
            lines.append(f"This servicing standard governs how the servicer must manage the underlying loans.")
            lines.append("")
            if source:
                lines.append(f"*Source: {source}*")
            lines.append("")
    else:
        lines.append("## Servicing (from PSA text)")
        lines.append("")
        lines.append(f"**Legal Text:**")
        lines.append(f"> {section_text[:3000]}")
        lines.append("")

    return "\n".join(lines)


def _generate_events_of_default_doc(
    items: list[dict],
    section_text: str,
    deal_id: str,
) -> str:
    """Generate events of default governing document."""
    timestamp = datetime.now(timezone.utc).isoformat()
    lines = [
        f"# Governing Document: Events of Default",
        f"**Deal:** {deal_id}",
        f"**Generated:** {timestamp}",
        f"**Source:** Payment Source of Truth (PSA)",
        "",
        "---",
        "",
    ]

    if not items and not section_text.strip():
        lines.append("*No events of default extracted.*")
        return "\n".join(lines)

    if items:
        for i, item in enumerate(items, 1):
            name = item.get("name", item.get("id", f"EOD-{i:03d}"))
            desc = item.get("description", item.get("condition", ""))
            remedy = item.get("remedy", item.get("effect", ""))
            source = item.get("source_section", "")

            lines.append(f"### EOD: {name}")
            lines.append("")
            lines.append(f"**Legal Text:**")
            lines.append(f"> {desc}")
            lines.append("")
            lines.append(f"**Interpretation:**")
            lines.append(f"This constitutes an event of default under the governing documents.")
            if remedy:
                lines.append(f"Remedy/Effect: {remedy}")
            lines.append("")
            if source:
                lines.append(f"*Source: {source}*")
            lines.append("")
    else:
        lines.append("## Events of Default (from PSA text)")
        lines.append("")
        lines.append(f"**Legal Text:**")
        lines.append(f"> {section_text[:3000]}")
        lines.append("")

    return "\n".join(lines)


def _generate_generic_doc(
    section_name: str,
    items: list[dict],
    section_text: str,
    deal_id: str,
) -> str:
    """
    Generic 4-layer governing document generator.
    Works for any section type not covered by a specialized generator.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    pretty_name = section_name.replace("_", " ").title()
    lines = [
        f"# Governing Document: {pretty_name}",
        f"**Deal:** {deal_id}",
        f"**Generated:** {timestamp}",
        f"**Source:** Payment Source of Truth (PSA)",
        "",
        "---",
        "",
    ]

    if not items and not section_text.strip():
        lines.append(f"*No {pretty_name.lower()} data extracted.*")
        return "\n".join(lines)

    if items:
        for i, item in enumerate(items, 1):
            name = (
                item.get("name")
                or item.get("term")
                or item.get("account_name")
                or item.get("rule_id")
                or item.get("id")
                or f"{section_name.upper()}-{i:03d}"
            )
            desc = (
                item.get("description")
                or item.get("definition")
                or item.get("condition")
                or item.get("requirement")
                or item.get("purpose")
                or item.get("methodology")
                or ""
            )
            source = item.get("source_section", "")

            lines.append(f"### {name}")
            lines.append("")
            lines.append(f"**Legal Text:**")
            lines.append(f"> {desc}")
            lines.append("")
            lines.append(f"**Interpretation:**")
            lines.append(f"This item is defined in the {pretty_name} section of the PSA.")
            lines.append("")
            if source:
                lines.append(f"*Source: {source}*")
            lines.append("")
    else:
        lines.append(f"## {pretty_name} (from PSA text)")
        lines.append("")
        lines.append(f"**Legal Text:**")
        lines.append(f"> {section_text[:5000]}")
        lines.append("")

    return "\n".join(lines)
