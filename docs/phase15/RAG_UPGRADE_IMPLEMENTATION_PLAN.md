# Phase 15: Cross-Deal Intelligence & Anomaly Detection — Implementation Plan

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## 1. Motivation — The Premium Intelligence Tier

### 1.1 The Problem No Other Tool Solves

Every tool an analyst uses today answers questions about *one document at a time*. Word. Acrobat. Even competitive AI tools are single-document or single-query. The intelligence gap between "what does this clause say" and "how does this clause compare across 200 deals" is where KTS becomes a fundamentally different category of product.

Phase 15 delivers three capabilities that exist nowhere else in the analyst's current workflow:

1. **Cross-Deal Contradiction Detection**: "The definition of 'Servicer Advance' in this deal explicitly excludes Delinquency Advances. In your 2005 deal with the same issuer, it includes them. This is a material divergence."

2. **Non-Standard Clause Flagging**: "This indemnification clause deviates from standard market language for HELOC-backed PSAs. Flag: unusual limitations on trustee liability."

3. **Cross-Deal Comps (/compare)**: "Show me the Servicer Advance definition from all Bear Stearns deals in the knowledge base, side by side."

### 1.2 Why Phase 15 Requires Phase 12

All three capabilities require isolated per-deal embedding spaces (Phase 12). Without named scopes:
- Contradiction detection cannot compare "this deal" vs "that deal" — there is no "this" or "that", only one blended space
- Anomaly detection cannot establish a "standard" baseline separate from the deal under review  
- Cross-deal comps cannot pull the same concept from N isolated deal collections

Phase 12 is the architectural prerequisite. Phase 15 is the intelligence that the architecture enables.

---

## 2. Implementation Order

| Order | Increment | Impact | Risk | Rationale |
|-------|-----------|--------|------|-----------|
| **15.1** | Cross-deal comparison (/compare command) | VERY HIGH | MEDIUM | Requires Phase 12 scopes + Phase 11 /compare command. Side-by-side concept retrieval. |
| **15.2** | Contradiction detection (two-deal) | HIGH | MEDIUM | Pair-wise: retrieve same concept from scope A and scope B, run contradiction prompt. |
| **15.3** | Market baseline corpus + anomaly scoring | HIGH | HIGH | Requires a "standard language" reference corpus. Most complex increment. |
| **15.4** | Full anomaly detection (/audit with anomaly flags) | HIGH | MEDIUM | Depends on 15.3 baseline. Run anomaly score on all retrieved clauses. |

---

## 3. Increment 15.1 — Cross-Deal Comparison (/compare)

### 3.1 Command Syntax

```
@kts /compare [concept]  across  /scope1  /scope2  ... /scopeN

Examples:
@kts /compare  Servicer Advance definition  across  /bear_stearns_2006_HE1  /bear_stearns_2006_HE2
@kts /compare  Optional Termination Date  across  /bear_stearns_2006_HE1  /wshfc_2025_1
```

Or using the deal catalog for smart scoping:
```
@kts /compare  DSCR Loan definition  across all bear stearns deals
```
(Phase 12 federated routing resolves "all bear stearns deals" to the relevant scopes)

### 3.2 Retrieval Strategy

For N scopes:
1. Run the same concept query against each scope independently (parallelized)
2. Extract the top-2 chunks per scope (definition-specific retrieval)
3. Assemble a comparison prompt:

```python
COMPARISON_PROMPT = """
The following are definitions of "{concept}" from {n} different legal documents.
Compare them:
1. Identify what is the same across all versions
2. Identify meaningful differences (not just wording — substantive legal differences)
3. Flag any definition that is materially narrower or broader than the others
4. If any definition is missing a component present in others, flag it

{per_scope_definitions}

Output as a markdown table followed by a bullet-point divergence summary.
"""
```

### 3.3 Output Format

```
## Comparison: "Determination Date" across 3 deals

| Deal | Definition | Source |
|------|-----------|--------|
| Bear Stearns 2006-HE1 | 25th day of each calendar month | Section 1.01 |
| Bear Stearns 2006-HE2 | 20th day of each calendar month | Section 1.01 |
| WSHFC 2025-1 | Business Day nearest to 20th | Section 2.01 |

**Divergences:**
- ⚠️ Day of month differs: HE1 uses 25th, HE2 and WSHFC use 20th
- ⚠️ Business Day adjustment present in WSHFC but absent in both Bear Stearns deals
- The core structure (monthly cycle) is consistent across all three
```

---

## 4. Increment 15.2 — Contradiction Detection (Two-Deal)

### 4.1 Contradiction vs. Divergence

| Type | Definition | Example |
|------|-----------|---------|
| **Divergence** | Definitions differ but are not mutually contradictory | HE1 says 25th, HE2 says 20th |
| **Contradiction** | Definitions conflict on a binary dimension | HE1 excludes Delinquency Advances; HE2 includes them |
| **Missing term** | Concept defined in one deal, absent in another | HE1 defines "Servicer Termination Event"; HE2 has no such term |

Contradiction detection focuses on binary-dimension conflicts — the genuinely high-value finding.

### 4.2 Contradiction Detection Prompt

```python
CONTRADICTION_PROMPT = """
You are comparing how "{concept}" is defined in two legal documents.

Document A ({scope_a}):
{definition_a}

Document B ({scope_b}):
{definition_b}

Answer ONLY with a JSON object:
{
  "contradicts": true/false,
  "contradiction_type": "inclusion/exclusion | scope | condition | party | amount | null",
  "summary": "one sentence describing the contradiction, or null if none",
  "severity": "material | minor | null"
}
"""
```

### 4.3 When to Run Automatically

Contradiction detection runs automatically when:
- User uses /compare (always)
- User asks "do these deals agree on [X]?" (intent classification)
- Phase 9 critique loop detects a cross-reference to another ingested deal

It does NOT run automatically on every query — too expensive and usually unnecessary.

---

## 5. Increment 15.3 — Market Baseline Corpus

### 5.1 What "Standard Language" Means

For HELOC and subprime ABS deals (the primary KTS use case), market standard language for key clauses is well-established. The same template language appears across hundreds of deals from the same era. Deviations from this template are meaningful.

The baseline corpus is a curated collection of "standard" clause text for ~50 clause types, derived from the most common language across ingested deals:

```python
@dataclass
class BaselineClause:
    clause_type: str          # "servicer_advance_definition"
    deal_type: str            # "PSA_HELOC"
    standard_text: str        # the modal text across N deals
    variant_texts: list[str]  # known acceptable variants
    deviation_signals: list[str]  # patterns that signal non-standard language
    source_deals: list[str]   # deals this baseline was derived from
```

### 5.2 Baseline Construction

Baseline is constructed from ingested deals by KTS itself, as a one-time setup operation per deal type:

```
@kts /admin  build-baseline  from all PSA_HELOC scopes
```

1. Retrieve the same 50 clause types from all ingested PSA_HELOC deals
2. Find the modal text for each clause type (most common phrasing)
3. Store as `baseline_corpus/PSA_HELOC/[clause_type].json`

This is a one-time cost. The baseline improves as more deals are ingested.

---

## 6. Increment 15.4 — Anomaly Detection (/audit with Anomaly Flags)

### 6.1 Anomaly Score Computation

For each retrieved clause, compute an anomaly score against the baseline:

```python
def compute_anomaly_score(clause_text: str, clause_type: str, deal_type: str) -> AnomalyResult:
    baseline = load_baseline(clause_type, deal_type)
    
    # Semantic similarity to standard text
    sim_score = cosine_similarity(embed(clause_text), embed(baseline.standard_text))
    
    # Deviation signal detection (keyword/pattern)
    deviation_signals_found = [
        sig for sig in baseline.deviation_signals 
        if sig.lower() in clause_text.lower()
    ]
    
    anomaly_score = 1.0 - sim_score  # 0 = identical to standard, 1 = completely different
    
    return AnomalyResult(
        score=anomaly_score,
        is_anomalous=anomaly_score > 0.35 or len(deviation_signals_found) > 0,
        deviation_signals=deviation_signals_found,
        severity="high" if anomaly_score > 0.6 else "medium" if anomaly_score > 0.35 else "low"
    )
```

### 6.2 /audit Output with Anomaly Flags

```
## Audit: Servicer Obligations — Bear Stearns 2006-HE1

### Section 3.01 — Servicer Duties
✅ Standard language (similarity: 0.94)
> "The Servicer shall service and administer the Mortgage Loans..."

### Section 3.04 — Servicer Advances  
⚠️ **Non-standard** (similarity: 0.61 | Severity: Medium)
> "The Servicer shall not be obligated to make any Delinquency Advance..."
> 
> *Standard language for this clause type includes Delinquency Advances. 
> This deal explicitly excludes them — material deviation from market standard.*

### Section 5.01 — Trustee Indemnification
🔴 **Significant deviation** (similarity: 0.38 | Severity: High)
> [clause text]
> *This indemnification scope is materially narrower than market standard for 
> PSA-HELOC deals. Standard language requires indemnification for gross negligence; 
> this clause limits to willful misconduct only.*
```

This is the feature that replaces 4 hours of manual clause review.

---

## 7. Files Changed

| File | Change Type | Increment |
|------|------------|-----------|
| `backend/retrieval/scope_router.py` | Modified | 15.1 (multi-scope fan-out) |
| `backend/retrieval/comparison_mode.py` | New | 15.1, 15.2 |
| `backend/retrieval/contradiction_detector.py` | New | 15.2 |
| `backend/retrieval/baseline_corpus.py` | New | 15.3 |
| `backend/retrieval/anomaly_scorer.py` | New | 15.4 |
| `extension/chat/participant.js` | Modified | 15.1 (table rendering), 15.4 (anomaly badge rendering) |
| `config/` | New folder | 15.3 (baseline corpus JSON files) |

---

## 8. Success Metrics

| Metric | Baseline | Target (Phase 15) |
|--------|----------|------------------|
| Cross-deal comparison time (analyst manual) | 3-4 hours | <30 seconds |
| Contradiction detection precision | N/A | >85% |
| Anomaly detection recall (known deviations) | N/A | >80% |
| False positive rate (anomaly flags on standard clauses) | N/A | <10% |
| Analyst deal review time reduction | Baseline | >60% estimated |
