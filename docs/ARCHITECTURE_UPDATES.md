# Architecture Updates Summary — VS Code Extension + Copilot Integration

**Date**: February 13, 2026

## Critical Architectural Pivot

**OLD DESIGN**: Standalone system with Streamlit UI + Conductor Agent + Q&A Agent generates answers via LLM API calls

**NEW DESIGN**: VS Code Extension + GitHub Copilot Chat integration + Retrieval Service returns context (Copilot generates answers)

---

## Key Changes

### 1. No Conductor Agent
- **Reason**: GitHub Copilot handles intent classification
- **Impact**: Remove `backend/conductor.py`, agent count goes from 11 → 10
- **Files affected**: All documentation, implementation plan, agent catalog

### 2. No Streamlit UI
- **Reason**: GitHub Copilot Chat is the user interface for Q&A
- **Impact**: Remove entire `apps/streamlit/` folder
- **Replacement**: VS Code Extension with Command Palette + custom panels

### 3. Q&A Agent → Retrieval Service
- **Reason**: Our system provides CONTEXT, Copilot's LLM generates ANSWERS
- **rename**: `agents/qa_agent.py` → `agents/retrieval_service.py`
- **Changes**:
  - Remove LLM API calls (no OpenAI/Anthropic keys needed)
  - Return `SearchResult` with context chunks + citations
  - Do NOT generate answer text
  - Do NOT return inline images
  - Return image notes like "Screenshot on page 12 shows..."

### 4. VS Code Extension (NEW)
- **Location**: `extension/` folder
- **Components**:
  - `package.json` — Extension manifest
  - `extension.js` — Entry point
  - `commands/` — Command Palette actions (Crawl, Status, Training, Impact, Audit)
  - `panels/` — Custom webview panels (Image Description workflow, Status reports)
  - `copilot/kts_tool.js` — @kts tool registration for Copilot Chat

### 5. User Interfaces

| Interface | Purpose | Users |
|-----------|---------|-------|
| **GitHub Copilot Chat** | Q&A only | All users |
| **Command Palette** | Quick admin actions | Maintenance Engineer |
| **Custom Panels** | Image description workflow, Status reports | Maintenance Engineer |
| **CLI** | Automation scripts, batch operations | Power users |

### 6. Multi-Modal Strategy (Simplified)
- **Extract images** from docs during ingest
- **Describe images** via human-in-the-loop (GitHub Models)
- **Index descriptions** for vector search
- **DO NOT return images** in chat responses
- **Return citations** with notes: "See page 12 for screenshot"
- **User clicks citation** → VS Code opens source doc at that page → user sees image in full context

### 7. User Screenshot Support
- **User uploads screenshot to Copilot Chat** → Copilot's built-in vision reads it
- **Copilot extracts context** from screenshot (error message, UI elements, etc.)
- **Copilot searches KTS** knowledge base with enriched query
- **KTS returns relevant context** → Copilot generates answer
- **Division of labor**: Copilot handles user-facing vision, KTS handles knowledge retrieval

### 8. No External API Keys for Q&A
- **GitHub Copilot** uses its built-in LLM (user already has Copilot subscription)
- **Image descriptions** use GitHub Models (free via VS Code, no API key)
- **Zero cost** for answering questions
- **On-premises** — ChromaDB local, NetworkX local, no cloud services

---

## Updated File Counts

| Category | Old Count | New Count | Change |
|----------|-----------|-----------|--------|
| Agents | 11 | 10 | Removed Conductor |
| Test files | 12 | 11 | Removed `test_conductor.py` |
| Prompt templates | 5 | 3 | Removed `intent_classification.md`, `qa_system.md` |
| UI code files | 5 (Streamlit) | ~8 (VS Code Extension) | Complete replacement |
| **Total files** | ~87 | ~85 | Net reduction |

---

## Documentation Files Needing Updates

All 7 documentation files need revisions to reflect this architecture:

1. **Executive_Summary.md** ✅ UPDATED
   - Changed "11-agent system" → "10-agent system"
   - Updated user interface from Streamlit → Copilot Chat
   - Clarified no API keys needed for Q&A
   - Updated technology stack table

2. **Architecture_Plan.md** ✅ PARTIALLY UPDATED
   - Updated system overview text
   - Updated query pipeline (removed Conductor, Copilot classifies intent)
   - Updated quality gates (context passed to Copilot)
   - Updated citation requirements (no inline images)
   - Updated deployment model (VS Code Extension)
   - Updated security section (zero API keys)
   - **Still needs**: Section 1.1 diagram update (ASCII art)

3. **System_Design.md** ⏳ IN PROGRESS
   - Need to update project structure (remove Streamlit, add Extension)
   - Need to update agent interaction patterns
   - Need to update all references to Conductor Agent
   - Need to update Q&A pipeline description
   - Need to add VS Code Extension design details

4. **Implementation_Plan.md** ⏳ PENDING
   - Phase 0: Remove Streamlit dependencies, add VS Code Extension SDK
   - Phase 8: Replace "Streamlit UI" with "VS Code Extension + Panels"
   - Update file counts per phase
   - Update Q&A Agent tasks → Retrieval Service tasks

5. **Agent_Catalog.md** ⏳ PENDING
   - Remove Conductor Agent specification (11 → 10 agents)
   - Update Q&A Agent → Retrieval Service
     - Remove "Generate answer" from responsibilities
     - Change outputs: Remove `answer: str`, focus on `SearchResult`
     - Update all test cases
   - Update Training Path/Impact/Freshness agents to clarify they can be called via:
     - Command Palette commands
     - @kts slash commands in Copilot
     - Natural language queries in Copilot

6. **Data_Model.md** ⏳ PENDING
   - Update `QAResponse` dataclass:
     - Remove `answer: str` field
     - Rename to `SearchResult`
     - Focus on `context_chunks` and `citations`
   - Update `Citation` dataclass:
     - Change `image_ref` → `image_note`
     - Add `uri: str` for file:// URIs (VS Code clickable)

7. **Reuse_Map.md** ⏳ PENDING
   - Update "What's 100% NEW" section to include VS Code Extension
   - Update reuse percentages (likely increases reuse since we removed Streamlit and Conductor)
   - Update code copy candidates from ABS

---

## Implementation Phase Updates

### Phase 0: Scaffold (Updated)
**Add**:
- `extension/package.json` — VS Code Extension manifest
- `extension/extension.js` — Entry point

**Remove**:
- Streamlit from `requirements.txt`

**Keep**:
- All existing Python dependencies

### Phase 8: User Interfaces (Completely Revised)
**OLD**: Build Streamlit UI with 4 panels (Q&A, Training, Admin, Impact)

**NEW**: Build VS Code Extension with:
- Command Palette commands (5-6 commands)
- Custom webview panel for image description workflow
- Copilot tool registration (`@kts` command)
- Status document generator (Markdown report)

---

## Next Steps

1. ✅ Executive_Summary.md — **COMPLETED**
2. ⏳ Complete Architecture_Plan.md (section 1.1 diagram)
3. ⏳ Update System_Design.md (project structure, agent patterns)
4. ⏳ Update Implementation_Plan.md (phases, file lists)
5. ⏳ Update Agent_Catalog.md (remove Conductor, update Retrieval Service)
6. ⏳ Update Data_Model.md (SearchResult, Citation updates)
7. ⏳ Review Reuse_Map.md for VS Code Extension reuse notes

---

## Validation Checklist

Before beginning implementation, verify all docs reflect:

- [ ] 10 agents (not 11)
- [ ] No Conductor Agent
- [ ] No Streamlit UI
- [ ] VS Code Extension + Copilot Chat
- [ ] Retrieval Service (not Q&A Agent with answer generation)
- [ ] No inline image rendering (citations link to source docs)
- [ ] Zero API keys needed for Q&A
- [ ] Copilot's vision handles user screenshots
- [ ] GitHub Models (free) for image descriptions
- [ ] Command Palette + custom panels for admin
- [ ] CLI for automation

---

*End of Architecture Updates Summary*
