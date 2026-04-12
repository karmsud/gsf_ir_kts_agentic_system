"""
Document Intelligence — Type detection + duplicate checking workflow.

Combines document classification and content hashing into a single
intelligence pipeline that determines whether to proceed with ingestion.

Ported from PayGen pipeline.ingestion.document_intelligence → backend.abs.ingestion
Import rewrites:
  pipeline.skills.document_classifier → backend.abs.skills.document_classifier
  pipeline.skills.document_hasher    → backend.abs.skills.document_hasher
  pipeline.config.constants          → backend.abs.config.constants
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from backend.abs.skills.document_classifier import classify_document, ClassificationResult
from backend.abs.skills.document_hasher import (
    compute_content_hash,
    check_duplicates,
    DuplicateCheckResult,
)
from backend.abs.config.constants import CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_LOW_THRESHOLD

logger = logging.getLogger(__name__)


@dataclass
class DocumentIntelligenceResult:
    """Combined result of document type detection and duplicate check."""
    classification: ClassificationResult
    duplicate_check: Optional[DuplicateCheckResult]
    should_proceed: bool
    decision: str  # "proceed", "reject_duplicate", "warn_near_duplicate", "reject_unknown"
    confidence_tier: str  # "high", "medium", "low"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "document_type": self.classification.document_type,
            "classification_confidence": self.classification.confidence,
            "matched_patterns": self.classification.matched_patterns,
            "is_duplicate": self.duplicate_check.is_duplicate if self.duplicate_check else False,
            "duplicate_match": self.duplicate_check.matching_deal_id if self.duplicate_check else "",
            "should_proceed": self.should_proceed,
            "decision": self.decision,
            "confidence_tier": self.confidence_tier,
            "warnings": self.warnings,
        }


def classify_and_check_duplicate(
    file_path: Path,
    hash_registry_path: Optional[Path] = None,
    deal_id: str = "",
    content: Optional[str] = None,
) -> DocumentIntelligenceResult:
    """
    Run the complete document intelligence pipeline:
    1. Classify document type (PSA, Indenture, ProSupp, etc.)
    2. Check content hash against registry for duplicates
    3. Determine confidence tier
    4. Make proceed/reject/warn decision

    Args:
        file_path: Path to document file
        hash_registry_path: Path to hash registry JSON (for dedup)
        deal_id: Current deal ID (skip self-matches in dedup)
        content: Optional pre-loaded content

    Returns:
        DocumentIntelligenceResult with decision
    """
    file_path = Path(file_path)

    # Step 1: Classify document type
    classification = classify_document(file_path, content=content)

    # Step 2: Determine confidence tier
    if classification.confidence >= CONFIDENCE_HIGH_THRESHOLD:
        confidence_tier = "high"
    elif classification.confidence >= CONFIDENCE_LOW_THRESHOLD:
        confidence_tier = "medium"
    else:
        confidence_tier = "low"

    # Step 3: Check for duplicates
    duplicate_check = None
    if hash_registry_path is not None and file_path.exists():
        try:
            duplicate_check = check_duplicates(
                file_path=file_path,
                hash_registry_path=hash_registry_path,
                deal_id=deal_id,
            )
        except Exception as e:
            logger.warning(f"Duplicate check failed: {e}")

    # Step 4: Make decision
    warnings: list[str] = []
    decision = "proceed"
    should_proceed = True

    # Check for duplicate rejection
    if duplicate_check and duplicate_check.is_duplicate:
        decision = "reject_duplicate"
        should_proceed = False
        logger.info(
            f"Duplicate detected: {file_path.name} matches "
            f"{duplicate_check.matching_deal_id}/{duplicate_check.matching_document}"
        )

    # Check for unknown document type
    elif classification.document_type == "UNKNOWN":
        if confidence_tier == "low":
            decision = "reject_unknown"
            should_proceed = False
            warnings.append(
                f"Cannot classify document '{file_path.name}' "
                f"(confidence: {classification.confidence:.2%})"
            )
        else:
            warnings.append(
                f"Document type uncertain for '{file_path.name}' "
                f"(confidence: {classification.confidence:.2%})"
            )

    # Check confidence tier warnings
    if confidence_tier == "medium":
        warnings.append(
            f"Classification confidence is medium ({classification.confidence:.2%}). "
            f"Review recommended."
        )
    elif confidence_tier == "low" and decision == "proceed":
        warnings.append(
            f"Classification confidence is low ({classification.confidence:.2%}). "
            f"Manual verification recommended."
        )

    return DocumentIntelligenceResult(
        classification=classification,
        duplicate_check=duplicate_check,
        should_proceed=should_proceed,
        decision=decision,
        confidence_tier=confidence_tier,
        warnings=warnings,
    )


def classify_and_register(
    file_path: Path,
    hash_registry_path: Path,
    deal_id: str,
    content: Optional[str] = None,
) -> DocumentIntelligenceResult:
    """
    Classify a document and register its hash if it should proceed.

    Convenience wrapper that combines classify_and_check_duplicate
    with hash registration.

    Args:
        file_path: Path to document file
        hash_registry_path: Path to hash registry JSON
        deal_id: Current deal ID
        content: Optional pre-loaded content

    Returns:
        DocumentIntelligenceResult with decision
    """
    from backend.abs.skills.document_hasher import register_hash

    result = classify_and_check_duplicate(
        file_path=file_path,
        hash_registry_path=hash_registry_path,
        deal_id=deal_id,
        content=content,
    )

    if result.should_proceed and file_path.exists():
        register_hash(
            file_path=file_path,
            hash_registry_path=hash_registry_path,
            deal_id=deal_id,
            document_type=result.classification.document_type,
        )

    return result
