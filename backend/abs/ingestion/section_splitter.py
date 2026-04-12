"""
Stage 2: Section Splitting — Split full.md into canonical sections.

Uses regex-first approach (Locked Decision D1) with per-issuer section maps.
Falls back to generic header detection when issuer-specific patterns miss.

Ported from PayGen pipeline.ingestion.section_splitter → backend.abs.ingestion
Import rewrites:
  pipeline.config.section_maps → backend.abs.config.section_maps
  pipeline.config.constants    → backend.abs.config.constants
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from backend.abs.config.section_maps import get_section_map, DEFAULT_SECTION_MAP
from backend.abs.config.constants import CANONICAL_SECTIONS

logger = logging.getLogger(__name__)


@dataclass
class SplitResult:
    """Result of section splitting."""
    sections: dict[str, Path]
    section_sizes: dict[str, int]
    unmatched_text_size: int
    total_sections: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "sections": {k: str(v) for k, v in self.sections.items()},
            "section_sizes": self.section_sizes,
            "unmatched_text_size": self.unmatched_text_size,
            "total_sections": self.total_sections,
            "warnings": self.warnings,
        }


def split_document(
    full_md_path: Path,
    output_dir: Path,
    issuer: str = "default",
    section_map: Optional[dict[str, str]] = None,
) -> SplitResult:
    """
    Split a full markdown document into canonical sections.

    Strategy:
    1. Load issuer-specific or default section map
    2. Scan document for section header matches (regex)
    3. Extract text between matched headers
    4. Write each section to output_dir/<section_name>.md
    5. Capture unmatched text as 'other.md'

    Args:
        full_md_path: Path to full.md document
        output_dir: Directory for section files (e.g., deal/sections/)
        issuer: Issuer name for section map lookup
        section_map: Optional override section map (pattern → canonical_name)

    Returns:
        SplitResult with paths to created section files

    Raises:
        FileNotFoundError: if full_md_path doesn't exist
    """
    full_md_path = Path(full_md_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not full_md_path.exists():
        raise FileNotFoundError(f"Document not found: {full_md_path}")

    text = full_md_path.read_text(encoding="utf-8")

    # Skip Table of Contents
    text = _skip_table_of_contents(text)

    if section_map is None:
        section_map = get_section_map(issuer)

    # Find all section boundaries
    matches = _find_section_boundaries(text, section_map)

    if not matches:
        # Fallback: try generic heading detection
        matches = _find_generic_headings(text)

    # Extract section content
    sections_content = _extract_sections(text, matches)

    # Write section files
    result = SplitResult(
        sections={},
        section_sizes={},
        unmatched_text_size=0,
        total_sections=0,
    )

    for section_name, content in sections_content.items():
        if not content.strip():
            continue

        filename = f"{section_name}.md"
        section_path = output_dir / filename
        section_path.write_text(content.strip(), encoding="utf-8")

        result.sections[section_name] = section_path
        result.section_sizes[section_name] = len(content.strip())
        result.total_sections += 1

    # Check for required sections
    required = {"definitions", "waterfall", "loss_allocations"}
    found = set(result.sections.keys())
    missing = required - found
    if missing:
        for m in sorted(missing):
            result.warnings.append(f"Required section missing: '{m}'")

    # Calculate unmatched text
    matched_chars = sum(result.section_sizes.values())
    result.unmatched_text_size = max(0, len(text) - matched_chars)

    return result


# ── Table of Contents Detection ───────────────────────────────

def _skip_table_of_contents(text: str) -> str:
    """
    Detect and skip the Table of Contents at the beginning of a document.
    """
    toc_pattern = re.compile(
        r"^.+\.{3,}\s*\d+\s*$", re.MULTILINE
    )

    toc_matches = list(toc_pattern.finditer(text))
    if not toc_matches:
        return text

    last_toc_end = toc_matches[-1].end()

    article_pattern = re.compile(
        r"^ARTICLE\s+[IVXLC]+\b",
        re.MULTILINE,
    )

    article_match = article_pattern.search(text, last_toc_end)
    if article_match:
        skip_to = article_match.start()
        logger.info(
            f"TOC detected (last dotted line at char {last_toc_end}). "
            f"Skipping to real content at char {skip_to} "
            f"(skipped {skip_to:,} of {len(text):,} chars)"
        )
        return text[skip_to:]

    logger.info(f"TOC detected but no ARTICLE header found after it. Skipping {last_toc_end:,} chars.")
    return text[last_toc_end:]


# ── Section Boundary Detection ────────────────────────────────

@dataclass
class _SectionMatch:
    """Internal: a matched section boundary."""
    position: int
    canonical_name: str
    header_end: int
    matched_pattern: str


def _find_section_boundaries(
    text: str,
    section_map: dict[str, str],
) -> list[_SectionMatch]:
    """Find section boundaries using regex patterns from section map."""
    matches: list[_SectionMatch] = []

    for pattern, canonical_name in section_map.items():
        try:
            for m in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
                matches.append(_SectionMatch(
                    position=m.start(),
                    canonical_name=canonical_name,
                    header_end=m.end(),
                    matched_pattern=pattern,
                ))
        except re.error as e:
            logger.warning(f"Invalid regex pattern '{pattern}': {e}")
            continue

    # Sort by position, remove duplicates
    matches.sort(key=lambda m: m.position)
    seen_positions: set[int] = set()
    unique: list[_SectionMatch] = []
    for m in matches:
        if m.position not in seen_positions:
            seen_positions.add(m.position)
            unique.append(m)

    return unique


def _find_generic_headings(text: str) -> list[_SectionMatch]:
    """Fallback: detect headings by markdown # headers or UPPERCASE lines."""
    matches: list[_SectionMatch] = []

    for m in re.finditer(r"^(#{1,3})\s+(.+)$", text, re.MULTILINE):
        header_text = m.group(2).strip().lower()
        canonical = _guess_canonical_name(header_text)
        matches.append(_SectionMatch(
            position=m.start(),
            canonical_name=canonical,
            header_end=m.end(),
            matched_pattern="generic_md_header",
        ))

    for m in re.finditer(r"^(ARTICLE\s+[IVXLC]+[\s\-—:]*\S.*)$", text, re.MULTILINE):
        header_text = m.group(1).strip().lower()
        canonical = _guess_canonical_name(header_text)
        matches.append(_SectionMatch(
            position=m.start(),
            canonical_name=canonical,
            header_end=m.end(),
            matched_pattern="generic_article_header",
        ))

    matches.sort(key=lambda m: m.position)
    return matches


def _guess_canonical_name(header_text: str) -> str:
    """Best-effort mapping of a header to a canonical section name."""
    header_lower = header_text.lower()

    keyword_map = {
        "definitions": "definitions",
        "defined terms": "definitions",
        "distribution": "waterfall",
        "waterfall": "waterfall",
        "payment": "waterfall",
        "priority": "waterfall",
        "application of funds": "waterfall",
        "account": "accounts",
        "trust account": "accounts",
        "loss alloc": "loss_allocations",
        "realized loss": "loss_allocations",
        "write-down": "loss_allocations",
        "writedown": "loss_allocations",
        "trigger": "triggers",
        "stepdown": "triggers",
        "step-down": "triggers",
        "overcollateral": "triggers",
        "report": "reporting_requirements",
        "statement": "reporting_requirements",
        "collection": "collections",
        "available funds": "collections",
        "credit enhance": "credit_enhancement",
        "subordinat": "credit_enhancement",
        "reserve fund": "credit_enhancement",
        "servic": "servicing",
        "default": "events_of_default",
    }

    for keyword, canonical in keyword_map.items():
        if keyword in header_lower:
            return canonical

    return "other"


def _extract_sections(
    text: str,
    matches: list[_SectionMatch],
) -> dict[str, str]:
    """Extract section content between boundaries."""
    if not matches:
        return {"other": text}

    sections: dict[str, str] = {}

    if matches[0].position > 0:
        preamble = text[: matches[0].position].strip()
        if preamble:
            sections["preamble"] = preamble

    for i, match in enumerate(matches):
        if i + 1 < len(matches):
            end = matches[i + 1].position
        else:
            end = len(text)

        content = text[match.header_end: end].strip()
        header = text[match.position: match.header_end].strip()
        full_content = f"{header}\n\n{content}" if header else content

        name = match.canonical_name
        if name in sections:
            sections[name] += "\n\n" + full_content
        else:
            sections[name] = full_content

    return sections
