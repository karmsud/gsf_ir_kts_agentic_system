# GSF IR KTS — Agent Catalog

Detailed specification for each of the 10 agents in the KTS system integrated with GitHub Copilot Chat. Each entry defines the agent's purpose, inputs, outputs, skills, error handling, and test cases.

**Note**: There is no Conductor Agent — GitHub Copilot handles intent classification and routing.

---

## 1. Crawler Agent

| Field | Value |
|-------|-------|
| **File** | `backend/agents/crawler_agent.py` |
| **Purpose** | Scan configured file share paths, detect new/modified/deleted files |
| **Reused from ABS?** | New — ABS had manual ingestion |

### Input

```python
@dataclass
class CrawlRequest:
    paths: list[str] | None = None  # Override config paths; None = use config
    dry_run: bool = False           # Preview only, don't update manifest
    force: bool = False             # Re-process even if hash unchanged
```

### Output

```python
@dataclass
class CrawlResult:
    new_files: list[FileInfo]       # Never seen before
    modified_files: list[FileInfo]  # Hash changed since last crawl
    deleted_files: list[FileInfo]   # In manifest but no longer on disk
    unchanged_files: int            # Count of skipped files
    errors: list[dict]              # Files that couldn't be accessed

@dataclass
class FileInfo:
    path: str
    filename: str
    extension: str
    size_bytes: int
    modified_time: str
    hash: str
    doc_id: str | None  # Assigned after first ingestion
```

### Skills
- **File System Scan**: Recursive directory walking with extension filter
- **Hash Computation**: SHA-256 of file contents
- **Manifest Comparison**: Compare current scan against stored manifest
- **Change Classification**: new / modified / deleted / unchanged

### Error Handling
- Path doesn't exist → log warning, skip, continue with other paths
- Permission denied → log error, add to `errors` list
- File too large (>100MB) → skip with warning

### Test Cases
1. Empty directory → `new_files=[], modified_files=[], unchanged=0`
2. Directory with 3 new .docx files → `new_files` has 3 entries
3. Re-scan same directory → `unchanged=3, new_files=[]`
4. Modify one file → `modified_files` has 1 entry
5. Delete one file → `deleted_files` has 1 entry
6. Non-existent path → logged in `errors`

---

## 2. Ingestion Agent

| Field | Value |
|-------|-------|
| **File** | `backend/agents/ingestion_agent.py` |
| **Purpose** | Convert documents to Markdown, extract images, generate metadata |
| **Reused from ABS?** | Yes — adapted from document_converter.py |

### Input

```python
@dataclass
class IngestionRequest:
    file_info: FileInfo            # From crawler
    knowledge_base_path: str       # Where to store results
    force_reprocess: bool = False  # Override existing
```

### Output

```python
@dataclass
class IngestedDocument:
    doc_id: str
    title: str
    source_path: str
    extension: str
    markdown_path: str             # Path to generated .md file
    metadata: DocumentMetadata
    images: list[ExtractedImage]   # Extracted images with paths
    chunk_count: int               # Number of text chunks created
    word_count: int
```

### Skills
- **Format Detection**: Route to correct converter based on extension
- **Text Extraction**: Extract all text content as Markdown
- **Image Extraction**: Save all embedded images with position context
- **Metadata Extraction**: Title, author, dates, page count from document properties
- **Doc ID Generation**: Deterministic ID from source path hash

### Converter Routing

```python
CONVERTERS = {
    ".docx": DocxConverter,
    ".pdf":  PdfConverter,
    ".pptx": PptxConverter,
    ".htm":  HtmlConverter,
    ".html": HtmlConverter,
    ".md":   MarkdownPassthrough,  # Already markdown, just copy
    ".txt":  PlainTextConverter,
}
```

### Error Handling
- Unsupported extension → reject with clear error message
- Corrupt file → log error, return failed AgentResult
- Password-protected file → escalation: "File requires password"
- Empty file → skip with warning

### Test Cases
1. Valid .docx → produces Markdown + metadata + images
2. Valid .pdf with 3 images → extracts all 3 images
3. Valid .pptx with 10 slides → produces Markdown with slide separators
4. HTML from OneNote export → clean Markdown
5. Corrupt .docx → returns error result
6. Unsupported .xlsx → rejected with message

---

## 3. Vision Agent

| Field | Value |
|-------|-------|
| **File** | `backend/agents/vision_agent.py` |
| **Purpose** | Manage image description lifecycle — track pending, store descriptions, index in vector store |
| **Reused from ABS?** | **New** — ABS had no multi-modal content |

### Input (Multiple Operations)

```python
@dataclass
class VisionRequest:
    operation: str  # "list_pending" | "complete" | "status"
    doc_id: str | None = None
    descriptions: dict[str, str] | None = None  # image_id → description text
```

### Output

```python
@dataclass
class VisionResult:
    pending_count: int
    described_count: int
    pending_images: list[dict]     # Images awaiting description
    newly_indexed: list[str]       # Image IDs just indexed
```

### Skills
- **Manifest Management**: Read/write image manifests (pending_descriptions.json)
- **Status Tracking**: pending → described → indexed
- **Description Indexing**: Add image descriptions to ChromaDB vector store
- **Graph Linking**: Add Image nodes to knowledge graph with description metadata

### Human-in-the-Loop Workflow (Maintenance Engineer)

```
Step 1: Engineer runs `kts describe pending`
        → Shows list of images needing descriptions with:
           - Image path (can open in VS Code)
           - Surrounding text context
           - Suggested prompt template

Step 2: Engineer opens image, uses GitHub Models to describe it
        → Pastes description into descriptions.json (or via CLI)

Step 3: Engineer runs `kts describe complete <doc_id>`
        → Vision Agent indexes descriptions, updates manifest
```

### Error Handling
- Image file missing → log warning, mark as `extraction_failed`
- Description is empty/too short → reject, ask for more detail
- Doc ID not found → return error

### Test Cases
1. After ingestion of doc with 5 images → 5 pending entries in manifest
2. Complete 3 descriptions → 3 indexed, 2 still pending
3. Vector search for described image content → finds the chunk
4. `status` operation → correct counts

---

## 4. Taxonomy Agent

| Field | Value |
|-------|-------|
| **File** | `backend/agents/taxonomy_agent.py` |
| **Purpose** | Auto-classify documents by type (SOP, User Guide, Release Note, etc.) |
| **Reused from ABS?** | **New** — ABS had fixed section maps instead of classification |

### Input

```python
@dataclass
class ClassifyRequest:
    doc_id: str
    filename: str
    content_preview: str    # First ~500 chars of document
    metadata: dict          # Document metadata (author, dates, etc.)
```

### Output

```python
@dataclass
class ClassificationResult:
    doc_type: str           # SOP, USER_GUIDE, RELEASE_NOTE, etc.
    confidence: float       # 0.0 - 1.0
    reasoning: str          # Why this classification was chosen
    matched_rules: list[str]  # Which rules triggered
    needs_review: bool      # True if confidence < threshold
```

### Skills
- **Rule-Based Classification**: Filename patterns + content keyword patterns
- **Confidence Scoring**: Number of matching rules → confidence score
- **Review Flagging**: Low-confidence results flagged for human review

### Classification Logic

```python
def classify(self, request: ClassifyRequest) -> ClassificationResult:
    scores = {}
    for doc_type, patterns in TAXONOMY_RULES["filename_patterns"].items():
        for pattern in patterns:
            if re.search(pattern, request.filename):
                scores[doc_type] = scores.get(doc_type, 0) + 0.3
    
    for doc_type, patterns in TAXONOMY_RULES["content_patterns"].items():
        for pattern in patterns:
            if re.search(pattern, request.content_preview, re.I):
                scores[doc_type] = scores.get(doc_type, 0) + 0.15
    
    if not scores:
        return ClassificationResult(
            doc_type="UNKNOWN", confidence=0.0,
            reasoning="No rules matched", matched_rules=[],
            needs_review=True,
        )
    
    best_type = max(scores, key=scores.get)
    return ClassificationResult(
        doc_type=best_type,
        confidence=min(scores[best_type], 1.0),
        reasoning=f"Matched {len(scores)} rule(s)",
        matched_rules=[...],
        needs_review=scores[best_type] < 0.50,
    )
```

### Test Cases
1. "SOP_Deployment_Process.docx" → `SOP` (filename match)
2. "Release Notes v5.2.pdf" → `RELEASE_NOTE` (filename match)
3. Document content containing "step 1", "step 2", "prerequisite" → `SOP` (content match)
4. "meeting_notes_20260115.docx" → `MEETING_NOTES` (filename match)
5. "random_file.docx" with no matching patterns → `UNKNOWN`, `needs_review=True`

---

## 5. Version Agent

| Field | Value |
|-------|-------|
| **File** | `backend/agents/version_agent.py` |
| **Purpose** | Detect document updates, compute diffs, maintain version chains |
| **Reused from ABS?** | Yes — adapted from Amendment Agent |

### Input

```python
@dataclass
class VersionRequest:
    doc_id: str
    old_content: str        # Previous version markdown
    new_content: str        # Updated version markdown
    old_metadata: dict
    new_metadata: dict
```

### Output

```python
@dataclass
class VersionDiff:
    doc_id: str
    old_version: int
    new_version: int
    added_sections: list[str]
    removed_sections: list[str]
    modified_sections: list[str]
    added_images: list[str]      # New images in this version
    removed_images: list[str]    # Images removed in this version
    summary: str                 # Human-readable change summary
    changed_chunks: list[int]    # Indices of chunks that need re-indexing
```

### Skills
- **Section-Level Diff**: Compare documents at the heading level, not line-by-line
- **Change Summary**: Generate human-readable summary of changes
- **Selective Re-Indexing**: Only update changed chunks in vector store
- **Version Chain**: Maintain `v1 → v2 → v3` chain in graph via `SUPERSEDES` edges
- **Image Change Detection**: Detect new/removed images between versions

### Test Cases
1. Same content → `VersionDiff` with no changes
2. Added section → `added_sections` populated
3. Modified section → `modified_sections` populated, `changed_chunks` identified
4. New image added → `added_images` populated
5. Version chain → graph has v1 SUPERSEDES v2 edge

---

## 6. Graph Builder Agent

| Field | Value |
|-------|-------|
| **File** | `backend/agents/graph_builder_agent.py` |
| **Purpose** | Construct and maintain the knowledge graph from document metadata |
| **Reused from ABS?** | Yes — same NetworkX engine, different schema |

### Input

```python
@dataclass
class GraphBuildRequest:
    doc_id: str
    metadata: DocumentMetadata
    classification: ClassificationResult
    entities: list[dict]    # Extracted entity mentions (tools, processes, people)
```

### Output

```python
@dataclass
class GraphBuildResult:
    nodes_added: int
    edges_added: int
    nodes_updated: int
    total_nodes: int
    total_edges: int
```

### Skills
- **Entity Extraction**: Identify tool names, process names, people from document text
- **Node Creation**: Create properly typed nodes with metadata attributes
- **Edge Creation**: Link documents to tools, processes, authors, teams
- **Deduplication**: Merge entities that refer to the same thing (fuzzy matching)
- **Graph Stats**: Report node/edge counts by type

### Entity Extraction Strategy

```python
# Two approaches combined:
# 1. Known entities (from config): exact match against registered tools/processes
# 2. Pattern-based: capitalize words, "Tool X", "Process Y" patterns

KNOWN_TOOLS = load_from_config("known_tools.json")  # Maintained by admin
KNOWN_PROCESSES = load_from_config("known_processes.json")

def extract_entities(text: str) -> list[dict]:
    entities = []
    for tool in KNOWN_TOOLS:
        if tool.lower() in text.lower():
            entities.append({"type": "tool", "name": tool})
    for proc in KNOWN_PROCESSES:
        if proc.lower() in text.lower():
            entities.append({"type": "process", "name": proc})
    return entities
```

### Test Cases
1. Document mentioning "Tool X" → creates Tool node + `DOCUMENTED_IN` edge
2. Document with author metadata → creates Person node + `AUTHORED_BY` edge
3. Re-ingesting same doc → updates existing nodes, doesn't create duplicates
4. Graph stats → correct counts by node type

---

## 7. Retrieval Service

| Field | Value |
|-------|-------|
| **File** | `backend/agents/retrieval_service.py` |
| **Purpose** | Search knowledge base and return context + citations to GitHub Copilot Chat (does NOT generate answers) |
| **Reused from ABS?** | Yes — same RAG retrieval pattern, but answer generation removed |

### Input

```python
@dataclass
class RetrievalRequest:
    query: str                       # From Copilot Chat
    max_results: int = 5
    doc_type_filter: str | None = None  # Optionally filter by doc type
    tool_filter: str | None = None      # Optionally filter by tool
```

### Output

```python
@dataclass
class SearchResult:
    context_chunks: list[TextChunk]    # Relevant text passages with metadata
    confidence: float                  # 0.0 - 1.0  
    citations: list[Citation]          # Source references with file:// URIs
    image_notes: list[str]             # Notes about relevant images (NOT image files)
    freshness: dict                    # Freshness status of cited sources
    related_topics: list[str]          # Suggested related queries
    escalation: EscalationReport | None  # If low confidence
```

**Note**: This service returns CONTEXT for Copilot to use. It does NOT generate the answer text — that's Copilot's job.

### Skills
- **Vector Search**: Search text chunks and image descriptions in ChromaDB
- **Graph Enrichment**: For each result, get related tools/processes/SMEs from graph
- **Re-Ranking**: Score results by relevance, recency, doc type appropriateness
- **Context Assembly**: Package top chunks with metadata for Copilot
- **Citation Generation**: Attach source doc with file:// URI, version, page for every chunk
- **Image Notes**: If context involves image-described content, include note like "Screenshot on page 12 shows..."
- **Freshness Badging**: 🟢 CURRENT / 🟡 AGING / 🔴 STALE for each source

### Re-Ranking Heuristics

```python
def rerank(self, results: list[dict], query: str) -> list[dict]:
    for r in results:
        score = r["similarity"]  # Base: vector similarity
        
        # Boost recent docs
        age_days = (now() - r["last_updated"]).days
        score *= max(0.5, 1.0 - (age_days / 365))
        
        # Boost SOPs and User Guides for "how to" questions
        if "how" in query.lower() and r["doc_type"] in ("SOP", "USER_GUIDE"):
            score *= 1.2
        
        # Boost troubleshooting docs for error-related questions
        if any(w in query.lower() for w in ("error", "fail", "broken", "fix")):
            if r["doc_type"] == "TROUBLESHOOT":
                score *= 1.3
        
        r["final_score"] = score
    
    return sorted(results, key=lambda r: r["final_score"], reverse=True)
```

### Test Cases
1. Query about known topic → returns context chunks with citations
2. Query about image content → returns context with image note ("See page 12 for screenshot")
3. Very obscure query → low confidence, escalation with SME suggestion
4. Query filtered to specific tool → only returns chunks about that tool
5. Context sources include stale doc → freshness badge shows 🔴 STALE

---

## 8. Training Path Agent

| Field | Value |
|-------|-------|
| **File** | `backend/agents/training_path_agent.py` |
| **Purpose** | Generate ordered learning sequences for topics, tools, or processes |
| **Reused from ABS?** | **New** — unique to KTS |

### Input

```python
@dataclass
class TrainingRequest:
    topic: str                       # "Tool X", "deployments", "onboarding"
    level: str = "beginner"          # "beginner", "intermediate", "advanced"
    max_steps: int = 10              # Maximum steps in learning path
```

### Output

```python
@dataclass
class LearningStep:
    order: int
    doc_id: str
    doc_title: str
    doc_type: str
    estimated_time_minutes: int
    difficulty: str                  # "beginner", "intermediate", "advanced"
    description: str                 # What you'll learn
    prerequisites: list[str]         # Other steps that should come first

@dataclass
class TrainingPath:
    topic: str
    level: str
    steps: list[LearningStep]
    total_time_minutes: int
    coverage: float                  # 0.0-1.0: how much of the topic is covered
```

### Skills
- **Topic Resolution**: Map user's free-text topic to graph nodes
- **Document Discovery**: Find all docs related to the topic via graph traversal
- **Prerequisite Ordering**: Topological sort using `PREREQUISITE` edges
- **Time Estimation**: Word count / 200 words per minute ≈ reading time
- **Difficulty Assignment**: Based on prerequisite chain depth

### Test Cases
1. "I'm new to Tool X" → ordered path starting with User Guide, ending with advanced topics
2. Topic with no documents → empty path with message
3. Circular prerequisites → detected and reported (not infinite loop)
4. Level filter → beginner path excludes advanced docs

---

## 9. Change Impact Agent

| Field | Value |
|-------|-------|
| **File** | `backend/agents/change_impact_agent.py` |
| **Purpose** | Analyze what documents, processes, and training are affected by a change |
| **Reused from ABS?** | **New** — unique to KTS |

### Input

```python
@dataclass
class ImpactRequest:
    entity: str              # Tool name, process name, or document name
    entity_type: str = "auto"  # "tool", "process", "document", or "auto" (detect)
    change_description: str | None = None  # Optional: what specifically changed
```

### Output

```python
@dataclass
class ImpactReport:
    entity: str
    entity_type: str
    direct_docs: list[dict]      # Documents directly about this entity
    indirect_docs: list[dict]    # Documents about processes that use this entity
    stale_images: list[dict]     # Images that may show outdated UI
    affected_processes: list[dict]
    affected_training: list[dict]
    recommended_actions: list[str]
    severity: str                # "low", "medium", "high"
```

### Skills
- **Entity Resolution**: Find the entity node in the graph
- **Forward Traversal**: Entity → all directly linked documents
- **Transitive Traversal**: Entity → processes → documents about those processes
- **Screenshot Staleness**: Images described before the change date
- **Action Recommendations**: Prioritized list of what to update

### Test Cases
1. Tool with 5 linked docs → all 5 in `direct_docs`
2. Tool used by 3 processes → their docs in `indirect_docs`
3. Recent change → images described before change flagged as stale
4. Unknown entity → error response with suggestion

---

## 10. Freshness Agent

| Field | Value |
|-------|-------|
| **File** | `backend/agents/freshness_agent.py` |
| **Purpose** | Detect stale, outdated, or potentially inaccurate content |
| **Reused from ABS?** | **New** — unique to KTS |

### Input

```python
@dataclass
class FreshnessRequest:
    scope: str = "all"          # "all", or specific doc_type, or specific tool
    threshold_days: int = 180   # Override config default
    include_images: bool = True
```

### Output

```python
@dataclass
class FreshnessReport:
    total_documents: int
    current: int                # Updated within threshold
    aging: int                  # Between 1x and 2x threshold
    stale: int                  # Older than 2x threshold
    unknown: int                # No date metadata
    stale_documents: list[dict]  # Details of stale docs
    stale_images: list[dict]     # Images with outdated descriptions
    recommendations: list[str]
```

### Skills
- **Age Calculation**: Compare document last_updated against threshold
- **Badge Assignment**: 🟢 CURRENT / 🟡 AGING / 🔴 STALE / ⚪ UNKNOWN
- **Image Freshness**: Check if image descriptions predate tool updates
- **Report Generation**: Prioritized list of content needing review

### Test Cases
1. All docs updated yesterday → all CURRENT
2. Doc not updated in 1 year → flagged as STALE
3. Doc with no date → flagged as UNKNOWN
4. Scope filter → only checks matching docs

---

*Each agent follows the same `AgentBase` contract: receives a typed request, returns `AgentResult` with confidence scoring and optional escalation. See Data_Model.md for all shared dataclasses.*
