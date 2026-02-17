"""Legacy Word .doc (OLE2 binary) converter.

Extracts text from the Word Binary File Format using olefile.
Parses the FIB (File Information Block) and CLX (Complex) structures
to locate and decode text runs (ANSI and Unicode pieces).

Falls back to brute-force ASCII extraction if the structured parse fails.
"""
from __future__ import annotations

import logging
import re
import struct
from pathlib import Path

logger = logging.getLogger(__name__)


def _parse_piece_table(table_data: bytes, clx_offset: int, clx_size: int,
                       word_data: bytes, total_chars: int) -> str:
    """Parse the CLX piece table to extract text with correct encoding."""
    pieces: list[str] = []
    pos = clx_offset
    end = clx_offset + clx_size

    # Skip any Grpprl (prefix) entries (type 0x01) to find the Pcdt (type 0x02)
    while pos < end:
        clxt = table_data[pos]
        if clxt == 0x02:  # Pcdt
            pos += 1  # skip type byte
            pcdt_size = struct.unpack_from("<I", table_data, pos)[0]
            pos += 4  # skip size field
            break
        elif clxt == 0x01:  # Grpprl
            pos += 1
            cb = struct.unpack_from("<H", table_data, pos)[0]
            pos += 2 + cb
        else:
            # Unknown – skip ahead
            pos += 1
    else:
        return ""

    # PlcPcd: array of CPs followed by array of PCDs
    # Number of pieces = (pcdt_size - 4) / (4 + 8)  ... actually we compute from CPs
    # CP entries are uint32, PCD entries are 8 bytes each
    # n+1 CPs and n PCDs → pcdt_size = (n+1)*4 + n*8 = 4 + n*12
    # → n = (pcdt_size - 4) / 12
    n_pieces = (pcdt_size - 4) // 12  # approximate
    if n_pieces <= 0:
        return ""

    cp_base = pos
    pcd_base = cp_base + (n_pieces + 1) * 4

    for i in range(n_pieces):
        cp_start = struct.unpack_from("<I", table_data, cp_base + i * 4)[0]
        cp_end = struct.unpack_from("<I", table_data, cp_base + (i + 1) * 4)[0]
        char_count = cp_end - cp_start
        if char_count <= 0:
            continue

        # PCD: 2 bytes flags + 4 bytes fc + 2 bytes prm
        pcd_offset = pcd_base + i * 8
        pcd_fc_raw = struct.unpack_from("<I", table_data, pcd_offset + 2)[0]

        # Bit 30 of fc indicates ANSI (compressed) vs Unicode
        is_ansi = bool(pcd_fc_raw & (1 << 30))
        fc = pcd_fc_raw & 0x3FFFFFFF  # mask off the flag bits

        if is_ansi:
            # ANSI: each char = 1 byte, fc is byte offset / 2
            byte_offset = fc
            raw = word_data[byte_offset:byte_offset + char_count]
            try:
                text = raw.decode("cp1252", errors="replace")
            except Exception:
                text = raw.decode("latin-1", errors="replace")
        else:
            # Unicode: each char = 2 bytes
            byte_offset = fc
            raw = word_data[byte_offset:byte_offset + char_count * 2]
            try:
                text = raw.decode("utf-16-le", errors="replace")
            except Exception:
                text = raw.decode("latin-1", errors="replace")

        pieces.append(text)

    return "".join(pieces)


def _extract_text_structured(path: str) -> str:
    """Extract text using FIB + CLX piece table parsing."""
    import olefile

    ole = olefile.OleFileIO(path)
    word_stream = ole.openstream("WordDocument")
    word_data = word_stream.read()
    word_stream.close()

    # FIB flags at 0x000A
    flags = struct.unpack_from("<H", word_data, 0x000A)[0]
    table_name = "1Table" if (flags & (1 << 9)) else "0Table"

    # Character counts from FIB
    ccpText = struct.unpack_from("<I", word_data, 0x004C)[0]
    total_chars = ccpText

    if total_chars == 0:
        ole.close()
        return ""

    if not ole.exists(table_name):
        ole.close()
        return ""

    table_stream = ole.openstream(table_name)
    table_data = table_stream.read()
    table_stream.close()

    # fcClx and lcbClx: offset depends on FIB version
    # For Word 97-2003 (nFib >= 193), the FIB has a variable-length structure.
    # The CLX offset is stored in FibRgFcLcb97 at specific positions.
    # FibBase = 32 bytes, FibRgW97 starts at offset 32, has csw*2 bytes,
    # FibRgLw97 starts after that, has cslw*4 bytes,
    # Then FibRgFcLcbBlob.
    # 
    # Shortcut: scan for the CLX in known positions
    # In Word 97: fcClx is at FIB offset 0x01A2, lcbClx at 0x01A6
    try:
        fcClx = struct.unpack_from("<I", word_data, 0x01A2)[0]
        lcbClx = struct.unpack_from("<I", word_data, 0x01A6)[0]
    except struct.error:
        ole.close()
        return ""

    if lcbClx == 0 or fcClx == 0:
        ole.close()
        return ""

    text = _parse_piece_table(table_data, fcClx, lcbClx, word_data, total_chars)
    ole.close()
    return text


def _extract_text_bruteforce(path: str) -> str:
    """Brute-force fallback: read the raw file and extract ASCII text runs."""
    raw = Path(path).read_bytes()
    decoded = raw.decode("latin-1", errors="ignore")
    # Find runs of printable ASCII characters (30+ chars)
    runs = re.findall(r"[\x20-\x7e\n\r\t]{30,}", decoded)
    return "\n".join(runs)


def convert_doc(path: str, images_dir: str | None = None) -> tuple[str, list[str]]:
    """Convert a legacy .doc file to text.

    Attempts structured parsing first, then falls back to brute-force.
    Image extraction from .doc is not supported (returns empty list).

    Args:
        path: Path to the .doc file.
        images_dir: Optional directory for extracted images (not used for .doc).

    Returns:
        Tuple of (extracted_text, image_paths).
    """
    text = ""

    # Try structured extraction first
    try:
        text = _extract_text_structured(path)
    except Exception as exc:
        logger.warning("Structured .doc parsing failed: %s — trying brute-force", exc)

    # Clean up control characters and Word-specific artifacts
    if text:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("\x07", " ")  # table cell markers
        text = text.replace("\x0b", "\n")  # vertical tab → newline
        text = text.replace("\x0c", "\n\n")  # page break
        text = re.sub(r"[\x00-\x08\x0e-\x1f]", "", text)
        # Remove Word field codes: PAGEREF, TOC, HYPERLINK, etc.
        text = re.sub(r"PAGEREF\s+_Toc\d+\s*\\h\s*\d*", "", text)
        text = re.sub(r"\\h\s+\d+", "", text)
        text = re.sub(r"HYPERLINK\s+\\l\s+\"[^\"]*\"", "", text)
        # Remove non-ASCII garbage at the end (formatting data that leaked through)
        text = re.sub(r"[\x80-\xff]{5,}", " ", text)
        # Collapse excessive whitespace but preserve paragraph breaks
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

    # Fall back to brute-force if structured parse yielded little text
    if len(text) < 100:
        logger.info("Structured parse yielded %d chars, trying brute-force", len(text))
        fallback = _extract_text_bruteforce(path)
        if len(fallback) > len(text):
            text = fallback

    if not text:
        raise ValueError(f"Could not extract text from .doc file: {path}")

    logger.info("Extracted %d characters from .doc file", len(text))

    # .doc image extraction is not supported (would require parsing the Data stream
    # for embedded OLE objects, which is extremely complex)
    return text, []
