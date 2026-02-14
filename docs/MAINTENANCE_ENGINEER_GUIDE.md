# GSF IR KTS — Maintenance Engineer Guide

This guide is the operational playbook for building a high-quality knowledge corpus and ingesting it so `@kts` retrieval returns the best possible results.

---

## 1) Principle: Better Source → Better Result

Yes — retrieval quality is directly tied to source quality.

KTS is retrieval-first. If source documents are:
- current,
- specific,
- consistently named,
- and richly described (especially screenshots),

then `@kts` responses are materially better.

---

## 2) Corpus Build Standards

## 2.1 Supported Formats
- `.docx`, `.pdf`, `.pptx`, `.html`, `.htm`, `.md`, `.txt`

Prefer `.md` or clean `.docx` for procedural content when possible.

## 2.2 Folder Structure (Recommended)

Use a stable structure on your network share, for example:

```text
\\server\IR_KTS\
  SOP\
  User_Guides\
  Troubleshooting\
  Release_Notes\
  Training\
  Reference\
```

Benefits:
- easier crawl targeting,
- easier governance,
- predictable doc type distribution.

## 2.3 Naming Convention (Strongly Recommended)

Use names that include document intent and target tool/process:

- `SOP_ToolX_Password_Reset_v3.docx`
- `Troubleshoot_ToolX_AUTH401.md`
- `ReleaseNotes_ToolX_2026Q1.pdf`
- `Training_ToolY_Onboarding.pptx`

Good names improve taxonomy and retrieval precision.

## 2.4 Content Authoring Rules

For each procedure/troubleshooting document:
- include exact tool names and environment names,
- include exact error codes/messages (`AUTH-401`, `timeout`, etc.),
- include clear step numbers (`Step 1`, `Step 2`, ...),
- include “Symptoms”, “Cause”, “Resolution”, “Validation” sections where applicable,
- include update date and owner where possible.

For release notes:
- include version identifiers,
- list breaking changes explicitly,
- link affected process names.

---

## 3) Ingestion Runbook (Network Folder)

Assume corpus path:

`\\server\IR_KTS`

From project root:

```powershell
python -m cli.main crawl --paths "\\server\IR_KTS"
python -m cli.main ingest --paths "\\server\IR_KTS"
python -m cli.main status
```

Optional checks:

```powershell
python -m cli.main freshness
python -m cli.main search "How do I reset password in ToolX?"
```

## 3.1 Ongoing Incremental Operation

Daily/weekly cycle:
1. `crawl` to detect new/changed files
2. `ingest` on source path
3. complete pending image descriptions
4. run `freshness`
5. run representative `search` smoke queries

---

## 4) Vision Workflow (Critical for Screenshot-heavy Knowledge)

After ingest:

```powershell
python -m cli.main describe pending
```

For each pending doc/image:
1. describe what is visible in operational terms,
2. include exact UI labels and error text,
3. include task context (what user is trying to do).

Submit descriptions:

```powershell
python -m cli.main describe complete --doc-id <doc_id> --descriptions-file <descriptions.json>
```

Description quality rule:
- minimum 12 chars enforced,
- high specificity strongly recommended.

Good description example:

`ToolX login dialog showing AUTH-401 after SSO redirect; Security tab displays “Token expired”; retry button disabled.`

---

## 5) Quality Tuning Checklist (Best Results)

## 5.1 Corpus Quality
- remove duplicate/stale drafts,
- prefer latest approved SOP over informal notes,
- include both “how-to” and “failure mode” documentation.

## 5.2 Retrieval Calibration
- run 20–30 real user queries and inspect citations,
- identify misses (missing error codes, weak section wording, missing screenshots),
- update source docs and re-ingest.

## 5.3 Freshness Governance
- schedule freshness audits,
- prioritize stale docs tied to frequently used tools/processes,
- ensure release notes land in corpus before major rollouts.

---

## 6) Acceptance Criteria Before Business Launch

- `python -m pytest -q` passes
- `python scripts/smoke.py` passes
- key domain corpora ingested successfully
- pending image queue is near-zero for high-traffic tools
- representative user questions return accurate citations
- extension command flows and chat participant (`@kts`) work in target VS Code version

---

## 7) Known Practical Limits

- KTS cannot invent missing knowledge; missing/poor sources degrade answers.
- Screenshot-driven issues require high-quality image descriptions for best retrieval.
- If two docs conflict, retrieval may surface both; governance should retire obsolete content.

---

## 8) Recommended Operating Cadence

- **Daily**: crawl + ingest delta for active folders
- **Weekly**: close pending image descriptions, run freshness, review top failed queries
- **Monthly**: corpus cleanup and naming/structure compliance review

This cadence keeps retrieval quality high and user trust stable.
