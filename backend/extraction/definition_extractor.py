"""
Module 1: Term Dictionary Extraction

Extracts {term_name: definition_text} from Article I (Definitions section).
Uses a state-machine parser that handles:
  - Pattern A: "Term Name": definition text...
  - Pattern B: "Term Name" means definition text...
  - Pattern C: "Term Name" shall mean definition text...
  - Multi-paragraph definitions
  - Definitions with sub-clauses (i), (ii), (iii)
  - Definitions that span page breaks (linearised text)
"""

from __future__ import annotations

import logging
import re
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Quoted capitalised term followed by a definition separator
# Supports both ASCII straight quotes (") and Unicode smart/curly quotes (“ ”)
# which are common in PDF-extracted text.
DEFINITION_START = re.compile(
    r'["\u201c\u2018]([A-Z][A-Za-z\s\-/\'()]+?)["\u201d\u2019]'  # Quoted capitalised term name
    r'\s*'                                   # Optional whitespace
    r'(?::|shall\s+mean|means|is\s+defined\s+as|has\s+the\s+meaning)',  # Separator patterns
    re.MULTILINE,
)

# Unquoted "Title Case Term: definition" format (common in .doc conversions and PDF)
# Supports hyphens, digits, and single-letter words in term names.
DEFINITION_START_COLON = re.compile(
    r'^([A-Z][A-Za-z0-9\-]+(?:\s+[A-Za-z0-9\-]+)*)'
    r'\s*:\s+(?=[A-Za-z(])',                # Colon followed by word or paren
    re.MULTILINE,
)

# Phase 18: Bare (unquoted) capitalised term followed by "means" / "shall mean"
# Common in PDFs where quote marks are stripped or missing.
# Requires term to be at start of line or after whitespace, with 2+ words
# to avoid false positives from ordinary sentences.
DEFINITION_BARE_MEANS = re.compile(
    r'(?:^|\n)\s*'
    r'([A-Z][A-Za-z]+(?:\s+[A-Z][a-z]+)+(?:\s+[A-Z][a-z]+)*)'  # Multi-word title-case term
    r'\s+'
    r'(?:shall\s+mean|means|is\s+defined\s+as|has\s+the\s+meaning)',
    re.MULTILINE,
)

# Glossary/acronym patterns for non-legal documents:
# "ABBREVIATION (Full Form)" or "Full Form (ABBREVIATION)"
GLOSSARY_ABBREV = re.compile(
    r'^([A-Z][A-Z0-9/]{1,15})\s*[\u2013\u2014\-]\s*(.+?)$'   # ABBR – Full form
    r'|'
    r'^([A-Z][A-Za-z0-9 \-/]{2,60}?)\s*\(([A-Z][A-Z0-9/]{1,15})\)',  # Full Form (ABBR)
    re.MULTILINE,
)

# Term followed by dash/em-dash/en-dash then definition (tech glossaries)
GLOSSARY_DASH = re.compile(
    r'^([A-Z][A-Za-z0-9 \-/]{2,60}?)\s*[\u2013\u2014]\s*(.+?)$',
    re.MULTILINE,
)

# Section/Article boundary markers (signals end of Article I definitions)
ARTICLE_BOUNDARY = re.compile(
    r'^\s*ARTICLE\s+[IVX]+[.\s]',
    re.MULTILINE,
)

# Dot-leader pattern (detects Table of Contents entries like "Section 1.01 ......19")
_TOC_DOTLEADER = re.compile(r'\.{4,}')

# Minimum section length to accept a definitions section candidate (chars).
# A real definitions section is thousands of chars; a TOC stub is < 1000.
_MIN_SECTION_LENGTH = 2000


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_glossary_lines(section_text: str) -> Dict[str, str]:
    """
    Parse glossary / acronym list formats that are common in technical docs.

    Supported formats:
      ABBR – Full form description          (dash-separated abbreviation)
      Full Form Name (ABBR)                 (parenthetical abbreviation)
      Term: definition text                 (colon-separated)
      Term — definition text                (em-dash / en-dash separated)
    """
    dictionary: Dict[str, str] = {}

    for line in section_text.splitlines():
        line = line.strip()
        if not line or len(line) < 4:
            continue

        # Pattern: ABBR – Full description  or  ABBR - Full description
        m = re.match(
            r'^([A-Z][A-Z0-9/]{1,15})\s*[\u2013\u2014\-]\s*(.+)$', line
        )
        if m:
            dictionary[m.group(1).strip()] = m.group(2).strip()
            continue

        # Pattern: Full Form Name (ABBR)
        m = re.match(
            r'^([A-Z][A-Za-z0-9 \-/]{2,60}?)\s*\(([A-Z][A-Z0-9/]{1,15})\)\s*$',
            line,
        )
        if m:
            full_form = m.group(1).strip()
            abbrev = m.group(2).strip()
            # Store both directions
            dictionary[abbrev] = full_form
            dictionary[full_form] = abbrev
            continue

        # Pattern: Title Case Term: definition sentence
        m = re.match(
            r'^([A-Z][A-Za-z]+(?:\s+[A-Za-z]+){0,5})\s*:\s+(.{10,})$', line
        )
        if m:
            dictionary[m.group(1).strip()] = m.group(2).strip()
            continue

        # Pattern: Term — definition  (em/en-dash — not plain hyphen to
        # avoid splitting hyphenated compound words)
        m = re.match(
            r'^([A-Z][A-Za-z0-9 ]{2,50}?)\s*[\u2013\u2014]\s*(.{10,})$', line
        )
        if m:
            dictionary[m.group(1).strip()] = m.group(2).strip()
            continue

    return dictionary


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_definitions_section(text: str) -> Tuple[str, int, int]:
    """
    Locate the Definitions section boundaries.

    Supports legal docs (Article I / Section 1.01 / DEFINITIONS heading)
    and non-legal docs (Glossary, Acronyms, Abbreviations, Terms, etc.).

    Returns:
        (section_text, start_offset, end_offset)
    """
    # Try "ARTICLE I" + "DEFINITIONS" header first
    art1_match = re.search(
        r'ARTICLE\s+I[.\s]*\n\s*(?:DEFINITIONS|Definitions)',
        text,
        re.MULTILINE,
    )
    if not art1_match:
        # Fallback: "Section 1.01" as definitions start
        art1_match = re.search(r'Section\s+1\.01', text)

    if not art1_match:
        # Fallback: bare "DEFINITIONS" heading on its own line
        # (.doc conversions may omit the ARTICLE prefix)
        art1_match = re.search(
            r'(?:^|\n)\n(DEFINITIONS)\s*\n',
            text,
        )

    if not art1_match:
        # Non-legal fallback: Glossary, Acronyms, Abbreviations, Terms
        # Common in technical guides, user manuals, troubleshooting docs
        art1_match = re.search(
            r'(?m)^\s*(?:#{0,4}\s*)?'
            r'(?:GLOSSARY|Glossary|ACRONYMS|Acronyms|ABBREVIATIONS|Abbreviations'
            r'|TERMS\s+AND\s+DEFINITIONS|Terms\s+and\s+Definitions'
            r'|KEY\s+TERMS|Key\s+Terms|TERMINOLOGY|Terminology)'
            r'\s*$',
            text,
        )

    if not art1_match:
        return '', 0, 0

    # Phase 18-fix: Skip TOC false-positives.
    # PDFs often have a Table of Contents with entries like
    #     ARTICLE I
    #     DEFINITIONS
    #     Section 1.01 Defined Terms.......19
    #     ARTICLE II
    # The first regex match hits the TOC stub (< 2000 chars) instead of
    # the real definitions section.  Detect this by checking candidate
    # length and presence of dot-leaders, then advance to the next match.
    _section_pattern = re.compile(
        r'ARTICLE\s+I[.\s]*\n\s*(?:DEFINITIONS|Definitions)'
        r'|Section\s+1\.01'
        r'|(?:^|\n)\n(DEFINITIONS)\s*\n'
        r'|^\s*(?:#{0,4}\s*)?'
        r'(?:GLOSSARY|Glossary|ACRONYMS|Acronyms|ABBREVIATIONS|Abbreviations'
        r'|TERMS\s+AND\s+DEFINITIONS|Terms\s+and\s+Definitions'
        r'|KEY\s+TERMS|Key\s+Terms|TERMINOLOGY|Terminology)'
        r'\s*$',
        re.MULTILINE,
    )
    while art1_match:
        start = art1_match.start()
        remaining = text[art1_match.end():]
        end_match = ARTICLE_BOUNDARY.search(remaining)
        if end_match:
            candidate = text[start:art1_match.end() + end_match.start()]
        else:
            candidate = text[start:start + 100_000]

        # Accept if long enough and not a TOC entry
        if len(candidate) >= _MIN_SECTION_LENGTH and not _TOC_DOTLEADER.search(candidate):
            break  # Good candidate

        logger.debug(
            'Skipping TOC-like definitions stub (%d chars) at offset %d.',
            len(candidate), start,
        )
        art1_match = _section_pattern.search(text, art1_match.end())

    if not art1_match:
        return '', 0, 0

    start = art1_match.start()

    # End: next ARTICLE boundary after definitions start
    remaining = text[art1_match.end():]
    end_match = ARTICLE_BOUNDARY.search(remaining)

    if not end_match:
        # Fallback: next all-caps heading preceded by blank line
        # (body headings in .doc conversions)
        end_match = re.search(
            r'\n\n([A-Z][A-Z ,;:&\-\u2013\u2014()/]{7,79})\s*\n',
            remaining,
        )

    if not end_match:
        # Non-legal fallback: next chapter/section heading
        end_match = re.search(
            r'(?m)^\s*(?:Chapter|CHAPTER|Section|SECTION|\d+[\.\s])\s+',
            remaining,
        )

    if end_match:
        end = art1_match.end() + end_match.start()
    else:
        end = min(start + 100_000, len(text))

    return text[start:end], start, end


def extract_term_dictionary(text: str) -> Dict[str, str]:
    """
    Extract all defined terms from the Definitions section.

    Returns:
        Dictionary mapping term names to their complete, verbatim definition text.
    """
    section_text, _start, _end = extract_definitions_section(text)
    if not section_text:
        logger.warning('Could not locate Definitions section in document.')
        return {}

    matches = list(DEFINITION_START.finditer(section_text))
    if not matches:
        # Fallback: try unquoted colon format (e.g. "Distribution Date: ...")
        matches = list(DEFINITION_START_COLON.finditer(section_text))

    if not matches:
        # Phase 18: Try bare (unquoted) capitalised terms followed by "means"
        matches = list(DEFINITION_BARE_MEANS.finditer(section_text))

    # ---- Non-legal glossary fast-path (returns early) ---- #
    if not matches:
        # Try abbreviation and dash-separated glossary formats
        glossary_terms = _parse_glossary_lines(section_text)
        if glossary_terms:
            logger.info(
                'Extracted %d glossary/acronym terms (non-legal format).',
                len(glossary_terms),
            )
            return glossary_terms

    if not matches:
        logger.warning('No definition patterns found in Definitions section.')
        return {}

    dictionary: Dict[str, str] = {}
    duplicates: list[str] = []

    for i, match in enumerate(matches):
        term_name = match.group(1).strip()

        def_start = match.end()
        def_end = matches[i + 1].start() if i + 1 < len(matches) else len(section_text)

        definition_text = section_text[def_start:def_end].strip()
        # Normalise internal whitespace but keep single spaces
        definition_text = re.sub(r'\s+', ' ', definition_text).strip()

        if not term_name or not definition_text:
            continue

        if term_name in dictionary:
            duplicates.append(term_name)
            logger.warning('Duplicate defined term "%s" — later definition kept.', term_name)

        dictionary[term_name] = definition_text

    logger.info(
        'Extracted %d defined terms (%d duplicates overwritten).',
        len(dictionary),
        len(duplicates),
    )
    return dictionary
