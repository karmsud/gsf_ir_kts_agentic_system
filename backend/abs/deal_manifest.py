"""
DealManifest — Deal metadata + document registry.
Tracks all documents, their types, ingestion status, and amendment history.
Ported from AI Payment Generator pipeline.deal_manifest.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class DocumentType(str, Enum):
    """Supported document types for ABS deals."""
    PSA = "psa"
    INDENTURE = "indenture"
    PROSPECTUS_SUPPLEMENT = "prospectus_supplement"
    TRUST_AGREEMENT = "trust_agreement"
    SERVICING_AGREEMENT = "servicing_agreement"
    UNKNOWN = "unknown"


class IngestionStatus(str, Enum):
    """Ingestion progress for a document."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class DocumentEntry:
    """Single document within a deal."""
    original_filename: str
    detected_type: DocumentType
    detection_confidence: float
    content_hash: str
    ingestion_status: IngestionStatus
    is_payment_source: bool
    ingested_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "original_filename": self.original_filename,
            "detected_type": self.detected_type.value,
            "detection_confidence": self.detection_confidence,
            "content_hash": self.content_hash,
            "ingestion_status": self.ingestion_status.value,
            "is_payment_source": self.is_payment_source,
            "ingested_at": self.ingested_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DocumentEntry:
        return cls(
            original_filename=data["original_filename"],
            detected_type=DocumentType(data["detected_type"]),
            detection_confidence=data["detection_confidence"],
            content_hash=data["content_hash"],
            ingestion_status=IngestionStatus(data["ingestion_status"]),
            is_payment_source=data["is_payment_source"],
            ingested_at=data.get("ingested_at"),
        )


@dataclass
class DealManifest:
    """
    Deal metadata + document registry.
    Persisted as deal_manifest.json in the deal folder root.
    """
    deal_id: str
    deal_name: str
    issuer: str
    series: str
    shelf: str
    closing_date: Optional[str] = None
    payment_source_of_truth: str = ""
    documents: dict[str, DocumentEntry] = field(default_factory=dict)
    amendment_history: list[dict] = field(default_factory=list)
    portfolio_comparison: dict = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    @classmethod
    def load(cls, deal_path: Path) -> DealManifest:
        """Load manifest from deal_manifest.json."""
        manifest_path = deal_path / "deal_manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")

        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        documents = {}
        for key, doc_data in data.get("documents", {}).items():
            documents[key] = DocumentEntry.from_dict(doc_data)

        return cls(
            deal_id=data["deal_id"],
            deal_name=data["deal_name"],
            issuer=data["issuer"],
            series=data["series"],
            shelf=data["shelf"],
            closing_date=data.get("closing_date"),
            payment_source_of_truth=data.get("payment_source_of_truth", ""),
            documents=documents,
            amendment_history=data.get("amendment_history", []),
            portfolio_comparison=data.get("portfolio_comparison", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    def save(self, deal_path: Path) -> None:
        """Save manifest to deal_manifest.json."""
        self.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        manifest_path = deal_path / "deal_manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "deal_id": self.deal_id,
            "deal_name": self.deal_name,
            "issuer": self.issuer,
            "series": self.series,
            "shelf": self.shelf,
            "closing_date": self.closing_date,
            "payment_source_of_truth": self.payment_source_of_truth,
            "documents": {k: v.to_dict() for k, v in self.documents.items()},
            "amendment_history": self.amendment_history,
            "portfolio_comparison": self.portfolio_comparison,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def add_document(self, doc_key: str, entry: DocumentEntry) -> None:
        """Add a document to the manifest."""
        self.documents[doc_key] = entry
        if entry.is_payment_source:
            self.payment_source_of_truth = doc_key

    def remove_document(self, doc_key: str) -> None:
        """Remove a document from the manifest."""
        if doc_key in self.documents:
            del self.documents[doc_key]
            if self.payment_source_of_truth == doc_key:
                self.payment_source_of_truth = ""

    def get_payment_source(self) -> Optional[DocumentEntry]:
        """Get the document designated as payment source of truth."""
        if self.payment_source_of_truth and self.payment_source_of_truth in self.documents:
            return self.documents[self.payment_source_of_truth]
        return None

    def list_documents(self) -> list[str]:
        """Return list of document keys."""
        return list(self.documents.keys())

    def validate(self) -> list[str]:
        """Validate manifest completeness. Returns list of errors."""
        errors = []
        if not self.deal_id:
            errors.append("deal_id is empty")
        if not self.deal_name:
            errors.append("deal_name is empty")
        if not self.issuer:
            errors.append("issuer is empty")
        if not self.series:
            errors.append("series is empty")
        if not self.documents:
            errors.append("No documents registered")
        if not self.payment_source_of_truth:
            errors.append("No payment source of truth designated")
        elif self.payment_source_of_truth not in self.documents:
            errors.append(
                f"Payment source '{self.payment_source_of_truth}' "
                f"not found in documents"
            )
        pst = self.get_payment_source()
        if pst and pst.ingestion_status != IngestionStatus.COMPLETE:
            errors.append(
                f"Payment source '{self.payment_source_of_truth}' "
                f"ingestion status is '{pst.ingestion_status.value}', expected 'complete'"
            )
        return errors

    def is_ready_for_model_generation(self) -> bool:
        """Check if deal is ready for payment model generation."""
        return len(self.validate()) == 0

    def add_amendment(self, version_label: str, description: str, sections_changed: list[str]) -> None:
        """Record an amendment in the history."""
        self.amendment_history.append({
            "version_label": version_label,
            "description": description,
            "sections_changed": sections_changed,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })

    def __repr__(self) -> str:
        return (
            f"DealManifest({self.deal_id}, "
            f"docs={len(self.documents)}, "
            f"source='{self.payment_source_of_truth}')"
        )
