"""Synthetic OneNote Binary File Builder for E2E Testing.

Creates valid .one and .onetoc2 binary files that the Phase 19 parser
can extract content from.  Uses the same structural markers and encoding
that parse_one_section() and parse_onetoc2() expect.

This is NOT a full MS-ONESTORE implementation — it produces the minimal
binary layout that our heuristic parser recognises.
"""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path
from typing import Optional


# ── MS-ONESTORE header magic (must match onenote_converter.py) ─────────
_ONE_HEADER_MAGIC = bytes([
    0xE4, 0x52, 0x5C, 0x7B, 0x8C, 0xD8, 0xA3, 0x4D,
    0xAE, 0xB1, 0x53, 0x78, 0xD0, 0x29, 0x96, 0xD3,
])

# Page-title property ID (what the parser looks for as page boundary)
# PropertyID 0x1C001D94 in little-endian
_PROP_TITLE_MARKER = b'\x94\x1d\x00\x1c'

# Minimum spacing between markers (parser filters < 256 bytes apart)
_MIN_PAGE_GAP = 512

# JPEG stub: a minimal 1x1 white JPEG (valid JPEG, > 512 bytes padded)
_JPEG_HEADER = bytes([0xFF, 0xD8, 0xFF, 0xE0])  # SOI + APP0
_JPEG_FOOTER = bytes([0xFF, 0xD9])               # EOI


def _encode_utf16le(text: str) -> bytes:
    """Encode a string as UTF-16LE without BOM."""
    return text.encode("utf-16-le")


def _pad_to(data: bytes, min_size: int) -> bytes:
    """Pad data with null bytes to reach min_size."""
    if len(data) >= min_size:
        return data
    return data + b'\x00' * (min_size - len(data))


# ── .one file builder ──────────────────────────────────────────────────

class SyntheticPage:
    """A page to embed in a synthetic .one file."""

    def __init__(
        self,
        title: str,
        text_blocks: list[str],
        images: Optional[list[bytes]] = None,
    ):
        self.title = title
        self.text_blocks = text_blocks
        self.images = images or []


def build_one_file(pages: list[SyntheticPage], section_name: str = "TestSection") -> bytes:
    """Build a synthetic .one binary file containing the given pages.

    The binary layout:
    1. 16-byte OneNote header magic
    2. 496 bytes padding (header block = 512 total)
    3. For each page:
       a. Page boundary marker (_PROP_TITLE_MARKER)
       b. Padding (4 bytes)
       c. Page title as UTF-16LE
       d. Null separator (16 bytes)
       e. Each text block as UTF-16LE with separators
       f. Any image blobs (raw JPEG/PNG)
       g. Padding to ensure next marker is >= 256 bytes away

    Returns the complete binary data.
    """
    buf = bytearray()

    # Header
    buf.extend(_ONE_HEADER_MAGIC)
    buf.extend(b'\x00' * (512 - len(_ONE_HEADER_MAGIC)))

    for page in pages:
        # Page boundary marker
        buf.extend(_PROP_TITLE_MARKER)
        buf.extend(b'\x00\x00\x00\x00')  # 4-byte marker padding

        # Page title (UTF-16LE)
        title_bytes = _encode_utf16le(page.title)
        buf.extend(title_bytes)
        buf.extend(b'\x00' * 16)  # null separator

        # Text blocks
        for block in page.text_blocks:
            text_bytes = _encode_utf16le(block)
            buf.extend(text_bytes)
            buf.extend(b'\x00' * 8)  # inter-block separator

        # Images
        for img_bytes in page.images:
            buf.extend(b'\x00' * 16)  # pre-image padding
            buf.extend(img_bytes)
            buf.extend(b'\x00' * 16)  # post-image padding

        # Ensure minimum gap for next page marker
        buf.extend(b'\x00' * _MIN_PAGE_GAP)

    return bytes(buf)


def build_onetoc2_file(section_names: list[str]) -> bytes:
    """Build a synthetic .onetoc2 Table-of-Contents binary file.

    The parser (parse_onetoc2) scans for UTF-16LE strings ending in ".one".
    We embed "<name>.one" as UTF-16LE for each section, separated by binary padding.
    """
    buf = bytearray()

    # Some initial binary header content (not strictly required but realistic)
    buf.extend(b'\x00' * 64)

    for name in section_names:
        # Encode "SectionName.one" as UTF-16LE
        full_name = f"{name}.one"
        buf.extend(_encode_utf16le(full_name))
        # Separator between entries
        buf.extend(b'\x00' * 32)

    buf.extend(b'\x00' * 64)  # footer padding
    return bytes(buf)


def create_minimal_jpeg(width: int = 4, height: int = 4) -> bytes:
    """Create a minimal but valid JPEG image (solid white).

    Returns raw JPEG bytes >= 512 bytes (our parser's minimum image size).
    """
    # Minimal JPEG: SOI + APP0 + DQT + SOF0 + DHT + SOS + data + EOI
    # This is a real minimal JPEG structure
    data = bytearray()

    # SOI (Start Of Image)
    data.extend(b'\xFF\xD8')

    # APP0 (JFIF marker)
    data.extend(b'\xFF\xE0')
    app0 = bytearray()
    app0.extend(b'JFIF\x00')       # identifier
    app0.extend(b'\x01\x01')       # version 1.1
    app0.extend(b'\x00')           # aspect ratio units
    app0.extend(struct.pack('>HH', 1, 1))  # x/y density
    app0.extend(b'\x00\x00')      # no thumbnail
    data.extend(struct.pack('>H', len(app0) + 2))
    data.extend(app0)

    # DQT (Define Quantization Table)
    data.extend(b'\xFF\xDB')
    qt = bytearray()
    qt.extend(b'\x00')  # table 0, 8-bit
    qt.extend(bytes([8] * 64))  # all quantization values = 8
    data.extend(struct.pack('>H', len(qt) + 2))
    data.extend(qt)

    # SOF0 (Start Of Frame, baseline)
    data.extend(b'\xFF\xC0')
    sof = bytearray()
    sof.extend(b'\x08')           # 8-bit precision
    sof.extend(struct.pack('>HH', height, width))
    sof.extend(b'\x01')           # 1 component (grayscale)
    sof.extend(b'\x01\x11\x00')  # component: id=1, sampling=1x1, quant table 0
    data.extend(struct.pack('>H', len(sof) + 2))
    data.extend(sof)

    # DHT (Define Huffman Table) - minimal DC table
    data.extend(b'\xFF\xC4')
    ht = bytearray()
    ht.extend(b'\x00')  # DC table 0
    # Counts: 1 code of length 1, 0 of other lengths
    ht.extend(bytes([1] + [0] * 15))
    ht.extend(b'\x00')  # symbol 0
    data.extend(struct.pack('>H', len(ht) + 2))
    data.extend(ht)

    # DHT - minimal AC table
    data.extend(b'\xFF\xC4')
    ht_ac = bytearray()
    ht_ac.extend(b'\x10')  # AC table 0
    ht_ac.extend(bytes([1] + [0] * 15))
    ht_ac.extend(b'\x00')  # EOB symbol
    data.extend(struct.pack('>H', len(ht_ac) + 2))
    data.extend(ht_ac)

    # SOS (Start Of Scan)
    data.extend(b'\xFF\xDA')
    sos = bytearray()
    sos.extend(b'\x01')           # 1 component
    sos.extend(b'\x01\x00')      # component 1, DC=0/AC=0
    sos.extend(b'\x00\x3F\x00')  # spectral selection 0-63, successive approx 0
    data.extend(struct.pack('>H', len(sos) + 2))
    data.extend(sos)

    # Compressed scan data (minimal - all zero MCUs)
    # For a 4x4 grayscale image with quantization=8, just pad with bytes
    scan_data = bytes([0x7F] * 32)
    data.extend(scan_data)

    # Pad to ensure we exceed _MIN_IMAGE_BYTES (512)
    while len(data) < 520:
        data.extend(b'\x00')

    # EOI (End Of Image)
    data.extend(b'\xFF\xD9')

    return bytes(data)


def create_test_png() -> bytes:
    """Create a minimal valid PNG image (1x1 white pixel).

    Returns raw PNG bytes >= 512 bytes (padded to exceed parser minimum).
    """
    import zlib

    # PNG signature
    sig = b'\x89PNG\r\n\x1a\n'

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        crc = struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack('>I', len(data)) + c + crc

    # IHDR: 1x1, 8-bit RGB
    ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    ihdr = _chunk(b'IHDR', ihdr_data)

    # IDAT: compressed scanline (filter=0, R=255, G=255, B=255)
    raw = b'\x00\xff\xff\xff'
    compressed = zlib.compress(raw)
    idat = _chunk(b'IDAT', compressed)

    # IEND
    iend = _chunk(b'IEND', b'')

    png = sig + ihdr + idat + iend

    # Pad to exceed 512 bytes (parser's _MIN_IMAGE_BYTES)
    # Insert a tEXt chunk with padding
    comment = b'Test image for KTS Phase 19 OneNote E2E testing' + b'\x00' * 450
    text_chunk = _chunk(b'tEXt', b'Comment\x00' + comment)

    png = sig + ihdr + text_chunk + idat + iend
    return png


# ── Test corpus content ────────────────────────────────────────────────

# Content extracted/adapted from GSF IR Support Library.md for testing
TROUBLESHOOTING_PAGES = [
    SyntheticPage(
        title="Import Problems",
        text_blocks=[
            "Category: Import",
            "Duplicate key error even if data not found in tblServ.",
            "Possible Cause: Loan listed multiple times in the servicer file. "
            "Look for duplicates in the source file prior to importing.",
            "Blank rows in the source file can cause import failures.",
            "If tblLoanCutoffOrig is wiped out, use IMPORT PREFUNDING CUTOFF EXCEL map. "
            "If it is after the first payment, can use the prefunding map to reload "
            "the cutoff data from scratch.",
            "Query the missing data from test environments (UAT or IT), copy into "
            "Excel and reformat to fit the template for the prefunding map and import.",
            "If have to update the SetupDt for the file to load, ask Manager to use "
            "DMT to fix the SetupDt in tblLoanCutoffOrig to what they should be. "
            "Then reprocess.",
            "Error in Microsoft.SqlServer.Dts.Runtime.Package: The package format "
            "was migrated from version 6 to version 8.",
            "Solution: Run iApplication_Cleaner.lnk. Reload the application via "
            "the desktop icon. Never open iApps from Program Files or Start menu.",
        ],
    ),
    SyntheticPage(
        title="Process Distribution Issues",
        text_blocks=[
            "Category: Open/Process Distrib/Review",
            "iManage fails to open or process the files, export inputs or throws "
            "an Excel.Interop error.",
            "CAS Entry Export failed: Unable to cast COM object of type "
            "Microsoft.Office.Interop.Excel.ApplicationClass to interface type "
            "Microsoft.Office.Interop.Excel._Application.",
            "Solution: Call or chat with ITSC to run a Quick Repair on the VDI. "
            "Restart VDI afterwards.",
            "If Quick Repair still does not work, possibly uninstalling Microsoft "
            "Teams on VDI will help.",
            "NAME errors throughout the files: Try running FormulaFix_IR on the "
            "file and saving it.",
            "Accept Data seems to do nothing when all loans transferred to another. "
            "Add LIDs in the import.",
            "Programmatic access to Visual Basic Project is not trusted. "
            "Update Excel settings per the Office 365 ProPlus Settings guide.",
        ],
    ),
    SyntheticPage(
        title="VDI and Citrix Issues",
        text_blocks=[
            "Category: Citrix/VDI",
            "VDI will not open. Have to end all related processes in Task Manager.",
            "Solution: Run Citrix_Receiver_Reset.CMD from the Systems Help Tools folder.",
            "Tip: Copy the file to your local machine desktop for quicker access, "
            "especially if you have the issue every day.",
            "Logging into Citrix via browser. After login get following error: "
            "Citrix Workspace app cannot create a secure connection in this browser.",
            "Clear browser cache and cookies. Close browser completely and retry.",
            "Alternative method of accessing VDI instead of through browser is "
            "setting it up on your work computer.",
            "The resource is unavailable currently. Try again later. "
            "The only way to fix this is to open an Incident with ITSC and "
            "refer your VDI hostname and the Transaction ID you received.",
            "Duplicate Icons on Desktop: All machines now use OneDrive Desktop "
            "as a default. You can delete the copy and it will be removed from "
            "all your machines.",
            "Default Printer in VDI: Bank policy forces the default printer on "
            "VDIs to Citrix UNIVERSAL Printer every time you log in.",
        ],
    ),
    SyntheticPage(
        title="Excel and Macro Errors",
        text_blocks=[
            "Category: Excel",
            "Programmatic access to Visual Basic Project is not trusted.",
            "Update Excel settings per the Office 365 ProPlus Settings guide.",
            "To get LID2 to show up on the Loan Level Export, "
            "enable LID2 on LoanExport via Deal Setup Other Settings.",
            "To lock or unlock a distrib, need to make sure there are no "
            "comments in the file. May get a delete any threaded comments error.",
            "Go to Review then Show Comments to find the comments that need "
            "to be deleted. This action must be performed per worksheet.",
            "Microsoft has blocked macros from running because the source of "
            "this file is untrusted.",
            "Solution: Verify the Trust Center Setting from Tech Tips. "
            "Reverify and apply the setting changes of iRibbon 3.0 Setup.",
            "Global Macros Error: Could not find GlobalMacro.xlsm. "
            "Ensure your J: drive is mapped and you can access the drive folders.",
            "Error in global macro ReportPackage_IR. Excel object returned failure. "
            "Add Macros to either Prepare Distrib or Process distrib step.",
        ],
    ),
    SyntheticPage(
        title="Package and Report Issues",
        text_blocks=[
            "Category: Package PDF",
            "Package does not generate with no obvious error.",
            "Go to PackagePDF folder and delete all the files in that folder.",
            "The cover page only generates if the package includes Crystal Reports "
            "or if the Distrib Reports custom views are set to L landscape orientation "
            "and Overlay is enabled.",
            "Error during Package PDF: Could not rename file because it could be "
            "locked or open.",
            "Underlying Delinq Summary support package pages are missing. "
            "Add that in setup.",
            "Archive report error: Final package changed since signoff.",
            "Solution: Revert the deal back to the Processor Signoff step and "
            "reran the workflow from that point.",
            "Error in ExportPackagePDF: System detected a revision for this deal. "
            "Revert to Step Generate Auto Reports and enable the check box for "
            "Revise Stamp then continue process.",
            "Reports are not posting to Pivot. The External Systems ID is not "
            "populated in SDDB or does not match iManage Payment ID.",
        ],
    ),
]

RELEASE_NOTES_PAGES = [
    SyntheticPage(
        title="Release Notes - March 2023",
        text_blocks=[
            "March 2023 Release Notes",
            "New Features:",
            "Added support for RESEC CUSIP batch loading via tblResecCutoff.",
            "Improved automation timeout handling for OpenFileAutomation.",
            "Enhanced the FormulaFix_IR macro for handling NAME errors.",
            "Bug Fixes:",
            "Fixed Processor Signoff error when multiple Account Administrators "
            "are assigned to the same deal.",
            "Resolved issue where Package PDF would not generate when cover page "
            "settings were misconfigured.",
            "Known Issues:",
            "The sensitivity label restriction on automation Excel processor "
            "is still active. Check for discreet sensitivity labels on files "
            "if OpenFileAutomation times out.",
        ],
    ),
    SyntheticPage(
        title="Release Notes - April 2023",
        text_blocks=[
            "April 2023 Release Notes",
            "New Features:",
            "Input Manager improvements: InputManager_IR now auto-refreshes "
            "when batch-loaded data is present.",
            "Added PDF Compare utility for comparing PDF files across periods.",
            "Copy From button in Deal Setup now works when all existing inputs "
            "are cleared first.",
            "Bug Fixes:",
            "Fixed iTracker screenshot pasting: use Ctrl+V from snipping tool.",
            "Resolved Import Prefunding Cutoff map issues for after first payment.",
            "Performance Improvements:",
            "Optimized SSIS import processing for large OLE DB batches.",
            "Reduced Package PDF generation time by 15 percent.",
        ],
    ),
    SyntheticPage(
        title="Release Notes - May 2023",
        text_blocks=[
            "May 2023 Release Notes",
            "Critical Update:",
            "SharePoint migration settings must be verified. All users must "
            "follow the SharePoint Migration May 2023 guide for OneDrive sync.",
            "A one-time process to sync Processing Notes with OneDrive is required.",
            "New Features:",
            "Impact Analysis Tool training video now available at the "
            "N Training Impact Analysis Tool Training folder.",
            "Improved ODBC driver detection with CheckSystemDriverProvider utility.",
            "Bug Fixes:",
            "Fixed workbook referenced by another workbook error by updating "
            "Calculation Options to Automatic.",
            "Resolved old VDI to new VDI migration issues with Company Portal.",
        ],
    ),
]


def create_test_notebook(
    output_dir: str | Path,
    notebook_name: str = "GSF_IR_Test_Notebook",
    include_images: bool = True,
) -> Path:
    """Create a complete test notebook folder with .one files and .onetoc2.

    Directory structure created:
        output_dir/
            Open Notebook.onetoc2
            Troubleshooting.one
            Release Notes.one

    Parameters
    ----------
    output_dir : str | Path
        Directory to create the notebook in.
    notebook_name : str
        Name for the notebook (used as folder name).
    include_images : bool
        Whether to embed test images in pages.

    Returns
    -------
    Path
        The notebook folder path.
    """
    nb_dir = Path(output_dir) / notebook_name
    nb_dir.mkdir(parents=True, exist_ok=True)

    # Add a test image to some pages if requested
    test_jpeg = create_minimal_jpeg() if include_images else None
    test_png = create_test_png() if include_images else None

    # Section 1: Troubleshooting (standard chunking)
    troubleshooting_pages = list(TROUBLESHOOTING_PAGES)
    if include_images and test_jpeg:
        # Add an image to the first page
        troubleshooting_pages[0] = SyntheticPage(
            title=troubleshooting_pages[0].title,
            text_blocks=troubleshooting_pages[0].text_blocks,
            images=[test_jpeg],
        )
    if include_images and test_png:
        # Add a PNG to the third page
        troubleshooting_pages[2] = SyntheticPage(
            title=troubleshooting_pages[2].title,
            text_blocks=troubleshooting_pages[2].text_blocks,
            images=[test_png],
        )

    one_data_trouble = build_one_file(troubleshooting_pages, "Troubleshooting")
    (nb_dir / "Troubleshooting.one").write_bytes(one_data_trouble)

    # Section 2: Release Notes (release-notes atomic chunking)
    one_data_release = build_one_file(RELEASE_NOTES_PAGES, "Release Notes")
    (nb_dir / "Release Notes.one").write_bytes(one_data_release)

    # Table of Contents
    toc_data = build_onetoc2_file(["Troubleshooting", "Release Notes"])
    (nb_dir / "Open Notebook.onetoc2").write_bytes(toc_data)

    return nb_dir


def verify_notebook_structure(nb_dir: Path) -> dict:
    """Verify a notebook folder has the expected files and return info."""
    result = {
        "exists": nb_dir.exists(),
        "one_files": sorted([f.name for f in nb_dir.glob("*.one")]),
        "toc_files": [f.name for f in nb_dir.glob("*.onetoc2")],
        "total_size": sum(f.stat().st_size for f in nb_dir.iterdir() if f.is_file()),
    }
    return result
