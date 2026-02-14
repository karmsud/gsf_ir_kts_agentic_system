from __future__ import annotations

from pathlib import Path


def convert_pptx(path: str) -> tuple[str, list[str]]:
    try:
        from pptx import Presentation
    except Exception as exc:
        raise RuntimeError("python-pptx is required for PPTX conversion") from exc

    file_path = Path(path)
    prs = Presentation(str(file_path))
    parts: list[str] = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text:
                parts.append(shape.text)
    return "\n".join(parts), []
