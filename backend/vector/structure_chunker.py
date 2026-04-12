"""Phase 19.2 — Structure-Aware Chunker (Non-Legal Store 3).

Converts the non-legal document into a structured markdown
representation first, then chunks at heading boundaries.

This approach preserves the document's natural hierarchy (H1 → H2 → H3)
and keeps related content together.  It works especially well when the
source document has some structural cues — numbered headings, bold
labels, separator lines, or even consistent indentation.

Pipeline:
1. **Structure detection** — identify headings, separators, tables, lists
2. **Markdown normalisation** — rewrite as clean markdown with hierarchy
3. **Heading-boundary chunking** — split at heading boundaries
4. **Contextual enrichment** — prepend breadcrumb path (H1 > H2 > H3)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from backend.common.models import TextChunk


# ── Structure detection patterns ──────────────────────────────────

# Markdown headings (already in doc)
_MD_HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

# Numbered headings: "1.", "1.2", "1.2.3", "A.", "A.1"
_NUMBERED_HEADING_RE = re.compile(
    r'^(?:'
    r'(?:\d+\.)+\s+[A-Z]'             # 1. Title, 1.2. Title
    r'|[A-Z]\.\d*\s+[A-Z]'           # A. Title, A.1 Title
    r')',
    re.MULTILINE,
)

# Bold/uppercase line headings (common in Word docs):
#   **Bold Heading**, UPPERCASE HEADING, Title Case Heading (followed by content)
_BOLD_HEADING_RE = re.compile(
    r'^\*\*(.+?)\*\*\s*$'             # **Bold Heading**
    r'|^([A-Z][A-Z\s]{5,}[A-Z])\s*$'  # UPPERCASE HEADING (min 7 chars)
    r'|^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,6})\s*[:—\-]?\s*$',  # Title Case:
    re.MULTILINE,
)

# Table-like lines (for table detection)
_TABLE_LINE_RE = re.compile(r'^[|+][-+|]+[|+]$', re.MULTILINE)

# Horizontal separators
_SEPARATOR_RE = re.compile(r'^[-=_*]{3,}\s*$', re.MULTILINE)


@dataclass
class StructuredSection:
    """A section parsed from the document structure."""
    level: int             # Heading level (1-6)
    heading: str           # Section heading text
    content: str           # Section content (text after heading)
    start_pos: int = 0
    end_pos: int = 0
    children: List['StructuredSection'] = field(default_factory=list)
    breadcrumb: str = ""   # "H1 > H2 > H3" path


def _detect_headings(text: str) -> List[Tuple[int, int, str]]:
    """Detect all heading positions and their levels.

    Returns
    -------
    List[Tuple[int, int, str]]
        (position, level, heading_text) sorted by position.
    """
    headings = []

    # Markdown headings → use # count as level
    for m in _MD_HEADING_RE.finditer(text):
        level = len(m.group(1))
        headings.append((m.start(), level, m.group(2).strip()))

    # Numbered headings → count dots for level
    for m in _NUMBERED_HEADING_RE.finditer(text):
        line = text[m.start():text.find('\n', m.start())]
        line = line.strip()
        # Count depth by dots: "1." = level 2, "1.2." = level 3
        dots = line.split('.', 1)[0].count('.') + 1
        num_part = re.match(r'[\d.A-Z]+\s*', line)
        heading_text = line[num_part.end():] if num_part else line
        level = min(dots + 1, 4)
        headings.append((m.start(), level, heading_text.strip()))

    # Bold/uppercase headings → level 2 (sub-headings)
    for m in _BOLD_HEADING_RE.finditer(text):
        heading_text = m.group(1) or m.group(2) or m.group(3)
        if heading_text:
            headings.append((m.start(), 2, heading_text.strip()))

    # Deduplicate overlapping detections (prefer earlier, higher-priority)
    headings.sort(key=lambda h: h[0])
    deduped = []
    last_pos = -50
    for pos, level, text_h in headings:
        if pos - last_pos < 10:  # Too close to previous — skip
            continue
        deduped.append((pos, level, text_h))
        last_pos = pos

    return deduped


def _build_hierarchy(
    text: str,
    headings: List[Tuple[int, int, str]],
) -> List[StructuredSection]:
    """Build a flat list of sections with breadcrumb paths."""
    if not headings:
        return [StructuredSection(
            level=1,
            heading="Document",
            content=text,
            start_pos=0,
            end_pos=len(text),
            breadcrumb="Document",
        )]

    sections = []
    # Track current heading stack for breadcrumb
    heading_stack: List[Tuple[int, str]] = []  # (level, heading)

    for i, (pos, level, heading) in enumerate(headings):
        # Content is text between this heading and next heading (or end)
        next_pos = headings[i + 1][0] if i + 1 < len(headings) else len(text)

        # Content starts after the heading line
        content_start = text.find('\n', pos)
        content_start = content_start + 1 if content_start >= 0 else pos
        content = text[content_start:next_pos].strip()

        # Update heading stack for breadcrumb
        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        heading_stack.append((level, heading))
        breadcrumb = " > ".join(h[1] for h in heading_stack)

        sections.append(StructuredSection(
            level=level,
            heading=heading,
            content=content,
            start_pos=pos,
            end_pos=next_pos,
            breadcrumb=breadcrumb,
        ))

    # If first heading doesn't start at 0, add preamble section
    if headings[0][0] > 0:
        preamble = text[:headings[0][0]].strip()
        if preamble and len(preamble) >= 50:
            sections.insert(0, StructuredSection(
                level=1,
                heading="Introduction",
                content=preamble,
                start_pos=0,
                end_pos=headings[0][0],
                breadcrumb="Introduction",
            ))

    return sections


def _extract_error_codes(text: str) -> List[str]:
    """Extract error codes from text."""
    patterns = [
        r'\bERR[-_]?[A-Z]*[-_]?\d{3,}\b',
        r'\bHTTP\s*\d{3}\b',
        r'\b[A-Z]{2,}\d{3,4}\b',
        r'\bError\s+(?:Code\s*)?(\d{3,})\b',
        r'\b0x[0-9A-Fa-f]{4,}\b',
    ]
    codes = set()
    for p in patterns:
        for m in re.finditer(p, text, re.IGNORECASE):
            codes.add(m.group().strip())
    return sorted(codes)


def chunk_by_structure(
    doc_id: str,
    source_path: str,
    text: str,
    target_chunk_size: int = 1500,
    max_chunk_size: int = 4000,
    min_chunk_size: int = 100,
    merge_short_sections: bool = True,
) -> List[TextChunk]:
    """Chunk a document by its structural headings with breadcrumb context.

    Parameters
    ----------
    doc_id : str
        Document identifier.
    source_path : str
        Source file path.
    text : str
        Full document text.
    target_chunk_size : int
        Target chunk size in characters.
    max_chunk_size : int
        Maximum chunk size before forced splitting.
    min_chunk_size : int
        Minimum chunk size. Short sections are merged with adjacent.
    merge_short_sections : bool
        Whether to merge very short sections with the next.

    Returns
    -------
    List[TextChunk]
        Chunks with breadcrumb metadata and error codes.
    """
    if not text or not text.strip():
        return []

    headings = _detect_headings(text)
    sections = _build_hierarchy(text, headings)

    if not sections:
        return []

    # Merge short sections
    if merge_short_sections:
        merged = []
        buffer: Optional[StructuredSection] = None
        for sec in sections:
            if buffer:
                buffer.content += f"\n\n## {sec.heading}\n{sec.content}"
                buffer.end_pos = sec.end_pos
                if len(buffer.content) >= min_chunk_size:
                    merged.append(buffer)
                    buffer = None
            elif len(sec.content) < min_chunk_size:
                buffer = sec
            else:
                merged.append(sec)
        if buffer:
            if merged:
                merged[-1].content += f"\n\n## {buffer.heading}\n{buffer.content}"
            else:
                merged.append(buffer)
        sections = merged

    # Build chunks
    chunks: List[TextChunk] = []
    chunk_index = 0

    for sec in sections:
        content = sec.content
        if not content.strip():
            continue

        # Split oversized sections
        if len(content) > max_chunk_size:
            # Split at paragraph boundaries first, then sentence
            paragraphs = re.split(r'\n\s*\n', content)
            current_part = ""
            for para in paragraphs:
                if len(current_part) + len(para) + 2 > max_chunk_size and current_part:
                    chunks.append(_make_chunk(
                        doc_id, source_path, sec, current_part, chunk_index,
                    ))
                    chunk_index += 1
                    current_part = para
                else:
                    current_part = (current_part + "\n\n" + para).strip() if current_part else para

            if current_part.strip():
                chunks.append(_make_chunk(
                    doc_id, source_path, sec, current_part, chunk_index,
                ))
                chunk_index += 1
        else:
            chunks.append(_make_chunk(
                doc_id, source_path, sec, content, chunk_index,
            ))
            chunk_index += 1

    return chunks


def _make_chunk(
    doc_id: str,
    source_path: str,
    section: StructuredSection,
    content: str,
    chunk_index: int,
) -> TextChunk:
    """Create a TextChunk with structure-aware metadata."""
    error_codes = _extract_error_codes(content)

    # Build evidence header with breadcrumb
    header_parts = [f"[EVIDENCE] source={source_path}"]
    header_parts.append(f"section={section.breadcrumb}")
    if error_codes:
        header_parts.append(f"error_codes={','.join(error_codes)}")
    header_parts.append("granularity=structure")
    header = " | ".join(header_parts)

    return TextChunk(
        chunk_id=f"{doc_id}_struct_{chunk_index:04d}",
        doc_id=doc_id,
        content=f"{header}\n{content}",
        source_path=source_path,
        chunk_index=chunk_index,
        doc_type="GENERIC_GUIDE",
    )
