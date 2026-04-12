"""
Document Tools — Unified document tool interface combining
classification, hashing, MinHash near-duplicate detection,
and intelligence workflows.

This module provides a single entry point for document-level
tools used by the Document Quality Agent and Ingestion Pipeline.

Ported from PayGen pipeline.skills.document_tools → backend.abs.skills
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backend.abs.skills.document_classifier import classify_document
from backend.abs.skills.document_hasher import (
    DuplicateCheckResult,
    HashRecord,
    check_duplicates,
    check_portfolio_duplicates,
    compute_content_hash,
    compute_text_hash,
    register_hash,
)

logger = logging.getLogger(__name__)


@dataclass
class DocumentAnalysisResult:
    """Combined result of classification + duplicate check + MinHash."""
    # Classification
    document_type: str = ""
    classification_confidence: float = 0.0
    filename_match: str = ""
    content_match: str = ""

    # Hashing
    content_hash: str = ""
    is_exact_duplicate: bool = False
    duplicate_deal_id: str = ""
    duplicate_document: str = ""

    # Near-duplicate (MinHash)
    is_near_duplicate: bool = False
    jaccard_similarity: float = 0.0
    near_duplicate_deal_id: str = ""

    # Decision
    decision: str = "proceed"  # proceed | reject | warn
    decision_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "document_type": self.document_type,
            "classification_confidence": round(self.classification_confidence, 3),
            "content_hash": self.content_hash,
            "is_exact_duplicate": self.is_exact_duplicate,
            "duplicate_deal_id": self.duplicate_deal_id,
            "is_near_duplicate": self.is_near_duplicate,
            "jaccard_similarity": round(self.jaccard_similarity, 3),
            "near_duplicate_deal_id": self.near_duplicate_deal_id,
            "decision": self.decision,
            "decision_reason": self.decision_reason,
        }


def analyze_document(
    file_path: Path,
    hash_registry_path: Path,
    deal_id: str = "",
    near_duplicate_threshold: float = 0.85,
) -> DocumentAnalysisResult:
    """
    Full document analysis: classify + exact duplicate check + near-duplicate.

    Args:
        file_path: Path to document file
        hash_registry_path: Path to hash registry JSON
        deal_id: Current deal ID (skip self-matches)
        near_duplicate_threshold: Jaccard threshold for near-duplicate

    Returns:
        DocumentAnalysisResult with decision
    """
    file_path = Path(file_path)
    result = DocumentAnalysisResult()

    # ── Step 1: Classification ──
    try:
        classification = classify_document(file_path)
        result.document_type = classification.document_type
        result.classification_confidence = classification.confidence
    except Exception as e:
        logger.warning("Classification failed for %s: %s", file_path, e)
        result.document_type = "unknown"

    # ── Step 2: Exact Duplicate Check (SHA-256) ──
    try:
        dup_result = check_duplicates(file_path, hash_registry_path, deal_id)
        result.content_hash = dup_result.content_hash
        result.is_exact_duplicate = dup_result.is_duplicate
        if dup_result.is_duplicate:
            result.duplicate_deal_id = dup_result.matching_deal_id
            result.duplicate_document = dup_result.matching_document
    except FileNotFoundError:
        result.content_hash = ""
    except Exception as e:
        logger.warning("Duplicate check failed: %s", e)

    # ── Step 3: Near-Duplicate Check (MinHash/Jaccard) ──
    try:
        from backend.abs.skills.document_hasher import check_near_duplicates
        near_result = check_near_duplicates(
            file_path, hash_registry_path, deal_id,
            threshold=near_duplicate_threshold,
        )
        if near_result:
            result.is_near_duplicate = True
            result.jaccard_similarity = near_result.get("jaccard_similarity", 0.0)
            result.near_duplicate_deal_id = near_result.get("matching_deal_id", "")
    except (ImportError, AttributeError):
        pass  # MinHash not available
    except Exception as e:
        logger.warning("Near-duplicate check failed: %s", e)

    # ── Step 4: Decision ──
    if result.is_exact_duplicate:
        result.decision = "reject"
        result.decision_reason = (
            f"Exact duplicate of document in deal {result.duplicate_deal_id}"
        )
    elif result.is_near_duplicate and result.jaccard_similarity >= 0.95:
        result.decision = "reject"
        result.decision_reason = (
            f"Near-duplicate (Jaccard={result.jaccard_similarity:.2f}) "
            f"of deal {result.near_duplicate_deal_id}"
        )
    elif result.is_near_duplicate:
        result.decision = "warn"
        result.decision_reason = (
            f"Possible near-duplicate (Jaccard={result.jaccard_similarity:.2f}) "
            f"of deal {result.near_duplicate_deal_id}"
        )
    elif result.document_type == "unknown" and result.classification_confidence < 0.3:
        result.decision = "warn"
        result.decision_reason = "Document type could not be determined"
    else:
        result.decision = "proceed"
        result.decision_reason = (
            f"Document classified as {result.document_type} "
            f"(confidence={result.classification_confidence:.2f})"
        )

    return result


def register_document(
    file_path: Path,
    hash_registry_path: Path,
    deal_id: str,
    document_type: str = "",
) -> HashRecord:
    """
    Register a document in the hash registry after ingestion.

    Args:
        file_path: Path to document
        hash_registry_path: Path to registry JSON
        deal_id: Deal ID
        document_type: Document type classification

    Returns:
        HashRecord with hash details
    """
    return register_hash(file_path, hash_registry_path, deal_id, document_type)


def get_document_fingerprint(file_path: Path) -> dict:
    """
    Get a document fingerprint: hash + classification + metadata.

    Args:
        file_path: Path to document

    Returns:
        Dict with fingerprint data
    """
    file_path = Path(file_path)
    content_hash = compute_content_hash(file_path)
    classification = classify_document(file_path)

    return {
        "path": str(file_path),
        "filename": file_path.name,
        "content_hash": content_hash,
        "file_size_bytes": file_path.stat().st_size,
        "document_type": classification.document_type,
        "classification_confidence": classification.confidence,
    }
