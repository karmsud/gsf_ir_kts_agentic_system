"""
Document Classifier — Classify incoming documents by type
using filename patterns and content signatures.

Ported from PayGen pipeline.skills.document_classifier → backend.abs.skills
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backend.abs.config.schemas import DOC_TYPE_SIGNATURES


@dataclass
class ClassificationResult:
    """Result of document classification."""
    document_type: str  # e.g., "PSA", "INDENTURE"
    confidence: float   # 0.0 to 1.0
    matched_patterns: list[str]
    source_file: str


def classify_document(
    file_path: Path,
    content: Optional[str] = None,
) -> ClassificationResult:
    """
    Classify a document by type using filename patterns and content analysis.

    Strategy:
    1. Match filename against known patterns → weighted 0.4
    2. Match content against known signatures → weighted 0.6
    3. Best combined score wins

    Args:
        file_path: Path to document file
        content: Optional pre-loaded content. If None, reads from file.

    Returns:
        ClassificationResult with best-matching type and confidence
    """
    file_path = Path(file_path)
    filename = file_path.name.lower()

    if content is None:
        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception:
                content = ""
        else:
            content = ""

    content_lower = content.lower() if content else ""

    best_type = "UNKNOWN"
    best_score = 0.0
    best_patterns: list[str] = []

    for doc_type, sig in DOC_TYPE_SIGNATURES.items():
        filename_patterns = sig.get("filename_patterns", [])
        content_patterns = sig.get("content_patterns", [])
        min_matches = sig.get("min_matches", 1)

        # Filename matching (weight: 0.4)
        filename_matches = []
        for pattern in filename_patterns:
            if re.search(pattern, filename, re.IGNORECASE):
                filename_matches.append(pattern)

        filename_score = min(len(filename_matches) / max(len(filename_patterns), 1), 1.0)

        # Content matching (weight: 0.6)
        content_matches = []
        for pattern in content_patterns:
            if re.search(pattern, content_lower, re.IGNORECASE):
                content_matches.append(pattern)

        content_score = min(len(content_matches) / max(len(content_patterns), 1), 1.0)

        # Combined score
        combined_score = (filename_score * 0.4) + (content_score * 0.6)

        # Must meet minimum match threshold
        total_matches = len(filename_matches) + len(content_matches)
        if total_matches >= min_matches and combined_score > best_score:
            best_score = combined_score
            best_type = doc_type.upper()
            best_patterns = filename_matches + content_matches

    return ClassificationResult(
        document_type=best_type,
        confidence=round(best_score, 4),
        matched_patterns=best_patterns,
        source_file=str(file_path),
    )


def classify_all_documents(
    directory: Path,
    extensions: tuple[str, ...] = (".md", ".txt", ".docx", ".pdf"),
) -> list[ClassificationResult]:
    """
    Classify all documents in a directory.

    Args:
        directory: Directory containing documents
        extensions: File extensions to consider

    Returns:
        List of ClassificationResult, one per file
    """
    results: list[ClassificationResult] = []
    directory = Path(directory)

    if not directory.is_dir():
        return results

    for f in sorted(directory.iterdir()):
        if f.is_file() and f.suffix.lower() in extensions:
            result = classify_document(f)
            results.append(result)

    return results
