from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Citation:
    doc_id: str
    doc_name: str
    source_path: str
    uri: str
    version: int
    section: str | None = None
    page: int | None = None
    last_updated: str | None = None
    freshness_badge: str = "UNKNOWN"
    image_note: str | None = None


@dataclass
class EscalationReport:
    type: str
    severity: str
    message: str
    suggested_contacts: list[str] = field(default_factory=list)


@dataclass
class AgentResult:
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    reasoning: str = ""
    citations: list[Citation] = field(default_factory=list)
    escalation: EscalationReport | None = None


@dataclass
class FileInfo:
    path: str
    filename: str
    extension: str
    size_bytes: int
    modified_time: str
    hash: str
    doc_id: str | None = None
    status: str = "active"  # active, missing, error, deleted
    last_seen: str | None = None
    retry_count: int = 0
    source_id: str | None = None  # Stable ID based on content hash
    versions: list[dict] = field(default_factory=list)  # History of {version, hash, date}


@dataclass
class FileChange:
    new_files: list[FileInfo] = field(default_factory=list)
    modified_files: list[FileInfo] = field(default_factory=list)
    deleted_files: list[FileInfo] = field(default_factory=list)
    unchanged_files: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class IngestedDocument:
    doc_id: str
    title: str
    source_path: str
    extension: str
    content_path: str
    metadata_path: str
    images_dir: str
    extracted_text: str
    image_paths: list[str] = field(default_factory=list)
    chunk_count: int = 0
    word_count: int = 0
    version: int = 1


@dataclass
class TextChunk:
    chunk_id: str
    doc_id: str
    content: str
    source_path: str
    chunk_index: int
    doc_type: str = "UNKNOWN"
    entities: list[dict] = field(default_factory=list)  # [{"text": str, "label": str}, ...]
    keyphrases: list[dict] = field(default_factory=list)  # [{"text": str, "score": float}, ...]


@dataclass
class SearchResult:
    context_chunks: list[TextChunk]
    confidence: float
    citations: list[Citation]
    image_notes: list[str] = field(default_factory=list)
    freshness: dict[str, int] = field(default_factory=dict)
    related_topics: list[str] = field(default_factory=list)
    escalation: EscalationReport | None = None


@dataclass
class LearningStep:
    order: int
    doc_id: str
    doc_title: str
    doc_type: str
    estimated_time_minutes: int
    difficulty: str
    description: str
    prerequisites: list[str] = field(default_factory=list)


@dataclass
class TrainingPath:
    topic: str
    level: str
    steps: list[LearningStep] = field(default_factory=list)
    total_time_minutes: int = 0
    coverage: float = 0.0


@dataclass
class ImpactReport:
    entity: str
    entity_type: str = "auto"
    direct_docs: list[dict[str, str]] = field(default_factory=list)
    indirect_docs: list[dict[str, str]] = field(default_factory=list)
    stale_images: list[dict[str, str]] = field(default_factory=list)
    affected_processes: list[dict[str, str]] = field(default_factory=list)
    affected_training: list[dict[str, str]] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    severity: str = "low"


@dataclass
class FreshnessReport:
    total_documents: int
    current: int
    aging: int
    stale: int
    unknown: int
    stale_documents: list[dict[str, str]] = field(default_factory=list)
    stale_images: list[dict[str, str]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
