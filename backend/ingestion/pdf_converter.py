from __future__ import annotations

from pathlib import Path


def convert_pdf(path: str) -> tuple[str, list[str]]:
    try:
        import fitz
    except Exception as exc:
        raise RuntimeError("PyMuPDF is required for PDF conversion") from exc

    file_path = Path(path)
    doc = fitz.open(str(file_path))
    parts: list[str] = []
    for page in doc:
        parts.append(page.get_text("text"))
    doc.close()
    return "\n".join(parts), []
