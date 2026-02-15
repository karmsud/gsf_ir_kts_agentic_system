"""PNG asset handler - stores metadata without OCR"""
from __future__ import annotations

from pathlib import Path


def convert_png(path: str) -> tuple[str, list[str]]:
    """
    Convert PNG to asset metadata entry (no OCR).
    
    Returns:
        - text: Minimal descriptive text (filename + path for searchability)
        - images: List containing the PNG path itself (for vision pipeline)
    """
    file_path = Path(path)
    
    # Generate minimal descriptive text for searchability
    # This allows retrieval queries to find images by filename
    text = f"""Asset: {file_path.stem}
Type: Image (PNG)
Path: {file_path.name}
Status: Image description pending (no OCR)

This is a screenshot or diagram referenced in documentation.
Filename keywords: {' '.join(file_path.stem.split('_'))}
"""
    
    # Return the image path so vision agent can process it later
    images = [str(file_path)]
    
    return text, images
