"""
Stage 3: Structured Extraction — Parse sections into JSON + CSV.

Orchestrates the 6 parsers (definitions, waterfall, accounts, loss_allocation,
triggers, reporting) plus deal setup / classes setup extractors.
All extraction is deterministic — no LLM required.

Ported from PayGen pipeline.ingestion.structured_extractor → backend.abs.ingestion
Import rewrites:
  pipeline.config.constants → backend.abs.config.constants
  pipeline.skills.parsers   → backend.abs.skills.parsers
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from backend.abs.config.constants import MIN_DEFINITION_COUNT, MIN_RULE_COUNT

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Result of structured extraction across all sections."""
    extractions: dict[str, list[dict]]
    extraction_counts: dict[str, int]
    csv_files: dict[str, Path]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "extraction_counts": self.extraction_counts,
            "csv_files": {k: str(v) for k, v in self.csv_files.items()},
            "warnings": self.warnings,
            "errors": self.errors,
        }


# Section type → parser mapping
SECTION_PARSER_MAP = {
    "definitions": "definitions",
    "waterfall": "waterfall_rules",
    "accounts": "accounts",
    "collections": "collections",
    "loss_allocations": "loss_allocations",
    "triggers": "triggers",
    "reporting_requirements": "reporting_requirements",
    "credit_enhancement": "credit_enhancement",
    "servicing": "servicing",
    "events_of_default": "events_of_default",
}


def extract_all_sections(
    sections_dir: Path,
    output_dir: Path,
    data_dir: Optional[Path] = None,
    deal_id: str = "",
) -> ExtractionResult:
    """
    Extract structured data from all section markdown files.

    For each section file, runs the matching parser and writes JSON output.
    Also generates deal_setup.csv and classes_setup.csv if possible.

    Args:
        sections_dir: Directory containing section .md files
        output_dir: Directory for extraction JSON outputs
        data_dir: Directory for CSV outputs (deal_setup.csv, classes_setup.csv)
        deal_id: Deal identifier for output metadata

    Returns:
        ExtractionResult with all extractions and statistics
    """
    sections_dir = Path(sections_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if data_dir is not None:
        data_dir = Path(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)

    result = ExtractionResult(
        extractions={},
        extraction_counts={},
        csv_files={},
    )

    # Try importing parsers
    try:
        from backend.abs.skills.parsers import parse_section, PARSERS_AVAILABLE
    except ImportError:
        PARSERS_AVAILABLE = False

    # Process each section file
    for section_file in sorted(sections_dir.glob("*.md")):
        section_name = section_file.stem
        parser_type = SECTION_PARSER_MAP.get(section_name)

        if parser_type is None:
            # Dynamic: unknown sections still get a generic extraction
            if section_name in ("preamble", "other", "full"):
                logger.debug(f"Skipping non-section file: {section_name}")
                continue
            parser_type = section_name  # Use section name as parser type
            logger.info(f"No parser for section '{section_name}', using generic extraction")

        section_text = section_file.read_text(encoding="utf-8")
        if not section_text.strip():
            result.warnings.append(f"Empty section: {section_name}")
            continue

        # Parse the section
        items = _parse_section_safe(parser_type, section_text, section_name)
        if items is None:
            # Parser not available, use fallback extraction
            items = _fallback_extract(parser_type, section_text)

        result.extractions[parser_type] = items
        result.extraction_counts[parser_type] = len(items)

        # Write extraction JSON
        json_path = output_dir / f"{parser_type}.json"
        json_path.write_text(
            json.dumps(items, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    # Validate minimum counts
    def_count = result.extraction_counts.get("definitions", 0)
    if def_count < MIN_DEFINITION_COUNT:
        result.warnings.append(
            f"Low definition count: {def_count} (minimum: {MIN_DEFINITION_COUNT})"
        )

    rule_count = result.extraction_counts.get("waterfall_rules", 0)
    if rule_count < MIN_RULE_COUNT:
        result.warnings.append(
            f"Low waterfall rule count: {rule_count} (minimum: {MIN_RULE_COUNT})"
        )

    # Generate CSV files if data_dir provided
    if data_dir is not None:
        csv_files = _generate_csvs(
            result.extractions, data_dir, deal_id, sections_dir=sections_dir,
        )
        result.csv_files = csv_files

    return result


def _parse_section_safe(
    parser_type: str,
    text: str,
    section_name: str,
) -> Optional[list[dict]]:
    """Safely attempt to parse a section using production parsers."""
    try:
        from backend.abs.skills.parsers import parse_section, PARSERS_AVAILABLE
        if not PARSERS_AVAILABLE:
            return None
        return parse_section(parser_type, text)
    except (ImportError, ValueError) as e:
        logger.warning(f"Parser unavailable for {parser_type}: {e}")
        return None
    except Exception as e:
        logger.error(f"Parser error for {section_name}: {e}")
        return None


def _fallback_extract(parser_type: str, text: str) -> list[dict]:
    """Fallback extraction using regex for when production parsers are unavailable."""
    import re

    if parser_type == "definitions":
        return _extract_definitions_fallback(text)
    elif parser_type == "waterfall_rules":
        return _extract_waterfall_fallback(text)
    elif parser_type == "accounts":
        return _extract_accounts_fallback(text)
    elif parser_type == "loss_allocations":
        return _extract_loss_allocation_fallback(text)
    elif parser_type == "triggers":
        return _extract_triggers_fallback(text)
    elif parser_type == "reporting_requirements":
        return _extract_reporting_fallback(text)
    elif parser_type == "collections":
        return _extract_collections_fallback(text)
    elif parser_type == "credit_enhancement":
        return _extract_credit_enhancement_fallback(text)
    elif parser_type == "servicing":
        return _extract_servicing_fallback(text)
    elif parser_type == "events_of_default":
        return _extract_events_of_default_fallback(text)
    else:
        return _extract_generic_fallback(parser_type, text)


def _extract_definitions_fallback(text: str) -> list[dict]:
    """Extract definitions using regex patterns."""
    import re

    definitions: list[dict] = []

    # Pattern 1: "Term" means ... (quoted term followed by means/shall mean)
    pattern1 = re.compile(
        r'"([^"]+)"\s+(?:means?|shall\s+mean|is\s+defined\s+as)\s+(.+?)(?=\n\s*"|\n\s*\n|\Z)',
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern1.finditer(text):
        definitions.append({
            "term": m.group(1).strip(),
            "definition": m.group(2).strip()[:500],
            "source_section": "definitions",
            "category": "other",
        })

    # Pattern 2: **Term**: definition (markdown bold)
    pattern2 = re.compile(
        r"\*\*([^*]+)\*\*\s*[:—-]\s*(.+?)(?=\n\s*\*\*|\n\s*\n|\Z)",
        re.DOTALL,
    )
    for m in pattern2.finditer(text):
        term = m.group(1).strip()
        if not any(d["term"] == term for d in definitions):
            definitions.append({
                "term": term,
                "definition": m.group(2).strip()[:500],
                "source_section": "definitions",
                "category": "other",
            })

    # Pattern 3: ### Term\n definition (markdown heading)
    pattern3 = re.compile(
        r"^#{2,4}\s+(.+?)$\n+(.+?)(?=\n#{2,4}\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    for m in pattern3.finditer(text):
        term = m.group(1).strip()
        if not any(d["term"] == term for d in definitions):
            definitions.append({
                "term": term,
                "definition": m.group(2).strip()[:500],
                "source_section": "definitions",
                "category": "other",
            })

    # Pattern 4: Term:  definition (colon-separated, common in Bear Stearns PSAs)
    pattern4 = re.compile(
        r"^([A-Z][A-Za-z\s\-/()]+?):\s{2,}(.+?)(?=\n[A-Z][A-Za-z\s\-/()]+?:\s{2,}|\n\n|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    for m in pattern4.finditer(text):
        term = m.group(1).strip()
        if len(term) < 3 or len(term) > 80:
            continue
        if re.match(r"^(Section|Article|Page|ARTICLE)\s", term, re.IGNORECASE):
            continue
        if not any(d["term"] == term for d in definitions):
            definitions.append({
                "term": term,
                "definition": m.group(2).strip()[:500],
                "source_section": "definitions",
                "category": _categorize_definition(term),
            })

    # Pattern 5: Term\n\n means/shall mean ...
    pattern5 = re.compile(
        r"^([A-Z][A-Za-z\s\-/()]+?)\n+(?:means?|shall\s+mean)\s+(.+?)(?=\n[A-Z][A-Za-z]{3,}|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    for m in pattern5.finditer(text):
        term = m.group(1).strip()
        if len(term) < 3 or len(term) > 80:
            continue
        if not any(d["term"] == term for d in definitions):
            definitions.append({
                "term": term,
                "definition": m.group(2).strip()[:500],
                "source_section": "definitions",
                "category": _categorize_definition(term),
            })

    return definitions


def _categorize_definition(term: str) -> str:
    """Categorize a definition term by keyword matching."""
    term_lower = term.lower()
    if any(kw in term_lower for kw in ["date", "period", "day"]):
        return "date"
    if any(kw in term_lower for kw in ["balance", "amount", "principal", "interest", "rate", "funds"]):
        return "financial"
    if any(kw in term_lower for kw in ["class", "certificate", "group"]):
        return "class"
    if any(kw in term_lower for kw in ["account", "reserve", "fund"]):
        return "account"
    if any(kw in term_lower for kw in ["servicer", "trustee", "depositor", "custodian"]):
        return "party"
    if any(kw in term_lower for kw in ["trigger", "event", "default", "stepdown"]):
        return "trigger"
    return "other"


def _extract_waterfall_fallback(text: str) -> list[dict]:
    """Extract waterfall rules using regex patterns."""
    import re

    rules: list[dict] = []

    pattern = re.compile(
        r"(?:^|\n)\s*(?:(\d+)\.|(?:\(([ivxlc]+|[a-z])\)))\s*(.+?)(?=\n\s*(?:\d+\.|(?:\([ivxlc]+\)|\([a-z]\)))|\Z)",
        re.IGNORECASE | re.DOTALL,
    )

    priority = 0
    for m in pattern.finditer(text):
        priority += 1
        step_num = m.group(1) or m.group(2) or str(priority)
        desc = m.group(3).strip()[:500]

        desc_lower = desc.lower()
        if "interest" in desc_lower and ("fund" in desc_lower or "distribut" in desc_lower):
            rule_type = "interest"
        elif "principal" in desc_lower and ("fund" in desc_lower or "distribut" in desc_lower):
            rule_type = "principal"
        elif "excess" in desc_lower or "overcollateral" in desc_lower:
            rule_type = "excess_cashflow"
        elif "loss" in desc_lower or "write" in desc_lower:
            rule_type = "loss_allocation"
        elif any(kw in desc_lower for kw in ("class ", "certificate")):
            rule_type = "certificate_payment"
        else:
            rule_type = "other"

        class_match = re.search(r"Class\s+([A-Z0-9][\w-]*)", desc)
        target = class_match.group(1) if class_match else ""

        rules.append({
            "rule_id": f"RULE-{priority:03d}",
            "priority": priority,
            "step": step_num,
            "description": desc,
            "target_class": target,
            "source_section": "waterfall",
            "rule_type": rule_type,
        })

    return rules


def _extract_accounts_fallback(text: str) -> list[dict]:
    """Extract account definitions using regex patterns."""
    import re

    accounts: list[dict] = []

    # Pattern 1: Quoted/bold account names
    pattern1 = re.compile(
        r"(?:\"|\*\*)([^\"*]+(?:Account|Fund|Reserve)[^\"*]*)(?:\"|\*\*)\s*[:—]?\s*(.+?)(?=\n\s*(?:\"|\*\*)|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern1.finditer(text):
        accounts.append({
            "account_name": m.group(1).strip(),
            "purpose": m.group(2).strip()[:300],
            "source_section": "accounts",
        })

    # Pattern 2: Section headers
    pattern2 = re.compile(
        r"Section\s+\d+\.\d+\s*([A-Z][^.]+(?:Account|Fund|Reserve|Payment)[^.]*)\.\s*\n",
        re.IGNORECASE,
    )
    seen_names = {a["account_name"].lower() for a in accounts}
    for m in pattern2.finditer(text):
        name = m.group(1).strip()
        if name.lower() not in seen_names:
            purpose_start = m.end()
            purpose_end = text.find("\n\n", purpose_start + 50)
            if purpose_end == -1:
                purpose_end = min(purpose_start + 300, len(text))
            accounts.append({
                "account_name": name,
                "purpose": text[purpose_start:purpose_end].strip()[:300],
                "source_section": "accounts",
            })
            seen_names.add(name.lower())

    # Pattern 3: "The Trustee shall establish and maintain..."
    pattern3 = re.compile(
        r"(?:Trustee|Servicer)\s+shall\s+establish\s+(?:and\s+maintain\s+)?[^,]*?(?:(?:the|an?)\s+)?\"?([^\"]*?(?:Account|Fund)[^\"]*?)\"?",
        re.IGNORECASE,
    )
    for m in pattern3.finditer(text):
        name = m.group(1).strip().rstrip(".,;")
        if name.lower() not in seen_names and len(name) > 3:
            accounts.append({
                "account_name": name,
                "purpose": text[m.start():min(m.end() + 200, len(text))].strip()[:300],
                "source_section": "accounts",
            })
            seen_names.add(name.lower())

    return accounts


def _extract_loss_allocation_fallback(text: str) -> list[dict]:
    """Extract loss allocation rules."""
    import re

    allocations: list[dict] = []
    pattern = re.compile(
        r"(?:Class\s+([A-Z0-9-]+))\s*.*?(?:loss|write.?down|alloc)",
        re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        allocations.append({
            "name": f"loss_alloc_{m.group(1)}",
            "description": text[max(0, m.start() - 20): m.end() + 100].strip()[:300],
            "source_section": "loss_allocations",
        })

    return allocations


def _extract_triggers_fallback(text: str) -> list[dict]:
    """Extract trigger and termination provisions."""
    import re

    triggers: list[dict] = []
    seen: set[str] = set()

    # Pattern 1: Quoted/bold trigger terms
    pattern1 = re.compile(
        r'(?:"|\*\*)([^"*]*(?:Trigger|Event|Stepdown|Step-?Down|Cleanup|Termination)[^"*]*)(?:"|\*\*)\s*[:—]?\s*(.+?)(?=\n\s*(?:"|\*\*)|\Z)',
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern1.finditer(text):
        name = m.group(1).strip()
        if name.lower() not in seen:
            triggers.append({
                "name": name,
                "condition": m.group(2).strip()[:300],
                "source_section": "triggers",
                "effect": "",
            })
            seen.add(name.lower())

    # Pattern 2: Section headers
    pattern2 = re.compile(
        r"Section\s+\d+\.\d+\s*([A-Z][^.]+?)\.\s*\n",
        re.IGNORECASE,
    )
    for m in pattern2.finditer(text):
        name = m.group(1).strip()
        if name.lower() not in seen:
            cond_start = m.end()
            cond_end = text.find("\n\n", cond_start + 50)
            if cond_end == -1:
                cond_end = min(cond_start + 300, len(text))
            triggers.append({
                "name": name,
                "condition": text[cond_start:cond_end].strip()[:300],
                "source_section": "triggers",
                "effect": "",
            })
            seen.add(name.lower())

    # Pattern 3: "shall terminate" / "termination" conditions
    pattern3 = re.compile(
        r"(?:shall\s+terminate|obligations.*?terminate|termination\s+(?:of|upon))\s+(.+?)(?:\.|;\s*\n)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern3.finditer(text):
        desc = m.group(1).strip()[:200]
        key = desc[:50].lower()
        if key not in seen:
            triggers.append({
                "name": "termination_condition",
                "condition": desc,
                "source_section": "triggers",
                "effect": "termination",
            })
            seen.add(key)

    return triggers


def _extract_reporting_fallback(text: str) -> list[dict]:
    """Extract reporting requirements."""
    import re

    requirements: list[dict] = []
    pattern = re.compile(
        r"(?:shall|must|will)\s+(?:provide|deliver|report|make\s+available)\s+(.+?)(?:\.|;|\n\n)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern.finditer(text):
        requirements.append({
            "requirement": m.group(1).strip()[:300],
            "source_section": "reporting_requirements",
        })

    return requirements


def _extract_collections_fallback(text: str) -> list[dict]:
    """Extract collection-related provisions."""
    import re

    items: list[dict] = []
    pattern = re.compile(
        r'(?:"|\*\*)([^"*]*(?:Collection|Available\s+Funds|Receipt|Remittance)[^"*]*)(?:"|\*\*)\s*[:—]?\s*(.+?)(?=\n\s*(?:"|\*\*)|\n\n|\Z)',
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern.finditer(text):
        items.append({
            "name": m.group(1).strip(),
            "description": m.group(2).strip()[:300],
            "source_section": "collections",
        })

    pattern2 = re.compile(
        r"(?:shall|must|will)\s+(?:deposit|remit|transfer|collect)\s+(.+?)(?:\.|;|\n\n)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern2.finditer(text):
        items.append({
            "name": f"collection_rule_{len(items)+1}",
            "description": m.group(1).strip()[:300],
            "source_section": "collections",
        })

    return items


def _extract_credit_enhancement_fallback(text: str) -> list[dict]:
    """Extract credit enhancement provisions."""
    import re

    items: list[dict] = []
    pattern = re.compile(
        r'(?:"|\*\*)([^"*]*(?:Subordinat|Reserve|Enhancement|Overcollateral|Excess\s+Spread)[^"*]*)(?:"|\*\*)\s*[:—]?\s*(.+?)(?=\n\s*(?:"|\*\*)|\n\n|\Z)',
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern.finditer(text):
        items.append({
            "name": m.group(1).strip(),
            "description": m.group(2).strip()[:300],
            "source_section": "credit_enhancement",
        })

    return items


def _extract_servicing_fallback(text: str) -> list[dict]:
    """Extract servicing provisions."""
    import re

    items: list[dict] = []
    pattern = re.compile(
        r"(?:shall|must|will)\s+(?:service|administer|manage|maintain)\s+(.+?)(?:\.|;|\n\n)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern.finditer(text):
        items.append({
            "name": f"servicing_standard_{len(items)+1}",
            "description": m.group(1).strip()[:300],
            "source_section": "servicing",
        })

    return items


def _extract_events_of_default_fallback(text: str) -> list[dict]:
    """Extract events of default."""
    import re

    items: list[dict] = []
    pattern = re.compile(
        r"\(([a-z]|[ivxlc]+|\d+)\)\s*(.+?)(?=\n\s*\([a-z]|\n\s*\([ivxlc]+|\n\n|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern.finditer(text):
        desc = m.group(2).strip()[:400]
        if any(kw in desc.lower() for kw in [
            "default", "fail", "breach", "insolvent", "bankrupt",
            "termination", "unremedied", "notice", "trustee", "servicer",
            "obligation", "material", "event"
        ]):
            items.append({
                "name": f"event_of_default_{m.group(1)}",
                "description": desc,
                "source_section": "events_of_default",
            })

    return items


def _extract_generic_fallback(section_name: str, text: str) -> list[dict]:
    """Generic fallback extraction using paragraph/heading detection."""
    import re

    items: list[dict] = []

    pattern = re.compile(
        r"^#{2,4}\s+(.+?)$\n+(.+?)(?=\n#{2,4}\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    for m in pattern.finditer(text):
        items.append({
            "name": m.group(1).strip(),
            "description": m.group(2).strip()[:500],
            "source_section": section_name,
        })

    if not items:
        pattern2 = re.compile(
            r'(?:"|\*\*)([^"*]+)(?:"|\*\*)\s*[:—]?\s*(.+?)(?=\n\s*(?:"|\*\*)|\n\n|\Z)',
            re.DOTALL,
        )
        for m in pattern2.finditer(text):
            items.append({
                "name": m.group(1).strip(),
                "description": m.group(2).strip()[:500],
                "source_section": section_name,
            })

    return items


def _generate_csvs(
    extractions: dict[str, list[dict]],
    data_dir: Path,
    deal_id: str,
    sections_dir: Optional[Path] = None,
) -> dict[str, Path]:
    """Generate deal_setup.csv and classes_setup.csv from extractions and raw section text."""
    import csv as csv_module

    csv_files: dict[str, Path] = {}

    raw_defs_text = ""
    if sections_dir:
        defs_path = Path(sections_dir) / "definitions.md"
        if defs_path.exists():
            raw_defs_text = defs_path.read_text(encoding="utf-8")

    raw_waterfall_text = ""
    if sections_dir:
        wf_path = Path(sections_dir) / "waterfall.md"
        if wf_path.exists():
            raw_waterfall_text = wf_path.read_text(encoding="utf-8")

    defs = extractions.get("definitions", [])

    deal_setup = _build_deal_setup(defs, deal_id, raw_defs_text)
    if deal_setup:
        deal_setup_path = data_dir / "deal_setup.csv"
        with open(deal_setup_path, "w", newline="", encoding="utf-8") as f:
            writer = csv_module.DictWriter(f, fieldnames=["Field", "Value"])
            writer.writeheader()
            writer.writerows(deal_setup)
        csv_files["deal_setup"] = deal_setup_path

    classes = _build_classes_setup(defs, raw_defs_text)
    if classes:
        classes_path = data_dir / "classes_setup.csv"
        with open(classes_path, "w", newline="", encoding="utf-8") as f:
            fieldnames = list(classes[0].keys())
            writer = csv_module.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(classes)
        csv_files["classes_setup"] = classes_path

    return csv_files


def _build_deal_setup(
    defs: list[dict], deal_id: str, raw_text: str = "",
) -> list[dict]:
    """Build deal_setup rows from definitions and raw section text."""
    import re

    rows: list[dict] = [{"Field": "deal_id", "Value": deal_id}]

    if raw_text:
        # Closing Date
        m = re.search(
            r"Closing\s+Date[:\s]+.*?(\w+\s+\d{1,2},?\s+\d{4})",
            raw_text, re.IGNORECASE,
        )
        if m:
            rows.append({"Field": "closing_date", "Value": m.group(1).strip()})

        # Cut-off Date
        m = re.search(
            r"Cut-?[Oo]ff\s+Date[:\s]+.*?(?:close\s+of\s+business\s+on\s+)?(\w+\s+\d{1,2},?\s+\d{4})",
            raw_text, re.IGNORECASE,
        )
        if m:
            rows.append({"Field": "cutoff_date", "Value": m.group(1).strip()})

        # Distribution Date
        m = re.search(
            r"Distribution\s+Date[:\s]+.*?((?:The\s+)?\d+(?:th|st|nd|rd)\s+day\s+of\s+each\s+\w+\s*\w*)",
            raw_text, re.IGNORECASE,
        )
        if m:
            rows.append({"Field": "distribution_date", "Value": m.group(1).strip()})

        # Aggregate pool balance
        for m in re.finditer(
            r"(?:aggregate|total)\s+Cut-?[Oo]ff\s+Date\s+Principal\s+Balance\s+of\s+(?:the\s+)?(?:Group\s+(I{1,3}|[12])\s+)?Mortgage\s+Loans\s+is\s+\$?([\d,]+(?:\.\d+)?)",
            raw_text, re.IGNORECASE,
        ):
            group = m.group(1) or "all"
            balance = m.group(2).replace(",", "")
            field = f"pool_balance_group_{group}" if group != "all" else "original_pool_balance"
            rows.append({"Field": field, "Value": balance})

        # Servicing Fee Rate
        m = re.search(
            r"Servicing\s+Fee\s+Rate[:\s]+.*?([\d.]+%)\s*per\s+annum",
            raw_text, re.IGNORECASE,
        )
        if m:
            rate = m.group(1).rstrip("%")
            rows.append({"Field": "servicing_fee_rate", "Value": str(float(rate) / 100)})

        # Trustee Fee
        m = re.search(
            r"Trustee\s+Fee:\s+[\s\S]*?([\d.]+)%\s*(?:multiplied|per\s+annum)",
            raw_text, re.IGNORECASE,
        )
        if m:
            rate = m.group(1)
            rows.append({"Field": "trustee_fee_rate", "Value": f"{float(rate) / 100:.10f}".rstrip("0").rstrip(".")})

        # Reserve Fund Deposit
        for m in re.finditer(
            r"Group\s+(I{1,3}|[12])\s+Reserve\s+Fund\s+Deposit:\s+[\s\S]*?\$\s*([\d,]+(?:\.\d+)?)",
            raw_text, re.IGNORECASE,
        ):
            group = m.group(1)
            val = m.group(2).replace(",", "")
            if float(val) > 0:
                rows.append({"Field": f"reserve_fund_group_{group}", "Value": val})

        # OC Target percentages
        for m in re.finditer(
            r"(?:Group\s+(I{1,3}|[12])\s+)?Overcollateralization\s+Target\s+Amount[:\s]+.*?([\d.]+%)\s*of",
            raw_text, re.IGNORECASE,
        ):
            group = m.group(1) or ""
            pct = m.group(2).rstrip("%")
            field = f"oc_target_pct_group_{group}" if group else "oc_target_pct"
            rows.append({"Field": field, "Value": str(float(pct) / 100)})

        # Number of Loan Groups
        groups = set(re.findall(r"Loan\s+Group\s+(I{1,3}|[12])\b", raw_text, re.IGNORECASE))
        if groups:
            rows.append({"Field": "num_loan_groups", "Value": str(len(groups))})

    else:
        key_terms = {
            "Closing Date": "closing_date",
            "Cut-Off Date": "cutoff_date",
            "Distribution Date": "distribution_date",
            "Record Date": "record_date",
        }
        for d in defs:
            term = d.get("term", "")
            for key, field_name in key_terms.items():
                if key.lower() in term.lower():
                    rows.append({
                        "Field": field_name,
                        "Value": d.get("value", d.get("definition", ""))[:100],
                    })
                    break

    return rows


def _build_classes_setup(
    defs: list[dict], raw_text: str = "",
) -> list[dict]:
    """Build classes_setup rows by mining raw section text for class details."""
    import re

    classes: list[dict] = []
    seen: set[str] = set()

    if raw_text:
        # Extract Certificate Margins from raw text
        margin_map: dict[str, str] = {}

        for m in re.finditer(
            r"(?:With\s+respect\s+to\s+)?(?:the\s+)?Class\s+([\w-]+)\s+Certificates?"
            r"[\s\S]{0,300}?(\d+\.\d+)%\s*per\s*annum",
            raw_text,
        ):
            cls_name = m.group(1).strip()
            margin = m.group(2)
            if cls_name not in margin_map and float(margin) < 10:
                margin_map[cls_name] = margin

        if not margin_map:
            for m in re.finditer(
                r"Class\s+([\w-]+)\s+Certificates?.*?(\d+\.\d+)%\s*per\s*annum",
                raw_text, re.IGNORECASE | re.DOTALL,
            ):
                cls_name = m.group(1).strip()
                margin = m.group(2)
                if cls_name not in margin_map and float(margin) < 10:
                    margin_map[cls_name] = margin

        # Extract class list
        class_pattern = re.compile(
            r"Class\s+((?:I{1,3}|II)-[A-Z]-?\d+|(?:I{1,3}|II)-[A-Z]\b|M-\d+|[A-Z]-\d+|CE|P|R(?:X|-\d+))",
            re.IGNORECASE,
        )

        all_classes: list[str] = []
        for cm in class_pattern.finditer(raw_text):
            cls_name = cm.group(1).strip().upper()
            if cls_name not in seen:
                seen.add(cls_name)
                all_classes.append(cls_name)

        # Extract pool balance per group
        pool_balances: dict[str, str] = {}
        for m in re.finditer(
            r"(?:aggregate|total)\s+Cut-?[Oo]ff\s+Date\s+Principal\s+Balance\s+of\s+(?:the\s+)?Group\s+(I{1,3}|[12])\s+Mortgage\s+Loans\s+is\s+\$?([\d,]+(?:\.\d+)?)",
            raw_text, re.IGNORECASE,
        ):
            pool_balances[m.group(1)] = m.group(2).replace(",", "")

        # Filter out aggregate parent classes
        filtered_classes = []
        for cls_name in all_classes:
            is_parent = False
            if re.match(r"^(?:I{1,3}|II)-[A-Z]$", cls_name):
                for other in all_classes:
                    if other.startswith(cls_name + "-") and other != cls_name:
                        is_parent = True
                        break
            if not is_parent:
                filtered_classes.append(cls_name)

        # Build class rows
        for cls_name in sorted(filtered_classes):
            group = ""
            if cls_name.startswith("I-"):
                group = "1"
            elif cls_name.startswith("II-"):
                group = "2"

            cls_upper = cls_name.upper()
            if "CE" in cls_upper:
                class_type = "credit_enhancement"
            elif cls_upper.startswith("R") or "RX" in cls_upper or re.match(r".*-R-?\d*$", cls_upper):
                class_type = "residual"
            elif cls_upper == "P" or cls_upper.endswith("-P"):
                class_type = "prepayment"
            elif re.match(r".*-?M-?\d+$", cls_upper):
                class_type = "mezzanine"
            elif re.match(r".*-?A-?\d*$", cls_upper) and "A" in cls_upper:
                class_type = "senior"
            else:
                class_type = "other"

            margin_val = margin_map.get(cls_name, "")
            if margin_val:
                margin_val = f"{float(margin_val) / 100:.6f}".rstrip("0").rstrip(".")

            balance = ""
            if class_type == "credit_enhancement":
                if group == "1" and "I" in pool_balances:
                    balance = pool_balances["I"]
                elif group == "2" and "II" in pool_balances:
                    balance = pool_balances["II"]

            classes.append({
                "class_name": cls_name,
                "group": group,
                "class_type": class_type,
                "original_balance": balance,
                "margin": margin_val,
                "current_balance": balance,
                "interest_type": "floating" if class_type in ("senior", "mezzanine") else "none",
                "day_count": "actual/360" if class_type in ("senior", "mezzanine") else "",
            })

    else:
        for d in defs:
            term = d.get("term", "")
            if re.match(r"Class\s+[A-Z0-9]", term, re.IGNORECASE):
                definition = d.get("definition", "")
                balance_match = re.search(r"\$[\d,]+(?:\.\d+)?", definition)
                balance = balance_match.group(0) if balance_match else ""
                classes.append({
                    "class_name": term,
                    "group": "",
                    "class_type": "",
                    "original_balance": balance,
                    "margin": "",
                    "current_balance": balance,
                    "interest_type": "",
                    "day_count": "",
                })

    return classes
