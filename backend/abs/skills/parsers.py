"""
Parsers — Adapter module that re-exports parsers from the v2 extraction layer.

This module provides a unified interface to all parsing functionality
for the ABS pipeline. It reuses the production-ready parsers from
abs_waterfall_ai_v2/extraction/parsers.py when available.

Ported from PayGen pipeline.skills.parsers → backend.abs.skills
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

# Add the v2 extraction path so we can import the existing parsers
_V2_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "abs_waterfall_ai_v2"
if str(_V2_ROOT) not in sys.path:
    sys.path.insert(0, str(_V2_ROOT))

try:
    from extraction.parsers import (
        DefinitionsParser,
        WaterfallParser,
        AccountsParser,
        LossAllocationParser,
        TriggersParser,
        ReportingRequirementsParser,
    )

    PARSERS_AVAILABLE = True
except ImportError:
    PARSERS_AVAILABLE = False


# ── Unified parse interface ───────────────────────────────────

def parse_section(section_type: str, text: str) -> list[dict]:
    """
    Parse a section using the appropriate parser.

    Args:
        section_type: One of "definitions", "waterfall_rules", "accounts",
                      "loss_allocations", "triggers", "reporting_requirements"
        text: Raw text content of the section

    Returns:
        List of extracted items (dicts)

    Raises:
        ValueError: If section_type is unknown
        ImportError: If v2 parsers are not available
    """
    if not PARSERS_AVAILABLE:
        raise ImportError(
            "Production parsers not available. Ensure abs_waterfall_ai_v2/ "
            "is in the workspace root."
        )

    parser_map = {
        "definitions": lambda t: DefinitionsParser.parse_definitions(t),
        "waterfall_rules": lambda t: WaterfallParser.parse_waterfall(t),
        "accounts": lambda t: AccountsParser.parse_accounts(t),
        "loss_allocations": lambda t: LossAllocationParser.parse_loss_allocation(t),
        "triggers": lambda t: TriggersParser.parse_triggers(t),
        "reporting_requirements": lambda t: ReportingRequirementsParser.parse_reporting(t),
    }

    if section_type not in parser_map:
        raise ValueError(
            f"Unknown section type: {section_type}. "
            f"Valid types: {list(parser_map.keys())}"
        )

    return parser_map[section_type](text)


def get_available_parsers() -> list[str]:
    """Return list of available parser section types."""
    if not PARSERS_AVAILABLE:
        return []
    return [
        "definitions", "waterfall_rules", "accounts",
        "loss_allocations", "triggers", "reporting_requirements",
    ]


# ── Section Splitter (lightweight) ────────────────────────────

def split_into_sections(
    text: str,
    section_map: dict[str, list[str]],
) -> dict[str, str]:
    """
    Split a document into sections using regex patterns.

    Args:
        text: Full document text
        section_map: Dict mapping section name → list of regex header patterns

    Returns:
        Dict mapping section name → section text
    """
    # Build a unified list of (position, section_name, match_end) tuples
    section_positions: list[tuple[int, str, int]] = []

    for section_name, patterns in section_map.items():
        for pattern in patterns:
            for m in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
                section_positions.append((m.start(), section_name, m.end()))

    # Sort by position in document
    section_positions.sort(key=lambda x: x[0])

    # Extract text between section headers
    sections: dict[str, str] = {}
    for i, (start, name, header_end) in enumerate(section_positions):
        # Text runs from header_end to start of next section (or end of doc)
        if i + 1 < len(section_positions):
            end = section_positions[i + 1][0]
        else:
            end = len(text)

        section_text = text[header_end:end].strip()

        # If same section found multiple times, concatenate
        if name in sections:
            sections[name] += "\n\n" + section_text
        else:
            sections[name] = section_text

    return sections
