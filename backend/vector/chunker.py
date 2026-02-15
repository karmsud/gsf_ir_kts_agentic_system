from __future__ import annotations

import re
from pathlib import Path

from backend.common.models import TextChunk
from backend.common.text_utils import chunk_text


def _extract_error_codes(text: str) -> list[str]:
    patterns = [
        r"\bERR-[A-Z]+-\d{3}\b",
        r"\bHTTP\s*\d{3}\b",
        r"\b[A-Z]+\d{3,4}\b",
    ]
    found: list[str] = []
    for pattern in patterns:
        found.extend(re.findall(pattern, text, flags=re.IGNORECASE))
    deduped: list[str] = []
    seen = set()
    for code in found:
        token = code.upper()
        if token not in seen:
            seen.add(token)
            deduped.append(token)
    return deduped[:5]


def _extract_section_title(chunk: str) -> str:
    for line in chunk.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def _extract_tool_hint(source_path: str) -> str:
    stem = Path(source_path).stem
    cleaned = re.sub(
        r"(?i)^(troubleshoot|sop|userguide|release\s*notes?|incident|config|architecture|arch|training|reference|legacy)[_\-\s]*",
        "",
        stem,
    )
    m = re.match(r"([A-Za-z0-9]+)", cleaned)
    return m.group(1) if m else ""


def _build_evidence_header(source_path: str, chunk: str) -> str:
    title = Path(source_path).stem.replace("_", " ").strip()
    section = _extract_section_title(chunk)
    error_codes = _extract_error_codes(f"{title} {chunk}")
    tool = _extract_tool_hint(source_path)

    parts = [f"title={title}"]
    if section:
        parts.append(f"section={section}")
    if tool:
        parts.append(f"tool={tool}")
    if error_codes:
        parts.append("error_codes=" + ",".join(error_codes))
    return "[EVIDENCE] " + " | ".join(parts)


def _anchor_chunk_with_metadata(source_path: str, chunk: str) -> str:
    if not chunk.strip():
        return chunk
    if chunk.lstrip().startswith("[EVIDENCE]"):
        return chunk
    header = _build_evidence_header(source_path, chunk)
    return f"{header}\n{chunk}"


def chunk_document(doc_id: str, source_path: str, text: str, chunk_size: int, chunk_overlap: int) -> list[TextChunk]:
    chunks = chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return [
        TextChunk(
            chunk_id=f"{doc_id}_chunk_{index}",
            doc_id=doc_id,
            content=_anchor_chunk_with_metadata(source_path=source_path, chunk=chunk),
            source_path=source_path,
            chunk_index=index,
        )
        for index, chunk in enumerate(chunks)
    ]
