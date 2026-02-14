# GSF IR KTS — Data Model

Complete definition of all dataclasses, enums, and type structures used across the system.

---

## 1. Core Agent Types

### 1.1 AgentResult

The universal return type for all agents.

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class Citation:
    """Reference to a source document used in retrieval results."""
    doc_id: str
    doc_name: str
    source_path: str
    uri: str                             # file:// URI for VS Code to open
    version: int
    section: str | None = None
    page: int | None = None
    last_updated: str | None = None
    freshness_badge: str = "UNKNOWN"     # CURRENT, AGING, STALE, UNKNOWN
    image_note: str | None = None        # Note about image location, e.g., "Screenshot on page 12 shows..."

@dataclass
class EscalationReport:
    """Structured report when an agent cannot confidently complete a task."""
    type: str                            # MISSING_INFO, LOW_CONFIDENCE, AGENT_ERROR, etc.
    severity: str                        # "info", "warning", "critical"
    message: str
    suggested_action: str
    suggested_sme: str | None = None     # SME name from knowledge graph
    agent_name: str | None = None

@dataclass
class AgentResult:
    """Universal result type returned by all agents."""
    success: bool
    data: dict[str, Any]
    confidence: float                    # 0.0 - 1.0
    reasoning: str                       # How the result was derived
    citations: list[Citation] = field(default_factory=list)
    escalation: EscalationReport | None = None
```

### 1.2 QualityAssessment

```python
@dataclass
class QualityAssessment:
    """Multi-dimension quality score for an agent output."""
    completeness: float     # 0.0 - 1.0: Is the output complete?
    accuracy: float         # 0.0 - 1.0: Are facts correct?
    relevance: float        # 0.0 - 1.0: Does it answer the question?
    recency: float          # 0.0 - 1.0: Are sources current?
    
    @property
    def overall(self) -> float:
        weights = {"completeness": 0.3, "accuracy": 0.3, "relevance": 0.25, "recency": 0.15}
        return sum(getattr(self, k) * v for k, v in weights.items())
```

---

## 2. Document & File Types

### 2.1 FileInfo

```python
@dataclass
class FileInfo:
    """Represents a file discovered on a file share."""
    path: str                    # Full path on file share
    filename: str                # Just the filename
    extension: str               # e.g., ".docx"
    size_bytes: int
    modified_time: str           # ISO 8601
    hash: str                    # SHA-256 of file contents
    doc_id: str | None = None    # Assigned after first ingestion
```

### 2.2 DocumentMetadata

```python
@dataclass
class DocumentMetadata:
    """Metadata extracted from a document during ingestion."""
    doc_id: str
    title: str
    source_path: str
    filename: str
    extension: str
    file_hash: str
    
    # From document properties
    author: str | None = None
    created_date: str | None = None
    modified_date: str | None = None
    
    # Computed
    word_count: int = 0
    page_count: int = 0
    image_count: int = 0
    chunk_count: int = 0
    
    # Classification (set by Taxonomy Agent)
    doc_type: str = "UNKNOWN"
    doc_type_confidence: float = 0.0
    tags: list[str] = field(default_factory=list)
    
    # Version tracking
    version: int = 1
    previous_version_id: str | None = None
    
    # Timestamps
    ingested_at: str | None = None
    last_reindexed_at: str | None = None
```

### 2.3 ConversionResult

```python
@dataclass
class ConversionResult:
    """Output of a document converter."""
    markdown: str                    # Full document as Markdown
    metadata: DocumentMetadata
    images: list[ExtractedImage]     # Extracted images
    headings: list[str]              # Extracted heading structure
    success: bool = True
    error: str | None = None
```

### 2.4 IngestedDocument

```python
@dataclass
class IngestedDocument:
    """Fully processed document ready for indexing."""
    doc_id: str
    title: str
    source_path: str
    extension: str
    markdown_path: str               # Path to stored .md file
    metadata: DocumentMetadata
    images: list[ExtractedImage]
    chunks: list[TextChunk]
    word_count: int
```

---

## 3. Image & Vision Types

### 3.1 ExtractedImage

```python
@dataclass
class ExtractedImage:
    """An image extracted from a document."""
    image_id: str                    # e.g., "img_001"
    doc_id: str
    filename: str                    # e.g., "img_001.png"
    saved_path: str                  # Full path to saved image file
    source_page: int | None = None   # Page/slide number in original doc
    source_context: str = ""         # Text surrounding the image
    width: int | None = None
    height: int | None = None
    format: str = "png"              # png, jpg, etc.
```

### 3.2 ImageDescription

```python
@dataclass
class ImageDescription:
    """A human-provided description of an extracted image."""
    image_id: str
    doc_id: str
    description: str                 # The textual description
    described_by: str = "maintenance_engineer"
    described_at: str | None = None  # ISO 8601
    indexed: bool = False            # True once added to vector store
```

### 3.3 ImageManifest

```python
@dataclass
class ImageManifestEntry:
    """Single entry in the image manifest."""
    image_id: str
    filename: str
    source_page: int | None
    source_context: str
    dimensions: dict[str, int] | None  # {"width": 800, "height": 600}
    status: str                        # "pending", "described", "indexed", "extraction_failed"
    description: str | None = None
    described_by: str | None = None
    described_at: str | None = None

@dataclass
class ImageManifest:
    """Manifest tracking all images for a document."""
    doc_id: str
    images: list[ImageManifestEntry]
    
    @property
    def pending_count(self) -> int:
        return sum(1 for img in self.images if img.status == "pending")
    
    @property
    def described_count(self) -> int:
        return sum(1 for img in self.images if img.status in ("described", "indexed"))
```

---

## 4. Vector Store Types

### 4.1 TextChunk

```python
@dataclass
class TextChunk:
    """A chunk of text ready for vector indexing."""
    chunk_id: str                    # "{doc_id}_chunk_{index}"
    doc_id: str
    content: str                     # The chunk text
    index: int                       # Position in document (0-based)
    
    # Metadata for filtered search
    doc_type: str = "UNKNOWN"
    source_path: str = ""
    version: int = 1
    heading: str | None = None       # Nearest heading above this chunk
    is_image_description: bool = False
    image_id: str | None = None      # If this chunk is an image description
    
    # For ChromaDB
    def to_chroma_metadata(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "chunk_index": self.index,
            "doc_type": self.doc_type,
            "source_path": self.source_path,
            "version": self.version,
            "heading": self.heading or "",
            "is_image_description": self.is_image_description,
            "image_id": self.image_id or "",
        }
```

### 4.2 SearchResult

```python
@dataclass
class SearchResult:
    """A single result from vector search."""
    chunk_id: str
    doc_id: str
    content: str
    similarity: float                # 0.0 - 1.0 (higher = more similar)
    metadata: dict
    
    # Enriched by graph
    doc_title: str | None = None
    doc_type: str | None = None
    related_tools: list[str] = field(default_factory=list)
    related_processes: list[str] = field(default_factory=list)
    author: str | None = None
    last_updated: str | None = None
    freshness_badge: str = "UNKNOWN"
```

---

## 5. Knowledge Graph Types

### 5.1 Node Types (Enum)

```python
from enum import Enum

class NodeType(str, Enum):
    TOOL = "tool"
    PROCESS = "process"
    DOCUMENT = "document"
    DOC_VERSION = "doc_version"
    IMAGE = "image"
    PERSON = "person"
    TEAM = "team"
    DOC_TYPE = "doc_type"
    TOPIC = "topic"
```

### 5.2 Edge Types (Enum)

```python
class EdgeType(str, Enum):
    USES = "uses"                    # Process → Tool
    DOCUMENTED_IN = "documented_in"  # Tool/Process → Document
    HAS_VERSION = "has_version"      # Document → DocVersion
    CONTAINS = "contains"            # Document → Image
    MENTIONS = "mentions"            # Document → Tool/Process
    AUTHORED_BY = "authored_by"      # Document → Person
    MEMBER_OF = "member_of"          # Person → Team
    HAS_RELEASE = "has_release"      # Tool → Document (release note)
    CHANGES = "changes"              # ReleaseNote → Process
    PREREQUISITE = "prerequisite"    # Process/Doc → Process/Doc
    TAGGED_AS = "tagged_as"          # Document → DocType
    COVERS_TOPIC = "covers_topic"    # Document → Topic
    SUPERSEDES = "supersedes"        # DocVersion → DocVersion
```

### 5.3 Node Attributes

```python
# Each node type has specific attributes stored in the graph

TOOL_ATTRS = {
    "name": str,            # Tool name
    "description": str,     # Brief description
    "latest_version": str,  # e.g., "5.2"
    "team": str,            # Owning team
}

PROCESS_ATTRS = {
    "name": str,
    "description": str,
    "category": str,        # e.g., "deployment", "testing", "onboarding"
}

DOCUMENT_ATTRS = {
    "doc_id": str,
    "title": str,
    "source_path": str,
    "doc_type": str,
    "version": int,
    "word_count": int,
    "image_count": int,
    "last_updated": str,
    "freshness": str,       # CURRENT, AGING, STALE, UNKNOWN
}

PERSON_ATTRS = {
    "name": str,
    "email": str,
    "role": str,
}

IMAGE_ATTRS = {
    "image_id": str,
    "filename": str,
    "description": str,
    "status": str,          # pending, described, indexed
}
```

---

## 6. Version Tracking Types

### 6.1 VersionDiff

```python
@dataclass
class VersionDiff:
    """Difference between two versions of a document."""
    doc_id: str
    old_version: int
    new_version: int
    added_sections: list[str]
    removed_sections: list[str]
    modified_sections: list[str]
    added_images: list[str]
    removed_images: list[str]
    summary: str                     # Human-readable change summary
    changed_chunk_indices: list[int] # Chunks that need re-indexing
    diff_timestamp: str              # When the diff was computed
```

### 6.2 VersionChain

```python
@dataclass
class VersionEntry:
    """Single version in a document's history."""
    version: int
    file_hash: str
    ingested_at: str
    markdown_path: str               # Path to stored version file
    metadata_path: str
    diff_path: str | None = None     # Path to diff JSON (None for v1)

@dataclass
class VersionChain:
    """Complete version history for a document."""
    doc_id: str
    current_version: int
    versions: list[VersionEntry]
```

---

## 7. Taxonomy Types

### 7.1 DocTypeEnum

```python
class DocTypeEnum(str, Enum):
    SOP = "SOP"
    USER_GUIDE = "USER_GUIDE"
    RELEASE_NOTE = "RELEASE_NOTE"
    TRAINING = "TRAINING"
    SDLC = "SDLC"
    ARCHITECTURE = "ARCHITECTURE"
    TROUBLESHOOT = "TROUBLESHOOT"
    MEETING_NOTES = "MEETING_NOTES"
    POLICY = "POLICY"
    REFERENCE = "REFERENCE"
    UNKNOWN = "UNKNOWN"
```

### 7.2 ClassificationResult

```python
@dataclass
class ClassificationResult:
    doc_type: str                    # From DocTypeEnum
    confidence: float                # 0.0 - 1.0
    reasoning: str
    matched_rules: list[str]
    needs_review: bool
```

---

## 8. Query & Response Types

### 8.1 SearchResult (Retrieval Service Output)

```python
@dataclass
class SearchResult:
    context_chunks: list[TextChunk]  # Relevant text passages for Copilot
    confidence: float
    citations: list[Citation]
    image_notes: list[str]           # Notes about images (NOT image files), e.g., "Screenshot on page 12 shows..."
    freshness: dict                  # {"current": 2, "aging": 1, "stale": 0}
    related_topics: list[str]
    escalation: EscalationReport | None = None
```

**Note**: This is returned to GitHub Copilot Chat. Copilot generates the answer, not our system.

### 8.2 TrainingPath

```python
@dataclass
class LearningStep:
    order: int
    doc_id: str
    doc_title: str
    doc_type: str
    estimated_time_minutes: int
    difficulty: str                  # "beginner", "intermediate", "advanced"
    description: str
    prerequisites: list[str]

@dataclass
class TrainingPath:
    topic: str
    level: str
    steps: list[LearningStep]
    total_time_minutes: int
    coverage: float                  # 0.0 - 1.0
```

### 8.3 ImpactReport

```python
@dataclass
class ImpactReport:
    entity: str
    entity_type: str
    direct_docs: list[dict]
    indirect_docs: list[dict]
    stale_images: list[dict]
    affected_processes: list[dict]
    affected_training: list[dict]
    recommended_actions: list[str]
    severity: str                    # "low", "medium", "high"
```

### 8.4 FreshnessReport

```python
@dataclass
class FreshnessReport:
    total_documents: int
    current: int
    aging: int
    stale: int
    unknown: int
    stale_documents: list[dict]
    stale_images: list[dict]
    recommendations: list[str]
    scan_timestamp: str
```

---

## 9. Manifest Types

### 9.1 FileManifest

```python
@dataclass
class FileManifestEntry:
    """Single file tracked in the manifest."""
    path: str
    filename: str
    extension: str
    hash: str
    doc_id: str
    last_ingested: str               # ISO 8601
    version: int
    status: str                      # "active", "deleted", "error"

@dataclass
class FileManifest:
    """Master manifest of all tracked files."""
    entries: dict[str, FileManifestEntry]  # keyed by path
    last_crawl: str | None = None
    total_files: int = 0
    
    def lookup(self, path: str) -> FileManifestEntry | None:
        return self.entries.get(path)
    
    def is_new(self, path: str) -> bool:
        return path not in self.entries
    
    def is_modified(self, path: str, current_hash: str) -> bool:
        entry = self.entries.get(path)
        return entry is not None and entry.hash != current_hash
```

---

## 10. Configuration Types

### 10.1 KTSConfig

```python
@dataclass
class KTSConfig:
    """Central configuration for the KTS system."""
    
    # File share paths to crawl
    source_paths: list[str] = field(default_factory=list)
    
    # Supported file extensions
    supported_extensions: list[str] = field(default_factory=lambda: [
        ".docx", ".pdf", ".pptx", ".htm", ".html", ".md", ".txt"
    ])
    
    # Knowledge base
    knowledge_base_path: str = "knowledge_base"
    
    # ChromaDB
    chroma_persist_dir: str = "knowledge_base/vectors"
    chroma_collection_text: str = "text_chunks"
    chroma_collection_images: str = "image_descriptions"
    
    # Graph
    graph_path: str = "knowledge_base/graph/knowledge_graph.json"
    
    # Chunking
    chunk_size: int = 1000
    chunk_overlap: int = 200
    
    # Quality gates
    confidence_high: float = 0.90
    confidence_medium: float = 0.66
    
    # Freshness
    stale_threshold_days: int = 180
    
    # Known entities (for graph builder)
    known_tools_path: str = "config/known_tools.json"
    known_processes_path: str = "config/known_processes.json"
```

---

## 11. File Relationship Map

```
KTSConfig ◄── loaded by all agents
    │
    ▼
FileManifest ◄── Crawler Agent writes, all agents read
    │
    ▼
FileInfo ──▶ Ingestion Agent
    │
    ▼
ConversionResult ──▶ IngestedDocument
    │                      │
    ├── DocumentMetadata   ├── TextChunk[] ──▶ ChromaDB
    │                      │
    └── ExtractedImage[]   └── ImageManifest ──▶ Vision Agent
                                                      │
                                              ImageDescription[] ──▶ ChromaDB
    
ClassificationResult ◄── Taxonomy Agent
    │
    ▼
Graph Builder Agent ──▶ NetworkX Graph
    │                        │
    │                   Nodes: Tool, Process, Document, Person, ...
    │                   Edges: uses, documented_in, authored_by, ...
    │
    ▼
Q&A Agent ◄── SearchResult[] from ChromaDB + graph enrichment
    │
    ▼
QAResponse (with Citations, Images, Freshness)

VersionDiff ◄── Version Agent (on document update)
TrainingPath ◄── Training Path Agent (graph traversal)
ImpactReport ◄── Change Impact Agent (graph traversal)
FreshnessReport ◄── Freshness Agent (age analysis)
```

---

*All dataclasses will be implemented in `backend/common/models.py` with proper `__post_init__` validation, JSON serialization (`to_dict()`/`from_dict()` methods), and type hints.*
