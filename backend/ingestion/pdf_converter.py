from __future__ import annotations

import hashlib
from pathlib import Path


def _extract_pdf_images(doc, output_dir: Path) -> list[str]:
    """Extract embedded images from a PDF via PyMuPDF.

    Uses page.get_images() and doc.extract_image() to pull raster
    images from every page.  Returns a list of saved file paths.
    """
    image_paths: list[str] = []
    seen_xrefs: set[int] = set()
    try:
        for page in doc:
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                base_image = doc.extract_image(xref)
                if not base_image or not base_image.get("image"):
                    continue
                blob = base_image["image"]
                ext = base_image.get("ext", "png")
                content_hash = hashlib.sha256(blob).hexdigest()[:12]
                filename = f"img_{content_hash}.{ext}"
                dest = output_dir / filename
                if not dest.exists():
                    dest.write_bytes(blob)
                image_paths.append(str(dest))
    except Exception:
        pass  # graceful — image extraction is best-effort
    return image_paths


def convert_pdf(path: str, images_dir: str | None = None) -> tuple[str, list[str]]:
    try:
        import fitz
    except Exception as exc:
        raise RuntimeError("PyMuPDF is required for PDF conversion") from exc

    file_path = Path(path)
    doc = fitz.open(str(file_path))
    parts: list[str] = []
    for page in doc:
        parts.append(page.get_text("text"))

    full_text = "\n".join(parts)

    # Normalise common Unicode characters that PDF fonts embed differently
    # from plain-text / .doc sources.  This ensures downstream regex patterns
    # (e.g. definition extraction) work consistently.
    full_text = full_text.replace("\u201c", '"')   # left double curly quote  → "
    full_text = full_text.replace("\u201d", '"')   # right double curly quote → "
    full_text = full_text.replace("\u2018", "'")   # left single curly quote  → '
    full_text = full_text.replace("\u2019", "'")   # right single curly quote → '
    full_text = full_text.replace("\u00a0", " ")   # non-breaking space       → space
    full_text = full_text.replace("\u00ad", "")    # soft hyphen              → remove
    full_text = full_text.replace("\u2011", "-")   # non-breaking hyphen      → -
    full_text = full_text.replace("\ufeff", "")    # BOM / zero-width no-break

    # Extract embedded images when an output directory is provided
    image_paths: list[str] = []
    if images_dir:
        out = Path(images_dir)
        out.mkdir(parents=True, exist_ok=True)
        image_paths = _extract_pdf_images(doc, out)

    doc.close()
    return full_text, image_paths
