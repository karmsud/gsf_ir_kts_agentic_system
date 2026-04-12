# Phase 17 — Command Reference

> **Document**: 06_COMMAND_REFERENCE.md
> **Phase**: 17 — Document-Level Isolation & Cross-Deal Intelligence
> **Status**: Design Specification
> **Last Updated**: 2025-07-14

---

## Table of Contents

1. [Overview](#1-overview)
2. [Command Syntax Grammar](#2-command-syntax-grammar)
3. [Quick Reference Card](#3-quick-reference-card)
4. [Detailed Command Reference](#4-detailed-command-reference)
5. [Scope Tokens](#5-scope-tokens)
6. [Document Filter Tokens](#6-document-filter-tokens)
7. [Key-Value Filter Tokens](#7-key-value-filter-tokens)
8. [Comparison Commands](#8-comparison-commands)
9. [Catalog Commands](#9-catalog-commands)
10. [Special Modes](#10-special-modes)
11. [Error Messages](#11-error-messages)
12. [Examples by Use Case](#12-examples-by-use-case)

---

## 1. Overview

Phase 17 introduces a unified **token-based command syntax** that extends
the existing slash-command system. Every command follows a consistent
grammar that can express scope, document filters, key-value filters,
modes, and the query itself.

### Command Structure

```
@kts [/SCOPE] [/DOC_TYPE] [MODE] [FILTERS] QUERY
```

Where:
- **`@kts`** — Chat participant mention (always required)
- **`/SCOPE`** — Deal scope slug (slash command)
- **`/DOC_TYPE`** — Document type filter within the scope
- **`MODE`** — Retrieval mode: `/compare`, `/diff`, `/aggregate`, `/extract`, `/audit`, `/define`
- **`FILTERS`** — Key-value filters: `/year:2006`, `/issuer:morgan`
- **`QUERY`** — Natural language question

### Backward Compatibility

All existing Phase 12–16 commands continue to work unchanged. Phase 17
adds new token types without breaking existing syntax.

---

## 2. Command Syntax Grammar

### 2.1 Formal Grammar (EBNF-like)

```
command       ::= "@kts" scope_token? doc_filter? mode_token? kv_filters* query_text
scope_token   ::= "/" SLUG
                | "/" SLUG "*"     (* wildcard: all deals matching *)
                | "//"             (* global: all deals *)
doc_filter    ::= "/" DOC_TYPE    (* must follow a scope_token *)
mode_token    ::= "/compare"
                | "/diff"
                | "/aggregate"
                | "/extract"
                | "/audit"
                | "/define"
                | "/summary"
kv_filters    ::= "/" KEY ":" VALUE
query_text    ::= .+              (* natural language query *)

SLUG          ::= [a-z0-9_]+
DOC_TYPE      ::= [A-Z][A-Z0-9_]* (* uppercase: PSA, PROSUPP, INDENTURE *)
KEY           ::= [a-z]+          (* year, issuer, type, collateral *)
VALUE         ::= [^\s]+          (* value — no spaces *)
```

### 2.2 Token Precedence (Disambiguation Rules)

| Rule | Condition | Resolution |
|------|-----------|------------|
| 1 | Token matches a known scope slug | → Scope token |
| 2 | Token is UPPERCASE and follows a scope | → Doc-type filter |
| 3 | Token is UPPERCASE and no scope precedes | → Global doc-type filter (`//DOC_TYPE`) |
| 4 | Token matches `/compare\|/diff\|/aggregate\|/extract\|/audit\|/define\|/summary` | → Mode token |
| 5 | Token contains `:` separator | → Key-value filter |
| 6 | Token ends with `*` after scope | → Wildcard scope |
| 7 | Everything else | → Part of query text |

---

## 3. Quick Reference Card

### 3.1 Single-Scope Queries

| Command | Description |
|---------|-------------|
| `@kts /bear_stearns_2006_he1 what is Realized Loss?` | Search all docs in deal |
| `@kts /bear_stearns_2006_he1 /PSA what is Realized Loss?` | Search only the PSA |
| `@kts /bear_stearns_2006_he1 /define Distribution Date` | Look up a definition |
| `@kts /bear_stearns_2006_he1 /PSA /audit Section 4.01` | Audit a specific section in PSA |
| `@kts /bear_stearns_2006_he1 /extract waterfall rules` | Extract structured data |

### 3.2 Cross-Deal Queries

| Command | Description |
|---------|-------------|
| `@kts //PSA what is Realized Loss?` | Search PSAs across ALL deals |
| `@kts /bear* what is Realized Loss?` | Search all "Bear" deals |
| `@kts /year:2006 what is Realized Loss?` | Search all 2006 deals |

### 3.3 Comparison Commands

| Command | Description |
|---------|-------------|
| `@kts /compare /bear_stearns_2006_he1 /morgan_2006_he2 Realized Loss` | Side-by-side compare |
| `@kts /compare /bear_stearns_2006_he1 /morgan_2006_he2 /PSA Realized Loss` | Compare PSAs only |
| `@kts /diff /bear_stearns_2006_he1 /bear_stearns_2006_he2 waterfall` | Highlight differences |
| `@kts /aggregate //PSA Servicer Advance` | Pattern analysis across all PSAs |

### 3.4 Catalog Commands

| Command | Description |
|---------|-------------|
| `@kts /catalog list` | List all indexed deals |
| `@kts /catalog docs /bear_stearns_2006_he1` | List docs in a deal |
| `@kts /catalog stats` | Show catalog statistics |
| `@kts /catalog search "bear stearns"` | Search catalog |

---

## 4. Detailed Command Reference

### 4.1 Standard Query

**Syntax**: `@kts /SCOPE [/DOC_TYPE] QUERY`

Searches a single deal scope for relevant content. When `/DOC_TYPE` is
specified, only chunks with matching `doc_name_prefix` metadata are searched.

**Parameters**:

| Parameter | Required | Description |
|-----------|----------|-------------|
| `SCOPE` | Yes | Deal scope slug (e.g., `bear_stearns_2006_he1`) |
| `DOC_TYPE` | No | Document type filter (e.g., `PSA`, `PROSUPP`) |
| `QUERY` | Yes | Natural language question |

**Behavior**:
1. Resolve scope → locate `.kts/` directory
2. If `DOC_TYPE` present → add `doc_name_prefix` filter to ChromaDB `where` clause
3. Run graph-first retrieval pipeline
4. Return ranked results with provenance attribution

**Example**:
```
@kts /bear_stearns_2006_he1 /PSA What triggers an Event of Default?
```

**Result Attribution**:
```
📄 Source: PSA_2006-HE1 > Section 7.01(a) > Item 3
📊 Confidence: 0.94 | Strategy: graph_first_legal
```

### 4.2 Definition Lookup

**Syntax**: `@kts /SCOPE [/DOC_TYPE] /define TERM`

Directly looks up a defined term using the definitions graph and glossary.

**Parameters**:

| Parameter | Required | Description |
|-----------|----------|-------------|
| `SCOPE` | Yes | Deal scope slug |
| `DOC_TYPE` | No | Document type filter |
| `TERM` | Yes | Defined term to look up |

**Behavior**:
1. Search `DEFINED_TERM` nodes in graph
2. Look up in definitions section via graph section scoping
3. If `DOC_TYPE` is specified, return only the definition from that document
4. If not specified, return definitions from all documents (with attribution)

**Example**:
```
@kts /bear_stearns_2006_he1 /define Certificate Principal Balance
```

**Result**:
```
📖 Certificate Principal Balance
   PSA_2006-HE1: "Certificate Principal Balance" as of any date...
   PROSUPP_2006-HE1: "Certificate Principal Balance" means...

   ⚠️ Note: Definitions differ between PSA and PROSUPP — see /compare for details.
```

### 4.3 Extraction Mode

**Syntax**: `@kts /SCOPE [/DOC_TYPE] /extract TOPIC`

Extracts structured data from the knowledge base into a table format.

**Example**:
```
@kts /bear_stearns_2006_he1 /PSA /extract waterfall distribution rules
```

### 4.4 Audit Mode

**Syntax**: `@kts /SCOPE [/DOC_TYPE] /audit [SECTION]`

Audits a section or document for anomalies against market baseline.

**Example**:
```
@kts /bear_stearns_2006_he1 /PSA /audit Section 4.01
```

### 4.5 Summary Mode

**Syntax**: `@kts /SCOPE [/DOC_TYPE] /summary`

Generates a deal or document summary.

**Example**:
```
@kts /bear_stearns_2006_he1 /PSA /summary
```

---

## 5. Scope Tokens

### 5.1 Single Scope

```
/bear_stearns_2006_he1
```

Resolves to exactly one deal folder. The slug is derived from the folder
name via `slugify()`: lowercase, spaces/hyphens to underscores, strip
special characters.

### 5.2 Wildcard Scope

```
/bear*
```

The trailing `*` triggers glob matching. Expands to all deal slugs
matching the pattern. Useful for searching related deals:

- `/bear*` → All Bear Stearns deals
- `/morgan*2006*` → All Morgan Stanley 2006 deals

### 5.3 Global Scope (`//`)

```
//PSA
```

The double-slash prefix means "all deals." When followed by a `DOC_TYPE`,
it searches that document type across every indexed deal.

When used alone:
```
// what is Realized Loss?
```
Searches ALL deals, ALL documents — equivalent to federated search.

### 5.4 No Scope (Fallback)

```
@kts what is Realized Loss?
```

No scope specified. Behavior depends on configuration:
- If only one deal is indexed → search that deal
- If multiple deals → prompt user to specify scope
- If `knowledgeSourceRoot` has a legacy `.kts/` → search global

---

## 6. Document Filter Tokens

### 6.1 Standard Doc-Type Filter

```
/PSA
/PROSUPP
/INDENTURE
/SAA
```

Must appear after a scope token. Uppercase convention signals doc-type
(vs. scope slugs which are lowercase).

### 6.2 Available Doc Types

Doc types are **not hard-coded**. They are discovered at ingestion time
and stored in the catalog. Common examples:

| Doc Type | Full Name |
|----------|-----------|
| `PSA` | Pooling and Servicing Agreement |
| `PROSUPP` | Prospectus Supplement |
| `INDENTURE` | Indenture Agreement |
| `SAA` | Sale and Assignment Agreement |
| `MLPA` | Mortgage Loan Purchase Agreement |
| `TA` | Trust Agreement |
| `SERVICING` | Servicing Agreement |
| `PROSPECTUS` | Base Prospectus |

### 6.3 Doc-Type Resolution

When a doc-type token is parsed, it is resolved to the `doc_name_prefix`
stored in ChromaDB metadata:

```
/PSA  →  catalog.get_document(scope, doc_type="PSA")
      →  doc_name_prefix = "PSA_2006-HE1"
      →  ChromaDB where: {"doc_name_prefix": "PSA_2006-HE1"}
```

---

## 7. Key-Value Filter Tokens

### 7.1 Syntax

```
/key:value
```

Key-value tokens provide structured filtering without natural language
ambiguity.

### 7.2 Supported Keys

| Key | Type | Description | Example |
|-----|------|-------------|---------|
| `year` | Integer | Vintage year of deal | `/year:2006` |
| `issuer` | String | Primary issuer (fuzzy) | `/issuer:morgan` |
| `type` | String | Deal type | `/type:RMBS` |
| `collateral` | String | Collateral type | `/collateral:HELOC` |
| `series` | String | Series identifier | `/series:2006-HE1` |

### 7.3 Multiple Filters

Multiple key-value filters are combined with AND semantics:

```
@kts /year:2006 /issuer:bear /type:RMBS what is Realized Loss?
```

This resolves to:
```python
catalog.structured_search(
    vintage_year=2006,
    issuer="bear",
    deal_type="RMBS",
)
```

### 7.4 Key-Value + Scope Combination

Key-value filters can be combined with explicit scopes for additional
filtering:

```
@kts /bear_stearns_2006_he1 /collateral:HELOC /PSA what is Realized Loss?
```

---

## 8. Comparison Commands

### 8.1 `/compare` — Side-by-Side Comparison

**Syntax**: `@kts /compare /SCOPE1 /SCOPE2 [/DOC_TYPE] CONCEPT`

Retrieves the same concept from two or more scopes and generates a
side-by-side comparison table with divergence analysis.

**Parameters**:

| Parameter | Required | Description |
|-----------|----------|-------------|
| `SCOPE1` | Yes | First deal scope |
| `SCOPE2` | Yes | Second deal scope |
| `DOC_TYPE` | No | Constrain comparison to one doc type |
| `CONCEPT` | Yes | Concept or term to compare |

**Output Format**:

```markdown
## Comparison: "Realized Loss" across 2 deals

| Aspect | Bear Stearns 2006-HE1 | Morgan Stanley 2006-HE2 |
|--------|----------------------|------------------------|
| Definition | "Realized Loss" means... | "Realized Loss" means... |
| Source | PSA § 1.01 | PSA § 1.01 |
| Key Difference | Includes modification losses | Excludes modification losses |

### Divergence Summary
- ⚠️ Bear Stearns includes "modification losses" in Realized Loss;
  Morgan Stanley does not.
- Both define the timing as "with respect to each Distribution Date."
```

**Variations**:

```
# Compare specific doc types
@kts /compare /bear_2006_he1 /morgan_2006_he2 /PSA Servicer Advance

# Compare across wildcard
@kts /compare /bear* Realized Loss

# Compare with global doc-type filter
@kts /compare //PSA Realized Loss
```

### 8.2 `/diff` — Difference Detection

**Syntax**: `@kts /diff /SCOPE1 /SCOPE2 [/DOC_TYPE] TOPIC`

Specialized comparison that focuses on **material differences** (red flags).
Uses the ContradictionDetector to find contradictions and the AnomalyScorer
to assess severity.

**Output Format**:

```markdown
## Diff: Waterfall provisions

### 🔴 Material Differences
1. **Interest Waterfall Priority** (Severity: HIGH)
   - Bear Stearns: Class A-1 → A-2 → A-3 → B → C
   - Morgan Stanley: Class A-1 → A-2 → B → A-3 → C
   - ⚠️ Subordination structure differs materially.

2. **Trigger Event Threshold** (Severity: MEDIUM)
   - Bear Stearns: 60+ days delinquent
   - Morgan Stanley: 90+ days delinquent

### ✅ Same Across Both
- Distribution Date definition
- Servicer Fee calculation
```

### 8.3 `/aggregate` — Pattern Analysis

**Syntax**: `@kts /aggregate [SCOPE_PATTERN|//DOC_TYPE] TOPIC`

Analyzes a concept across many deals to identify patterns and outliers.

**Output Format**:

```markdown
## Aggregate Analysis: Servicer Advance definition (across 15 PSAs)

### Market Standard (12/15 deals)
- Servicer shall make advances of delinquent P&I
- Subject to non-recoverability determination
- Advance obligations terminate upon deal event of default

### Outliers (3/15 deals)
- ⚠️ **Bear Stearns 2006-HE1**: No advance obligation for modified loans
- ⚠️ **Morgan 2007-HE3**: Advance cap of 3% of outstanding balance
- ⚠️ **Lehman 2006-HE4**: Advance obligation survives deal EOD

### Pattern Summary
| Feature | Standard | % Adoption |
|---------|----------|-----------|
| P&I advance required | Yes | 100% |
| Non-recoverability out | Yes | 93% |
| Advance survives EOD | No | 80% |
| Advance cap | None | 87% |
```

---

## 9. Catalog Commands

### 9.1 `/catalog list`

```
@kts /catalog list
```

**Output**:
```
📁 Indexed Deals (3 deals, 12 documents)

1. Bear Stearns 2006-HE1 (bear_stearns_2006_he1)
   📄 4 docs: PSA, PROSUPP, INDENTURE, SAA
   📊 1,045 chunks | 120 definitions | 85 rules
   📅 Indexed: 2025-07-14T10:30:00Z

2. Morgan Stanley 2006-HE2 (morgan_stanley_2006_he2)
   📄 3 docs: PSA, PROSUPP, INDENTURE
   📊 890 chunks | 98 definitions | 72 rules
   📅 Indexed: 2025-07-14T11:15:00Z

3. Lehman 2006-HE4 (lehman_2006_he4)
   📄 5 docs: PSA, PROSUPP, INDENTURE, SAA, SERVICING
   📊 1,320 chunks | 145 definitions | 110 rules
   📅 Indexed: 2025-07-14T12:00:00Z
```

### 9.2 `/catalog docs`

```
@kts /catalog docs /bear_stearns_2006_he1
```

**Output**:
```
📁 Bear Stearns 2006-HE1 — Documents

| Doc Type  | File                    | Chunks | Definitions | Rules | Sections |
|-----------|------------------------|--------|-------------|-------|----------|
| PSA       | PSA_2006-HE1.pdf       | 450    | 120         | 85    | 42       |
| PROSUPP   | ProSupp_2006-HE1.pdf   | 320    | 45          | 30    | 28       |
| INDENTURE | Indenture_2006-HE1.pdf | 180    | 30          | 22    | 18       |
| SAA       | SAA_2006-HE1.pdf       | 95     | 15          | 10    | 8        |

Total: 1,045 chunks | 210 definitions | 147 rules | 96 sections
```

### 9.3 `/catalog stats`

```
@kts /catalog stats
```

**Output**:
```
📊 Knowledge Base Statistics

Deals:          3
Documents:      12
Total Chunks:   3,255
Definitions:    363
Rules:          267
Graph Nodes:    4,820
Graph Edges:    12,450

Vintage Range:  2006 – 2006
Doc Types:      INDENTURE, PROSUPP, PSA, SAA, SERVICING
Issuers:        Bear Stearns, Lehman, Morgan Stanley
```

### 9.4 `/catalog search`

```
@kts /catalog search "bear stearns"
```

Uses FTS5 search to find matching deals.

---

## 10. Special Modes

### 10.1 Available Modes

| Mode | Description | Backend Method |
|------|-------------|---------------|
| `/define` | Definition lookup | Definition-focused retrieval |
| `/extract` | Structured extraction | Phase 14.3 extraction engine |
| `/audit` | Anomaly detection | AnomalyScorer + cross-baseline |
| `/summary` | Deal/doc summary | Phase 14.2 summary engine |
| `/compare` | Cross-deal comparison | ComparisonMode + LLM |
| `/diff` | Difference detection | ContradictionDetector enhanced |
| `/aggregate` | Pattern analysis | New AggregationEngine |

### 10.2 Mode + Doc Filter Interaction

Modes work seamlessly with document filters:

```
@kts /bear_stearns_2006_he1 /PSA /extract waterfall rules
@kts /bear_stearns_2006_he1 /PSA /audit Section 4.01
@kts /bear_stearns_2006_he1 /INDENTURE /define Trust Fund
```

### 10.3 Mode + Wildcard Interaction

Modes can be combined with wildcard scopes for powerful cross-deal analysis:

```
# Aggregate PSA definitions across all deals
@kts /aggregate //PSA Servicer Advance

# Diff PSAs between two specific deals
@kts /diff /bear_2006_he1 /morgan_2006_he2 /PSA waterfall

# Audit a section across all Bear Stearns deals
@kts /bear* /PSA /audit Section 4.01
```

---

## 11. Error Messages

### 11.1 Scope Errors

| Error | Message | Resolution |
|-------|---------|------------|
| Unknown scope | `Scope 'xyz' not found. Available: bear_stearns_2006_he1, morgan_2006_he2. Use /catalog list.` | Check spelling or run `/catalog list` |
| Not indexed | `Scope 'abc' exists but has not been indexed. Run: kts ingest <path>` | Ingest the deal first |
| Too many wildcard matches | `Wildcard '/bear*' matched 150 scopes — max is 100. Narrow your pattern.` | Use more specific pattern |

### 11.2 Doc-Type Errors

| Error | Message | Resolution |
|-------|---------|------------|
| Unknown doc type | `Doc type 'XYZ' not found in bear_stearns_2006_he1. Available: PSA, PROSUPP, INDENTURE, SAA.` | Check available doc types |
| No doc type in global | `Doc type 'MLPA' not found in any indexed deal.` | Verify the doc type exists |

### 11.3 Comparison Errors

| Error | Message | Resolution |
|-------|---------|------------|
| Single scope for compare | `/compare requires at least 2 scopes. Usage: /compare /scope1 /scope2 concept` | Add a second scope |
| No results in scope | `No results for 'Realized Loss' in morgan_2006_he2. Comparison limited to 1/2 scopes.` | Verify content exists |

### 11.4 Filter Errors

| Error | Message | Resolution |
|-------|---------|------------|
| Invalid key | `Unknown filter key 'status'. Valid: year, issuer, type, collateral, series.` | Use a valid key |
| No results | `No deals match: year=2025, issuer=bear. Try broadening your filters.` | Relax filters |

---

## 12. Examples by Use Case

### Use Case 1: Single Document Search

> "I want to search only the PSA of Bear Stearns 2006-HE1 for the definition
> of Realized Loss."

```
@kts /bear_stearns_2006_he1 /PSA what is Realized Loss?
```

### Use Case 2: All Documents in a Deal

> "Search all documents in Bear Stearns 2006-HE1."

```
@kts /bear_stearns_2006_he1 what triggers an Event of Default?
```

### Use Case 3: Same Doc Type Across All Deals

> "Search the PSA in every deal for Servicer Advance definition."

```
@kts //PSA what is Servicer Advance?
```

### Use Case 4: Wildcard Scope

> "Search all Bear Stearns deals for waterfall rules."

```
@kts /bear* what are the waterfall distribution rules?
```

### Use Case 5: Wildcard + Doc Type

> "Search PSAs across all Bear Stearns deals."

```
@kts /bear* /PSA what is the loss allocation methodology?
```

### Use Case 6: Compare Two Deals (Same Concept)

> "Compare how 'Realized Loss' is defined in Bear Stearns 2006-HE1
> vs. Morgan Stanley 2006-HE2."

```
@kts /compare /bear_stearns_2006_he1 /morgan_stanley_2006_he2 Realized Loss
```

### Use Case 7: Compare Two Deals (Same Doc Type)

> "Compare the PSA waterfall rules between two deals."

```
@kts /compare /bear_stearns_2006_he1 /morgan_stanley_2006_he2 /PSA waterfall distribution
```

### Use Case 8: Define Across All Documents

> "Show me how Distribution Date is defined across all docs in this deal."

```
@kts /bear_stearns_2006_he1 /define Distribution Date
```

### Use Case 9: Audit One Document

> "Audit Section 4.01 of the PSA for anomalies."

```
@kts /bear_stearns_2006_he1 /PSA /audit Section 4.01
```

### Use Case 10: Diff Within a Deal

> "What are the differences between the PSA and Indenture regarding
> Events of Default?"

```
@kts /diff /bear_stearns_2006_he1/PSA /bear_stearns_2006_he1/INDENTURE Events of Default
```

### Use Case 11: Diff Across Deals

> "Show me the material differences in PSA loss allocation between
> Bear Stearns and Morgan Stanley."

```
@kts /diff /bear_stearns_2006_he1 /morgan_stanley_2006_he2 /PSA loss allocation
```

### Use Case 12: Catalog / List Deals

> "What deals are indexed?"

```
@kts /catalog list
```

### Use Case 13: List Documents in a Deal

> "What documents are in the Bear Stearns deal?"

```
@kts /catalog docs /bear_stearns_2006_he1
```

### Use Case 14: Aggregate Pattern Analysis

> "How is Servicer Advance defined across all PSAs? Show me the
> market standard and any outliers."

```
@kts /aggregate //PSA Servicer Advance definition
```

---

*End of Document — 06_COMMAND_REFERENCE.md*
