"""Phase 19 — OneNote Binary Converter (.one / .onetoc2).

Parses Microsoft OneNote Section files (.one) and Table-of-Contents files
(.onetoc2) without requiring the OneNote desktop application.

Approach
--------
The MS-ONESTORE binary format is parsed in two tiers:

Tier 1  Fast UTF-16LE text scanner + image-blob scanner.
        Works for the vast majority of OneNote pages produced by the
        desktop application.  Does not require any third-party library
        beyond the Python stdlib.

Tier 2  If a section file cannot yield meaningful content from Tier 1
        (e.g. corrupt header, unusual encoding) a fallback raw-bytes
        scan extracts every printable ASCII/UTF-16LE run longer than 20
        characters.

Public API
----------
parse_onetoc2(path)  → list[str]              section names in notebook order
parse_one_section(path) → list[OneNotePage]   pages extracted from a .one file

Data model
----------
OneNoteImage      image_bytes (bytes), width, height (optional)
OneNoteTable      headers (list[str]), rows (list[list[str]])
OneNotePage       guid, title, text_blocks, tables, images, modified_iso
"""

from __future__ import annotations

import hashlib
import logging
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── OneNote file magic ─────────────────────────────────────────────────────
# A valid .one file starts with this 16-byte GUID (MS-ONESTORE §2.3.1)
_ONE_HEADER_MAGIC = bytes([
    0xE4, 0x52, 0x5C, 0x7B, 0x8C, 0xD8, 0xA3, 0x4D,
    0xAE, 0xB1, 0x53, 0x78, 0xD0, 0x29, 0x96, 0xD3,
])

# Image magic bytes
_JPEG_MAGIC = bytes([0xFF, 0xD8, 0xFF])
_PNG_MAGIC  = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
_GIF_MAGIC  = b"GIF8"

# Minimum blob sizes to avoid false positives
_MIN_IMAGE_BYTES = 512

# UTF-16LE scan parameters
_MIN_UTF16_RUN = 6   # minimum chars in a valid text run

# Page header signal: OneNote page object GUID prefix (appears before page titles)
# This is a heuristic — the full spec uses FileNodeID 0x008 for page series.
_PAGE_BOUNDARY_MARKERS = [
    b'\x0b\x00\xa4\x00',   # PageSeries FileNode heuristic
    b'\x00\x1f\x00\x1f',   # Object space boundary
]


# ── Data model ─────────────────────────────────────────────────────────────

@dataclass
class OneNoteImage:
    """An image extracted from a OneNote page."""
    image_bytes: bytes
    fmt: str = "jpeg"          # "jpeg", "png", "gif"
    content_hash: str = ""

    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = hashlib.sha256(self.image_bytes).hexdigest()[:16]


@dataclass
class OneNoteTable:
    """A table extracted from a OneNote page (best-effort)."""
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Serialize as GitHub-flavoured Markdown table."""
        if not self.headers and not self.rows:
            return ""
        all_rows = ([self.headers] if self.headers else []) + self.rows
        col_count = max(len(r) for r in all_rows)
        # Pad all rows to same width
        padded = [r + [""] * (col_count - len(r)) for r in all_rows]
        # Column widths
        widths = [max(len(str(padded[r][c])) for r in range(len(padded)))
                  for c in range(col_count)]
        lines = []
        for i, row in enumerate(padded):
            cells = " | ".join(str(row[c]).ljust(widths[c]) for c in range(col_count))
            lines.append(f"| {cells} |")
            if i == 0:
                sep = " | ".join("-" * widths[c] for c in range(col_count))
                lines.append(f"| {sep} |")
        return "\n".join(lines)


@dataclass
class OneNotePage:
    """A single page extracted from a .one section file."""
    guid: str                                    # internal page identifier
    title: str                                   # page title
    text_blocks: list[str] = field(default_factory=list)   # ordered text runs
    tables: list[OneNoteTable] = field(default_factory=list)
    images: list[OneNoteImage] = field(default_factory=list)
    modified_iso: Optional[str] = None          # ISO-8601 or None
    order_index: int = 0                         # position within section

    @property
    def full_text(self) -> str:
        """Concatenate all text blocks and table markdown into a single string."""
        parts: list[str] = []
        for block in self.text_blocks:
            block = block.strip()
            if block:
                parts.append(block)
        for table in self.tables:
            md = table.to_markdown()
            if md:
                parts.append(md)
        return "\n\n".join(parts)

    def content_hash(self) -> str:
        """Hash of raw page content — used for delta ingestion."""
        raw = self.full_text + "".join(img.content_hash for img in self.images)
        return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:32]


# ── .onetoc2 parser ────────────────────────────────────────────────────────

def parse_onetoc2(path: str | Path) -> list[str]:
    """Extract section names from a .onetoc2 Table-of-Contents file.

    Returns a list of section names (without .one extension) in the order
    they appear in the notebook.  Falls back to an empty list if the file
    cannot be read.

    The .onetoc2 format embeds section filenames as UTF-16LE strings.
    We scan for strings ending in the null-terminated .one extension.
    """
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        logger.warning("[Phase19] Cannot read .onetoc2 '%s': %s", path, exc)
        return []

    # Scan for UTF-16LE strings that look like "<name>.one" (with .one encoded as
    # 2E 00 6F 00 6E 00 65 00)
    _ONE_EXT_UTF16 = ".one".encode("utf-16-le")
    sections: list[tuple[int, str]] = []
    pos = 0
    while pos < len(data) - 2:
        idx = data.find(_ONE_EXT_UTF16, pos)
        if idx == -1:
            break
        # Walk backwards to find start of this UTF-16LE string
        start = idx
        while start >= 2:
            ch_bytes = data[start - 2 : start]
            # Valid UTF-16LE printable char: second byte is 0x00 and first is printable
            try:
                ch = ch_bytes.decode("utf-16-le")
            except Exception:
                break
            if ch.isprintable() and ch not in ('\x00', '\n', '\r'):
                start -= 2
            else:
                break
        raw = data[start : idx + len(_ONE_EXT_UTF16)]
        try:
            name = raw.decode("utf-16-le")
            # Strip the .one extension for the display name
            clean = name[: -len(".one")] if name.endswith(".one") else name
            if clean and len(clean) > 0:
                sections.append((start, clean))
        except Exception:
            pass
        pos = idx + len(_ONE_EXT_UTF16)

    # De-duplicate preserving first occurrence order
    seen: set[str] = set()
    result: list[str] = []
    for _, name in sections:
        if name not in seen:
            seen.add(name)
            result.append(name)

    logger.info("[Phase19] .onetoc2 '%s' → %d sections: %s",
                Path(path).name, len(result), result[:8])
    return result


# ── .one section parser ─────────────────────────────────────────────────────

def parse_one_section(path: str | Path) -> list[OneNotePage]:
    """Parse a .one section file and return its pages.

    Uses a two-tier approach:
    1. Structural scan: detects page boundaries using MS-ONESTORE heuristics,
       then extracts UTF-16LE text and image blobs per page.
    2. Fallback: if structural scan yields < 2 pages, performs a whole-file
       raw scan and packs everything into a single synthetic page.

    Parameters
    ----------
    path : str | Path
        Absolute path to the .one section file.

    Returns
    -------
    list[OneNotePage]
        Ordered list of pages.  Empty if the file cannot be read.
    """
    p = Path(path)
    try:
        data = p.read_bytes()
    except OSError as exc:
        logger.error("[Phase19] Cannot read '%s': %s", path, exc)
        return []

    if len(data) < 16:
        logger.warning("[Phase19] '%s' too small to be a .one file", p.name)
        return []

    # Validate header magic (best-effort — not fatal if missing)
    if data[:16] != _ONE_HEADER_MAGIC:
        logger.debug("[Phase19] '%s' header magic mismatch — still attempting parse", p.name)

    pages = _structural_scan(data, section_name=p.stem)

    if len(pages) < 1:
        logger.info("[Phase19] Structural scan yielded 0 pages for '%s' — using fallback", p.name)
        pages = _fallback_scan(data, section_name=p.stem)

    # Assign order indices
    for i, page in enumerate(pages):
        page.order_index = i

    logger.info("[Phase19] '%s' → %d pages extracted", p.name, len(pages))
    return pages


# ── Tier-1: Structural scan ────────────────────────────────────────────────

def _structural_scan(data: bytes, section_name: str) -> list[OneNotePage]:
    """Attempt to detect page boundaries and extract per-page content."""

    # Find candidate page-boundary positions by looking for the
    # FileNode list structure.  In practice, OneNote writes page title
    # objects at known file-node IDs.  We use a safe heuristic:
    # scan for repeated block-separator patterns that appear before
    # each UTF-16LE title string.

    separators = _find_page_separators(data)

    if len(separators) < 1:
        return []

    # Add virtual end sentinel
    separators.append(len(data))

    pages: list[OneNotePage] = []
    for i, start in enumerate(separators[:-1]):
        end = separators[i + 1]
        chunk = data[start:end]
        page = _extract_page(chunk, page_index=i, section_name=section_name)
        pages.append(page)

    return pages


def _find_page_separators(data: bytes) -> list[int]:
    """Return byte offsets that likely mark the start of new pages.

    Strategy: look for the pattern of a 4-byte aligned block that
    precedes a UTF-16LE string of 3-80 characters (likely a page title).
    Additionally look for repeating structural markers.
    """
    positions: list[int] = []

    # Heuristic: OneNote stores an ObjectSpaceObjectPropSet per page.
    # The page title property (PropertyID 0x1C001D94) is encoded with
    # a 4-byte property-set header followed by a UTF-16LE string.
    # We scan for the property ID bytes as a page-start signal.
    PROP_TITLE = b'\x94\x1d\x00\x1c'      # 0x1C001D94 little-endian
    PROP_ALT   = b'\x00\x1d\x00\x1c'      # alternate encoding seen in practice

    for marker in (PROP_TITLE, PROP_ALT):
        pos = 0
        while pos < len(data):
            idx = data.find(marker, pos)
            if idx == -1:
                break
            positions.append(idx)
            pos = idx + 4

    if not positions:
        # Secondary heuristic: look for "page" separator patterns
        for marker in _PAGE_BOUNDARY_MARKERS:
            pos = 0
            while pos < len(data):
                idx = data.find(marker, pos)
                if idx == -1:
                    break
                positions.append(idx)
                pos = idx + len(marker)

    # Sort, deduplicate, and filter out positions < 512 bytes apart
    positions = sorted(set(positions))
    filtered: list[int] = []
    prev = -2000
    for p in positions:
        if p - prev >= 256:   # minimum page-chunk size
            filtered.append(p)
            prev = p

    return filtered


def _extract_page(chunk: bytes, page_index: int, section_name: str) -> OneNotePage:
    """Extract a OneNotePage from a raw byte chunk."""
    texts = _extract_utf16_strings(chunk, min_length=_MIN_UTF16_RUN)
    images = _extract_images(chunk)
    tables = _detect_tables(texts)

    # The first non-trivial string in the chunk is likely the page title
    title = _pick_title(texts, page_index, section_name)

    # Remove title from text blocks (avoid duplication)
    remaining_texts = [t for t in texts if t != title and len(t.strip()) > 2]

    return OneNotePage(
        guid=f"{section_name}_p{page_index:04d}",
        title=title,
        text_blocks=remaining_texts,
        tables=tables,
        images=images,
    )


def _pick_title(texts: list[str], page_index: int, section_name: str) -> str:
    """Best-effort title selection from a list of extracted text runs."""
    # Try to find a short, non-empty string that looks like a title (≤120 chars,
    # no newlines, starts with uppercase or number)
    for t in texts:
        t = t.strip()
        if 2 < len(t) <= 120 and '\n' not in t and '\r' not in t:
            if t[0].isupper() or t[0].isdigit():
                return t
    # Fallback
    return f"{section_name} — Page {page_index + 1}"


# ── Tier-2: Fallback raw scan ──────────────────────────────────────────────

def _fallback_scan(data: bytes, section_name: str) -> list[OneNotePage]:
    """Scan the whole file as one big text+image blob.

    Creates one synthetic page per ~200 text-runs or at "paragraph break"
    heuristics to keep chunks manageable.
    """
    texts = _extract_utf16_strings(data, min_length=4)
    images = _extract_images(data)
    tables = _detect_tables(texts)

    if not texts and not images:
        return []

    # Split into synthetic pages of ~100 text blocks each
    BLOCK_SIZE = 100
    pages: list[OneNotePage] = []
    for part_idx, start in enumerate(range(0, max(1, len(texts)), BLOCK_SIZE)):
        block_texts = texts[start : start + BLOCK_SIZE]
        title = _pick_title(block_texts, part_idx, section_name)
        page = OneNotePage(
            guid=f"{section_name}_fallback_p{part_idx:04d}",
            title=title,
            text_blocks=[t for t in block_texts if t != title],
            tables=tables if part_idx == 0 else [],
            images=images if part_idx == 0 else [],
        )
        pages.append(page)

    return pages


# ── UTF-16LE text extraction ───────────────────────────────────────────────

def _extract_utf16_strings(data: bytes, min_length: int = 6) -> list[str]:
    """Scan binary data for UTF-16LE encoded text runs.

    Returns list of unique, cleaned strings in order of appearance.
    """
    results: list[str] = []
    seen: set[str] = set()

    # Pattern: alternating printable-char / null bytes  (little-endian UTF-16)
    # We slide a 2-byte window looking for valid char pairs
    i = 0
    while i < len(data) - 2:
        # Check if this and next byte form a plausible UTF-16LE char
        low, high = data[i], data[i + 1]
        if high == 0x00 and 0x20 <= low <= 0x7E:
            # Start of a possible UTF-16LE ASCII string
            run_start = i
            run_bytes = bytearray()
            while i < len(data) - 1:
                lo, hi = data[i], data[i + 1]
                if hi == 0x00 and (0x20 <= lo <= 0x7E or lo in (0x0A, 0x0D, 0x09)):
                    run_bytes += bytes([lo, hi])
                    i += 2
                else:
                    break
            if len(run_bytes) >= min_length * 2:
                try:
                    text = run_bytes.decode("utf-16-le", errors="ignore")
                    text = _clean_extracted_text(text)
                    if text and text not in seen:
                        seen.add(text)
                        results.append(text)
                except Exception:
                    pass
        else:
            i += 1

    return results


def _clean_extracted_text(text: str) -> str:
    """Normalise extracted text: strip control chars, collapse whitespace."""
    # Remove null characters and other control chars (keep \n \t)
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    # Collapse multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Collapse spaces (but not newlines)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()


# ── Image extraction ───────────────────────────────────────────────────────

def _extract_images(data: bytes) -> list[OneNoteImage]:
    """Scan binary data for embedded JPEG, PNG and GIF image blobs."""
    images: list[OneNoteImage] = []
    seen_hashes: set[str] = set()

    # JPEG: starts FF D8 FF, ends FF D9
    pos = 0
    while pos < len(data):
        idx = data.find(_JPEG_MAGIC, pos)
        if idx == -1:
            break
        end = data.find(b'\xFF\xD9', idx + 3)
        if end == -1:
            break
        end += 2  # include EOI marker
        blob = data[idx:end]
        if len(blob) >= _MIN_IMAGE_BYTES:
            h = hashlib.sha256(blob).hexdigest()[:16]
            if h not in seen_hashes:
                seen_hashes.add(h)
                images.append(OneNoteImage(image_bytes=blob, fmt="jpeg", content_hash=h))
        pos = end

    # PNG: starts 89 50 4E 47, ends 49 45 4E 44 AE 42 60 82 (IEND chunk)
    _PNG_IEND = b'\x49\x45\x4E\x44\xAE\x42\x60\x82'
    pos = 0
    while pos < len(data):
        idx = data.find(_PNG_MAGIC, pos)
        if idx == -1:
            break
        end = data.find(_PNG_IEND, idx + 8)
        if end == -1:
            break
        end += len(_PNG_IEND)
        blob = data[idx:end]
        if len(blob) >= _MIN_IMAGE_BYTES:
            h = hashlib.sha256(blob).hexdigest()[:16]
            if h not in seen_hashes:
                seen_hashes.add(h)
                images.append(OneNoteImage(image_bytes=blob, fmt="png", content_hash=h))
        pos = end

    return images


# ── Table detection ────────────────────────────────────────────────────────

def _detect_tables(texts: list[str]) -> list[OneNoteTable]:
    """Heuristically detect tab-delimited or pipe-delimited table data.

    OneNote exports table cell content as tab-delimited strings.
    When we see multiple consecutive short strings that look like
    aligned cells, we group them into a OneNoteTable.
    """
    tables: list[OneNoteTable] = []
    TAB = '\t'

    # Find text blocks that look like tab-delimited rows
    candidate_rows: list[list[str]] = []
    for text in texts:
        if TAB in text:
            cells = [c.strip() for c in text.split(TAB)]
            if 2 <= len(cells) <= 20:
                candidate_rows.append(cells)

    if not candidate_rows:
        return tables

    # Group consecutive rows with same column count into tables
    current_rows: list[list[str]] = []
    current_width: int = 0

    def _flush():
        nonlocal current_rows, current_width
        if len(current_rows) >= 2:
            headers = current_rows[0]
            rows = current_rows[1:]
            tables.append(OneNoteTable(headers=headers, rows=rows))
        current_rows = []
        current_width = 0

    for row in candidate_rows:
        if current_width == 0:
            current_width = len(row)
            current_rows.append(row)
        elif len(row) == current_width:
            current_rows.append(row)
        else:
            _flush()
            current_width = len(row)
            current_rows = [row]

    _flush()
    return tables
