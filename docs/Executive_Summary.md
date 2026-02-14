# GSF IR KTS Agentic System — Executive Summary

## What Is This?

**GSF IR KTS** (Knowledge, Training & Support) is an AI-powered agentic system that transforms scattered institutional knowledge — buried in Word documents, PDFs, PowerPoints, OneNote exports, SDLC artifacts, and process guides — into a searchable, version-tracked, interconnected knowledge base that serves both **new hire onboarding** and **daily operational support**.

## The Problem

| Pain Point | Impact |
|-----------|--------|
| Knowledge is scattered across network file shares in 100s of documents | Users can't find what they need quickly |
| Documents contain critical screenshots, annotated UIs, and visual walkthroughs | Text-only search misses image-based knowledge |
| When tools get updated, no one knows which training/process docs are stale | Users follow outdated procedures |
| New hires have no structured learning path | Onboarding is slow and inconsistent |
| Institutional knowledge lives in people's heads, not in searchable systems | Knowledge loss when people transition roles |

## The Solution

A **VS Code Extension + 10-agent system** that integrates with **GitHub Copilot Chat** to provide:

1. **Crawls** network file shares and detects new or changed documents
2. **Ingests** Word, PDF, PowerPoint, and exported OneNote files — extracting both text and images
3. **Describes images** (screenshots, UI walkthroughs, error dialogs) using a human-in-the-loop vision workflow via GitHub Models
4. **Auto-classifies** documents by type (SOP, User Guide, Release Note, Training Deck, etc.)
5. **Tracks versions** — when a document is updated, the system detects the change, diffs it, and updates the knowledge base
6. **Builds a knowledge graph** linking Tools → Processes → Documents → People → Teams
7. **Enables natural language Q&A** — Copilot Chat calls our retrieval service to search the knowledge base and provide context with citations
8. **Generates training paths** for new hires based on topic dependencies
9. **Analyzes change impact** — "Tool X just got updated, what docs/training are affected?"
10. **Detects stale content** — flags documents that haven't been updated, reference deprecated tools, or have broken image references

**Key architectural decision**: Questions are answered by **GitHub Copilot's LLM** using knowledge retrieved from our system. No external API keys needed for Q&A.

## Who Uses It?

| User Role | How They Use KTS |
|-----------|-----------------|
| **New hires** | Ask in Copilot Chat: "I'm new to Tool X — give me a learning path" → structured sequence of docs |
| **Experienced staff** | Ask in Copilot Chat (with or without screenshot): "How do I fix connection timeout in Tool X?" → answer with citations to open source docs |
| **Team leads** | Use `@kts /impact Tool X` in Copilot or Command Palette → Change Impact report |
| **KTS Maintenance Engineer** | Uses Command Palette + Image Description Panel to describe images, review classifications, trigger ingestion, run audits |

## Technology Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Language | Python 3.11+ | Consistent with ABS Waterfall AI project |
| Vector Store | ChromaDB (local, persistent) | Free, no server required, default embeddings |
| Knowledge Graph | NetworkX (persistent JSON) | Free, no server required, proven in ABS project |
| Document Conversion | python-docx, PyMuPDF, python-pptx, markdownify | One library per format |
| Vision for Image Descriptions | GitHub Models (Claude, GPT-4o, etc. via VS Code) | No API key needed, premium model access, human-in-the-loop |
| User Interface | **GitHub Copilot Chat** (via VS Code Extension) | Already in users' workflow, native vision support, conversational |
| Admin Interface | VS Code Extension (Command Palette + Custom Panels) | Integrated admin experience |
| CLI | Click or argparse | Power user workflows, automation |

## What We're Reusing from ABS Waterfall AI

~60-70% of the system design is conceptually reused from the ABS project:

- **Agent framework** — AgentBase, AgentResult, conductor-delegate pattern
- **Quality gates** — Confidence scoring, multi-dimension assessment
- **Escalation protocol** — Structured "I don't know" handling
- **Document ingestion** — PDF/DOCX → Markdown pipeline
- **Version tracking** — Amendment agent concept adapted for document versions
- **Vector store integration** — ChromaDB collection management
- **Knowledge graph** — Same engine (NetworkX), different schema
- **Testing patterns** — TDD for parsers, regression tests

## What's New in KTS (Not in ABS)

- **GitHub Copilot Chat integration** — Users ask questions in Copilot, system provides retrieval context
- **VS Code Extension architecture** — Integrated admin experience with Command Palette and custom panels
- **Multi-modal pipeline** — Image extraction + vision-model descriptions for searchability
- **Human-in-the-loop vision workflow** — Maintenance Engineer describes images using GitHub Models
- **Document taxonomy** — Auto-classification across diverse document types
- **Cross-domain linking** — Opposite of ABS's deal isolation; KTS actively connects knowledge across tools and processes
- **Training Path generation** — Graph-based learning sequence construction
- **Change Impact analysis** — Reverse dependency traversal
- **Freshness detection** — Stale content identification
- **File share crawler** — Hash-based change detection on network drives
- **User screenshot support** — Copilot's vision reads user-uploaded screenshots, searches our knowledge base

## Key Design Principle

> **ABS Waterfall AI isolates knowledge by deal. KTS connects knowledge across everything.**

In ABS, cross-deal contamination was dangerous. In KTS, the interconnection IS the value — a question about one tool might require knowledge from a process doc, a release note, and a training screenshot that span multiple sources.

## Project Metrics (Targets)

| Metric | Target |
|--------|--------|
| Document types supported | 4 (DOCX, PDF, PPTX, HTML) |
| Agents | 10 (no separate Conductor — Copilot handles intent) |
| Time to ingest a 50-page document | < 2 minutes (text), + manual vision time |
| Knowledge retrieval time | < 3 seconds (return context to Copilot) |
| Citation coverage | 100% (every context chunk includes source doc + page/section) |
| Image description coverage | Human-paced, tracked by manifest |
| User experience | Zero API keys, works in existing Copilot Chat workflow |

---

*This document provides a high-level overview. See Architecture_Plan.md, System_Design.md, and Implementation_Plan.md for technical details.*
