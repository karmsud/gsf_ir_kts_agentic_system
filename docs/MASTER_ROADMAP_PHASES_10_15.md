# KTS RAG Platform — Master Roadmap (Phases 10–15)

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## The Build Sequence and Why It Matters

Each phase is a foundation for the next. This is not arbitrary ordering — it reflects hard technical dependencies and a deliberate progression from infrastructure plumbing to deal intelligence.

```
Phase 10 ──► Phase 11 ──► Phase 12 ──► Phase 13 ──► Phase 14 ──► Phase 15
   │              │              │              │              │              │
Conversation  VS Code       Scoped         Retrieval      Deal          Cross-Deal
  Memory      Native        Namespaces     Quality        Intelligence   Intelligence
  (Plumbing)  (UX Layer)    (Architecture) (Precision)    (Structure)    (Premium)
```

**You cannot build Phase 14 (deal comparison) without Phase 12 (named scopes).**  
**You cannot build Phase 15 (anomaly detection) without Phase 13 (confidence scores).**  
**Phase 10 makes every subsequent phase more accurate** (query rewriting improves all retrieval).

---

## Phase Summary Table

| Phase | Name | Core Capability | Key Feature | Depends On |
|-------|------|----------------|------------|-----------|
| **10** | Conversation Memory | Query context across turns | Coreference resolution, session memory | Phase 8/9 |
| **11** | VS Code Native Intelligence | Platform capabilities | #file/#selection, follow-ups, /define, /extract | Phase 10 |
| **12** | Named Scoped Knowledge Spaces | Folder = embedding namespace | Auto slash commands, 2-level scope, federated search | Phase 10 |
| **13** | Retrieval Quality Upgrades | Better retrieval mechanics | HyDE, parent-child chunking, confidence scoring, gap alerts | Phase 10 |
| **14** | Structured Deal Intelligence | Deal data model | Session summary cache, temporal reasoning, JSON extraction | Phase 10, 11, 12 |
| **15** | Cross-Deal Intelligence | Cross-document analysis | /compare, contradiction detection, anomaly flagging | Phase 12, 13, 14 |

---

## Phase 10: Conversation Memory & Session Intelligence

**Problem it solves:** Every question is treated as a cold start. Follow-up questions fail silently.

**What changes:**
- `context.history` (VS Code gives this for free) is extracted and passed to the backend
- Query rewriter resolves pronouns and coreferences before retrieval
- Session memory tracks resolved terms and active documents, biasing retrieval toward in-context docs
- Rolling summary buffer keeps context window bounded regardless of session length

**The single most impactful increment:** Query rewriting (10.2). One LLM call that transforms "And the same for the Closing Date?" into a fully-specified standalone query. Fixes an entire class of retrieval failure.

**Docs:** [IMPLEMENTATION_PLAN](phase10/RAG_UPGRADE_IMPLEMENTATION_PLAN.md) | [ARCHITECTURE](phase10/RAG_UPGRADE_ARCHITECTURE.md)

---

## Phase 11: VS Code Native Intelligence Layer

**Problem it solves:** We use 20% of the VS Code Chat API. The other 80% is free and untouched.

**What changes:**
- `#file` and `#selection` variables: analyst highlights a clause, drags it into chat, asks about it — zero copy-pasting
- `response.followUp()`: after every answer, clickable suggested follow-up questions appear
- `/define`, `/extract`, `/compare`, `/audit`, `/summary` as structured retrieval modes — same retrieval pipeline, different prompt templates and output formats
- `vscode.lm.selectChatModels()`: user picks the generation model at runtime (GPT-4o-mini for speed, o1 for deep synthesis)
- Live progress streaming during retrieval ("Searching 3 documents... Reranking 47 candidates...")

**The single most impactful increment:** #file/#selection (11.1). Changes the UX from "ask about a document" to "ask about a specific passage." This is precision legal review.

**Docs:** [IMPLEMENTATION_PLAN](phase11/RAG_UPGRADE_IMPLEMENTATION_PLAN.md) | [ARCHITECTURE](phase11/RAG_UPGRADE_ARCHITECTURE.md)

---

## Phase 12: Named Scoped Knowledge Spaces

**Problem it solves:** 10,000 deals in one embedding space causes scope bleed, cross-contamination, slow retrieval, and unverifiable grounding.

**What changes:**
- Each folder in the knowledge source gets its own `.kts/` directory — its own isolated ChromaDB collection
- Folder names become slash commands automatically: `bear_stearns_2006_HE1/` → `@kts /bear_stearns_2006_HE1`
- Level 2 scope: `@kts /bear_stearns_2006_HE1 /psa` narrows retrieval to PSA doc type only within that deal (ChromaDB `where` filter — no new collections)
- Deal catalog index: SQLite table of all indexed folders with issuer/year/type metadata
- Smart federated routing: `@kts how many bear deals have "dscr loans"?` → catalog lookup → fan-out to 50-60 Bear scopes only, not all 10,000

**Why this is the architectural cornerstone of phases 14 and 15:** Without per-deal isolated scopes, cross-deal intelligence (contradiction detection, comps, anomaly detection) is impossible. Phase 12 is the prerequisite.

**Docs:** [IMPLEMENTATION_PLAN](phase12/RAG_UPGRADE_IMPLEMENTATION_PLAN.md) | [ARCHITECTURE](phase12/RAG_UPGRADE_ARCHITECTURE.md)

---

## Phase 13: Retrieval Quality Upgrades

**Problem it solves:** The best reranking and critique loops cannot compensate for retrieval that never found the right chunk in the first place.

**What changes:**
- **HyDE** (13.4): Generate a hypothetical answer paragraph, embed that instead of the raw query. The hypothetical matches document vocabulary — precision on legal definitions improves ~20-30%.
- **Parent-child chunking** (13.3): Index small precise child chunks (~150 tokens) for retrieval accuracy, but send large parent chunks (~600 tokens) to the LLM for generation context. Eliminates mid-clause fragment answers.
- **Confidence scoring** (13.1): Every answer now displays a confidence tier (✅ High / 🔵 Medium / ⚠️ Low / 🔴 Speculative) derived from rerank scores. Users know when to trust and when to verify.
- **Proactive gap alerts** (13.2): If the user asked about 3 terms and retrieval only found 2, the system explicitly says "Note: 'Record Date' could not be located." No more silent omissions.

**The single most impactful increment:** Confidence scoring (13.1). Zero retrieval change, pure trust transformation. The user finally knows what the system knows and doesn't know.

**Docs:** [IMPLEMENTATION_PLAN](phase13/RAG_UPGRADE_IMPLEMENTATION_PLAN.md) | [ARCHITECTURE](phase13/RAG_UPGRADE_ARCHITECTURE.md)

---

## Phase 14: Structured Deal Intelligence Layer

**Problem it solves:** Every query is stateless and prose-only. The system cannot produce structured data, has no persistent model of the deal, and doesn't know what date it is.

**What changes:**
- **Session deal summary cache** (14.1): As the user asks questions, the system builds a progressive deal data model in memory. Subsequent queries check this cache first — resolved terms are returned instantly with 100% recall, no retrieval cost.
- **Temporal reasoning** (14.2): `current_date` injected into every prompt. "Has the Optional Termination Date passed?" gets a real answer: "Yes — it passed on March 15, 2023 (3 years ago)."
- **/extract mode** (14.3): Structured JSON extraction of all key deal data points (parties, dates, amounts, defined terms, gaps). Machine-readable output for downstream systems.
- **/summary mode** (14.4): Fixed 5-section executive deal summary (Parties, Key Dates, Key Amounts, Key Obligations, Risk Factors) with temporal status on every date.

**The single most impactful increment:** Session deal summary cache (14.1). After 10 turns on a deal, >50% of subsequent term lookups hit cache — zero retrieval, perfect recall.

**Docs:** [IMPLEMENTATION_PLAN](phase14/RAG_UPGRADE_IMPLEMENTATION_PLAN.md) | [ARCHITECTURE](phase14/RAG_UPGRADE_ARCHITECTURE.md)

---

## Phase 15: Cross-Deal Intelligence & Anomaly Detection

**Problem it solves:** Every existing tool analyzes one document at a time. The value of having 10,000 deals in a knowledge base is currently zero — they cannot talk to each other.

**What changes:**
- **/compare across scopes** (15.1): Retrieve the same concept from N deals simultaneously, produce a side-by-side comparison table with divergence summary. What was 4 hours of analyst work becomes 30 seconds.
- **Contradiction detection** (15.2): Pairwise comparison of definitions across deals on specific binary dimensions (inclusion/exclusion, scope, conditions). Flags material legal contradictions between deals.
- **Market baseline corpus** (15.3): Derive "standard market language" for ~50 clause types from the ingested deal corpus. The modal text across N deals becomes the baseline.
- **Anomaly detection** (15.4): For every clause in a /audit query, score semantic distance from baseline. Flag non-standard clauses: ✅ Standard / ⚠️ Non-standard / 🔴 Significant deviation. The feature that replaces 4 hours of manual clause review.

**The single most impactful increment:** /compare (15.1). The first capability that makes the multi-deal knowledge base genuinely more valuable than a single-deal search tool. The moment users see a 3-deal comparison table in 8 seconds, the product category changes.

**Docs:** [IMPLEMENTATION_PLAN](phase15/RAG_UPGRADE_IMPLEMENTATION_PLAN.md) | [ARCHITECTURE](phase15/RAG_UPGRADE_ARCHITECTURE.md)

---

## Dependency Map

```
Feature                              Requires
─────────────────────────────────────────────────────────────────
Query rewriting                      Phase 10 (history plumbing)
#file / #selection                   Phase 11 (VS Code API)
Named scopes / slash commands        Phase 12 (folder structure)
Two-level scope /deal /doctype       Phase 12 (metadata filters)
HyDE                                 Phase 13 (standalone, no deps)
Parent-child chunking                Phase 13 (re-ingest required)
Confidence scoring                   Phase 13 (rerank scores, Phase 8)
Session deal summary                 Phase 10 (session_memory)
Temporal reasoning                   Standalone (current_date injection)
/extract JSON mode                   Phase 11 (/extract command)
/compare command                     Phase 12 (named scopes)
Contradiction detection              Phase 12 (scopes) + Phase 11 (/compare)
Baseline corpus                      Phase 12 (enough indexed deals)
Anomaly detection                    Phase 13 (confidence) + Phase 15.3 (baseline)
```

---

## Platform Evolution

```
v0.0.12  (today)
  Answer questions. Sometimes miss follow-ups. No scope, no structure, no comparison.

Phase 10
  Answer with conversation context. Follow-up questions work. Session awareness.

Phase 11
  Use VS Code as intended. Highlight a clause, ask about it. Structured modes.

Phase 12
  10,000 deals, zero contamination. Folder = namespace = command. 
  Ask across all bear deals in 8 seconds, not 8 hours.

Phase 13
  Know what you don't know. Every answer has a confidence score.
  Never silently miss a term again.

Phase 14
  Know the deal, not just the document. Session memory. Temporal awareness.
  "Has this date passed?" answered correctly, every time.

Phase 15
  The first truly cross-deal intelligence platform in legal document review.
  Compare. Detect contradictions. Flag anomalies. Replace hours with seconds.
```

---

## What We Are Building

Not a better search engine. Not a smarter chatbot.

**A deal intelligence platform** that lives inside the tool analysts already use, speaks the language of the documents they already work with, and makes the relationships between those documents visible for the first time.

The question was: *"What if we never asked this?"*

The answer: we would have shipped a retrieval engine. We are building something far more interesting.
