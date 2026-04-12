# Enterprise RAG Test Diagnosis — Misses & Partials Analysis

**Date:** 2026-02-17 — Updated from latest `enterprise_test_results.json`  
**Summary:** 100 queries tested — **79 FULL HITS (rank 1) | 15 PARTIAL HITS (ranks 2-3) | 6 MISSES**  
**Scores:** top1=**79%** | top3=**94%** | top5=**94%** | avg_latency=~600ms

> **Note:** Major improvement from previous run (64 hits / 19 misses). Cross-corpus contamination resolved. Chunk deduplication working. Remaining failures are chunking and evidence formatting issues.

---

## Fix Category Summary

| Fix Category | Count | Queries |
|---|---|---|
| **Wrong doc at rank 1** | 6 | Q032, Q057, Q059, Q100 (misses), Q013, Q067 (partials) |
| **Right doc, related-but-wrong chunk at rank 1** | 8 | Q016, Q018, Q021, Q046, Q078, Q081, Q087, Q098 (partials) |
| **Right doc, overview chunk at rank 1** | 4 | Q015, Q035, Q064, Q076 (partials) |
| **Evidence terms too strict** | 3 | Q033, Q069 (misses), Q043 (partial) |
| **Data not in corpus** | 0 | — |
| **TOTAL** | **21** | |

### What Each Fix Addresses

| Priority | Fix | Effort | Impact |
|---|---|---|---|
| **1** | **Evidence relaxation** (Q033, Q069, Q043) | Low — update 3 golden query entries | +3 top-1 (2 misses→hits, 1 partial→hit) → **82%** |
| **2** | **Keyword/section boost in re-ranker** (8 partials) | Medium — boost chunks containing query key terms | +8 top-1 → **90%** |
| **3** | **Overview-chunk demotion / drill-down** (4 partials) | Medium — penalize intro/title chunks for specific queries | +4 top-1 → **94%** |
| **4** | **Cross-doc routing / doc-type awareness** (6 queries) | High — definition queries→Glossary, tech→Architecture | +6 top-1 → **100%** |

---

## 1. MISS Analysis (6 Queries)

### MISS 1: ENT-Q032 — "What Kubernetes version is used in the ESP platform?"

| Field | Value |
|---|---|
| **Expected** | ESP_Architecture §2.2: `"Kubernetes 1.29"` |
| **must_include** | `1.29` |
| **Rank 1** | ESP_Glossary chunk_0 (title/overview) — score 0.979 |
| **Rank 2** | ESP_Glossary chunk_2 |
| **Rank 3** | ESP_Architecture chunk_2 (Component Summary table — mentions K8s hosting, not version) |
| **Corpus verified** | ESP_Architecture.md line 65: `"Orchestration: Kubernetes 1.29"` ✅ |
| **Root Cause** | **Wrong doc at rank 1.** Glossary mentions "Kubernetes" generically. ESP_Architecture §2.2 has the version but the specific chunk didn't reach top-3. |
| **Fix Category** | Wrong doc at rank 1 → cross-doc routing needed |

---

### MISS 2: ENT-Q033 — "What is the size of the analytics database in the ESP platform?"

| Field | Value |
|---|---|
| **Expected** | ESP_Architecture §2.3: `"datadesk_analytics \| 2.3 TB"` |
| **must_include** | `2.3TB` |
| **Rank 1** | **ESP_Architecture chunk_4 (§2.3 Database Architecture)** — score 0.895 |
| **Rank 2** | ESP_Architecture chunk_1 |
| **Corpus verified** | ESP_Architecture.md line 77: `"datadesk_analytics \| 2.3 TB \| 147 datasets"` ✅ |
| **Root Cause** | **Evidence terms too strict.** Rank 1 IS the correct chunk. But `must_include_terms: ["2.3TB"]` fails because corpus has `"2.3 TB"` (with space). Retrieval is already correct. |
| **Fix Category** | Evidence terms too strict — update `"2.3TB"` → `["2.3 TB"]` |

---

### MISS 3: ENT-Q057 — "What is the definition of RPO?"

| Field | Value |
|---|---|
| **Expected** | ESP_Glossary line 137: `"RPO (Recovery Point Objective) — Maximum acceptable data loss…"` |
| **must_include** | `Recovery Point Objective` |
| **Rank 1** | ESP_Incident_Response_SOP section-level chunk — score **0.00005** (near zero!) |
| **Rank 2** | OpsFlow_FAQ section-level chunk |
| **Rank 3** | ESP_Architecture section-level chunk |
| **Rank 4** | ESP_Glossary section-level chunk (correct doc, wrong rank) |
| **Corpus verified** | ESP_Glossary.md line 137: `"RPO (Recovery Point Objective)"` ✅ |
| **Root Cause** | **Wrong doc at rank 1.** All 5 returned results are section-level summary chunks (`section_doc_*` IDs). The cross-encoder scored them near zero. The generic 3-word query "definition of RPO" failed to pull the specific glossary content chunk. |
| **Fix Category** | Wrong doc at rank 1 → definition queries should route to REFERENCE docs |

---

### MISS 4: ENT-Q059 — "What is PKI in the context of SecureVault?"

| Field | Value |
|---|---|
| **Expected** | ESP_Glossary line 127: `"PKI (Public Key Infrastructure) — certificate management infrastructure managed by SecureVault's PKI engine"` |
| **must_include** | `Public Key Infrastructure` |
| **Rank 1** | SecureVault_UserGuide chunk_0 (intro/overview) — score 0.701 |
| **Rank 2** | SecureVault_Replication_RCA chunk_0 |
| **Rank 3** | SecureVault_UserGuide chunk_7 |
| **Corpus verified** | ESP_Glossary.md line 127: `"PKI (Public Key Infrastructure)"` ✅ |
| **Root Cause** | **Wrong doc at rank 1.** The word "SecureVault" in the query biases the retriever toward SecureVault docs. The PKI definition in ESP_Glossary didn't make top-3 at all. |
| **Fix Category** | Wrong doc at rank 1 → acronym/definition queries should boost Glossary |

---

### MISS 5: ENT-Q069 — "When was the SecureVault seal event incident?"

| Field | Value |
|---|---|
| **Expected** | ESP_Incident_Response_SOP line 279: `"SecureVault Seal Event \| 2025-04-18 \| P1 \| 22 min"` |
| **must_include** | `April`, `2025` |
| **Rank 1** | **ESP_Incident_Response_SOP chunk_18 (Appendix: Recent Major Incidents)** — score 0.983 |
| **Rank 2** | SecureVault_Replication_RCA chunk_4 |
| **Corpus verified** | ESP_Incident_Response_SOP.md line 279: `"2025-04-18"` (ISO format, not "April") ✅ |
| **Root Cause** | **Evidence terms too strict.** Rank 1 IS the correct chunk — the incident table with the seal event. But `must_include_terms: ["April", "2025"]` fails because the corpus uses ISO date `"2025-04-18"`, not the word "April". |
| **Fix Category** | Evidence terms too strict — update to `["2025-04-18"]` or `["2025-04"]` |

---

### MISS 6: ENT-Q100 — "What technology does FinReport use for its backend?"

| Field | Value |
|---|---|
| **Expected** | ESP_Architecture line 44: `"FinReport \| Java Spring Boot + JINJA2 + PostgreSQL"` |
| **must_include** | `Java Spring Boot` |
| **Rank 1** | FinReport_UserGuide chunk_0 (intro/overview) — score 0.832 |
| **Rank 2** | FinReport_UserGuide chunk_14 |
| **Rank 3** | FinReport_UserGuide chunk_9 |
| **Corpus verified** | FinReport_UserGuide.md contains **zero** mentions of "Java", "Spring Boot", or "backend" ❌ — tech stack only in ESP_Architecture ✅ |
| **Root Cause** | **Wrong doc at rank 1.** "FinReport" in the query pulls FinReport_UserGuide (user-facing guide with no tech info). The tech stack is only in ESP_Architecture's Component Summary table, which didn't appear in top-3. |
| **Fix Category** | Wrong doc at rank 1 → "technology/backend/stack" queries should boost ARCHITECTURE docs |

---

## 2. PARTIAL HIT Analysis (15 Queries)

### Pattern A: Right Doc, Overview Chunk at Rank 1 (4 queries)

The right document is at rank 1 but the intro/overview chunk outranks the specific content chunk. A **document drill-down re-ranker** would fix all of these.

#### Q015 — "What encryption algorithm does SecureVault use?" (matched rank 3)

| Rank | Source | Section | Issue |
|---|---|---|---|
| 1 | SecureVault_UserGuide chunk_0 | Title/Overview | Generic intro; no AES-256-GCM |
| 2 | SecureVault_UserGuide chunk_12 | (other section) | Not the right section |
| **3 ✓** | **SecureVault_UserGuide chunk_1** | **§2.1 Architecture** | **Has `"AES-256-GCM"` (line 35)** |

#### Q035 — "What monitoring tools are used in the ESP platform?" (matched rank 2)

| Rank | Source | Section | Issue |
|---|---|---|---|
| 1 | ESP_Architecture chunk_1 | Platform Overview | Mentions tools generally, no monitoring specifics |
| **2 ✓** | **ESP_Architecture chunk_11** | **Monitoring section** | **Has Prometheus, Grafana, ELK, Jaeger, PagerDuty** |
| 3 | ESP_Incident_Response_SOP chunk_3 | — | Different doc |

#### Q064 — "How long should new employee onboarding take?" (matched rank 2)

| Rank | Source | Section | Issue |
|---|---|---|---|
| 1 | ESP_Onboarding_Guide chunk_0 | Title/Overview | Generic intro; no "30-day" |
| **2 ✓** | **ESP_Onboarding_Guide chunk_12** | **Milestones** | **Has `"30-day onboarding milestones"`** |
| 3 | ESP_Onboarding_Guide chunk_5 | — | Wrong section |

#### Q076 — "What caused the SecureVault replication lag in December 2025?" (matched rank 2)

| Rank | Source | Section | Issue |
|---|---|---|---|
| 1 | SecureVault_Replication_RCA chunk_0 | Title/Overview | Describes incident overview, not root cause |
| **2 ✓** | **SecureVault_Replication_RCA chunk_4** | **Root Cause (5 Whys)** | **Has `"quarterly rotation of 14,200 secrets"`** |
| 3 | SecureVault_Replication_RCA chunk_5 | Resolution Actions | Different section |

---

### Pattern B: Right Doc, Related-but-Wrong Chunk at Rank 1 (8 queries)

The right document is at rank 1 but a semantically adjacent section outranks the target section. A **keyword boost** (prefer chunks containing exact query terms) would fix most of these.

#### Q016 — "How many unseal keys are needed for SecureVault's Shamir threshold?" (matched rank 2)

| Rank | Source | Section | Why Wrong |
|---|---|---|---|
| 1 | SecureVault_UserGuide chunk_10 | §6.4 ERR-SV-503: Vault Sealed | Troubleshooting section mentions unsealing but not the 3-of-5 architecture spec |
| **2 ✓** | **SecureVault_UserGuide chunk_1** | **§2.1 Architecture** | **`"Shamir's Secret Sharing with a 3-of-5 threshold"`** |

#### Q018 — "How often are database credentials rotated in SecureVault?" (matched rank 3)

| Rank | Source | Section | Why Wrong |
|---|---|---|---|
| 1 | SecureVault_UserGuide chunk_2 | §2.2 Authentication Methods | "credentials" semantic overlap, not rotation |
| 2 | SecureVault_UserGuide chunk_6 | §4.3 Emergency Rotation | Emergency context, not scheduled |
| **3 ✓** | **SecureVault_UserGuide chunk_5** | **§4.1 Automatic Rotation** | **`"Database passwords \| Every 30 days"`** |

#### Q021 — "What are the five job types supported by BatchBridge?" (matched rank 2)

| Rank | Source | Section | Why Wrong |
|---|---|---|---|
| 1 | BatchBridge_Training chunk_2 | §2.1 Core Concepts - Jobs | Defines what a "Job" is, but not the 5 type names |
| **2 ✓** | **BatchBridge_Training chunk_3** | **§2.2 Job Types** | **Lists SQL-to-SQL, File-to-DB, DB-to-File, API-to-DB, Python** |

#### Q046 — "Are DataDesk webhooks available?" (matched rank 2)

| Rank | Source | Section | Why Wrong |
|---|---|---|---|
| 1 | DataDesk_API_Reference chunk_11 | §7. SDK & Client Libraries | Has webhook config details but lacks the "Beta" keyword from the section header |
| **2 ✓** | **DataDesk_API_Reference chunk_10** | **§6. Webhooks (Beta)** | **Has `"Webhooks (Beta)"` header** |

#### Q078 — "What was the fix for the SecureVault replication lag issue?" (matched rank 3)

| Rank | Source | Section | Why Wrong |
|---|---|---|---|
| 1 | SecureVault_Replication_RCA chunk_3 | Contributing Factors | Analysis of what went wrong, not the remediation |
| 2 | SecureVault_Replication_RCA chunk_6 | — | Other section |
| **3 ✓** | **SecureVault_Replication_RCA chunk_5** | **Resolution Actions** | **`"200 secrets per minute"` throttle** |

#### Q081 — "What is the recommended maximum number of charts on a DataDesk dashboard?" (matched rank 2)

| Rank | Source | Section | Why Wrong |
|---|---|---|---|
| 1 | DataDesk_Best_Practices chunk_13 | Scheduled Reports | Completely wrong section (same doc) |
| **2 ✓** | **DataDesk_Best_Practices chunk_1** | **§1. Dashboard Design** | **`"Keep Chart Count Under 12 Per Dashboard"`** |

#### Q087 — "How many bulk actions can you perform at once in OpsFlow?" (matched rank 2)

| Rank | Source | Section | Why Wrong |
|---|---|---|---|
| 1 | OpsFlow_FAQ chunk_15 | Q22: Pending Approval | Adjacent FAQ entry (one Q before the answer) |
| **2 ✓** | **OpsFlow_FAQ chunk_16** | **Q23: Bulk-update tasks** | **`"limited to 50 tasks at a time"`** |

#### Q098 — "What is the trace sampling rate in BatchBridge production?" (matched rank 3)

| Rank | Source | Section | Why Wrong |
|---|---|---|---|
| 1 | BatchBridge_Config_Ref chunk_8 | UAT Config | Has `trace_sampling_rate: 0.1` — wrong environment! |
| 2 | BatchBridge_Config_Ref chunk_7 | — | Other section |
| **3 ✓** | **BatchBridge_Config_Ref chunk_9** | **Production Config** | **`trace_sampling_rate: 0.01`** |

---

### Pattern C: Wrong Doc at Rank 1 (2 partials)

#### Q013 — "What is the DataDesk audit log retention period?" (matched rank 3)

| Rank | Source | Section | Issue |
|---|---|---|---|
| 1 | **OpsFlow_FAQ** chunk_13 | Q20: Data retention for OpsFlow | **Wrong product** — OpsFlow retention (7 years) pulled by "retention" semantic match |
| 2 | SecureVault_UserGuide chunk_11 | — | Wrong doc |
| **3 ✓** | **DataDesk_UserGuide chunk_14** | **§8.2 Audit Logging** | **`"retained for 2 years"`** |

**Fix:** Product-aware retrieval — "DataDesk" in query should boost DataDesk docs over OpsFlow.

#### Q067 — "How long does a SecureVault rollback take?" (matched rank 3)

| Rank | Source | Section | Issue |
|---|---|---|---|
| 1 | **SecureVault_Replication_RCA** chunk_5 | Resolution timeline | **Wrong doc** — RCA incident resolution, not generic rollback SOP |
| 2 | SecureVault_Replication_RCA chunk_6 | — | Wrong doc |
| **3 ✓** | **ESP_Incident_Response_SOP chunk_13** | **Rollback Procedure** | **`"SecureVault: ~2 minutes"`** |

**Fix:** "rollback procedure/time" queries should prefer SOP doc types over INCIDENT reports.

---

### Pattern D: Evidence Terms Too Strict (1 partial)

#### Q043 — "What is the API rate limit for DataDesk service accounts?" (matched rank 2)

| Rank | Source | Section | Issue |
|---|---|---|---|
| 1 | **DataDesk_API_Reference chunk_10** | **§4. Rate Limiting** | **Correct section!** Has `"Service Account \| 1000 req/min"` — but uses `1000` (no comma) |
| **2 ✓** | DataDesk_Best_Practices chunk_8 | — | Has `1,000` (with comma) matching `must_include_terms` |

**Fix:** Relax evidence: `"1,000"` → `["1,000", "1000"]`. Retrieval is already correct.

---

## 3. Pattern Analysis

### Pattern 1: Overview/Intro Chunks Dominate (12 queries)

Document overview chunks consistently outrank specific content sections. The intro paragraph has high keyword density (product name, purpose, features) creating strong semantic matches for any query about that product.

| Document | "Magnet" Chunk | Affected Queries |
|---|---|---|
| SecureVault_UserGuide intro | Generic overview | Q015, Q016 (partially), Q059 |
| ESP_Architecture overview | "ESP consists of five tools…" | Q032, Q035 |
| SecureVault_Replication_RCA intro | Incident summary | Q076, Q078 |
| ESP_Onboarding_Guide intro | Guide overview | Q064 |
| FinReport_UserGuide intro | Platform description | Q100 |

**Recommendation:** Demote intro/title chunks when the query asks a specific factual question (contains "how many", "what is the", "when was", etc.).

### Pattern 2: Adjacent Section Confusion (8 queries)

The retriever picks a semantically related but wrong section in the correct document. Common sub-patterns:

- **Neighboring FAQ entries** (Q087: FAQ Q22 instead of Q23)
- **Wrong environment config** (Q098: UAT config instead of Production)
- **Related but distinct sections** (Q018: Auth Methods instead of Rotation Policies)
- **Parent concept vs specific list** (Q021: "Jobs concept" instead of "Job Types list")

**Recommendation:** Keyword boost — when a query contains specific terms ("production", "service account", "five job types", "bulk"), boost chunks containing those exact terms.

### Pattern 3: Cross-Doc Confusion (6 queries)

The retriever picks the wrong document entirely:

| Query Pattern | Wrong Doc | Right Doc | Root Cause |
|---|---|---|---|
| "Definition of X" (Q057, Q059) | SOP / UserGuide | **ESP_Glossary** | Glossary definitions not prioritized for definition queries |
| "Tech stack of X" (Q032, Q100) | Glossary / UserGuide | **ESP_Architecture** | Architecture details not in product-specific docs |
| "X retention period" (Q013) | OpsFlow_FAQ | **DataDesk_UserGuide** | Semantically similar topic in wrong product |
| "X rollback time" (Q067) | Replication_RCA | **ESP_Incident_Response_SOP** | Incident report outranks operational SOP |

**Recommendation:** Implement doc-type routing:
- "definition/what is" queries → boost REFERENCE/GLOSSARY
- "technology/backend/stack" queries → boost ARCHITECTURE
- "rollback/procedure" queries → boost SOP
- Product-specific queries → filter to matching product docs

---

## 4. Quick Wins (Zero Retrieval Changes Needed)

These 3 queries already have the **correct content at rank 1** — only the evidence test scoring is wrong:

| Query | Current `must_include_terms` | Fix | Corpus Text |
|---|---|---|---|
| **Q033** | `["2.3TB"]` | → `["2.3 TB"]` or `["2.3"]` | `"2.3 TB"` (space) |
| **Q069** | `["April", "2025"]` | → `["2025-04-18"]` or `["2025-04"]` | `"2025-04-18"` (ISO date) |
| **Q043** | `["1,000"]` | → `["1,000", "1000"]` | `"1000 req/min"` (no comma) |

Applying these fixes: **79% → 82% top-1 accuracy** with no code changes.

---

## 5. Corpus Verification Summary

All evidence terms exist in the corpus — **zero "data not in corpus" issues**:

| Document | Evidence Verified |
|---|---|
| ESP_Architecture.md | `Kubernetes 1.29` (line 65), `2.3 TB` (line 77), `Java Spring Boot + JINJA2` (line 44) ✅ |
| ESP_Glossary.md | `RPO (Recovery Point Objective)` (line 137), `PKI (Public Key Infrastructure)` (line 127) ✅ |
| ESP_Incident_Response_SOP.md | `SecureVault Seal Event \| 2025-04-18` (line 279), `SecureVault: ~2 minutes` rollback (line 196) ✅ |
| SecureVault_UserGuide.md | `AES-256-GCM` (line 35), `3-of-5` Shamir (line 35), `Every 30 days` rotation (line 121) ✅ |
| BatchBridge_Training.md | 5 job types in §2.2 ✅ |
| DataDesk_UserGuide.md | `2 years` audit retention (line 253) ✅ |
| DataDesk_API_Reference.md | `1000 req/min` service account (line 331), `Webhooks (Beta)` (line 365) ✅ |
| DataDesk_Best_Practices.md | `12 charts per dashboard` (line 20) ✅ |
| SecureVault_Replication_RCA.md | `200 secrets per minute` throttle (line 91), `quarterly rotation` cause (line 43) ✅ |
| BatchBridge_Config_Ref.md | `trace_sampling_rate: 0.01` in prod (line 181) ✅ |
| OpsFlow_FAQ.md | `50 tasks` bulk limit (line 236) ✅ |
| ESP_Onboarding_Guide.md | `30-day` milestones ✅ |
