"""Phase 19 — OneNote Semantic Chunker.

Converts ``OneNotePage`` objects into ``TextChunk`` instances ready for
vector-store ingestion.

Chunking strategies
-------------------
Release-notes section (detected by section name pattern)
    One page → one atomic chunk.  The monthly release-note page is
    already a bounded semantic unit; splitting it would break temporal
    retrieval ("when was X added?").  Pages up to 2 000 tokens are kept
    whole; larger pages (rare) fall back to heading-boundary splitting.

Standard sections (all others)
    Outline-container aware splitting at the following priority order:
    1. Heading boundaries (bold/capitalised lines, ## markers)
    2. Paragraph / blank-line boundaries when a container exceeds the
       token budget (~600 tokens)
    3. Table rows: large tables (>30 rows) are split into header + 25-row
       slices, carrying the header forward in every slice.

Metadata in chunks
------------------
Each chunk's *content* is prefixed with a context header:

    [Section: Tech Tips] [Page: Filemask Legend] [Chunk 2/5]

This ensures that retrieval results always carry provenance, even when
only the content text is passed downstream.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Optional

from backend.common.models import TextChunk
from backend.ingestion.onenote_converter import OneNotePage, OneNoteTable

# ── Constants ──────────────────────────────────────────────────────────────

# Rough token estimate: 1 token ≈ 4 chars
_CHARS_PER_TOKEN = 4
_TOKEN_BUDGET_STANDARD = 600    # target chunk size (tokens)
_TOKEN_BUDGET_MAX      = 1500   # hard ceiling before forced split
_TOKEN_BUDGET_RELEASE  = 2000   # release-notes section max (tokens)
_TABLE_MAX_ROWS        = 25     # rows per table slice

# Section-name patterns that indicate a release-notes section
_RELEASE_NOTES_PATTERNS = [
    re.compile(r'release\s*note', re.IGNORECASE),
    re.compile(r'what.s\s*new',   re.IGNORECASE),
    re.compile(r'change\s*log',   re.IGNORECASE),
    re.compile(r'version\s*hist', re.IGNORECASE),
    re.compile(r'update\s*hist',  re.IGNORECASE),
]

# Month names for release-date extraction from page titles
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


# ── Public API ─────────────────────────────────────────────────────────────

def chunk_onenote_page(
    page: OneNotePage,
    section_name: str,
    one_file_path: str,
    notebook_name: str = "OneNote",
    section_order: int = 0,
    image_descriptions: Optional[list[str]] = None,
) -> list[TextChunk]:
    """Convert one ``OneNotePage`` into one or more ``TextChunk`` objects.

    Parameters
    ----------
    page : OneNotePage
    section_name : str
        Human-readable section name (e.g. "Release Notes", "Tech Tips").
    one_file_path : str
        Absolute path to the source .one file.
    notebook_name : str
        Notebook display name (for doc_id and metadata).
    section_order : int
        Position of this section in the notebook (0-based).
    image_descriptions : list[str] | None
        GPT-4.1 vision descriptions for each image on this page.
        If provided, they are appended as text blocks before chunking.

    Returns
    -------
    list[TextChunk]
        Ordered chunks ready for vector-store insertion.
    """
    # Merge image descriptions into text blocks
    enriched_blocks = list(page.text_blocks)
    if image_descriptions:
        for i, desc in enumerate(image_descriptions):
            if desc and desc.strip():
                enriched_blocks.append(f"[Image {i + 1}]: {desc.strip()}")

    # Build the effective text (tables rendered as markdown)
    table_texts = [t.to_markdown() for t in page.tables if t.to_markdown()]
    all_blocks = enriched_blocks + table_texts

    # Detect section type
    if _is_release_notes_section(section_name):
        raw_chunks = _chunk_release_notes_page(page, all_blocks)
    else:
        raw_chunks = _chunk_standard_page(page, all_blocks)

    # Wrap into TextChunk objects with metadata headers
    doc_id = _make_doc_id(notebook_name, section_name)
    result: list[TextChunk] = []
    total = len(raw_chunks)
    for idx, text in enumerate(raw_chunks):
        if not text.strip():
            continue
        header = _make_header(section_name, page.title, idx, total, section_order)
        content = f"{header}\n\n{text.strip()}"
        chunk_id = _make_chunk_id(doc_id, page.guid, idx)
        result.append(TextChunk(
            chunk_id=chunk_id,
            doc_id=doc_id,
            content=content,
            source_path=one_file_path,
            chunk_index=page.order_index * 1000 + idx,
            doc_type=_doc_type(section_name),
        ))

    return result


# ── Section type helpers ───────────────────────────────────────────────────

def _is_release_notes_section(section_name: str) -> bool:
    return any(p.search(section_name) for p in _RELEASE_NOTES_PATTERNS)


def _doc_type(section_name: str) -> str:
    if _is_release_notes_section(section_name):
        return "ONENOTE_RELEASE_NOTES"
    return "ONENOTE_GUIDE"


# ── Release-notes chunking ─────────────────────────────────────────────────

def _chunk_release_notes_page(page: OneNotePage, blocks: list[str]) -> list[str]:
    """Keep a release-notes page as a single atomic chunk.

    The full text is kept together so temporal queries ("when was X added")
    always hit one complete monthly entry.  Only split if content exceeds
    the release-notes token budget.
    """
    full = "\n\n".join(b.strip() for b in blocks if b.strip())
    # Prepend title so it's always searchable
    if page.title and page.title not in full:
        full = f"{page.title}\n\n{full}"

    if _token_estimate(full) <= _TOKEN_BUDGET_RELEASE:
        return [full]

    # Oversized page — split at heading boundaries (unusual but safe to handle)
    return _split_at_headings(full, _TOKEN_BUDGET_RELEASE)


# ── Standard section chunking ──────────────────────────────────────────────

def _chunk_standard_page(page: OneNotePage, blocks: list[str]) -> list[str]:
    """Semantic chunking for non-release-notes pages.

    Priority:
    1. Natural block boundaries (OneNote outline containers map to blocks)
    2. Heading boundaries within a large block
    3. Sentence-boundary fallback if a block still exceeds token budget
    """
    # Identify large table blocks (already rendered as markdown)
    processed: list[str] = []
    for block in blocks:
        if block.strip().startswith("|") and block.count("\n") > _TABLE_MAX_ROWS:
            # Large table — split into row slices
            processed.extend(_split_large_table(block))
        else:
            processed.append(block)

    # Add title as first content item if not already present
    title_block = page.title
    has_title = any(title_block.lower() in b.lower() for b in processed[:3])
    if not has_title and title_block:
        processed = [title_block] + processed

    # Merge small adjacent blocks, split large ones
    chunks = _merge_and_split_blocks(processed, _TOKEN_BUDGET_STANDARD, _TOKEN_BUDGET_MAX)
    return chunks


def _merge_and_split_blocks(blocks: list[str], target: int, ceiling: int) -> list[str]:
    """Merge too-small blocks together; split too-large blocks.

    Returns chunks where each is roughly within [target/3 … ceiling] tokens.
    """
    chunks: list[str] = []
    buffer: list[str] = []
    buffer_tokens = 0

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        btokens = _token_estimate(block)

        if btokens > ceiling:
            # Flush buffer first
            if buffer:
                chunks.append("\n\n".join(buffer))
                buffer, buffer_tokens = [], 0
            # Split oversized block
            chunks.extend(_split_at_headings(block, target))
        elif buffer_tokens + btokens > target and buffer:
            chunks.append("\n\n".join(buffer))
            buffer, buffer_tokens = [block], btokens
        else:
            buffer.append(block)
            buffer_tokens += btokens

    if buffer:
        chunks.append("\n\n".join(buffer))

    return [c for c in chunks if c.strip()]


def _split_at_headings(text: str, token_budget: int) -> list[str]:
    """Split *text* at heading boundaries, then at sentence boundaries if needed."""
    # Heading patterns: ## heading, **Bold**, UPPERCASE LINE, "Title:"
    _HEADING_RE = re.compile(
        r'(?m)^(?:#{1,3}\s+.+|'          # ## Heading
        r'\*\*[^*]+\*\*\s*$|'            # **Bold line**
        r'[A-Z][A-Z\s]{4,}[A-Z]\s*$|'   # UPPERCASE LINE
        r'[A-Z][a-z].*:\s*$)',           # Title:
    )
    positions = [0] + [m.start() for m in _HEADING_RE.finditer(text)] + [len(text)]
    sections = [text[positions[i]:positions[i + 1]].strip()
                for i in range(len(positions) - 1)
                if text[positions[i]:positions[i + 1]].strip()]

    result: list[str] = []
    buffer = ""
    for sec in sections:
        candidate = (buffer + "\n\n" + sec).strip() if buffer else sec
        if _token_estimate(candidate) <= token_budget:
            buffer = candidate
        else:
            if buffer:
                result.append(buffer)
            if _token_estimate(sec) <= token_budget:
                buffer = sec
            else:
                # Last resort: sentence-boundary split
                result.extend(_split_at_sentences(sec, token_budget))
                buffer = ""
    if buffer:
        result.append(buffer)

    return result or [text]


def _split_at_sentences(text: str, token_budget: int) -> list[str]:
    """Fallback: split at sentence boundaries if a block is still too large."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks: list[str] = []
    buffer = ""
    for sent in sentences:
        candidate = (buffer + " " + sent).strip() if buffer else sent
        if _token_estimate(candidate) <= token_budget:
            buffer = candidate
        else:
            if buffer:
                chunks.append(buffer)
            buffer = sent
    if buffer:
        chunks.append(buffer)
    return chunks or [text]


# ── Table splitting ────────────────────────────────────────────────────────

def _split_large_table(md_table: str) -> list[str]:
    """Split a large markdown table into header + row-slices of _TABLE_MAX_ROWS."""
    lines = md_table.strip().splitlines()
    if len(lines) < 3:
        return [md_table]

    header_line = lines[0]
    sep_line    = lines[1] if lines[1].startswith("|---") or lines[1].startswith("| --") else ""
    data_lines  = lines[2:] if sep_line else lines[1:]
    header_block = f"{header_line}\n{sep_line}" if sep_line else header_line

    result: list[str] = []
    for start in range(0, len(data_lines), _TABLE_MAX_ROWS):
        rows = data_lines[start : start + _TABLE_MAX_ROWS]
        slice_text = header_block + "\n" + "\n".join(rows)
        result.append(slice_text)

    return result or [md_table]


# ── Release-date extraction ────────────────────────────────────────────────

def extract_release_date(page_title: str) -> Optional[tuple[int, int]]:
    """Parse (year, month) from a release-notes page title, or None.

    Examples that are handled:
      "Release Notes - March 2024"   → (2024, 3)
      "March 2024 Update"            → (2024, 3)
      "2024-03 Release"              → (2024, 3)
    """
    # Pattern: Month YYYY  or  YYYY-MM
    m = re.search(
        r'(?P<month_name>[A-Za-z]+)\s+(?P<year>\d{4})'
        r'|(?P<year2>\d{4})[-/](?P<month_num>\d{1,2})',
        page_title,
    )
    if not m:
        return None
    if m.group("month_name"):
        mon = _MONTH_MAP.get(m.group("month_name").lower()[:3])
        yr  = int(m.group("year"))
        return (yr, mon) if mon else None
    else:
        yr  = int(m.group("year2"))
        mon = int(m.group("month_num"))
        return (yr, mon) if 1 <= mon <= 12 else None


# ── Utilities ──────────────────────────────────────────────────────────────

def _token_estimate(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _make_doc_id(notebook_name: str, section_name: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '_', section_name.lower()).strip('_')
    nb   = re.sub(r'[^a-z0-9]+', '_', notebook_name.lower()).strip('_')
    return f"onenote_{nb}_{slug}"


def _make_chunk_id(doc_id: str, page_guid: str, idx: int) -> str:
    raw = f"{doc_id}::{page_guid}::{idx}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _make_header(
    section_name: str,
    page_title: str,
    chunk_idx: int,
    total_chunks: int,
    section_order: int,
) -> str:
    parts = [f"[Section: {section_name}]", f"[Page: {page_title}]"]
    if total_chunks > 1:
        parts.append(f"[Chunk {chunk_idx + 1}/{total_chunks}]")
    return " ".join(parts)
