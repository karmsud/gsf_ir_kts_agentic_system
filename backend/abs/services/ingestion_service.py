"""
IngestionService — PDF → TOC-aware sections → page-cited chunks → store.

Bridges the existing :class:`LegalChunker` (section detection) and the page
tracking in :mod:`backend.abs.services.pdf_extract` to populate a deal's
SQLite spine with documents, hierarchical sections, and chunks that each carry
an accurate source page range.

Stateless + async; emits incremental progress events for the animated
ingestion UI.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from backend.abs.services.base import ABSService, ProgressFn, ServiceContext, ServiceResult
from backend.abs.services.pdf_extract import ExtractedDoc, extract_pdf
from backend.abs.store import DealStore, new_id

_DEFAULT_CHUNK_CHARS = 1500
_MIN_CHUNK_CHARS = 200

# Paragraph-boundary patterns for PDF text.  PDF extractors emit single \n
# line wraps, sometimes with a trailing space on blank lines (\n \n).  Try
# the richest delimiter first and fall back to plain \n so every document
# format gets properly split.
_PARA_SPLIT_RE = re.compile(r'\n[ \t]*\n')


def _split_into_chunks(content: str, max_chars: int = _DEFAULT_CHUNK_CHARS) -> list[tuple[int, str]]:
    """Split ``content`` into ``(relative_offset, chunk_text)`` at paragraph
    boundaries, packing up to ``max_chars`` per chunk.

    Handles both Markdown (double-\\n) and PDF (single-\\n) paragraph breaks.
    """
    if not content.strip():
        return []
    if len(content) <= max_chars:
        return [(0, content)]

    # Try rich paragraph splits first (\n<whitespace>\n).  If too few
    # boundaries result (dense PDF prose), fall back to single newlines.
    parts = _PARA_SPLIT_RE.split(content)
    min_splits_needed = max(2, len(content) // (max_chars * 4))
    if len(parts) < min_splits_needed:
        parts = content.split('\n')
    sep = '\n'

    chunks: list[tuple[int, str]] = []
    buf: list[str] = []
    buf_len = 0
    buf_start = 0
    cursor = 0
    for part in parts:
        piece = part + sep
        # If a single part exceeds max_chars, hard-split it.
        if len(piece) > max_chars:
            if buf:
                chunks.append((buf_start, ''.join(buf).strip()))
                buf, buf_len, buf_start = [], 0, cursor
            for i in range(0, len(piece), max_chars):
                sub = piece[i:i + max_chars].strip()
                if sub:
                    chunks.append((cursor + i, sub))
            cursor += len(piece)
            continue
        if buf_len + len(piece) > max_chars and buf_len >= _MIN_CHUNK_CHARS:
            chunks.append((buf_start, ''.join(buf).strip()))
            buf, buf_len, buf_start = [], 0, cursor
        buf.append(piece)
        buf_len += len(piece)
        cursor += len(piece)
    if buf:
        chunks.append((buf_start, ''.join(buf).strip()))
    return [(off, txt) for off, txt in chunks if txt]


class IngestionService(ABSService):
    """Ingest a deal document into the structured store with page citations."""

    name = "ingestion"

    def __init__(self, deals_root: Path) -> None:
        self.deals_root = Path(deals_root)

    def context(self, deal_id: str) -> ServiceContext:
        return ServiceContext(deal_id=deal_id, deals_root=self.deals_root)

    async def ingest_document(
        self,
        deal_id: str,
        *,
        pdf_path: Optional[Path] = None,
        extracted: Optional[ExtractedDoc] = None,
        doc_type: str = "PSA",
        title: str = "",
        actor: str = "system",
        progress: Optional[ProgressFn] = None,
    ) -> ServiceResult:
        return await self.guard(
            self._ingest(deal_id, pdf_path, extracted, doc_type, title, actor, progress)
        )

    async def _ingest(
        self,
        deal_id: str,
        pdf_path: Optional[Path],
        extracted: Optional[ExtractedDoc],
        doc_type: str,
        title: str,
        actor: str,
        progress: Optional[ProgressFn],
    ) -> dict[str, Any]:
        def emit(stage: str, status: str, **extra: Any) -> None:
            if progress is not None:
                progress({"stage": stage, "status": status, **extra})

        # 1. Extract text + page map -------------------------------------
        emit("extract", "in-progress")
        if extracted is None:
            if pdf_path is None:
                raise ValueError("Provide either pdf_path or extracted.")
            extracted = await self._to_thread(extract_pdf, Path(pdf_path))
        emit("extract", "done", pages=extracted.page_count)

        # 2. Section detection (TOC-aware) -------------------------------
        emit("sections", "in-progress")
        sections = await self._to_thread(self._detect_sections, extracted)
        emit("sections", "done", count=len(sections))

        # 3. Persist (document → sections → chunks) ----------------------
        emit("store", "in-progress")
        result = await self._to_thread(
            self._persist, deal_id, pdf_path, doc_type, title, extracted, sections, actor
        )
        emit("store", "done", **result)
        return result

    # ------------------------------------------------------------------
    # Sync helpers (run off-thread)
    # ------------------------------------------------------------------
    def _detect_sections(self, extracted: ExtractedDoc) -> list[dict[str, Any]]:
        """Return section dicts with absolute char + page spans."""
        try:
            from backend.vector.legal_chunker import LegalChunker

            chunker = LegalChunker()
            doc_sections = chunker.extract_sections(extracted.text)
        except Exception:
            doc_sections = []

        out: list[dict[str, Any]] = []
        if not doc_sections:
            # Fallback: whole document as a single section.
            out.append({
                "section_path": "Document",
                "title": "Full Document",
                "level": 0,
                "start_pos": 0,
                "end_pos": len(extracted.text),
            })
            return out

        for sec in doc_sections:
            start = getattr(sec, "start_pos", 0) or 0
            end = getattr(sec, "end_pos", len(extracted.text)) or len(extracted.text)
            number = getattr(sec, "number", "") or ""
            sec_title = getattr(sec, "title", "") or ""
            out.append({
                "section_path": (f"{number} {sec_title}").strip() or "Section",
                "title": sec_title,
                "level": getattr(sec, "level", 1) or 1,
                "number": number,
                "content": getattr(sec, "content", "") or "",
                "start_pos": start,
                "end_pos": end,
            })
        return out

    def _persist(
        self,
        deal_id: str,
        pdf_path: Optional[Path],
        doc_type: str,
        title: str,
        extracted: ExtractedDoc,
        sections: list[dict[str, Any]],
        actor: str,
    ) -> dict[str, Any]:
        ctx = self.context(deal_id)
        store: DealStore = ctx.store()

        doc_id = store.add_document({
            "deal_id": deal_id,
            "doc_type": doc_type,
            "title": title or (Path(pdf_path).stem if pdf_path else doc_type),
            "source_path": str(pdf_path) if pdf_path else "",
            "page_count": extracted.page_count,
            "status": "draft",
        })

        section_rows: list[dict[str, Any]] = []
        chunk_rows: list[dict[str, Any]] = []
        for ordinal, sec in enumerate(sections):
            section_id = new_id("sec_")
            start = sec["start_pos"]
            end = sec["end_pos"]
            # Always derive content from the raw document span so large sections
            # (e.g. a 254K-char DEFINITIONS article) are fully chunked.  The
            # LegalChunker "content" attribute is a short heading excerpt only.
            content = extracted.text[start:end] or sec.get("content") or ""
            page_start = extracted.char_to_page(start)
            page_end = extracted.char_to_page(max(start, end - 1))
            section_rows.append({
                "section_id": section_id,
                "doc_id": doc_id,
                "section_path": sec["section_path"],
                "title": sec.get("title", ""),
                "level": sec.get("level", 0),
                "ordinal": ordinal,
                "page_start": page_start,
                "page_end": page_end,
                "char_start": start,
                "char_end": end,
            })
            # Chunk the section content.
            for c_ord, (rel_off, chunk_text) in enumerate(_split_into_chunks(content)):
                abs_off = start + rel_off
                chunk_rows.append({
                    "chunk_id": new_id("chk_"),
                    "doc_id": doc_id,
                    "section_id": section_id,
                    "ordinal": len(chunk_rows),
                    "text": chunk_text,
                    "page_start": extracted.char_to_page(abs_off),
                    "page_end": extracted.char_to_page(abs_off + max(0, len(chunk_text) - 1)),
                    "token_count": max(1, len(chunk_text) // 4),
                })

        store.add_sections(section_rows)
        store.add_chunks(chunk_rows)
        store.audit(
            "ingest_document",
            actor=actor,
            object_type="document",
            object_id=doc_id,
            after={"sections": len(section_rows), "chunks": len(chunk_rows)},
        )
        return {
            "doc_id": doc_id,
            "sections": len(section_rows),
            "chunks": len(chunk_rows),
            "pages": extracted.page_count,
        }
