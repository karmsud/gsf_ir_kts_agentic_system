from __future__ import annotations

from pathlib import Path


def convert_html(path: str) -> tuple[str, list[str]]:
    try:
        from bs4 import BeautifulSoup
    except Exception as exc:
        raise RuntimeError("beautifulsoup4 is required for HTML conversion") from exc

    file_path = Path(path)
    html = file_path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    image_refs = [img.get("src", "") for img in soup.find_all("img") if img.get("src")]
    return text, image_refs
