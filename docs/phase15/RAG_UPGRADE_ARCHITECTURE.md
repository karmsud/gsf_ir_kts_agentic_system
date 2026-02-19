# Phase 15: Cross-Deal Intelligence & Anomaly Detection — Architecture Document

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## 1. Architectural Principles

| Decision | Rationale |
|----------|-----------|
| **Cross-deal = multi-scope fan-out** | /compare queries hit N scopes in parallel. Each scope is queried independently (Phase 12 foundation). |
| **Contradiction detection is binary** | Don't ask "are these similar?" Ask "on the dimension of [X], do these conflict yes/no?" Binary prompts are far more reliable. |
| **Baseline corpus is derived from ingested deals** | No external data source. Standard language is what the modal text across ingested deals says it is. Self-improving as more deals are added. |
| **Anomaly score = semantic distance from baseline** | Cosine distance between clause embedding and baseline embedding. Augmented by deviation signal pattern matching. |
| **Anomaly detection is opt-in per query** | Not run on every /query. Runs on /audit and when user explicitly asks for clause review. |
| **Exceptions-safe fan-out** | Failed scope search (corrupt index, timeout) logs and skips. Does not fail the entire cross-deal query. |

---

## 2. Layer Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                   CROSS-SCOPE ORCHESTRATION                       │
│   backend/retrieval/scope_router.py   MODIFIED 15.1             │
│   • Multi-scope fan-out (asyncio.gather)                         │
│   • Results merge + cross-encoder rerank                          │
│   • Exceptions-safe (skip failed scopes)                          │
├──────────────────────────────────────────────────────────────────┤
│                   COMPARISON INTELLIGENCE LAYER                   │
│   backend/retrieval/comparison_mode.py     NEW 15.1, 15.2       │
│   • Side-by-side concept retrieval from N scopes                  │
│   • Divergence classification (equivalence / divergence / missing)│
│   • Markdown table assembly                                       │
│                                                                   │
│   backend/retrieval/contradiction_detector.py  NEW 15.2         │
│   • Pairwise contradiction scoring                                │
│   • Binary-dimension prompt (include/exclude, scope, condition)   │
│   • severity: material | minor | null                             │
├──────────────────────────────────────────────────────────────────┤
│                   ANOMALY INTELLIGENCE LAYER                      │
│   backend/retrieval/baseline_corpus.py    NEW 15.3              │
│   • Baseline construction from ingested deal corpus               │
│   • Per-clause-type, per-deal-type baseline storage               │
│   • Deviation signal pattern catalog                              │
│                                                                   │
│   backend/retrieval/anomaly_scorer.py     NEW 15.4              │
│   • Semantic similarity: clause vs. baseline                      │
│   • Deviation signal pattern matching                             │
│   • AnomalyResult: score, is_anomalous, signals, severity        │
├──────────────────────────────────────────────────────────────────┤
│                   PRESENTATION LAYER                              │
│   extension/chat/participant.js     MODIFIED 15.1, 15.4         │
│   • Comparison table rendering                                    │
│   • Anomaly badge rendering (✅ / ⚠️ / 🔴 per clause)           │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Cross-Deal Comparison Data Flow

```
@kts /compare  Servicer Advance definition  across  /he1  /he2  /wshfc

    │
    ├─ parse scopes: [he1, he2, wshfc]
    ├─ parse concept: "Servicer Advance definition"
    │
    ├─ Fan out (parallel):
    │     search /he1  → top 2 chunks (Servicer Advance)
    │     search /he2  → top 2 chunks (Servicer Advance)  
    │     search /wshfc → top 2 chunks (Servicer Advance)
    │
    ├─ Assemble comparison prompt with per-scope definitions
    │
    ├─ LLM generates:
    │     - Equivalence summary
    │     - Divergence bullets
    │     - Material differences flagged
    │
    ├─ Contradiction detector runs pairwise:
    │     HE1 vs HE2 → {"contradicts": false, "summary": "differ on day only"}
    │     HE1 vs WSHFC → {"contradicts": true, "type": "inclusion/exclusion",
    │                      "summary": "WSHFC includes Delinquency Advances, HE1 excludes", 
    │                      "severity": "material"}
    │
    └─ Output: comparison table + contradiction flag + divergence summary
```

---

## 4. Baseline Corpus Structure

```
config/baseline_corpus/
    PSA_HELOC/
        servicer_advance_definition.json
        determination_date_definition.json
        trustee_indemnification.json
        optional_termination.json
        ... (~50 clause types)
    PSA_SUBPRIME/
        ...
    INDENTURE/
        ...
```

Each JSON file:
```json
{
  "clause_type": "servicer_advance_definition",
  "deal_type": "PSA_HELOC",
  "standard_text": "The Servicer shall make Servicer Advances, including Delinquency Advances...",
  "variant_texts": ["The Servicer shall advance..."],
  "deviation_signals": ["shall not be obligated", "excluding", "no obligation to advance"],
  "source_deals": ["bear_stearns_2006_HE1", "bear_stearns_2006_HE2"],
  "derived_date": "2026-02-18",
  "sample_size": 12
}
```

---

## 5. Anomaly Scoring Pipeline

```
Input: clause_text (retrieved from audit query)
       clause_type (classified from section heading)
       deal_type (from scope metadata)

Step 1: Load baseline for clause_type + deal_type
         → baseline.standard_text, baseline.deviation_signals

Step 2: Semantic similarity
         sim = cosine_similarity(embed(clause_text), embed(baseline.standard_text))
         raw_anomaly_score = 1.0 - sim

Step 3: Deviation signal scan
         signals_found = [s for s in baseline.deviation_signals if s in clause_text.lower()]
         signal_boost = 0.15 * len(signals_found)

Step 4: Final score
         anomaly_score = min(1.0, raw_anomaly_score + signal_boost)

Step 5: Severity classification
         score > 0.60 → HIGH (🔴)
         score > 0.35 → MEDIUM (⚠️)
         score > 0.20 → LOW (🔵)
         score <= 0.20 → STANDARD (✅)
```

---

## 6. Phase 15 Completes the Deal Intelligence Platform

With Phase 15, KTS transforms from a retrieval system into a deal intelligence platform:

| Capability | Phase |
|-----------|-------|
| Answer questions about a document | Phase 1-7 |
| Answer with high recall and precision | Phase 8-9 |
| Answer with conversation context | Phase 10 |
| Use VS Code natively (references, follow-ups, modes) | Phase 11 |
| Isolated per-deal scope with folder commands | Phase 12 |
| Confidence-scored, gap-flagged, HyDE-enhanced retrieval | Phase 13 |
| Session cache, temporal reasoning, structured extraction | Phase 14 |
| **Cross-deal comparison, contradiction detection, anomaly flagging** | **Phase 15** |

Phase 15 is not the end — it is the first tier of capabilities that make KTS irreplaceable. The analyst who has used it for 30 minutes cannot go back to reading documents manually.
