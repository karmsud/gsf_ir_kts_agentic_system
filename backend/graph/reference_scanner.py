"""
Module 3: Reference Scanning

Scans each definition's text to find all referenced defined terms.
Uses longest-match dictionary scanning to produce DEPENDS_ON edges.
Also extracts section cross-references (e.g., "Section 5.04(b)").
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Section cross-reference pattern
# ---------------------------------------------------------------------------

SECTION_REF_PATTERN = re.compile(
    r'(?:Section|Sections)\s+(\d+\.\d+(?:\([a-z]\))?(?:\([ivx]+\))?)'
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_reference_map(term_dictionary: Dict[str, str]) -> Dict[str, Set[str]]:
    """
    For each term, find all other terms referenced in its definition.

    Uses longest-match scanning: if both "Certificate" and
    "Certificate Principal Balance" are defined, only the longer match
    at a given position is recorded.

    Args:
        term_dictionary: {term_name → definition_text} from Module 1.

    Returns:
        {term_name → set of referenced term names}
    """
    # Sort terms longest-first for greedy matching
    sorted_terms = sorted(term_dictionary.keys(), key=len, reverse=True)

    reference_map: Dict[str, Set[str]] = {}

    for term_name, definition_text in term_dictionary.items():
        references: Set[str] = set()
        pos = 0

        while pos < len(definition_text):
            matched = False
            for candidate in sorted_terms:
                if candidate == term_name:
                    continue  # no self-references

                end = pos + len(candidate)
                if end > len(definition_text):
                    continue

                if definition_text[pos:end] == candidate:
                    references.add(candidate)
                    pos = end
                    matched = True
                    break

            if not matched:
                pos += 1

        reference_map[term_name] = references

    total_edges = sum(len(v) for v in reference_map.values())
    logger.info(
        'Reference scanning complete: %d terms, %d DEPENDS_ON edges.',
        len(reference_map),
        total_edges,
    )
    return reference_map


def extract_section_references(definition_text: str) -> List[str]:
    """Extract section cross-references (e.g., ``Section 5.04(b)``)."""
    return [m.group(1) for m in SECTION_REF_PATTERN.finditer(definition_text)]


def build_section_reference_map(term_dictionary: Dict[str, str]) -> Dict[str, List[str]]:
    """
    For each term, extract section cross-references from its definition text.

    Returns:
        {term_name → list of section ids like "5.04", "3.01(a)"}
    """
    section_map: Dict[str, List[str]] = {}

    for term_name, definition_text in term_dictionary.items():
        refs = extract_section_references(definition_text)
        if refs:
            section_map[term_name] = refs

    return section_map
