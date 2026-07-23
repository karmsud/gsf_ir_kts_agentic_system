"""
PDF extraction with page tracking.

Produces a single text stream plus a *page offset map* so any character
position in the concatenated text can be resolved back to a 1-based page
number. This is what lets every section/chunk carry an accurate page citation
back to the source PDF — the backbone of traceability.

The heavy dependency (PyMuPDF / ``fitz``) is imported lazily so this module can
be unit-tested with synthetic ``(text, page_offsets)`` without a real PDF.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ExtractedDoc:
    """Concatenated document text with a page-offset index."""

    text: str
    #: ``page_offsets[i]`` = char index in ``text`` where page ``i`` (0-based) begins.
    page_offsets: list[int] = field(default_factory=list)
    page_count: int = 0

    def char_to_page(self, offset: int) -> int:
        """Resolve a char offset to a 1-based page number."""
        return char_to_page(offset, self.page_offsets)


def char_to_page(offset: int, page_offsets: list[int]) -> int:
    """Return the 1-based page number containing ``offset``.

    ``page_offsets`` must be sorted ascending. Offsets before the first page
    resolve to page 1; an empty map resolves to page 1.
    """
    if not page_offsets:
        return 1
    # Rightmost page whose start offset is <= the target offset.
    idx = bisect.bisect_right(page_offsets, offset) - 1
    if idx < 0:
        idx = 0
    return idx + 1


def extract_pdf(pdf_path: Path) -> ExtractedDoc:
    """Extract text from a PDF, tracking where each page begins.

    Raises ``FileNotFoundError`` if the path does not exist and ``RuntimeError``
    if PyMuPDF is unavailable.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("PyMuPDF (fitz) is required to extract PDFs.") from exc

    parts: list[str] = []
    page_offsets: list[int] = []
    cursor = 0
    doc = fitz.open(str(pdf_path))
    try:
        for page in doc:
            page_offsets.append(cursor)
            page_text = page.get_text("text") or ""
            parts.append(page_text)
            cursor += len(page_text)
        page_count = doc.page_count
    finally:
        doc.close()

    return ExtractedDoc(text="".join(parts), page_offsets=page_offsets, page_count=page_count)


def extracted_from_pages(pages: list[str]) -> ExtractedDoc:
    """Build an :class:`ExtractedDoc` from a list of page texts (test helper)."""
    parts: list[str] = []
    page_offsets: list[int] = []
    cursor = 0
    for page_text in pages:
        page_offsets.append(cursor)
        parts.append(page_text)
        cursor += len(page_text)
    return ExtractedDoc(text="".join(parts), page_offsets=page_offsets, page_count=len(pages))
