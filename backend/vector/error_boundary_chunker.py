"""Phase 19.2 — Error-Boundary Chunker (Non-Legal Store 1).

Parses troubleshooting / error-resolution documents by detecting
**error entry boundaries** rather than fixed character counts.

Each chunk contains a complete error entry: error code + symptoms +
root cause + solution / workaround.  This ensures the retriever never
returns a chunk that has the right error code but the wrong solution.

Boundary detection uses a prioritised regex cascade:
1. Explicit error-code headings  (``ERROR E-1234``, ``Error Code: 504``)
2. Problem / Solution markers    (``Problem:``, ``Resolution:``, ``Workaround:``)
3. Numbered-entry patterns       (``1. ``, ``Issue #3``)
4. Horizontal-rule / separator   (``---``, ``===``, ``***``)
5. Heading-style lines           (``## Some Title``)

When an entry exceeds *max_chunk_chars* it is split at the nearest
sentence boundary to avoid truncation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from backend.common.models import TextChunk

# ── Boundary patterns (ordered by priority) ───────────────────────

# Explicit error/issue headings
_ERROR_HEADING_RE = re.compile(
    r'^(?:'
    r'(?:ERROR|Error|error)\s*(?:Code)?[\s:]*[A-Z0-9][\w\-.]*'  # Error E-1234, Error Code: 504
    r'|(?:ERR|WARN|CRIT|FATAL)[\s\-]*[A-Z]*[\s\-]*\d{3,}'      # ERR-AUTH-001
    r'|HTTP\s*\d{3}'                                              # HTTP 500
    r'|Issue\s*#?\d+'                                             # Issue #3
    r')',
    re.MULTILINE,
)

# Problem / Resolution / Workaround section markers
_SECTION_MARKER_RE = re.compile(
    r'^(?:'
    r'(?:Problem|Issue|Symptom|Error|Cause|Root\s*Cause|Resolution|Solution|Fix|Workaround|Mitigation|Remediation)'
    r'\s*[:—\-]'
    r')',
    re.MULTILINE | re.IGNORECASE,
)

# Horizontal rules / separators
_SEPARATOR_RE = re.compile(
    r'^(?:'
    r'[-=*]{3,}'                                                   # ---, ===, ***
    r'|_{3,}'                                                      # ___
    r')',
    re.MULTILINE,
)

# Markdown / numbered headings
_HEADING_RE = re.compile(
    r'^(?:'
    r'#{1,4}\s+\S'                                                 # ## Heading
    r'|\d+\.\s+[A-Z]'                                             # 1. Title
    r')',
    re.MULTILINE,
)

# Sentence boundary (for splitting oversized entries)
_SENTENCE_END_RE = re.compile(r'(?<=[.!?])\s+')


@dataclass
class ErrorEntry:
    """A single error/issue entry parsed from the document."""
    start_pos: int
    end_pos: int
    heading: str = ""
    content: str = ""
    error_codes: List[str] = field(default_factory=list)


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


def _find_boundaries(text: str) -> List[int]:
    """Find all error-entry boundary positions in the text.

    Returns sorted, deduplicated list of character offsets where new
    error entries begin.
    """
    positions = set()

    # Pass 1: Error headings (highest priority)
    for m in _ERROR_HEADING_RE.finditer(text):
        positions.add(m.start())

    # Pass 2: Section markers — only if they follow a blank line or separator
    for m in _SECTION_MARKER_RE.finditer(text):
        # Check if preceded by blank line (new entry) vs inline continuation
        pre = text[max(0, m.start() - 3):m.start()]
        if '\n\n' in pre or m.start() < 3:
            positions.add(m.start())

    # Pass 3: Separators
    for m in _SEPARATOR_RE.finditer(text):
        # The entry starts AFTER the separator
        end = m.end()
        while end < len(text) and text[end] in ' \t\n':
            end += 1
        if end < len(text):
            positions.add(end)

    # Pass 4: Headings (lowest priority — only add if gap between previous is big)
    if len(positions) < 3:  # Few boundaries found → use headings too
        for m in _HEADING_RE.finditer(text):
            positions.add(m.start())

    return sorted(positions)


def _split_oversized(content: str, max_chars: int, overlap: int = 200) -> List[str]:
    """Split an oversized entry at sentence boundaries."""
    if len(content) <= max_chars:
        return [content]

    chunks = []
    sentences = _SENTENCE_END_RE.split(content)
    current = ""
    for sent in sentences:
        if len(current) + len(sent) + 1 > max_chars and current:
            chunks.append(current.strip())
            # Overlap: keep last N chars
            if overlap > 0:
                current = current[-overlap:] + " " + sent
            else:
                current = sent
        else:
            current = (current + " " + sent).strip() if current else sent

    if current.strip():
        chunks.append(current.strip())

    return chunks or [content]


def chunk_by_error_boundaries(
    doc_id: str,
    source_path: str,
    text: str,
    max_chunk_chars: int = 4000,
    min_chunk_chars: int = 100,
    chunk_overlap: int = 200,
) -> List[TextChunk]:
    """Chunk a troubleshooting/error document by error-entry boundaries.

    Parameters
    ----------
    doc_id : str
        Document identifier.
    source_path : str
        Source file path.
    text : str
        Full document text.
    max_chunk_chars : int
        Maximum characters per chunk. Oversized entries are split at
        sentence boundaries.
    min_chunk_chars : int
        Minimum characters. Short entries are merged with the next.
    chunk_overlap : int
        Overlap chars when splitting oversized entries.

    Returns
    -------
    List[TextChunk]
        Chunks with error-code metadata attached.
    """
    if not text or not text.strip():
        return []

    boundaries = _find_boundaries(text)

    # If no boundaries detected, fall back to heading-based splitting
    if not boundaries:
        boundaries = [0]

    # Always include document start
    if boundaries[0] != 0:
        boundaries.insert(0, 0)

    # Extract entries between boundaries
    entries: List[ErrorEntry] = []
    for i, start in enumerate(boundaries):
        end = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
        content = text[start:end].strip()
        if not content:
            continue

        # Extract heading (first line)
        first_newline = content.find('\n')
        heading = content[:first_newline].strip() if first_newline > 0 else content[:80]

        entries.append(ErrorEntry(
            start_pos=start,
            end_pos=end,
            heading=heading,
            content=content,
            error_codes=_extract_error_codes(content),
        ))

    # Merge short entries with next
    merged: List[ErrorEntry] = []
    buffer = None
    for entry in entries:
        if buffer:
            buffer.content += "\n\n" + entry.content
            buffer.end_pos = entry.end_pos
            buffer.error_codes = list(set(buffer.error_codes + entry.error_codes))
            if len(buffer.content) >= min_chunk_chars:
                merged.append(buffer)
                buffer = None
        elif len(entry.content) < min_chunk_chars:
            buffer = entry
        else:
            merged.append(entry)
    if buffer:
        if merged:
            merged[-1].content += "\n\n" + buffer.content
            merged[-1].end_pos = buffer.end_pos
            merged[-1].error_codes = list(set(merged[-1].error_codes + buffer.error_codes))
        else:
            merged.append(buffer)

    # Build TextChunks — split oversized entries
    chunks: List[TextChunk] = []
    chunk_index = 0
    for entry in merged:
        parts = _split_oversized(entry.content, max_chunk_chars, chunk_overlap)
        for part in parts:
            # Build evidence header
            header_parts = [f"[EVIDENCE] source={source_path}"]
            if entry.heading:
                header_parts.append(f"heading={entry.heading[:80]}")
            if entry.error_codes:
                header_parts.append(f"error_codes={','.join(entry.error_codes)}")
            header = " | ".join(header_parts)

            chunk = TextChunk(
                chunk_id=f"{doc_id}_errb_{chunk_index:04d}",
                doc_id=doc_id,
                content=f"{header}\n{part}",
                source_path=source_path,
                chunk_index=chunk_index,
                doc_type="GENERIC_GUIDE",
            )
            chunks.append(chunk)
            chunk_index += 1

    return chunks
