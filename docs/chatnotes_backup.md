1. The Testing Cycle Is Broken
Current loop: Edit → build VSIX (3min) → reinstall → reload window → re-ingest (5min) → type question → copy Output tab → paste into chat → wait for analysis → repeat

The fix is embarrassingly simple — we're not using it: VS Code has an Extension Development Host. You press F5, it launches a second VS Code window running your extension from source. Edit JS → save → reload the dev window (Ctrl+R) → test. No VSIX build, no reinstall. We've been doing this the hard way.

For backend Python changes, the compiled exe also isn't needed during dev. We can point the extension at the live Python source via kts.backendMode: "venv" — changes are instant.

We should have set this up on day 1. That alone eliminates 80% of the cycle time.

2. Too Many Settings / Decision Fatigue
Here's the honest inventory of what we've accumulated:

Category	Settings	Should Exist?
5 model dropdowns	generationModel, reasoningModel, multiQueryModel, selfRagModel, critiqueModel	1 is enough — the user picks a model in the chat picker, we use it for everything
RAG technique toggles	selfRagEnabled, critiqueLoopEnabled, multiQueryEnabled, graphRagEnabled	Zero — these should all be ON, always, with no toggle
Numeric tuning knobs	maxContextChunks, tokenBudget, selfRagMaxRounds, graphRagMaxIterations, multiQueryVariants, critiqueMaxRounds	Zero exposed to user — we should compute these from the model's context window
Backend config	20+ settings in settings.py	Internal only — never surfaced to users
Proposal: Strip user-facing settings down to 3:

kts.sourceFolder — where the documents are
kts.logLevel — normal / verbose
kts.model — auto (default) / specific model override
Everything else becomes hardcoded internal defaults tuned for GPT-4.1's 1M context. No more asking users to configure their RAG pipeline.

3. The Output Format Is Wrong
Our current system prompt forces this rigid structure:

Compare with how I (GitHub Copilot) answer you: I just answer your question. If I need to cite something, I link it inline. If there's a gap, I mention it naturally. No numbered sections, no academic format.

The problem: We wrote a report template when users want a conversation. The system prompt should be:

You are a document-grounded assistant. Answer the user's question naturally and conversationally using ONLY the retrieved context. Cite specific sections/clauses inline when relevant (e.g., "per Section 5.06, the Trustee must..."). If information is missing from the context, say so naturally within your answer. Do not use numbered output sections.

That's it. One paragraph of instruction instead of 40 lines of rigid formatting rules.

For citations: VS Code's Chat API has a native ChatResponseReferencePart — clickable file references that appear as pills below the answer, exactly like Copilot does. We're currently building markdown citation blocks manually instead of using the API.

For follow-ups: We already have a followupProvider but we're also rendering them as markdown bullets. Use only the native API — it renders as clickable chips.

4. Automated Testing Harness
This is the most important piece. Here's what I propose:

Golden Answer Test Suite
A JSON file like:

Test Runner (runs without VSIX)
A Node.js script that:

Calls the backend exe/Python directly (same as the extension does)
Feeds the search results through the same prompt + LLM call (using the VS Code LM API in dev host, or a direct OpenAI call for CI)
Evaluates the answer against golden criteria
Produces a scorecard
This means you write golden_queries.json once, I run the harness, see what fails, fix the pipeline, re-run — all without you in the loop.

LLM-as-Judge (for subjective quality)
For questions where "must_contain" strings aren't enough, use a second LLM call to judge: "Given this question and this reference answer, does the generated answer adequately cover the same information? Score 1-5."

5. Leverage Copilot Chat's Native APIs
We're reinventing wheels that VS Code already provides:

Feature	We Build	VS Code Provides
Citations	Manual markdown with [file](uri)file	ChatResponseReferencePart — native clickable pills
Follow-ups	Markdown bullets in answer	ChatFollowup via followupProvider (we have it but also duplicate in markdown)
Progress	stream.progress() (correct)	Already using correctly
Streaming	stream.markdown() (correct)	Already using correctly
File references	Manual file:// URIs	vscode.Uri + ChatResponseReferencePart
Anchor links	Not doing	ChatResponseAnchorPart — links to specific file locations
Proposed Plan
Phase A: Dev Environment (1 hour)
Set up launch.json for Extension Development Host (F5)
Configure kts.backendMode: "venv" for live Python dev
Document the dev workflow: edit → save → Ctrl+R → test
Phase B: Simplify Settings (30 min)
Strip user-facing settings from ~25 down to 3
Hardcode all RAG tuning internally
Remove all Phase X toggle switches
Phase C: Conversational Output (1-2 hours)
Replace rigid 5-section prompt with conversational instruction
Use native ChatResponseReferencePart for citations
Remove duplicate markdown follow-ups (keep only followupProvider)
Clean up the streaming pipeline
Phase D: Golden Test Harness (2-3 hours)
Create tests/golden_rag_tests.json with 10-20 real questions
Build scripts/run_golden_tests.js (or .py) that runs queries without VSIX
Add LLM-as-judge scoring for subjective quality
Make it runnable as npm test:golden or python -m pytest tests/test_golden.py
Phase E: Iterate on Quality (ongoing)
You provide questions + expected behavior in the golden file
I run the harness, diagnose failures, fix pipeline
No more copy-paste-from-Output-tab cycles
What would you like to prioritize? My recommendation: Phase A first (immediate 10x speedup in testing), then Phase C (the output quality you actually want), then Phase D (so we can iterate without manual testing). Phase B can happen alongside C.

Q1: Golden Test Question Design
Your existing golden_psa_2006he1.json already has 100 tests across 6 buckets (A: Definitions, B: Precedence/Amendments, C: Waterfall, D: Servicing, E: Negative Controls, F: Evidence). That's a solid retrieval test suite. But it tests retrieval correctness (did the right chunks come back?), not answer quality (did the user get the answer they needed in a useful format?).

Based on your description of how real users work, the golden test harness needs a new layer — one that tests the end-to-end answer, not just the retrieval pipeline. Here's what I'd design:

New Test Categories Based on Real User Workflows
Category 1: "Give me the key dates for this deal"
This is the first thing an analyst does with a new PSA. They need: Closing Date, Cut-off Date, Distribution Date, Record Date, Determination Date, Accrual Period, Remittance Date, etc. — all in one answer.

Test: "What are the key dates for this deal?"
Expected: A table or list of 8-12 dates with their exact values and section references. Not just one definition.
What this tests: Can the system synthesize ACROSS multiple definitions into a single coherent answer? Current RAG retrieves chunks for individual terms — this requires the LLM to identify and gather ALL date-type terms.
Category 2: "Walk me through the distribution waterfall"
The analyst needs to understand payment priority — who gets paid first, second, etc.

Test: "How are interest distributions prioritized among the certificate classes?"
Expected: The full sequential priority from Section 5.04 (or wherever the waterfall lives), with each step identified by its (i), (ii), (iii) numbering and the Capitalized Terms explained.
What this tests: Can the system retrieve a full contiguous section (not fragments) and present the logic in order? This is where the .slice(0,8) bug hurt us — waterfall sections are long.
Category 3: "What does the statement to certificateholders contain?"
This was your actual test question that produced bad output.

Test: "What information must be included in the statement to Certificateholders under Section 5.06?"
Expected: The complete enumerated list of reporting items from Section 5.06, with each item explained.
What this tests: Retrieval of body text from a specific section (not just the section header), and the ability to present a long enumerated list.
Category 4: "Define [term] and resolve all nested terms to depth N"
This is your core definition-chain use case.

Test: "What is Current Interest? Explain all the terms used in its definition."
Expected: The definition of Current Interest, PLUS the definitions of Certificate Principal Balance, Pass-Through Rate, Accrual Period, Prepayment Interest Shortfall, Compensating Interest, Relief Act Interest Shortfall — resolved to whatever depth the document requires.
What this tests: Whether the definition enrichment + term resolver actually works for a real multi-hop case. This is the test that Phase 7 Module 5 is designed to solve.
Category 5: "Tell me about the parties and their roles"

Test: "Who are the transaction parties and what are their roles?"
Expected: Depositor (Bear Stearns Asset Backed Securities I LLC), Master Servicer (EMC Mortgage Corporation), Trustee (LaSalle Bank), Securities Administrator, etc. — with a brief role description for each.
What this tests: Cross-section synthesis from preamble + Section 1.01 + various articles.
Category 6: Conversational follow-ups

Turn 1: "What is the Distribution Date?"
Turn 2: "What happens if it falls on a weekend?"
Turn 3: "Does the same rule apply to the Record Date?"
What this tests: Conversation history injection, coreference resolution ("it" → Distribution Date), and whether the system can handle multi-turn dialogue.
How to Score
Instead of just checking if expected_must_include_terms appear in the retrieval output, the golden harness should score the final LLM answer on:

Completeness — Did it answer the full question, or just part of it?
Accuracy — Are the quoted facts correct per the PSA?
Grounding — Is every claim traceable to a specific section?
Usability — Is the answer something a finance professional would actually use? (subjective, but can be templated)
No hallucination — Did it invent anything not in the document?
The scoring can be automated with a second LLM call (GPT-4.1 as judge) using the golden answer as reference.

Q2: RAG Architecture Critical Review
I mapped the complete pipeline from frontend to backend. Here's the honest assessment:

The Full Chain (in execution order)
What's Definitely Needed (Keep)
Technique	Why
Graph-first section discovery	This is the killer feature. Legal docs have a TOC structure. Finding the right section first, then searching within it, is exactly how humans navigate these docs.
Dual vector store (items + sections)	Items for fine-grained answers, sections for broad context. Good design.
Cross-encoder rerank	Bi-encoder retrieval is approximate; cross-encoder provides precise relevance scoring. This is well-established to add 5-15% quality.
Definition enrichment	Legal docs are unusable without resolving capitalized terms. Core differentiator.
BM25 hybrid	Catches exact keyword matches that embedding similarity misses (e.g., "Section 5.06" is a keyword match, not a semantic one).
Per-doc dedup	Without this you'd get 50 chunks from the same section. Necessary.

What's Questionable (Evaluate During Testing)
Technique	Concern
Multi-query expansion (8 variants)	8 is very aggressive. Each variant triggers a full retrieval cycle. I'd test with 0, 2, 4, 8 and measure quality vs. latency. For legal docs where the user often names the exact section ("Section 5.06"), multi-query may add noise more than signal.
Self-RAG iterative loop	The idea is sound but the implementation has problems: (1) each round fires a NEW ktsTool call which reruns the entire backend pipeline, (2) gap analysis is LLM-generated and often redundant, (3) context accumulates across rounds causing token overflow. Until we can measure that round 2+ actually improves answers, this should be off by default.
MMR diversity (λ=0.7)	For legal docs, you usually WANT multiple chunks from the same section (waterfall steps are sequential). Diversity pushes chunks apart. λ=0.7 is mild, but test whether removing MMR hurts or helps for legal doc queries specifically.
Keyword-boost rerank AFTER cross-encoder	The cross-encoder already considers token overlap via attention. Running a keyword boost after it can override the CE's carefully calibrated scores. This is suspicious. Either trust the CE or don't use one.
Parent-child expansion	This expands items to their parent section. But if graph-first already found the right section and you searched within it, parent expansion may be redundant. Test it.
What's Actively Harmful or Dead Code
Technique	Problem
4 overlapping query expansion mechanisms	Backend QueryExpander.expand() (synonyms), QueryExpander.generate_query_variations() (multi-query), IterativeOrchestrator._expand_query() (domain reformulations), AND JS-side expandQueryWithLLM(). These stack and interact unpredictably. Consolidate to ONE.
context_expansion_enabled declared twice	Second declaration silently overrides first to False. The feature is dead code. Bug.
Critique loop	It runs AFTER Self-RAG, on an answer that's already been iteratively refined. The critique questions come from ingestion-time metadata, not from analyzing the actual answer. In practice, it either (a) does nothing because the answer already covers the questions, or (b) forces a rewrite that may be worse. Test rigorously before keeping.
Confidence scoring triple-computation	Three different formulas in three different code paths. The user sees the Phase 13.1 scorer output, which may disagree with the pipeline's internal confidence used for convergence. Unify.
IterativeOrchestrator fallback	The entire convergence-loop retriever (10 iterations, 0.85 confidence target) exists as a fallback. But HumanLikeRetriever is always chosen for legal docs. The PageRank computations, hybrid reranker, and convergence loop are effectively dead code for your primary use case.

Ordering Issue
The most concerning sequence is:

Cross-encoder rerank (line C3a.8) produces a carefully calibrated relevance score
Keyword-boost rerank (line C3a.9) then overrides that score based on simple keyword overlap
This is like having a specialist doctor diagnose you, then having a nurse override the diagnosis based on a temperature reading. The CE score should be the final word on relevance, or if keyword signals matter THAT much, they should be a feature input to the CE, not a post-hoc override.

My Recommendation
For the golden test harness, run an ablation study:

Baseline: Graph-first + dual vector + BM25 hybrid + cross-encoder + definition enrichment. No multi-query, no Self-RAG, no critique, no MMR, no keyword boost.
+Multi-query (2 variants): Does it help?
+Multi-query (8 variants): Diminishing returns?
+Self-RAG: Does round 2 ever improve over round 1?
+Critique: Does the critique-revised answer score better?
+MMR: Does diversity help or hurt for legal docs?
This will tell you empirically which techniques earn their keep. I suspect the baseline (step 1) will produce 80-90% of the quality, and most of the fancy techniques are adding complexity without proportional value.

Q3: Pre-Resolve Capitalized Terms at Ingestion (Phase 7 Module 5)
I've now read the complete Phase 7 design end to end. Here's my assessment:

It's the Right Idea at the Right Time
The current definition enrichment at retrieval time (D7: term_resolver.py, BFS depth 8) is a band-aid. It runs on EVERY query, re-traverses the graph from scratch, and is limited by whatever terms happen to be in the retrieved chunks. If a chunk mentions "Current Interest" but the retrieval didn't also pull the chunks for "Certificate Principal Balance", "Pass-Through Rate", etc., the definition chain is incomplete.

Pre-computing the full resolution tree at ingestion solves this permanently:

One-time cost: DFS with memoization over ~300 terms, O(V+E), runs in milliseconds
Stored as: JSON attribute on each graph node (~1 MB total)
At query time: When someone asks about "Current Interest", you don't search for definitions — you just read the pre-computed tree that already contains all 23 dependent terms in topological order
What Makes It High-Impact
Your Phase 7 design correctly identifies that PSA definitions are a DAG. Once the DAG is built and the resolution trees are pre-computed:

Any term query becomes instant — no retrieval loop needed for definitions
Waterfall questions get full context — the LLM receives not just the waterfall text but the complete definition of every Capitalized Term used in it
The resolution tree is the PERFECT golden test oracle — you can verify that "Current Interest" resolves to exactly these 23 terms, no more, no less
Implementation Path (Modules 1-5 Only)
The Phase 7 design wisely separates the "buildable with confidence" modules (1-5) from the "research-grade" ones (7-8). I agree with this staging. Here's what's needed:

Module 1 (Term Dictionary Extraction): You already have DefinedTermExtractor in defined_term_extractor.py. But as the design notes, it truncates and classifies — it doesn't preserve the full verbatim text. Enhancement needed: extract complete definition text from the Definitions section (Article I / Section 1.01).

Module 3 (Reference Scanning): Scan each definition for other Capitalized Terms. Aho-Corasick longest-match against the term dictionary. Creates DEPENDS_ON edges.

Module 4 (Graph Construction): You already have NetworkX DiGraph from builder.py. Add the DEPENDS_ON edges as a new edge type.

Module 5 (Resolution Trees): DFS from each node, memoized. Store as JSON attribute. This is ~50 lines of Python.

The Critical Decision
The design says "we are going to create user stories, FRD, PRD, TRD, implement one story at a time." I agree. But there's a question of when to do this relative to the other planned work:

Option A: Do Phase 7 Modules 1-5 FIRST (before output format, before test harness)

Pro: Resolution trees become both a product feature AND the golden test oracle
Pro: You can validate the resolution tree's correctness manually (does "Current Interest" produce the right 23 terms?) without needing the full LLM pipeline
Con: Requires backend changes + re-ingestion of the PSA
Option B: Do dev environment + conversational output + golden harness FIRST, then Phase 7

Pro: You get the F5 dev workflow and automated testing before touching the backend
Pro: You can measure current baseline before adding definition resolution
Con: The golden tests would initially test without resolution trees, then need re-baseline
I recommend Option B — get the testing infrastructure right first. The reason: you'll want to MEASURE the impact of definition resolution against a baseline. If you build the resolution engine first, you'll never know how much it actually improved things. Build the test harness, measure the baseline, THEN add Module 1-5, re-measure. That's how you prove it works.

One Concern About Module 1
The existing DefinedTermExtractor uses regex patterns to find Capitalized Terms in generic text. For a PSA, you need something smarter: the Definitions section (Article I) has a very specific format — "Term Name" means [definition text] — and that format is far more reliable than regex-scanning body text for Capitalized Words. I'd recommend building a PSA-specific definitions parser (it's essentially a state machine: look for the quoted term, then capture everything until the next quoted term or section boundary) rather than enhancing the existing generic extractor.

Summary of Recommendations
Question	Answer
Q1: Golden tests	Add 6 new categories testing answer quality, not just retrieval. Score with LLM-as-judge on completeness, accuracy, grounding, usability, no-hallucination.
Q2: RAG architecture	The baseline (graph-first + dual vector + BM25 + cross-encoder + definition enrichment) is solid. Self-RAG, critique loop, 8-variant multi-query, and keyword-boost-after-CE are all suspect. Run an ablation study with the test harness before keeping them.
Q3: Definition resolution	Modules 1-5 are the right thing to build. But build the test harness FIRST so you can measure the before/after impact. The resolution tree becomes both a feature and an oracle.
What do you want to discuss further or shall I start creating the design docs?

Yes — all three pieces are implemented. Here's the status against each section you asked about:

Q1: Golden Test Question Design — Fully Implemented
golden_answer_tests.json has 30 questions across all 6 categories you specified:

Category	Your Design	Implemented	Count
Defined Terms	"Define [term] and resolve nested terms"	defined_terms (G01-G05)	5
Waterfall	"Walk me through the distribution waterfall"	waterfall (G06-G10)	5
Reporting	"What does the statement to certificateholders contain?"	reporting (G11-G15)	5
Key Dates	"Give me the key dates for this deal"	key_dates (G16-G20)	5
Parties & Roles	"Tell me about the parties and their roles"	parties (G21-G25)	5
Conversational Follow-ups	Multi-turn with coreference	follow_ups (G26-G30)	5
Each question has: expected_answer_contains, expected_answer_not_contains, ideal_answer_summary, scoring_rubric (per-dimension), expected_sections, difficulty, depends_on, and prior_context (for follow-ups).

The 5-dimension LLM-as-Judge scoring is implemented in golden_answer_scorer.js:

completeness (0.25), accuracy (0.30), grounding (0.20), usability (0.15), no_hallucination (0.10)
Regression detection: overall drop ≥1.0, any dimension drop ≥2, new critical failures
Dev Environment (F5 workflow) — Fully Implemented
launch.json has 2 Extension Development Host configurations:

"Run KTS Extension (Dev Host)" — basic F5 launch
"Run KTS Extension (Dev Host + Test Folder)" — opens the Knowledge Base test/ folder automatically
Both set KTS_DEV_MODE=true, KTS_LOG_LEVEL=DEBUG. settings.json sets kts.backendMode: "venv" so the extension uses your live Python source instead of the compiled exe.

Automated Testing Harness — Fully Implemented
Component	File	What it does
Test data	golden_answer_tests.json	30 Q&A pairs with rubrics
Runner	golden_answer_runner.js	Calls ktsTool (backend search) → builds context → calls VS Code LM API → captures answer
Scorer	golden_answer_scorer.js	LLM-as-Judge scoring, baseline comparison, regression detection
Command	kts.runGoldenTests	Registered in extension.js and package.json
How to test it
Step 1: F5 launch

Open this workspace in VS Code
Press F5 → pick "Run KTS Extension (Dev Host + Test Folder)"
A second VS Code window opens with your extension loaded from source, pointed at the Knowledge Base test/ folder
The backend runs from .venv_build (live Python, no exe needed)
Step 2: Run golden tests

In the Dev Host window: Ctrl+Shift+P → type "KTS: Run Golden Answer Tests"
The harness runs all 30 questions through the full pipeline (backend search → LLM generation → LLM-as-Judge scoring)
Results are saved to tests/golden_answer_results/{timestamp}_results.json
Scores are saved to tests/golden_answer_results/{timestamp}_scores.json
Step 3: Iterate

Edit JS → Ctrl+R in Dev Host → re-run tests (no rebuild)
Edit Python → just re-run tests (venv mode picks up changes instantly)
Compare scores against baseline to detect regressions
Note: The test corpus needs to be ingested first. If you haven't ingested into the Knowledge Base test/ folder yet, run Ctrl+Shift+P → "KTS: Ingest" in the Dev Host window first.
