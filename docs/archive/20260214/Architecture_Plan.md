# GSF IR KTS — Architecture Plan

## 1. System Overview

GSF IR KTS is a **multi-agent system** integrated with GitHub Copilot Chat via a VS Code Extension. The system has 10 specialized agents (no separate conductor — Copilot handles intent classification). The system ingests heterogeneous documents from network file shares, extracts text and images, builds a searchable knowledge base, and serves both onboarding and operational support use cases through Copilot Chat.

### 1.1 High-Level Architecture

```
                    ┌──────────────────────────────┐
                    │         User Interface        │
                    │   (Streamlit UI  +  CLI)      │
                    └──────────────┬────────────────┘
                                   │
                    ┌──────────────▼────────────────┐
                    │       Conductor Agent          │
                    │  (Request Classification &     │
                    │   Pipeline Orchestration)      │
                    └──┬───┬───┬───┬───┬───┬───┬───┘
                       │   │   │   │   │   │   │
         ┌─────────────┘   │   │   │   │   │   └─────────────┐
         │                 │   │   │   │   │                  │
    ┌────▼────┐      ┌────▼───▼┐  │  ┌▼───▼────┐       ┌────▼────┐
    │ Crawler │      │Ingestion│  │  │  Graph   │       │Freshness│
    │  Agent  │      │ Agent   │  │  │ Builder  │       │  Agent  │
    └────┬────┘      └────┬────┘  │  └────┬─────┘       └─────────┘
         │                │       │       │
         │           ┌────▼────┐  │  ┌────▼─────┐
         │           │ Vision  │  │  │   Q&A    │
         │           │  Agent  │  │  │  Agent   │
         │           └─────────┘  │  └──────────┘
         │                        │
    ┌────▼─────────┐         ┌───▼──────────┐
    │   Taxonomy   │         │   Version    │
    │    Agent     │         │    Agent     │
    └──────────────┘         └──────────────┘
                                  
              ┌──────────────┐  ┌──────────────┐
              │Training Path │  │Change Impact │
              │    Agent     │  │    Agent     │
              └──────────────┘  └──────────────┘
```

### 1.2 Data Flow — Ingestion Pipeline

```
Network File Share(s)
    │
    ▼
[Crawler Agent] ─── scans paths, computes hashes ───▶ manifest.json
    │                                                    │
    │  new/changed files detected                        │ known files
    ▼                                                    ▼
[Ingestion Agent] ─── extracts text + images            (skip)
    │
    ├── text ──▶ Markdown (.md) ──▶ [Taxonomy Agent] ──▶ tagged metadata
    │                                                         │
    │                                                    ┌────▼────────┐
    │                                                    │ Vector Store │
    │                                                    │  (ChromaDB)  │
    │                                                    └─────────────┘
    │
    └── images ──▶ assets/{doc_id}/img_NNN.png
                        │
                   pending_descriptions.json
                        │
                   [Vision Agent] ◄── Maintenance Engineer
                        │               (GitHub Models)
                        ▼
                   descriptions.json ──▶ Vector Store
                                    ──▶ [Graph Builder] ──▶ Knowledge Graph
```

### 1.3 Data Flow — Query Pipeline

```
User Question in Copilot Chat
    │
    ▼
[GitHub Copilot] ─── classifies intent, calls @kts tool
    │
    ├── QUESTION ──▶ [Retrieval Service]
    │                   │
    │                   ├── Vector search (text + image descriptions)
    │                   ├── Graph traversal (related docs, tools, processes)
    │                   ├── Re-rank results by relevance
    │                   └── Return context + citations to Copilot
    │                       │
    │                       ▼
    │                   [Copilot's LLM generates answer using context]
    │
    ├── TRAINING ──▶ [Training Path Agent]
    │                   │
    │                   ├── Graph query: find topic-related documents
    │                   ├── Follow prerequisite edges
    │                   ├── Order by difficulty / dependency
    │                   └── Return structured learning path
    │
    ├── IMPACT ──▶ [Change Impact Agent]
    │                   │
    │                   ├── Graph query: tool/process → all dependent docs
    │                   ├── Check document freshness
    │                   └── Return impact report
    │
    └── AUDIT ──▶ [Freshness Agent]
                    │
                    ├── Scan all documents for staleness indicators
                    ├── Check for broken image references
                    ├── Cross-reference with latest tool versions
                    └── Return freshness report
```

---

## 2. Component Architecture

### 2.1 Agent Framework (Reused from ABS)

All agents inherit from `AgentBase` and return `AgentResult`:

```python
@dataclass
class AgentResult:
    success: bool
    data: dict
    confidence: float        # 0.0 - 1.0
    reasoning: str           # Explanation of how result was derived
    citations: list[dict]    # Source documents referenced
    escalation: dict | None  # If confidence < threshold

class AgentBase(ABC):
    agent_name: str
    agent_version: str

    @abstractmethod
    def execute(self, request: dict) -> AgentResult:
        ...

    def quality_check(self, result: AgentResult) -> AgentResult:
        """Standard quality gate — reused from ABS playbook."""
        ...
```

### 2.2 Storage Layer

```
┌─────────────────────────────────────────────────┐
│                  Storage Layer                   │
├─────────────────┬───────────────────────────────┤
│  Vector Store   │    Knowledge Graph            │
│  (ChromaDB)     │    (NetworkX → JSON)          │
│                 │                               │
│  Collections:   │    Node Types:                │
│  - text_chunks  │    - Tool, Process, Document, │
│  - image_descs  │      DocVersion, Image,       │
│                 │      Person, Team, DocType,    │
│  Metadata per   │      Topic                    │
│  chunk:         │                               │
│  - doc_id       │    Edge Types:                │
│  - doc_type     │    - uses, documented_in,     │
│  - source_path  │      has_version, contains,   │
│  - version      │      mentions, authored_by,   │
│  - chunk_index  │      member_of, has_release,  │
│  - is_image_desc│      changes, prerequisite,   │
│  - image_path   │      tagged_as, covers_topic, │
│                 │      supersedes               │
├─────────────────┴───────────────────────────────┤
│                  File System                     │
│  knowledge_base/                                │
│  ├── manifest.json     (crawler state)          │
│  ├── documents/{doc_id}/                        │
│  │   ├── content.md    (extracted text)         │
│  │   ├── metadata.json (tags, dates, author)    │
│  │   ├── images/       (extracted images)       │
│  │   ├── descriptions.json (image descriptions) │
│  │   └── versions/     (version history)        │
│  ├── vectors/chroma.sqlite3                     │
│  └── graph/knowledge_graph.json                 │
└─────────────────────────────────────────────────┘
```

### 2.3 Configuration Layer

```python
# config/settings.py

@dataclass
class KTSConfig:
    """Central configuration for the KTS system."""
    
    # File share paths to crawl
    source_paths: list[str]
    
    # Supported file extensions
    supported_extensions: list[str] = field(default_factory=lambda: [
        ".docx", ".pdf", ".pptx", ".htm", ".html", ".md", ".txt"
    ])
    
    # Knowledge base root directory
    knowledge_base_path: str = "knowledge_base"
    
    # ChromaDB settings
    chroma_persist_dir: str = "knowledge_base/vectors"
    chroma_collection_text: str = "text_chunks"
    chroma_collection_images: str = "image_descriptions"
    
    # Graph settings
    graph_path: str = "knowledge_base/graph/knowledge_graph.json"
    
    # Chunking settings
    chunk_size: int = 1000       # characters per chunk
    chunk_overlap: int = 200     # overlap between chunks
    
    # Quality gate thresholds (reused from ABS playbook)
    confidence_high: float = 0.90
    confidence_medium: float = 0.66
    
    # Freshness settings
    stale_threshold_days: int = 180  # flag docs older than 6 months
```

---

## 3. Cross-Domain Linking (The Inverted Scope Model)

### 3.1 ABS vs KTS Scoping

```
ABS Waterfall AI                    GSF IR KTS
─────────────────                   ─────────────
Deal A ──┐                          Tool X ──────┐
         │ ISOLATED                               ├── Process A ──┐
Deal B ──┘                          Tool Y ──┐    │               │
                                             ├────┘               │
Cross-deal = BAD                    Tool Z ──┘                    │
                                                                  │
                                    Doc 1 ◄───────────────────────┘
                                    Doc 2 ◄── spans multiple tools
                                    Doc 3 ◄── and processes
                                    
                                    Cross-domain = THE VALUE
```

### 3.2 How Cross-Linking Works

The knowledge graph enables cross-domain queries:

```python
# "What docs are affected if Tool X changes?"
def get_impact(graph, tool_name: str) -> list[dict]:
    tool_node = find_node(graph, type="tool", name=tool_name)
    
    # Direct: docs that mention this tool
    direct_docs = graph.neighbors(tool_node, edge_type="documented_in")
    
    # Indirect: processes that use this tool → docs about those processes
    processes = graph.neighbors(tool_node, edge_type="uses", reverse=True)
    indirect_docs = []
    for proc in processes:
        indirect_docs.extend(
            graph.neighbors(proc, edge_type="documented_in")
        )
    
    # Training: docs tagged as "training" that cover affected topics
    all_affected = set(direct_docs + indirect_docs)
    training_docs = [d for d in all_affected 
                     if graph.node_attr(d, "doc_type") == "training"]
    
    return {
        "direct_docs": direct_docs,
        "indirect_docs": indirect_docs,
        "training_to_update": training_docs,
    }
```

---

## 4. Multi-Modal Architecture

### 4.1 Image Extraction Pipeline

```python
# Per-format image extraction strategy

EXTRACTION_STRATEGY = {
    ".docx": "python-docx — extract embedded images from document.part.rels",
    ".pdf":  "PyMuPDF — extract images per page with position metadata",
    ".pptx": "python-pptx — extract images from slide shapes",
    ".html": "BeautifulSoup — extract <img> tags, download src files",
}
```

### 4.2 Image Manifest Structure

```json
{
  "doc_id": "doc_abc123",
  "images": [
    {
      "image_id": "img_001",
      "filename": "img_001.png",
      "source_page": 5,
      "source_context": "Text immediately surrounding the image...",
      "dimensions": {"width": 800, "height": 600},
      "status": "pending",
      "description": null,
      "described_by": null,
      "described_at": null
    },
    {
      "image_id": "img_002",
      "filename": "img_002.png",
      "source_page": 12,
      "source_context": "Step 3: Click the Settings button...",
      "dimensions": {"width": 1024, "height": 768},
      "status": "described",
      "description": "Screenshot of the Settings dialog in Tool X. The Security tab is selected. The 'Reset Password' button is highlighted in the bottom-right corner. Current user shown as 'jsmith'.",
      "described_by": "maintenance_engineer",
      "described_at": "2026-02-10T14:30:00Z"
    }
  ],
  "summary": {
    "total": 2,
    "pending": 1,
    "described": 1
  }
}
```

### 4.3 Maintenance Engineer Prompt Template

```markdown
# Image Description Template — GSF IR KTS

## Instructions
You are describing a screenshot/image extracted from a knowledge document.
Your description will be indexed for search. Be thorough and specific.

## Required Elements
1. **What type of image** — screenshot, diagram, flowchart, table, photo
2. **Application/tool shown** — name the tool, version if visible
3. **UI elements visible** — menus, buttons, tabs, fields, dialogs
4. **Text visible in image** — read ALL text: labels, error messages, data values
5. **What action is being shown** — what step in a process this represents
6. **Context clues** — browser URL, window title, status indicators

## Format
Write 2-5 sentences. Start with the image type, then describe content.

## Example
"Screenshot of the Jenkins CI/CD dashboard showing the 'Production Deploy' 
pipeline. Three stages are visible: Build (green/passed), Test (green/passed), 
and Deploy (yellow/in-progress). The current build number is #1247. The 
sidebar shows 5 previous builds, all green. URL bar shows 
jenkins.internal.gsf.com/job/prod-deploy."
```

---

## 5. Quality Assurance Architecture

### 5.1 Quality Gates (Reused from ABS)

```
Agent Output (Retrieval Service returns context to Copilot)
    │
    ▼
Quality Gate
    │
    ├── confidence ≥ 0.90 ──▶ AUTO-ACCEPT, return to Copilot
    │                          Copilot generates confident answer
    │
    ├── 0.66 ≤ confidence < 0.90 ──▶ ACCEPT WITH CAVEAT
    │                                  Pass caveat to Copilot:
    │                                  "Relevant information found but
    │                                   not fully confident. Consider
    │                                   confirming with: [SME name from graph]"
    │
    └── confidence < 0.66 ──▶ ESCALATE
                               Pass escalation to Copilot:
                               "Insufficient information to answer
                                reliably. Recommend contacting:
                                [SME name from graph, based on doc authorship]"
```

### 5.2 Citation Requirements

Every retrieval response MUST include:
- Source document name and path (file:// URI for VS Code to open)
- Version number
- Page/section reference
- Last updated date
- If context includes image-described content: note about image location (e.g., "see page 12 for screenshot")

**Note**: Images are NOT returned inline. Citations link to source documents where users can see images in full context.

```python
@dataclass
class Citation:
    doc_id: str
    doc_name: str
    source_path: str              # file:// URI
    version: int
    section: str | None
    page: int | None
    last_updated: str
    image_note: str | None        # "Screenshot on page 12 shows..." (not the image file itself)
```

### 5.3 Freshness Indicators

Every answer includes a freshness badge:

| Badge | Meaning | Criteria |
|-------|---------|----------|
| 🟢 CURRENT | Document recently verified | Updated within `stale_threshold_days` |
| 🟡 AGING | May be outdated | Between 1x and 2x `stale_threshold_days` |
| 🔴 STALE | Likely outdated | Older than 2x `stale_threshold_days` |
| ⚪ UNKNOWN | No update date available | Metadata missing |

---

## 6. Security & Access Considerations

| Concern | Approach |
|---------|----------|
| File share permissions | KTS reads files using the service account's permissions — same files users can already access |
| No sensitive data reversible from vector store | Embeddings are numerical vectors, not reversible to original text. But chunk text IS stored — ensure file shares don't contain restricted content |
| No external API calls for Q&A | GitHub Copilot Chat uses its built-in LLM models. No OpenAI/Anthropic API keys needed for answering questions. |
| Image descriptions via GitHub Models | Human-in-the-loop workflow uses GitHub Models (free via VS Code) — no API keys or external services required |
| All processing local/on-premises | ChromaDB is local SQLite. NetworkX is local JSON. Everything runs on-premises. |
| Audit trail | All ingestion actions logged with timestamps, source paths, and operator |

---

## 7. Deployment Model

```
Phase 1: Single-machine deployment
──────────────────────────────────
Developer laptop / shared VM
├── Python virtual environment
├── ChromaDB (local SQLite)
├── NetworkX graph (local JSON)
├── VS Code with KTS Extension installed
├── GitHub Copilot Chat (user interface for Q&A)
└── CLI for maintenance tasks (crawl, ingest, describe images)

Phase 2 (Future): Shared deployment
────────────────────────────────────
Shared server / VM
├── VS Code Extension points to shared backend
├── Scheduled crawler (cron / Task Scheduler)
├── Persistent storage on network share
└── Optional: ChromaDB client-server mode

Admin Interface Access:
─────────────────────────
- Command Palette: KTS: Crawl & Ingest, View Status, Describe Images, etc.
- Image Description Panel: Custom VS Code webview panel for human-in-the-loop vision
- On-demand Status Documents: Markdown reports generated via command
- CLI: Power-user scripts for batch operations
```

---

*Next: See System_Design.md for detailed agent specifications, Data_Model.md for all data structures, and Implementation_Plan.md for the build sequence.*
