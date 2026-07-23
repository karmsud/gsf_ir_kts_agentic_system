"""
HTML → PDF rendering via PyMuPDF (already bundled — no extra dependency).

Uses the PyMuPDF ``Story`` API to flow styled HTML across paginated US-Letter
pages. Falls back gracefully (returns ``None``) if the runtime lacks the Story
API so callers can still rely on the HTML rendering.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def html_to_pdf(html: str, pdf_path: Path) -> Optional[Path]:
    """Render ``html`` to a paginated PDF at ``pdf_path``.

    Returns the path on success, or ``None`` if PDF generation is unavailable.
    """
    pdf_path = Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import fitz  # PyMuPDF
    except ImportError:  # pragma: no cover
        return None
    if not hasattr(fitz, "Story"):  # pragma: no cover - very old PyMuPDF
        return None

    try:
        story = fitz.Story(html=html)
        writer = fitz.DocumentWriter(str(pdf_path))
        mediabox = fitz.paper_rect("letter")
        where = mediabox + (36, 54, -36, -36)
        more = 1
        while more:
            device = writer.begin_page(mediabox)
            more, _ = story.place(where)
            story.draw(device)
            writer.end_page()
        writer.close()
        return pdf_path
    except Exception:  # pragma: no cover - rendering edge cases
        return None
