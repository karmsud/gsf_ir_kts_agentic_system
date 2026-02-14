from __future__ import annotations

from pathlib import Path


def convert_docx(path: str) -> tuple[str, list[str]]:
    try:
        from docx import Document
    except Exception as exc:
        raise RuntimeError("python-docx is required for DOCX conversion") from exc

    file_path = Path(path)
    doc = Document(str(file_path))
    text = "\n".join(paragraph.text for paragraph in doc.paragraphs if paragraph.text)
    return text, []
