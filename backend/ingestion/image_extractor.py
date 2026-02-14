from __future__ import annotations

from pathlib import Path


def extract_image_refs(path: str, extracted_refs: list[str]) -> list[str]:
    source = Path(path).parent
    resolved: list[str] = []
    for ref in extracted_refs:
        candidate = (source / ref).resolve()
        if candidate.exists():
            resolved.append(str(candidate))
    return resolved
