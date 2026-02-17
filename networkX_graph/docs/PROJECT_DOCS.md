# Project Documentation — GraphRAG (Team 6)

## Table of contents
- Executive summary
- Functional requirements
- Business requirements
- Technical requirements
- Architecture overview (plain-language)
- Technology stack summary
- Source file responsibilities
- RAG Chatbot process flow
- How to run locally (commands & usage)
- How to generate extraction JSON from .txt files
- Limitations, assumptions & recommended next steps
- Appendix — item JSON schema

---

## Executive summary
This repository implements a lightweight, local "GraphRAG" retrieval system with a Streamlit web UI. The system:
- Extracts rules and definitions from plain-text legal/contract documents.
- Builds an in-memory directed graph linking Document → Section → Item (Rule / Definition).
- Retrieves relevant rules/definitions for a user question using a content + graph-based algorithm (GraphRAG).
- Optionally invokes an LLM (OpenAI) to synthesize a fluent answer from retrieved context.

This document is written for both business stakeholders and technical teams to understand what the system does, why it matters, and how to run / maintain it.

---

## Functional requirements
- Accept a JSON payload of extracted items (array of objects) or produce that JSON from source .txt files using the provided extractor.
- Parse and index legal text into items classified as "Rule" or "Definition", preserving section metadata.
- Build a directed graph representing document structure and relations between items.
- Allow end-users to submit a natural-language question and get a ranked list of supporting rules/definitions.
- Optionally synthesize an answer using an LLM (OpenAI) from the retrieved context.
- Export graph node and edge data as downloadable JSON (nodes.json, edges.json).
- Provide UI controls for retrieval tuning (Top-K, hops, PageRank alpha) and document restriction.

---

## Business requirements
- Decision support: Enable legal/compliance/deal teams to quickly locate authoritative clauses and rules relevant to questions.
- Auditability: Provide exact source text and metadata to support traceability and audit.
- Lightweight local operation: Run without external DB or index infrastructure; useful in secure or demo contexts.
- Cost control: Default extractive retrieval is deterministic and cost-free; using an LLM is optional and billable.
- Use cases:
  - Pre-deal diligence (e.g., "What must Trustee establish on Closing Date?")
  - Compliance checks and regulatory obligations extraction
  - Contract knowledge discovery and indexing

---

## Technical requirements
- Python 3.9+ (repository venv indicates Python 3.12 used here).
- Libraries (core and optional):
  - streamlit (UI)
  - networkx (graph + PageRank)
  - rapidfuzz (optional; fuzzy matching)
  - openai (optional; LLM)
  - numpy (optional)
- Input formats:
  - Extraction consumes .txt files in txts/ (naming examples present in repository).
  - Streamlit accepts a JSON upload with item schema (see appendix).
- Data handling:
  - Graphs and indices are in-memory; suitable for small-to-medium corpora.
  - Enabling OpenAI sends context externally — observe data privacy and compliance.
- Operational constraints:
  - Not optimized for very large corpora without persistent stores or precomputed indices.

---

## Architecture overview (plain-language)
1. Ingest: The system accepts either plain-text contract files or pre-extracted JSON containing sentence-level items.
2. Extract: Sentences that look like "rules" (contain tokens such as shall, must) or "definitions" (contain means / is defined as) are extracted from text and stored as items with metadata (document id, section heading/index, item index).
3. Build graph: Items are organized into a hierarchical directed graph: Document nodes → Section nodes → Item nodes. Optionally create Rule→Definition REFERENCES edges when rules mention defined terms.
4. Retrieve: For a user query, perform tokenization and scoring (TF-IDF–like), select seed nodes (or use fuzzy fallback), expand via graph hops, run personalized PageRank, and combine content + PageRank scores to rank items.
5. Answer: Present extractive supporting items to the user or optionally pass retrieved items to an LLM for synthesis.
6. UI: Streamlit provides a single-page interface for upload / path selection, retrieval tuning, and downloads.

---

## Technology stack summary
- Python: Implementation language for scripts and UI.
- Streamlit: Interactive web UI for rapid demos.
- NetworkX: Graph representation and algorithms (PageRank).
- rapidfuzz: Optional fast fuzzy string matching for fallback retrieval.
- openai: Optional LLM integration for answer synthesis.
- Rationale: Simple, explainable, and fast to prototype locally with minimal infrastructure.

---

## Source file responsibilities (quick mapping)
- extract_def_rules_with_sections.py
  - Extracts rules and definitions from .txt files (txts/ directory).
  - Outputs JSON (azure_search_upload.json by default).
- app.py
  - Streamlit UI; loads items, builds graph, runs retrieval (graphrag_retrieve), optional OpenAI summarization.
- showTime.py
  - Utility example script that prints the current time in multiple formats.
- azure_search_upload.json
  - Example/test JSON produced by the extractor.
- README.md
  - Repo-level guidance and GitLab template text.

---

## RAG Chatbot process flow (detailed)
This section documents the GraphRAG pipeline step-by-step.

1. Data ingestion
   - Option A: Run the extractor on .txt files in txts/ to produce an items JSON (azure_search_upload.json).
   - Option B: Upload an items JSON via the Streamlit UI.

2. Item normalization & graph construction
   - Each item is normalized (whitespace, default fields).
   - Graph nodes:
     - Document node: `doc::DocumentID`
     - Section node: `sec::DocumentID::SectionIndex`
     - Item nodes: unique stable id per item
   - Graph edges:
     - Document → Section: `CONTAINS`
     - Section → Item: `HAS_RULE` / `HAS_DEFINITION`
     - Section → next Section: `NEXT` (ordering)
     - Rule → Definition: `REFERENCES` (when term mention detected)

3. Indexing & scoring (content-based)
   - Tokenize text into lowercase alphanumeric tokens (length > 1).
   - Build inverted index capturing token presence per node and compute an idf-like weight: idf = log((N+1)/(df+1)) + 1.
   - Score nodes by sum(idf for overlapping query tokens), with a small boost for Rule/Definition types.

4. Seed selection & fallback
   - If content overlap yields no seeds, fallback to fuzzy similarity using rapidfuzz (or difflib if rapidfuzz is missing) to pick candidate seeds.

5. Graph expansion (hops)
   - Expand the node set by including predecessor/successor neighbors of seed nodes for N hops (configurable).

6. Personalized PageRank
   - Run PageRank over the subgraph with personalization weights derived from seed scores to prioritize nodes central to the seed context.

7. Combined ranking
   - Combine content-based base score and PageRank score (weighted mix), apply a type boost for Rule/Definition, and produce a top-K ranking.

8. Answer generation
   - Default: Extractive listing of supporting items with context.
   - Optional LLM: Send the retrieved items as context to an OpenAI chat completion with instructions to answer strictly from the provided context.

---

## How to run locally (commands & usage)
Prerequisites:
- Python 3.9+ and pip. Use a venv for isolation.

Quick-run (developer steps)
1. Create and activate a virtual environment (recommended):
   - Windows:
     - python -m venv venv
     - venv\Scripts\activate
   - macOS / Linux:
     - python -m venv venv
     - source venv/bin/activate

2. Install dependencies (example):
   - pip install streamlit networkx rapidfuzz openai

   Note: rapidfuzz and openai are optional. The app will run without them, but fuzzy matching and the LLM flow will be limited.

3. Run the Streamlit UI:
   - streamlit run app.py

4. In the UI:
   - Upload the JSON (azure_search_upload.json) or enter a path to a JSON file.
   - Set retrieval parameters (Top-K, Hops, PageRank alpha).
   - Optionally enable "Use OpenAI LLM" and paste an API key (session-only).

---

## How to generate the extraction JSON from .txt files
1. Place .txt contract files in the `txts/` directory. Typical naming patterns used in this repo:
   - `*-Definitions.txt` (definition lists)
   - `*-Waterfall.txt` (sectioned rules)
2. Run the extractor:
   - python extract_def_rules_with_sections.py --output-json azure_search_upload.json
3. The extractor will parse sections, extract candidate rules/definitions, and write `azure_search_upload.json`.

---

## Limitations, assumptions & recommended next steps
Limitations & assumptions
- Extraction is heuristic-based and may miss or misclassify some sentences.
- No dense vector retrieval; the system relies on token overlap + fuzzy matching + graph signals. This is explainable but may underperform with paraphrased queries.
- In-memory NetworkX graphs are not optimized for very large datasets.
- Enabling OpenAI sends data externally — ensure compliance with policies.

Recommended next steps
- Add `requirements.txt` or `pyproject.toml` with pinned dependency versions for reproducible installs.
- Add unit tests for extraction, graph building, and retrieval.
- Add embedding-based retrieval (OpenAI or local models) for paraphrase robustness and hybrid retrieval.
- Add logging, monitoring, upload size limits, and secure OpenAI key handling (server-managed secrets).
- Add example queries, UI screenshots, and a small sample dataset for demos.

---

## Appendix — item JSON schema
Each item in the extraction JSON is an object with:
- `id` (string) — stable unique ID
- `type` (string) — "Rule" or "Definition"
- `text` (string) — extracted sentence
- `document_id` (string) — source identifier (filename)
- `section_heading` (string) — heading text for the section
- `section_number` (string|null) — parsed section number (if available)
- `section_index` (int) — 0-based index of section within document
- `item_index` (int) — 0-based index of item within the section

---

If you want, I can now:
- Write this documentation as separate files (e.g., `docs/PROJECT_DOCS.md` and `docs/RAG_PROCESS.md`), or
- Add a `requirements.txt` with recommended dependency pins, or
- Create both documentation files and a `requirements.txt`.

Reply with which files you'd like created and I'll write them into the repository.
