from __future__ import annotations

import hashlib
from pathlib import Path


def _extract_docx_images(doc, output_dir: Path) -> list[str]:
    """Extract embedded images from a DOCX document.

    Iterates over the document's relationship parts and saves any image
    content types (png, jpeg, gif, bmp, tiff, emf, wmf) to *output_dir*.
    Returns a list of saved file paths.
    """
    image_paths: list[str] = []
    try:
        for rel in doc.part.rels.values():
            ct = getattr(rel, "target_ref", "") or ""
            # Relationship parts whose content type signals an image
            if not hasattr(rel, "target_part"):
                continue
            target_part = rel.target_part
            part_ct = getattr(target_part, "content_type", "") or ""
            if not part_ct.startswith("image/"):
                continue
            blob = target_part.blob
            if not blob:
                continue
            # Derive a stable filename from content hash to prevent duplicates
            ext = part_ct.split("/")[-1].replace("jpeg", "jpg")
            content_hash = hashlib.sha256(blob).hexdigest()[:12]
            filename = f"img_{content_hash}.{ext}"
            dest = output_dir / filename
            if not dest.exists():
                dest.write_bytes(blob)
            image_paths.append(str(dest))
    except Exception:
        pass  # graceful — image extraction is best-effort
    return image_paths


def convert_docx(path: str, images_dir: str | None = None) -> tuple[str, list[str]]:
    try:
        from docx import Document
    except Exception as exc:
        raise RuntimeError("python-docx is required for DOCX conversion") from exc

    file_path = Path(path)
    doc = Document(str(file_path))
    text = "\n".join(paragraph.text for paragraph in doc.paragraphs if paragraph.text)

    # Extract embedded images when an output directory is provided
    image_paths: list[str] = []
    if images_dir:
        out = Path(images_dir)
        out.mkdir(parents=True, exist_ok=True)
        image_paths = _extract_docx_images(doc, out)

    return text, image_paths
