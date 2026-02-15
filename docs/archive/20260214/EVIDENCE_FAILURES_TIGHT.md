# Evidence Failures (Tight)

## V1 Isolated

- Failures: 2

### Q11

- Classification: D) EXTRACTION GAP
- Query: How do I onboard a new user to ToolX?
- Required evidence: {"must_include_terms": ["onboard", "user", "new"], "must_not_include_terms": [], "expected_evidence_rules": {"at_least_one_chunk_has_terms": true, "at_least_one_chunk_from_top_doc_type": true, "description": "Onboarding query should return USER_GUIDE"}, "parsed_rules": {"all_of_terms": ["onboard", "user", "new"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"at_least_one_chunk_has_terms": true, "at_least_one_chunk_from_top_doc_type": true, "description": "Onboarding query should return USER_GUIDE"}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_8630007 | doc_type=USER_GUIDE | chunk_id=doc_8630007_chunk_0 | similarity=0.0
  - Excerpt: # ToolX — Quick Start for New Users  **Last updated:** 2026-02-14    ## What is ToolX? ToolX is a ticketing and job-monitoring interface used to view **Tickets**, run **Jobs**, and check **System Status**.  ## First login 1. Open ToolX. 2. Click **Si ... see `ERR-AUTH-401`, follow the troubleshooting guide:    - `Troubleshoot_ToolX_AUTH401.md`  ## Daily workflow - Check **Tickets** for assignments - Use **Jobs** to rerun a failed batch - Use **Help → Run Connection Test** if the Dashboard looks stale
- Rank 2 | doc_id=doc_5826854 | doc_type=TROUBLESHOOT | chunk_id=doc_5826854_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: ToolX — ERR-AUTH-401 (Token expired after SSO redirect)  **Last updated:** 2026-02-14   **Owner:** KTS Test Corpus Team   **Applies to:** ToolX Web UI (Prod / UAT)  ## Symptoms - Users attempt to sign in via SSO and are redirected bac ... ab, then sign back in. 3. In the browser, **allow third‑party cookies** for the identity domain (temporary test). 4. If still failing, run the ToolX built‑in connection test:    - ToolX → **Settings** → **Help** → **Run Connection Test** 5. Validate:
- Rank 3 | doc_id=doc_4843481 | doc_type=TROUBLESHOOT | chunk_id=doc_4843481_chunk_0 | similarity=0.0
  - Excerpt: SOP — Handling ToolX Login Failures (Tier 1) Last updated: 2026-02-14 Purpose Provide a consistent Tier 1 process for resolving ToolX sign-in issues. Procedure Step 1: Collect the error code and TraceId from the user. Step 2: Ask the user to hard ref ... esh (Ctrl+Shift+R). Step 3: If still failing, have user sign out and sign in again. Step 4: Check third-party cookie setting (temporary test). Step 5: If unresolved, capture browser version and environment and escalate to Tier 2. Reference screenshot
- Rank 4 | doc_id=doc_2700947 | doc_type=TRAINING | chunk_id=doc_2700947_chunk_0 | similarity=0.0
  - Excerpt: ToolY Upload Policy — Common Failures How to interpret ERR-UPL-013 and resolve it quickly ERR-UPL-013: File type not allowed Resolution: upload only allowed extensions (.csv .xlsx .pdf); request policy change for new types.
- Rank 5 | doc_id=doc_6608752 | doc_type=RELEASE_NOTE | chunk_id=doc_6608752_chunk_0 | similarity=0.0
  - Excerpt: # ToolX Release Notes — 2026 Q1  **Release window:** 2026-01-10 to 2026-02-07   **Version:** 6.3.0  ## Highlights - New Dashboard banner for connectivity issues (HTTP 504) - Improved SSO retry logic (reduced `ERR-AUTH-401` frequency)  ## Breaking changes - Attachment upload now blocks additional extensions: `.js .ps1 .exe`  ## Known issues - Some users may still see `ERR-AUTH-401` if browser blocks third-party cookies.

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::onboard | false | - |
| term::user | true | 1 |
| term::new | true | 1 |

### Q12

- Classification: D) EXTRACTION GAP
- Query: What are the steps to deploy ToolX?
- Required evidence: {"must_include_terms": ["deploy", "step"], "must_not_include_terms": [], "expected_evidence_rules": {"at_least_one_chunk_has_terms": true, "at_least_one_chunk_from_top_doc_type": true, "description": "Procedural query should return SOP"}, "parsed_rules": {"all_of_terms": ["deploy", "step"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"at_least_one_chunk_has_terms": true, "at_least_one_chunk_from_top_doc_type": true, "description": "Procedural query should return SOP"}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_8630007 | doc_type=USER_GUIDE | chunk_id=doc_8630007_chunk_0 | similarity=0.0
  - Excerpt: # ToolX — Quick Start for New Users  **Last updated:** 2026-02-14    ## What is ToolX? ToolX is a ticketing and job-monitoring interface used to view **Tickets**, run **Jobs**, and check **System Status**.  ## First login 1. Open ToolX. 2. Click **Si ... see `ERR-AUTH-401`, follow the troubleshooting guide:    - `Troubleshoot_ToolX_AUTH401.md`  ## Daily workflow - Check **Tickets** for assignments - Use **Jobs** to rerun a failed batch - Use **Help → Run Connection Test** if the Dashboard looks stale
- Rank 2 | doc_id=doc_5826854 | doc_type=TROUBLESHOOT | chunk_id=doc_5826854_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: ToolX — ERR-AUTH-401 (Token expired after SSO redirect)  **Last updated:** 2026-02-14   **Owner:** KTS Test Corpus Team   **Applies to:** ToolX Web UI (Prod / UAT)  ## Symptoms - Users attempt to sign in via SSO and are redirected bac ... ab, then sign back in. 3. In the browser, **allow third‑party cookies** for the identity domain (temporary test). 4. If still failing, run the ToolX built‑in connection test:    - ToolX → **Settings** → **Help** → **Run Connection Test** 5. Validate:
- Rank 3 | doc_id=doc_3073331 | doc_type=TROUBLESHOOT | chunk_id=doc_3073331_chunk_0 | similarity=0.0
  - Excerpt: ToolX Troubleshooting Pack (Training) This training pack is part of the KTS test corpus. It includes common errors, symptoms, and validation steps. Module 1: ERR-AUTH-401 Token expired after SSO redirect  - Symptoms: error modal after redirect  - Fix: hard refresh, re-auth, allow cookies (test), capture TraceId Module 2: HTTP 504 Gateway Timeout  - Symptoms: dashboard banner, partial widget load  - Fix: connection test, clear cache, verify VPN/proxy  Appendix: Sample screenshots (for indexing)
- Rank 4 | doc_id=doc_4843481 | doc_type=TROUBLESHOOT | chunk_id=doc_4843481_chunk_0 | similarity=0.0
  - Excerpt: SOP — Handling ToolX Login Failures (Tier 1) Last updated: 2026-02-14 Purpose Provide a consistent Tier 1 process for resolving ToolX sign-in issues. Procedure Step 1: Collect the error code and TraceId from the user. Step 2: Ask the user to hard ref ... esh (Ctrl+Shift+R). Step 3: If still failing, have user sign out and sign in again. Step 4: Check third-party cookie setting (temporary test). Step 5: If unresolved, capture browser version and environment and escalate to Tier 2. Reference screenshot
- Rank 5 | doc_id=doc_7774454 | doc_type=TROUBLESHOOT | chunk_id=doc_7774454_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: ToolX — HTTP 504 Gateway Timeout (Dashboard banner)  **Last updated:** 2026-02-14   **Owner:** KTS Test Corpus Team   **Applies to:** ToolX Web UI  ## Symptoms - Banner on Dashboard shows: `HTTP 504 Gateway Timeout` - Widgets load par ... f the issue is site‑wide, check your incident banner or status page.  ## Validation - Refresh Dashboard; confirm banner disappears. - Open **Jobs** and confirm list loads.  ## Notes - If timeouts occur only on one widget, capture widget name and time

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::deploy | false | - |
| term::step | true | 3 |

## V2 Isolated

- Failures: 17

### V2-Q02

- Classification: D) EXTRACTION GAP
- Query: How do I troubleshoot OpsFlow ERR-AUTH-407 during SSO redirect behind a proxy?
- Required evidence: {"must_include_terms": ["ERR-AUTH-407", "HTTP 407"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["ERR-AUTH-407", "HTTP 407"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_7594425 | doc_type=TROUBLESHOOT | chunk_id=doc_7594425_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: OpsFlow — ERR-AUTH-407 (Proxy authentication required)  **Last updated:** 2026-02-14   **Applies to:** OpsFlow (Web UI + API)  ## Symptoms - User sees `ERR-AUTH-407` and cannot complete the workflow. - UI may show a banner/dialog.  ** ... . Capture evidence for escalation if unresolved.  ### Resolution details for ERR-AUTH-407 - If `ERR-AUTH-407` relates to **limits**, reduce batch size or split workload. - If `ERR-AUTH-407` relates to **identity**, re-auth and validate time sync. - I
- Rank 2 | doc_id=doc_4582988 | doc_type=TROUBLESHOOT | chunk_id=doc_4582988_chunk_0 | similarity=0.0
  - Excerpt: SOP — Proxy Authentication Errors (ERR-AUTH-407) Last updated: 2026-02-14 If users are behind a corporate proxy, ensure the proxy auth handshake is successful. Key data to collect: TraceId, proxy PAC URL, browser version.
- Rank 3 | doc_id=doc_2370364 | doc_type=REFERENCE | chunk_id=doc_2370364_chunk_0 | similarity=0.0
  - Excerpt: # Error Code Catalog V2 This is a reference catalog for error codes and diagnostics.  ## OPSFLOW Error Codes - **ERR-RUN-204**: Worker exited with code 137 (OOM) (Category: Compute, Severity: high) - **ERR-AUTH-407**: Proxy authentication required (C ... Limit, Severity: high) - **ERR-TLS-014**: Unknown CA (Category: TLS, Severity: high)  ## FINREPORT Error Codes - **ERR-EXP-003**: Excel template missing (Category: Config, Severity: medium) - **ERR-SYNC-101**: Data refresh stale (Category: Freshness,
- Rank 4 | doc_id=doc_5363701 | doc_type=INCIDENT | chunk_id=doc_5363701_chunk_0 | similarity=0.0
  - Excerpt: Incident Log: incident_log_sample.csv Format: CSV Total Records: 60 Columns: incident_id, date, tool, code, severity, summary  === AGGREGATED SUMMARY ===  Affected Tools/Platforms:   - OpsFlow: 18 incidents   - FinReport: 15 incidents   - SecureVault ... erations  Row 3:   incident_id: INC-0003   date: 2025-11-20   tool: FinReport   code: ERR-AUTH-407   severity: P2   summary: FinReport experienced ERR-AUTH-407 during routine operations  Row 4:   incident_id: INC-0004   date: 2026-02-10   tool: OpsFl
- Rank 5 | doc_id=doc_3254544 | doc_type=TROUBLESHOOT | chunk_id=doc_3254544_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: OpsFlow — ERR-RUN-204 (Worker exited with code 137 (OOM))  **Last updated:** 2026-02-14   **Applies to:** OpsFlow (Web UI + API)  ## Symptoms - User sees `ERR-RUN-204` and cannot complete the workflow. - UI may show a banner/dialog.   ...  3. Capture evidence for escalation if unresolved.  ### Resolution details for ERR-RUN-204 - If `ERR-RUN-204` relates to **limits**, reduce batch size or split workload. - If `ERR-RUN-204` relates to **identity**, re-auth and validate time sync. - If

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::ERR-AUTH-407 | true | 1 |
| term::HTTP 407 | false | - |

### V2-Q06

- Classification: D) EXTRACTION GAP
- Query: How do I reduce the chance of ERR-UPL-021 when uploading PDFs?
- Required evidence: {"must_include_terms": ["ERR-UPL-021", "Compress"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["ERR-UPL-021", "Compress"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_0481592 | doc_type=TROUBLESHOOT | chunk_id=doc_0481592_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: DataDesk — ERR-UPL-021 (Payload too large (max 50MB))  **Last updated:** 2026-02-14   **Applies to:** DataDesk (Web UI + API)  ## Symptoms - User sees `ERR-UPL-021` and cannot complete the workflow. - UI may show a banner/dialog.  **S ...  Capture evidence for escalation if unresolved.  ### Resolution details for ERR-UPL-021 - If `ERR-UPL-021` relates to **limits**, reduce batch size or split workload. - If `ERR-UPL-021` relates to **identity**, re-auth and validate time sync. - If `E
- Rank 2 | doc_id=doc_7594425 | doc_type=TROUBLESHOOT | chunk_id=doc_7594425_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: OpsFlow — ERR-AUTH-407 (Proxy authentication required)  **Last updated:** 2026-02-14   **Applies to:** OpsFlow (Web UI + API)  ## Symptoms - User sees `ERR-AUTH-407` and cannot complete the workflow. - UI may show a banner/dialog.  ** ... . Capture evidence for escalation if unresolved.  ### Resolution details for ERR-AUTH-407 - If `ERR-AUTH-407` relates to **limits**, reduce batch size or split workload. - If `ERR-AUTH-407` relates to **identity**, re-auth and validate time sync. - I
- Rank 3 | doc_id=doc_7188612 | doc_type=TROUBLESHOOT | chunk_id=doc_7188612_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: SecureVault — ERR-MFA-009 (Device time out of sync)  **Last updated:** 2026-02-14   **Applies to:** SecureVault (Web UI + API)  ## Symptoms - User sees `ERR-MFA-009` and cannot complete the workflow. - UI may show a banner/dialog.  ** ... . Capture evidence for escalation if unresolved.  ### Resolution details for ERR-MFA-009 - If `ERR-MFA-009` relates to **limits**, reduce batch size or split workload. - If `ERR-MFA-009` relates to **identity**, re-auth and validate time sync. - If `
- Rank 4 | doc_id=doc_7447053 | doc_type=TROUBLESHOOT | chunk_id=doc_7447053_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: All Tools — HTTP 502/504 (Gateway errors and triage)  **Last updated:** 2026-02-14   **Applies to:** All Tools (Web UI + API)  ## Symptoms - User sees `HTTP 502/504` and cannot complete the workflow. - UI may show a banner/dialog.  ** ... . Capture evidence for escalation if unresolved.  ### Resolution details for HTTP 502/504 - If `HTTP 502/504` relates to **limits**, reduce batch size or split workload. - If `HTTP 502/504` relates to **identity**, re-auth and validate time sync. - I
- Rank 5 | doc_id=doc_3158773 | doc_type=RELEASE_NOTE | chunk_id=doc_3158773_chunk_0 | similarity=0.0
  - Excerpt: # DataDesk Release Notes — 2026 Q1  **Version:** 8.0.2  ## Highlights - Upload size limit increased to 50MB (ERR-UPL-021 still triggers above that) - Query runner now shows SQLSTATE codes and truncated column info  ## Known issues - SQLSTATE 22001 can still occur when exporting to fixed-width downstream systems.

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::ERR-UPL-021 | true | 1 |
| term::Compress | false | - |

### V2-Q18

- Classification: D) EXTRACTION GAP
- Query: I am seeing HTTP 504 on a dashboard. What's the generic gateway triage and what evidence should I capture?
- Required evidence: {"must_include_terms": ["HTTP 504", "gateway"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["HTTP 504", "gateway"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_7447053 | doc_type=TROUBLESHOOT | chunk_id=doc_7447053_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: All Tools — HTTP 502/504 (Gateway errors and triage)  **Last updated:** 2026-02-14   **Applies to:** All Tools (Web UI + API)  ## Symptoms - User sees `HTTP 502/504` and cannot complete the workflow. - UI may show a banner/dialog.  ** ... . Capture evidence for escalation if unresolved.  ### Resolution details for HTTP 502/504 - If `HTTP 502/504` relates to **limits**, reduce batch size or split workload. - If `HTTP 502/504` relates to **identity**, re-auth and validate time sync. - I
- Rank 2 | doc_id=doc_3138757 | doc_type=TROUBLESHOOT | chunk_id=doc_3138757_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: BatchBridge+OpsFlow — HTTP 429 (Differentiate HTTP 429 vs ERR-RATE-429)  **Last updated:** 2026-02-14   **Applies to:** BatchBridge+OpsFlow (Web UI + API)  ## Symptoms - User sees `HTTP 429` and cannot complete the workflow. - UI may  ... he workflow end-to-end. 3. Capture evidence for escalation if unresolved.  ### Resolution details for HTTP 429 - If `HTTP 429` relates to **limits**, reduce batch size or split workload. - If `HTTP 429` relates to **identity**, re-auth and validate t
- Rank 3 | doc_id=doc_7594425 | doc_type=TROUBLESHOOT | chunk_id=doc_7594425_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: OpsFlow — ERR-AUTH-407 (Proxy authentication required)  **Last updated:** 2026-02-14   **Applies to:** OpsFlow (Web UI + API)  ## Symptoms - User sees `ERR-AUTH-407` and cannot complete the workflow. - UI may show a banner/dialog.  ** ... . Capture evidence for escalation if unresolved.  ### Resolution details for ERR-AUTH-407 - If `ERR-AUTH-407` relates to **limits**, reduce batch size or split workload. - If `ERR-AUTH-407` relates to **identity**, re-auth and validate time sync. - I
- Rank 4 | doc_id=doc_7016225 | doc_type=TROUBLESHOOT | chunk_id=doc_7016225_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: BatchBridge — ERR-RATE-429 (Backoff required (retry-after: 30s))  **Last updated:** 2026-02-14   **Applies to:** BatchBridge (Web UI + API)  ## Symptoms - User sees `ERR-RATE-429` and cannot complete the workflow. - UI may show a bann ...  end-to-end. 3. Capture evidence for escalation if unresolved.  ### Resolution details for ERR-RATE-429 - If `ERR-RATE-429` relates to **limits**, reduce batch size or split workload. - If `ERR-RATE-429` relates to **identity**, re-auth and validate 
- Rank 5 | doc_id=doc_5310494 | doc_type=TROUBLESHOOT | chunk_id=doc_5310494_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: BatchBridge — ERR-TLS-014 (Unknown CA during TLS handshake)  **Last updated:** 2026-02-14   **Applies to:** BatchBridge (Web UI + API)  ## Symptoms - User sees `ERR-TLS-014` and cannot complete the workflow. - UI may show a banner/dia ... o-end. 3. Capture evidence for escalation if unresolved.  ### Resolution details for ERR-TLS-014 - If `ERR-TLS-014` relates to **limits**, reduce batch size or split workload. - If `ERR-TLS-014` relates to **identity**, re-auth and validate time sync

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::HTTP 504 | false | - |
| term::gateway | true | 1 |

### V2-Q19

- Classification: D) EXTRACTION GAP
- Query: Differentiate generic HTTP 502 vs 504 in triage steps.
- Required evidence: {"must_include_terms": ["HTTP 502", "HTTP 504"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["HTTP 502", "HTTP 504"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_7447053 | doc_type=TROUBLESHOOT | chunk_id=doc_7447053_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: All Tools — HTTP 502/504 (Gateway errors and triage)  **Last updated:** 2026-02-14   **Applies to:** All Tools (Web UI + API)  ## Symptoms - User sees `HTTP 502/504` and cannot complete the workflow. - UI may show a banner/dialog.  ** ... . Capture evidence for escalation if unresolved.  ### Resolution details for HTTP 502/504 - If `HTTP 502/504` relates to **limits**, reduce batch size or split workload. - If `HTTP 502/504` relates to **identity**, re-auth and validate time sync. - I
- Rank 2 | doc_id=doc_3138757 | doc_type=TROUBLESHOOT | chunk_id=doc_3138757_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: BatchBridge+OpsFlow — HTTP 429 (Differentiate HTTP 429 vs ERR-RATE-429)  **Last updated:** 2026-02-14   **Applies to:** BatchBridge+OpsFlow (Web UI + API)  ## Symptoms - User sees `HTTP 429` and cannot complete the workflow. - UI may  ... he workflow end-to-end. 3. Capture evidence for escalation if unresolved.  ### Resolution details for HTTP 429 - If `HTTP 429` relates to **limits**, reduce batch size or split workload. - If `HTTP 429` relates to **identity**, re-auth and validate t
- Rank 3 | doc_id=doc_2397856 | doc_type=SOP | chunk_id=doc_2397856_chunk_0 | similarity=0.0
  - Excerpt: SOP — Handling Rate Limits (HTTP 429 / ERR-RATE-429) Last updated: 2026-02-14 Purpose Standardize Tier 1 response when connectors hit rate limiting. Procedure Step 1: Confirm whether error is HTTP 429 or ERR-RATE-429; capture retry-after value. Step 2: Enable exponential backoff in connector settings. Step 3: Reduce concurrency (workers/threads) and retry. Step 4: If persistent, request quota increase with evidence (RunId, timestamps, volume). Reference screenshot
- Rank 4 | doc_id=doc_9478667 | doc_type=TROUBLESHOOT | chunk_id=doc_9478667_chunk_0 | similarity=0.0
  - Excerpt: # KTS Synthetic Corpus v2 (Complex)  This corpus is intentionally more complex than v1: - Multiple tools (OpsFlow, DataDesk, SecureVault, BatchBridge, FinReport) - Overlapping errors (HTTP 429 vs ERR-RATE-429; generic gateway 5xx) - Mixed formats (MD, DOCX, PDF, PPTX, CSV, JSON, YAML, INI, PNG) - A legacy/deprecated troubleshooting doc for freshness/version testing  Top screenshot folder: `Reference/images/`
- Rank 5 | doc_id=doc_7444792 | doc_type=INCIDENT | chunk_id=doc_7444792_chunk_0 | similarity=0.0
  - Excerpt: # Postmortem: BatchBridge Rate Limiting Spike (INC-0021)  **Date:** 2026-01-18   **Severity:** P1   **Primary signal:** HTTP 429 / ERR-RATE-429  ## Summary A surge in downstream API usage caused rate limiting. Retries without backoff amplified the issue.  ## Corrective actions - Default backoff enabled in 3.1.0 (see release notes) - SOP published: SOP_Rate_Limit_Response_v1.docx  ## Evidence Screenshot: `Reference/images/ui_07.png`

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::HTTP 502 | true | 1 |
| term::HTTP 504 | false | - |

### V2-Q26

- Classification: D) EXTRACTION GAP
- Query: Which documents in this corpus look archived or outdated based on dates?
- Required evidence: {"must_include_terms": ["ARCHIVED", "DEPRECATED"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["ARCHIVED", "DEPRECATED"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_2448499 | doc_type=USER_GUIDE | chunk_id=doc_2448499_chunk_0 | similarity=0.0
  - Excerpt: # BatchBridge — Quick Start  **Last updated:** 2026-02-14  ## What is BatchBridge? BatchBridge is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 2 | doc_id=doc_8531073 | doc_type=USER_GUIDE | chunk_id=doc_8531073_chunk_0 | similarity=0.0
  - Excerpt: # DataDesk — Quick Start  **Last updated:** 2026-02-14  ## What is DataDesk? DataDesk is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 3 | doc_id=doc_5085837 | doc_type=USER_GUIDE | chunk_id=doc_5085837_chunk_0 | similarity=0.0
  - Excerpt: # FinReport — Quick Start  **Last updated:** 2026-02-14  ## What is FinReport? FinReport is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 4 | doc_id=doc_0594944 | doc_type=USER_GUIDE | chunk_id=doc_0594944_chunk_0 | similarity=0.0
  - Excerpt: # OpsFlow — Quick Start  **Last updated:** 2026-02-14  ## What is OpsFlow? OpsFlow is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 5 | doc_id=doc_4660264 | doc_type=USER_GUIDE | chunk_id=doc_4660264_chunk_0 | similarity=0.0
  - Excerpt: # SecureVault — Quick Start  **Last updated:** 2026-02-14  ## What is SecureVault? SecureVault is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::ARCHIVED | false | - |
| term::DEPRECATED | false | - |

### V2-Q27

- Classification: D) EXTRACTION GAP
- Query: Summarize incident INC-0021: what happened and what corrective actions were taken?
- Required evidence: {"must_include_terms": ["INC-0021", "ERR-RATE-429"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["INC-0021", "ERR-RATE-429"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_2448499 | doc_type=USER_GUIDE | chunk_id=doc_2448499_chunk_0 | similarity=0.0
  - Excerpt: # BatchBridge — Quick Start  **Last updated:** 2026-02-14  ## What is BatchBridge? BatchBridge is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 2 | doc_id=doc_8531073 | doc_type=USER_GUIDE | chunk_id=doc_8531073_chunk_0 | similarity=0.0
  - Excerpt: # DataDesk — Quick Start  **Last updated:** 2026-02-14  ## What is DataDesk? DataDesk is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 3 | doc_id=doc_5085837 | doc_type=USER_GUIDE | chunk_id=doc_5085837_chunk_0 | similarity=0.0
  - Excerpt: # FinReport — Quick Start  **Last updated:** 2026-02-14  ## What is FinReport? FinReport is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 4 | doc_id=doc_0594944 | doc_type=USER_GUIDE | chunk_id=doc_0594944_chunk_0 | similarity=0.0
  - Excerpt: # OpsFlow — Quick Start  **Last updated:** 2026-02-14  ## What is OpsFlow? OpsFlow is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 5 | doc_id=doc_4660264 | doc_type=USER_GUIDE | chunk_id=doc_4660264_chunk_0 | similarity=0.0
  - Excerpt: # SecureVault — Quick Start  **Last updated:** 2026-02-14  ## What is SecureVault? SecureVault is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::INC-0021 | false | - |
| term::ERR-RATE-429 | false | - |

### V2-Q29

- Classification: D) EXTRACTION GAP
- Query: Where do I configure BatchBridge retry/backoff defaults? Provide the key YAML fields.
- Required evidence: {"must_include_terms": ["retry", "exponential", "max_concurrency"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["retry", "exponential", "max_concurrency"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_2448499 | doc_type=USER_GUIDE | chunk_id=doc_2448499_chunk_0 | similarity=0.0
  - Excerpt: # BatchBridge — Quick Start  **Last updated:** 2026-02-14  ## What is BatchBridge? BatchBridge is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 2 | doc_id=doc_7016225 | doc_type=TROUBLESHOOT | chunk_id=doc_7016225_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: BatchBridge — ERR-RATE-429 (Backoff required (retry-after: 30s))  **Last updated:** 2026-02-14   **Applies to:** BatchBridge (Web UI + API)  ## Symptoms - User sees `ERR-RATE-429` and cannot complete the workflow. - UI may show a bann ...  end-to-end. 3. Capture evidence for escalation if unresolved.  ### Resolution details for ERR-RATE-429 - If `ERR-RATE-429` relates to **limits**, reduce batch size or split workload. - If `ERR-RATE-429` relates to **identity**, re-auth and validate 
- Rank 3 | doc_id=doc_0799576 | doc_type=TROUBLESHOOT | chunk_id=doc_0799576_chunk_0 | similarity=0.0
  - Excerpt: # LEGACY (OUTDATED): BatchBridge — ERR-TLS-014 Unknown CA  **Last updated:** 2025-08-03   **Status:** DEPRECATED — Use the newer troubleshooting guide.  ## Warning This document contains older steps that no longer apply after the 2026-01 certificate rollout.  ## Old resolution (do not use) - Import certificate manually into Java keystore (legacy JRE)  ## New reference See: `Troubleshoot_BatchBridge_ERR-TLS-014_UnknownCA.md`
- Rank 4 | doc_id=doc_7444792 | doc_type=INCIDENT | chunk_id=doc_7444792_chunk_0 | similarity=0.0
  - Excerpt: # Postmortem: BatchBridge Rate Limiting Spike (INC-0021)  **Date:** 2026-01-18   **Severity:** P1   **Primary signal:** HTTP 429 / ERR-RATE-429  ## Summary A surge in downstream API usage caused rate limiting. Retries without backoff amplified the issue.  ## Corrective actions - Default backoff enabled in 3.1.0 (see release notes) - SOP published: SOP_Rate_Limit_Response_v1.docx  ## Evidence Screenshot: `Reference/images/ui_07.png`
- Rank 5 | doc_id=doc_5310494 | doc_type=TROUBLESHOOT | chunk_id=doc_5310494_chunk_1 | similarity=0.0
  - Excerpt: olved.  ### Resolution details for ERR-TLS-014 - If `ERR-TLS-014` relates to **limits**, reduce batch size or split workload. - If `ERR-TLS-014` relates to **identity**, re-auth and validate time sync. - If `ERR-TLS-014` relates to **network**, verif ...  Validation - User can reproduce success path and error no longer appears. - A fresh log event confirms completion.  ## Escalation package - code: `ERR-TLS-014` - tool: `BatchBridge` - timestamp + environment - TraceId/RunId - screenshots/log snippet

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::retry | true | 2 |
| term::exponential | false | - |
| term::max_concurrency | false | - |

### V2-Q30

- Classification: D) EXTRACTION GAP
- Query: Where is the OpsFlow proxy PAC URL configured and what are timeout defaults?
- Required evidence: {"must_include_terms": ["pac_url", "read_seconds"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["pac_url", "read_seconds"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_0594944 | doc_type=USER_GUIDE | chunk_id=doc_0594944_chunk_0 | similarity=0.0
  - Excerpt: # OpsFlow — Quick Start  **Last updated:** 2026-02-14  ## What is OpsFlow? OpsFlow is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 2 | doc_id=doc_4582988 | doc_type=TROUBLESHOOT | chunk_id=doc_4582988_chunk_0 | similarity=0.0
  - Excerpt: SOP — Proxy Authentication Errors (ERR-AUTH-407) Last updated: 2026-02-14 If users are behind a corporate proxy, ensure the proxy auth handshake is successful. Key data to collect: TraceId, proxy PAC URL, browser version.
- Rank 3 | doc_id=doc_7594425 | doc_type=TROUBLESHOOT | chunk_id=doc_7594425_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: OpsFlow — ERR-AUTH-407 (Proxy authentication required)  **Last updated:** 2026-02-14   **Applies to:** OpsFlow (Web UI + API)  ## Symptoms - User sees `ERR-AUTH-407` and cannot complete the workflow. - UI may show a banner/dialog.  ** ... . Capture evidence for escalation if unresolved.  ### Resolution details for ERR-AUTH-407 - If `ERR-AUTH-407` relates to **limits**, reduce batch size or split workload. - If `ERR-AUTH-407` relates to **identity**, re-auth and validate time sync. - I
- Rank 4 | doc_id=doc_2448499 | doc_type=USER_GUIDE | chunk_id=doc_2448499_chunk_0 | similarity=0.0
  - Excerpt: # BatchBridge — Quick Start  **Last updated:** 2026-02-14  ## What is BatchBridge? BatchBridge is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 5 | doc_id=doc_8531073 | doc_type=USER_GUIDE | chunk_id=doc_8531073_chunk_0 | similarity=0.0
  - Excerpt: # DataDesk — Quick Start  **Last updated:** 2026-02-14  ## What is DataDesk? DataDesk is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::pac_url | true | 2 |
| term::read_seconds | false | - |

### V2-Q31

- Classification: D) EXTRACTION GAP
- Query: What is the max concurrency default for BatchBridge connectors?
- Required evidence: {"must_include_terms": ["max_concurrency"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["max_concurrency"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_2448499 | doc_type=USER_GUIDE | chunk_id=doc_2448499_chunk_0 | similarity=0.0
  - Excerpt: # BatchBridge — Quick Start  **Last updated:** 2026-02-14  ## What is BatchBridge? BatchBridge is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 2 | doc_id=doc_7016225 | doc_type=TROUBLESHOOT | chunk_id=doc_7016225_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: BatchBridge — ERR-RATE-429 (Backoff required (retry-after: 30s))  **Last updated:** 2026-02-14   **Applies to:** BatchBridge (Web UI + API)  ## Symptoms - User sees `ERR-RATE-429` and cannot complete the workflow. - UI may show a bann ...  end-to-end. 3. Capture evidence for escalation if unresolved.  ### Resolution details for ERR-RATE-429 - If `ERR-RATE-429` relates to **limits**, reduce batch size or split workload. - If `ERR-RATE-429` relates to **identity**, re-auth and validate 
- Rank 3 | doc_id=doc_5310494 | doc_type=TROUBLESHOOT | chunk_id=doc_5310494_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: BatchBridge — ERR-TLS-014 (Unknown CA during TLS handshake)  **Last updated:** 2026-02-14   **Applies to:** BatchBridge (Web UI + API)  ## Symptoms - User sees `ERR-TLS-014` and cannot complete the workflow. - UI may show a banner/dia ... o-end. 3. Capture evidence for escalation if unresolved.  ### Resolution details for ERR-TLS-014 - If `ERR-TLS-014` relates to **limits**, reduce batch size or split workload. - If `ERR-TLS-014` relates to **identity**, re-auth and validate time sync
- Rank 4 | doc_id=doc_3138757 | doc_type=TROUBLESHOOT | chunk_id=doc_3138757_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: BatchBridge+OpsFlow — HTTP 429 (Differentiate HTTP 429 vs ERR-RATE-429)  **Last updated:** 2026-02-14   **Applies to:** BatchBridge+OpsFlow (Web UI + API)  ## Symptoms - User sees `HTTP 429` and cannot complete the workflow. - UI may  ... he workflow end-to-end. 3. Capture evidence for escalation if unresolved.  ### Resolution details for HTTP 429 - If `HTTP 429` relates to **limits**, reduce batch size or split workload. - If `HTTP 429` relates to **identity**, re-auth and validate t
- Rank 5 | doc_id=doc_0481592 | doc_type=TROUBLESHOOT | chunk_id=doc_0481592_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: DataDesk — ERR-UPL-021 (Payload too large (max 50MB))  **Last updated:** 2026-02-14   **Applies to:** DataDesk (Web UI + API)  ## Symptoms - User sees `ERR-UPL-021` and cannot complete the workflow. - UI may show a banner/dialog.  **S ...  Capture evidence for escalation if unresolved.  ### Resolution details for ERR-UPL-021 - If `ERR-UPL-021` relates to **limits**, reduce batch size or split workload. - If `ERR-UPL-021` relates to **identity**, re-auth and validate time sync. - If `E

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::max_concurrency | false | - |

### V2-Q32

- Classification: D) EXTRACTION GAP
- Query: What are the backoff base_seconds and max_seconds defaults?
- Required evidence: {"must_include_terms": ["base_seconds", "max_seconds"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["base_seconds", "max_seconds"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_2448499 | doc_type=USER_GUIDE | chunk_id=doc_2448499_chunk_0 | similarity=0.0
  - Excerpt: # BatchBridge — Quick Start  **Last updated:** 2026-02-14  ## What is BatchBridge? BatchBridge is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 2 | doc_id=doc_8531073 | doc_type=USER_GUIDE | chunk_id=doc_8531073_chunk_0 | similarity=0.0
  - Excerpt: # DataDesk — Quick Start  **Last updated:** 2026-02-14  ## What is DataDesk? DataDesk is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 3 | doc_id=doc_5085837 | doc_type=USER_GUIDE | chunk_id=doc_5085837_chunk_0 | similarity=0.0
  - Excerpt: # FinReport — Quick Start  **Last updated:** 2026-02-14  ## What is FinReport? FinReport is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 4 | doc_id=doc_0594944 | doc_type=USER_GUIDE | chunk_id=doc_0594944_chunk_0 | similarity=0.0
  - Excerpt: # OpsFlow — Quick Start  **Last updated:** 2026-02-14  ## What is OpsFlow? OpsFlow is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 5 | doc_id=doc_4660264 | doc_type=USER_GUIDE | chunk_id=doc_4660264_chunk_0 | similarity=0.0
  - Excerpt: # SecureVault — Quick Start  **Last updated:** 2026-02-14  ## What is SecureVault? SecureVault is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::base_seconds | false | - |
| term::max_seconds | false | - |

### V2-Q34

- Classification: D) EXTRACTION GAP
- Query: Find where upload gateway is mentioned in the architecture overview.
- Required evidence: {"must_include_terms": ["Upload Gateway"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["Upload Gateway"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_2448499 | doc_type=USER_GUIDE | chunk_id=doc_2448499_chunk_0 | similarity=0.0
  - Excerpt: # BatchBridge — Quick Start  **Last updated:** 2026-02-14  ## What is BatchBridge? BatchBridge is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 2 | doc_id=doc_8531073 | doc_type=USER_GUIDE | chunk_id=doc_8531073_chunk_0 | similarity=0.0
  - Excerpt: # DataDesk — Quick Start  **Last updated:** 2026-02-14  ## What is DataDesk? DataDesk is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 3 | doc_id=doc_5085837 | doc_type=USER_GUIDE | chunk_id=doc_5085837_chunk_0 | similarity=0.0
  - Excerpt: # FinReport — Quick Start  **Last updated:** 2026-02-14  ## What is FinReport? FinReport is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 4 | doc_id=doc_0594944 | doc_type=USER_GUIDE | chunk_id=doc_0594944_chunk_0 | similarity=0.0
  - Excerpt: # OpsFlow — Quick Start  **Last updated:** 2026-02-14  ## What is OpsFlow? OpsFlow is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 5 | doc_id=doc_4660264 | doc_type=USER_GUIDE | chunk_id=doc_4660264_chunk_0 | similarity=0.0
  - Excerpt: # SecureVault — Quick Start  **Last updated:** 2026-02-14  ## What is SecureVault? SecureVault is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::Upload Gateway | false | - |

### V2-Q36

- Classification: D) EXTRACTION GAP
- Query: In the training deck, what are the two most common SecureVault issues covered?
- Required evidence: {"must_include_terms": ["ERR-ACL-002", "ERR-MFA-009"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["ERR-ACL-002", "ERR-MFA-009"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_4660264 | doc_type=USER_GUIDE | chunk_id=doc_4660264_chunk_0 | similarity=0.0
  - Excerpt: # SecureVault — Quick Start  **Last updated:** 2026-02-14  ## What is SecureVault? SecureVault is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 2 | doc_id=doc_2448499 | doc_type=USER_GUIDE | chunk_id=doc_2448499_chunk_0 | similarity=0.0
  - Excerpt: # BatchBridge — Quick Start  **Last updated:** 2026-02-14  ## What is BatchBridge? BatchBridge is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 3 | doc_id=doc_8531073 | doc_type=USER_GUIDE | chunk_id=doc_8531073_chunk_0 | similarity=0.0
  - Excerpt: # DataDesk — Quick Start  **Last updated:** 2026-02-14  ## What is DataDesk? DataDesk is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 4 | doc_id=doc_5085837 | doc_type=USER_GUIDE | chunk_id=doc_5085837_chunk_0 | similarity=0.0
  - Excerpt: # FinReport — Quick Start  **Last updated:** 2026-02-14  ## What is FinReport? FinReport is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 5 | doc_id=doc_0594944 | doc_type=USER_GUIDE | chunk_id=doc_0594944_chunk_0 | similarity=0.0
  - Excerpt: # OpsFlow — Quick Start  **Last updated:** 2026-02-14  ## What is OpsFlow? OpsFlow is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::ERR-ACL-002 | false | - |
| term::ERR-MFA-009 | false | - |

### V2-Q43

- Classification: D) EXTRACTION GAP
- Query: From the incident CSV, find incidents in the last 14 days and list their codes.
- Required evidence: {"must_include_terms": ["incident_log_sample.csv"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["incident_log_sample.csv"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_2448499 | doc_type=USER_GUIDE | chunk_id=doc_2448499_chunk_0 | similarity=0.0
  - Excerpt: # BatchBridge — Quick Start  **Last updated:** 2026-02-14  ## What is BatchBridge? BatchBridge is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 2 | doc_id=doc_8531073 | doc_type=USER_GUIDE | chunk_id=doc_8531073_chunk_0 | similarity=0.0
  - Excerpt: # DataDesk — Quick Start  **Last updated:** 2026-02-14  ## What is DataDesk? DataDesk is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 3 | doc_id=doc_5085837 | doc_type=USER_GUIDE | chunk_id=doc_5085837_chunk_0 | similarity=0.0
  - Excerpt: # FinReport — Quick Start  **Last updated:** 2026-02-14  ## What is FinReport? FinReport is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 4 | doc_id=doc_0594944 | doc_type=USER_GUIDE | chunk_id=doc_0594944_chunk_0 | similarity=0.0
  - Excerpt: # OpsFlow — Quick Start  **Last updated:** 2026-02-14  ## What is OpsFlow? OpsFlow is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 5 | doc_id=doc_4660264 | doc_type=USER_GUIDE | chunk_id=doc_4660264_chunk_0 | similarity=0.0
  - Excerpt: # SecureVault — Quick Start  **Last updated:** 2026-02-14  ## What is SecureVault? SecureVault is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::incident_log_sample.csv | false | - |

### V2-Q46

- Classification: D) EXTRACTION GAP
- Query: Create a training path specific to FinReport exports and staleness issues.
- Required evidence: {"must_include_terms": ["FinReport", "ERR-EXP-003", "ERR-SYNC-101"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["FinReport", "ERR-EXP-003", "ERR-SYNC-101"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_5085837 | doc_type=USER_GUIDE | chunk_id=doc_5085837_chunk_0 | similarity=0.0
  - Excerpt: # FinReport — Quick Start  **Last updated:** 2026-02-14  ## What is FinReport? FinReport is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 2 | doc_id=doc_9039050 | doc_type=TROUBLESHOOT | chunk_id=doc_9039050_chunk_1 | similarity=0.0
  - Excerpt: esolution details for ERR-EXP-003 - If `ERR-EXP-003` relates to **limits**, reduce batch size or split workload. - If `ERR-EXP-003` relates to **identity**, re-auth and validate time sync. - If `ERR-EXP-003` relates to **network**, verify proxy/VPN a ... ## Validation - User can reproduce success path and error no longer appears. - A fresh log event confirms completion.  ## Escalation package - code: `ERR-EXP-003` - tool: `FinReport` - timestamp + environment - TraceId/RunId - screenshots/log snippet
- Rank 3 | doc_id=doc_9693041 | doc_type=TROUBLESHOOT | chunk_id=doc_9693041_chunk_1 | similarity=0.0
  - Excerpt: olution details for ERR-SYNC-101 - If `ERR-SYNC-101` relates to **limits**, reduce batch size or split workload. - If `ERR-SYNC-101` relates to **identity**, re-auth and validate time sync. - If `ERR-SYNC-101` relates to **network**, verify proxy/VPN ... # Validation - User can reproduce success path and error no longer appears. - A fresh log event confirms completion.  ## Escalation package - code: `ERR-SYNC-101` - tool: `FinReport` - timestamp + environment - TraceId/RunId - screenshots/log snippet
- Rank 4 | doc_id=doc_7016225 | doc_type=TROUBLESHOOT | chunk_id=doc_7016225_chunk_1 | similarity=0.0
  - Excerpt:  unresolved.  ### Resolution details for ERR-RATE-429 - If `ERR-RATE-429` relates to **limits**, reduce batch size or split workload. - If `ERR-RATE-429` relates to **identity**, re-auth and validate time sync. - If `ERR-RATE-429` relates to **networ ... Validation - User can reproduce success path and error no longer appears. - A fresh log event confirms completion.  ## Escalation package - code: `ERR-RATE-429` - tool: `BatchBridge` - timestamp + environment - TraceId/RunId - screenshots/log snippet
- Rank 5 | doc_id=doc_5310494 | doc_type=TROUBLESHOOT | chunk_id=doc_5310494_chunk_1 | similarity=0.0
  - Excerpt: olved.  ### Resolution details for ERR-TLS-014 - If `ERR-TLS-014` relates to **limits**, reduce batch size or split workload. - If `ERR-TLS-014` relates to **identity**, re-auth and validate time sync. - If `ERR-TLS-014` relates to **network**, verif ...  Validation - User can reproduce success path and error no longer appears. - A fresh log event confirms completion.  ## Escalation package - code: `ERR-TLS-014` - tool: `BatchBridge` - timestamp + environment - TraceId/RunId - screenshots/log snippet

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::FinReport | true | 1 |
| term::ERR-EXP-003 | true | 2 |
| term::ERR-SYNC-101 | true | 3 |

### V2-Q47

- Classification: D) EXTRACTION GAP
- Query: Where is the trust_store configured and what value indicates system store?
- Required evidence: {"must_include_terms": ["trust_store", "system"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["trust_store", "system"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_2448499 | doc_type=USER_GUIDE | chunk_id=doc_2448499_chunk_0 | similarity=0.0
  - Excerpt: # BatchBridge — Quick Start  **Last updated:** 2026-02-14  ## What is BatchBridge? BatchBridge is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 2 | doc_id=doc_8531073 | doc_type=USER_GUIDE | chunk_id=doc_8531073_chunk_0 | similarity=0.0
  - Excerpt: # DataDesk — Quick Start  **Last updated:** 2026-02-14  ## What is DataDesk? DataDesk is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 3 | doc_id=doc_5085837 | doc_type=USER_GUIDE | chunk_id=doc_5085837_chunk_0 | similarity=0.0
  - Excerpt: # FinReport — Quick Start  **Last updated:** 2026-02-14  ## What is FinReport? FinReport is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 4 | doc_id=doc_0594944 | doc_type=USER_GUIDE | chunk_id=doc_0594944_chunk_0 | similarity=0.0
  - Excerpt: # OpsFlow — Quick Start  **Last updated:** 2026-02-14  ## What is OpsFlow? OpsFlow is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 5 | doc_id=doc_4660264 | doc_type=USER_GUIDE | chunk_id=doc_4660264_chunk_0 | similarity=0.0
  - Excerpt: # SecureVault — Quick Start  **Last updated:** 2026-02-14  ## What is SecureVault? SecureVault is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::trust_store | false | - |
| term::system | false | - |

### V2-Q48

- Classification: D) EXTRACTION GAP
- Query: What is the recommended evidence to include when escalating a generic HTTP 5xx gateway issue?
- Required evidence: {"must_include_terms": ["HTTP 502", "HTTP 504"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["HTTP 502", "HTTP 504"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_7447053 | doc_type=TROUBLESHOOT | chunk_id=doc_7447053_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: All Tools — HTTP 502/504 (Gateway errors and triage)  **Last updated:** 2026-02-14   **Applies to:** All Tools (Web UI + API)  ## Symptoms - User sees `HTTP 502/504` and cannot complete the workflow. - UI may show a banner/dialog.  ** ... . Capture evidence for escalation if unresolved.  ### Resolution details for HTTP 502/504 - If `HTTP 502/504` relates to **limits**, reduce batch size or split workload. - If `HTTP 502/504` relates to **identity**, re-auth and validate time sync. - I
- Rank 2 | doc_id=doc_3138757 | doc_type=TROUBLESHOOT | chunk_id=doc_3138757_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: BatchBridge+OpsFlow — HTTP 429 (Differentiate HTTP 429 vs ERR-RATE-429)  **Last updated:** 2026-02-14   **Applies to:** BatchBridge+OpsFlow (Web UI + API)  ## Symptoms - User sees `HTTP 429` and cannot complete the workflow. - UI may  ... he workflow end-to-end. 3. Capture evidence for escalation if unresolved.  ### Resolution details for HTTP 429 - If `HTTP 429` relates to **limits**, reduce batch size or split workload. - If `HTTP 429` relates to **identity**, re-auth and validate t
- Rank 3 | doc_id=doc_7016225 | doc_type=TROUBLESHOOT | chunk_id=doc_7016225_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: BatchBridge — ERR-RATE-429 (Backoff required (retry-after: 30s))  **Last updated:** 2026-02-14   **Applies to:** BatchBridge (Web UI + API)  ## Symptoms - User sees `ERR-RATE-429` and cannot complete the workflow. - UI may show a bann ...  end-to-end. 3. Capture evidence for escalation if unresolved.  ### Resolution details for ERR-RATE-429 - If `ERR-RATE-429` relates to **limits**, reduce batch size or split workload. - If `ERR-RATE-429` relates to **identity**, re-auth and validate 
- Rank 4 | doc_id=doc_5310494 | doc_type=TROUBLESHOOT | chunk_id=doc_5310494_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: BatchBridge — ERR-TLS-014 (Unknown CA during TLS handshake)  **Last updated:** 2026-02-14   **Applies to:** BatchBridge (Web UI + API)  ## Symptoms - User sees `ERR-TLS-014` and cannot complete the workflow. - UI may show a banner/dia ... o-end. 3. Capture evidence for escalation if unresolved.  ### Resolution details for ERR-TLS-014 - If `ERR-TLS-014` relates to **limits**, reduce batch size or split workload. - If `ERR-TLS-014` relates to **identity**, re-auth and validate time sync
- Rank 5 | doc_id=doc_0481592 | doc_type=TROUBLESHOOT | chunk_id=doc_0481592_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: DataDesk — ERR-UPL-021 (Payload too large (max 50MB))  **Last updated:** 2026-02-14   **Applies to:** DataDesk (Web UI + API)  ## Symptoms - User sees `ERR-UPL-021` and cannot complete the workflow. - UI may show a banner/dialog.  **S ...  Capture evidence for escalation if unresolved.  ### Resolution details for ERR-UPL-021 - If `ERR-UPL-021` relates to **limits**, reduce batch size or split workload. - If `ERR-UPL-021` relates to **identity**, re-auth and validate time sync. - If `E

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::HTTP 502 | true | 1 |
| term::HTTP 504 | false | - |

### V2-Q50

- Classification: D) EXTRACTION GAP
- Query: Summarize the SecureVault training deck: key slides and takeaways.
- Required evidence: {"must_include_terms": ["SecureVault", "ERR-ACL-002", "ERR-MFA-009"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["SecureVault", "ERR-ACL-002", "ERR-MFA-009"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_4660264 | doc_type=USER_GUIDE | chunk_id=doc_4660264_chunk_0 | similarity=0.0
  - Excerpt: # SecureVault — Quick Start  **Last updated:** 2026-02-14  ## What is SecureVault? SecureVault is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 2 | doc_id=doc_3154314 | doc_type=TROUBLESHOOT | chunk_id=doc_3154314_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: SecureVault — ERR-ACL-002 (Role missing: vault.read)  **Last updated:** 2026-02-14   **Applies to:** SecureVault (Web UI + API)  ## Symptoms - User sees `ERR-ACL-002` and cannot complete the workflow. - UI may show a banner/dialog.  * ... 3. Capture evidence for escalation if unresolved.  ### Resolution details for ERR-ACL-002 - If `ERR-ACL-002` relates to **limits**, reduce batch size or split workload. - If `ERR-ACL-002` relates to **identity**, re-auth and validate time sync. - If 
- Rank 3 | doc_id=doc_7188612 | doc_type=TROUBLESHOOT | chunk_id=doc_7188612_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: SecureVault — ERR-MFA-009 (Device time out of sync)  **Last updated:** 2026-02-14   **Applies to:** SecureVault (Web UI + API)  ## Symptoms - User sees `ERR-MFA-009` and cannot complete the workflow. - UI may show a banner/dialog.  ** ... . Capture evidence for escalation if unresolved.  ### Resolution details for ERR-MFA-009 - If `ERR-MFA-009` relates to **limits**, reduce batch size or split workload. - If `ERR-MFA-009` relates to **identity**, re-auth and validate time sync. - If `
- Rank 4 | doc_id=doc_4582988 | doc_type=TROUBLESHOOT | chunk_id=doc_4582988_chunk_0 | similarity=0.0
  - Excerpt: SOP — Proxy Authentication Errors (ERR-AUTH-407) Last updated: 2026-02-14 If users are behind a corporate proxy, ensure the proxy auth handshake is successful. Key data to collect: TraceId, proxy PAC URL, browser version.
- Rank 5 | doc_id=doc_7016225 | doc_type=TROUBLESHOOT | chunk_id=doc_7016225_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: BatchBridge — ERR-RATE-429 (Backoff required (retry-after: 30s))  **Last updated:** 2026-02-14   **Applies to:** BatchBridge (Web UI + API)  ## Symptoms - User sees `ERR-RATE-429` and cannot complete the workflow. - UI may show a bann ...  end-to-end. 3. Capture evidence for escalation if unresolved.  ### Resolution details for ERR-RATE-429 - If `ERR-RATE-429` relates to **limits**, reduce batch size or split workload. - If `ERR-RATE-429` relates to **identity**, re-auth and validate 

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::SecureVault | true | 1 |
| term::ERR-ACL-002 | true | 2 |
| term::ERR-MFA-009 | true | 3 |

## Mixed (Realism)

- Failures: 16

### V2-Q02

- Classification: D) EXTRACTION GAP
- Query: How do I troubleshoot OpsFlow ERR-AUTH-407 during SSO redirect behind a proxy?
- Required evidence: {"must_include_terms": ["ERR-AUTH-407", "HTTP 407"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["ERR-AUTH-407", "HTTP 407"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_7064022 | doc_type=TROUBLESHOOT | chunk_id=doc_7064022_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: OpsFlow — ERR-AUTH-407 (Proxy authentication required)  **Last updated:** 2026-02-14   **Applies to:** OpsFlow (Web UI + API)  ## Symptoms - User sees `ERR-AUTH-407` and cannot complete the workflow. - UI may show a banner/dialog.  ** ... . Capture evidence for escalation if unresolved.  ### Resolution details for ERR-AUTH-407 - If `ERR-AUTH-407` relates to **limits**, reduce batch size or split workload. - If `ERR-AUTH-407` relates to **identity**, re-auth and validate time sync. - I
- Rank 2 | doc_id=doc_2412097 | doc_type=TROUBLESHOOT | chunk_id=doc_2412097_chunk_0 | similarity=0.0
  - Excerpt: SOP — Proxy Authentication Errors (ERR-AUTH-407) Last updated: 2026-02-14 If users are behind a corporate proxy, ensure the proxy auth handshake is successful. Key data to collect: TraceId, proxy PAC URL, browser version.
- Rank 3 | doc_id=doc_8469478 | doc_type=REFERENCE | chunk_id=doc_8469478_chunk_0 | similarity=0.0
  - Excerpt: # Error Code Catalog V2 This is a reference catalog for error codes and diagnostics.  ## OPSFLOW Error Codes - **ERR-RUN-204**: Worker exited with code 137 (OOM) (Category: Compute, Severity: high) - **ERR-AUTH-407**: Proxy authentication required (C ... Limit, Severity: high) - **ERR-TLS-014**: Unknown CA (Category: TLS, Severity: high)  ## FINREPORT Error Codes - **ERR-EXP-003**: Excel template missing (Category: Config, Severity: medium) - **ERR-SYNC-101**: Data refresh stale (Category: Freshness,
- Rank 4 | doc_id=doc_4695415 | doc_type=INCIDENT | chunk_id=doc_4695415_chunk_0 | similarity=0.0
  - Excerpt: Incident Log: incident_log_sample.csv Format: CSV Total Records: 60 Columns: incident_id, date, tool, code, severity, summary  === AGGREGATED SUMMARY ===  Affected Tools/Platforms:   - OpsFlow: 18 incidents   - FinReport: 15 incidents   - SecureVault ... erations  Row 3:   incident_id: INC-0003   date: 2025-11-20   tool: FinReport   code: ERR-AUTH-407   severity: P2   summary: FinReport experienced ERR-AUTH-407 during routine operations  Row 4:   incident_id: INC-0004   date: 2026-02-10   tool: OpsFl
- Rank 5 | doc_id=doc_4505736 | doc_type=TROUBLESHOOT | chunk_id=doc_4505736_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: OpsFlow — ERR-RUN-204 (Worker exited with code 137 (OOM))  **Last updated:** 2026-02-14   **Applies to:** OpsFlow (Web UI + API)  ## Symptoms - User sees `ERR-RUN-204` and cannot complete the workflow. - UI may show a banner/dialog.   ...  3. Capture evidence for escalation if unresolved.  ### Resolution details for ERR-RUN-204 - If `ERR-RUN-204` relates to **limits**, reduce batch size or split workload. - If `ERR-RUN-204` relates to **identity**, re-auth and validate time sync. - If

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::ERR-AUTH-407 | true | 1 |
| term::HTTP 407 | false | - |

### V2-Q06

- Classification: D) EXTRACTION GAP
- Query: How do I reduce the chance of ERR-UPL-021 when uploading PDFs?
- Required evidence: {"must_include_terms": ["ERR-UPL-021", "Compress"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["ERR-UPL-021", "Compress"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_3509776 | doc_type=TROUBLESHOOT | chunk_id=doc_3509776_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: DataDesk — ERR-UPL-021 (Payload too large (max 50MB))  **Last updated:** 2026-02-14   **Applies to:** DataDesk (Web UI + API)  ## Symptoms - User sees `ERR-UPL-021` and cannot complete the workflow. - UI may show a banner/dialog.  **S ...  Capture evidence for escalation if unresolved.  ### Resolution details for ERR-UPL-021 - If `ERR-UPL-021` relates to **limits**, reduce batch size or split workload. - If `ERR-UPL-021` relates to **identity**, re-auth and validate time sync. - If `E
- Rank 2 | doc_id=doc_7064022 | doc_type=TROUBLESHOOT | chunk_id=doc_7064022_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: OpsFlow — ERR-AUTH-407 (Proxy authentication required)  **Last updated:** 2026-02-14   **Applies to:** OpsFlow (Web UI + API)  ## Symptoms - User sees `ERR-AUTH-407` and cannot complete the workflow. - UI may show a banner/dialog.  ** ... . Capture evidence for escalation if unresolved.  ### Resolution details for ERR-AUTH-407 - If `ERR-AUTH-407` relates to **limits**, reduce batch size or split workload. - If `ERR-AUTH-407` relates to **identity**, re-auth and validate time sync. - I
- Rank 3 | doc_id=doc_6607544 | doc_type=TROUBLESHOOT | chunk_id=doc_6607544_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: SecureVault — ERR-MFA-009 (Device time out of sync)  **Last updated:** 2026-02-14   **Applies to:** SecureVault (Web UI + API)  ## Symptoms - User sees `ERR-MFA-009` and cannot complete the workflow. - UI may show a banner/dialog.  ** ... . Capture evidence for escalation if unresolved.  ### Resolution details for ERR-MFA-009 - If `ERR-MFA-009` relates to **limits**, reduce batch size or split workload. - If `ERR-MFA-009` relates to **identity**, re-auth and validate time sync. - If `
- Rank 4 | doc_id=doc_4468773 | doc_type=TROUBLESHOOT | chunk_id=doc_4468773_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: All Tools — HTTP 502/504 (Gateway errors and triage)  **Last updated:** 2026-02-14   **Applies to:** All Tools (Web UI + API)  ## Symptoms - User sees `HTTP 502/504` and cannot complete the workflow. - UI may show a banner/dialog.  ** ... . Capture evidence for escalation if unresolved.  ### Resolution details for HTTP 502/504 - If `HTTP 502/504` relates to **limits**, reduce batch size or split workload. - If `HTTP 502/504` relates to **identity**, re-auth and validate time sync. - I
- Rank 5 | doc_id=doc_8469478 | doc_type=REFERENCE | chunk_id=doc_8469478_chunk_0 | similarity=0.0
  - Excerpt: # Error Code Catalog V2 This is a reference catalog for error codes and diagnostics.  ## OPSFLOW Error Codes - **ERR-RUN-204**: Worker exited with code 137 (OOM) (Category: Compute, Severity: high) - **ERR-AUTH-407**: Proxy authentication required (C ... Limit, Severity: high) - **ERR-TLS-014**: Unknown CA (Category: TLS, Severity: high)  ## FINREPORT Error Codes - **ERR-EXP-003**: Excel template missing (Category: Config, Severity: medium) - **ERR-SYNC-101**: Data refresh stale (Category: Freshness,

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::ERR-UPL-021 | true | 1 |
| term::Compress | false | - |

### V2-Q19

- Classification: D) EXTRACTION GAP
- Query: Differentiate generic HTTP 502 vs 504 in triage steps.
- Required evidence: {"must_include_terms": ["HTTP 502", "HTTP 504"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["HTTP 502", "HTTP 504"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_4468773 | doc_type=TROUBLESHOOT | chunk_id=doc_4468773_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: All Tools — HTTP 502/504 (Gateway errors and triage)  **Last updated:** 2026-02-14   **Applies to:** All Tools (Web UI + API)  ## Symptoms - User sees `HTTP 502/504` and cannot complete the workflow. - UI may show a banner/dialog.  ** ... . Capture evidence for escalation if unresolved.  ### Resolution details for HTTP 502/504 - If `HTTP 502/504` relates to **limits**, reduce batch size or split workload. - If `HTTP 502/504` relates to **identity**, re-auth and validate time sync. - I
- Rank 2 | doc_id=doc_4013709 | doc_type=TROUBLESHOOT | chunk_id=doc_4013709_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: BatchBridge+OpsFlow — HTTP 429 (Differentiate HTTP 429 vs ERR-RATE-429)  **Last updated:** 2026-02-14   **Applies to:** BatchBridge+OpsFlow (Web UI + API)  ## Symptoms - User sees `HTTP 429` and cannot complete the workflow. - UI may  ... he workflow end-to-end. 3. Capture evidence for escalation if unresolved.  ### Resolution details for HTTP 429 - If `HTTP 429` relates to **limits**, reduce batch size or split workload. - If `HTTP 429` relates to **identity**, re-auth and validate t
- Rank 3 | doc_id=doc_6002097 | doc_type=SOP | chunk_id=doc_6002097_chunk_0 | similarity=0.0
  - Excerpt: SOP — Handling Rate Limits (HTTP 429 / ERR-RATE-429) Last updated: 2026-02-14 Purpose Standardize Tier 1 response when connectors hit rate limiting. Procedure Step 1: Confirm whether error is HTTP 429 or ERR-RATE-429; capture retry-after value. Step 2: Enable exponential backoff in connector settings. Step 3: Reduce concurrency (workers/threads) and retry. Step 4: If persistent, request quota increase with evidence (RunId, timestamps, volume). Reference screenshot
- Rank 4 | doc_id=doc_5624591 | doc_type=TROUBLESHOOT | chunk_id=doc_5624591_chunk_0 | similarity=0.0
  - Excerpt: ToolX Troubleshooting Pack (Training) This training pack is part of the KTS test corpus. It includes common errors, symptoms, and validation steps. Module 1: ERR-AUTH-401 Token expired after SSO redirect  - Symptoms: error modal after redirect  - Fix: hard refresh, re-auth, allow cookies (test), capture TraceId Module 2: HTTP 504 Gateway Timeout  - Symptoms: dashboard banner, partial widget load  - Fix: connection test, clear cache, verify VPN/proxy  Appendix: Sample screenshots (for indexing)
- Rank 5 | doc_id=doc_5000037 | doc_type=TROUBLESHOOT | chunk_id=doc_5000037_chunk_0 | similarity=0.0
  - Excerpt: # KTS Synthetic Corpus v2 (Complex)  This corpus is intentionally more complex than v1: - Multiple tools (OpsFlow, DataDesk, SecureVault, BatchBridge, FinReport) - Overlapping errors (HTTP 429 vs ERR-RATE-429; generic gateway 5xx) - Mixed formats (MD, DOCX, PDF, PPTX, CSV, JSON, YAML, INI, PNG) - A legacy/deprecated troubleshooting doc for freshness/version testing  Top screenshot folder: `Reference/images/`

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::HTTP 502 | true | 1 |
| term::HTTP 504 | true | 4 |

### V2-Q26

- Classification: D) EXTRACTION GAP
- Query: Which documents in this corpus look archived or outdated based on dates?
- Required evidence: {"must_include_terms": ["ARCHIVED", "DEPRECATED"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["ARCHIVED", "DEPRECATED"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_5077281 | doc_type=USER_GUIDE | chunk_id=doc_5077281_chunk_0 | similarity=0.0
  - Excerpt: # BatchBridge — Quick Start  **Last updated:** 2026-02-14  ## What is BatchBridge? BatchBridge is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 2 | doc_id=doc_4126911 | doc_type=USER_GUIDE | chunk_id=doc_4126911_chunk_0 | similarity=0.0
  - Excerpt: # DataDesk — Quick Start  **Last updated:** 2026-02-14  ## What is DataDesk? DataDesk is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 3 | doc_id=doc_4277722 | doc_type=USER_GUIDE | chunk_id=doc_4277722_chunk_0 | similarity=0.0
  - Excerpt: # FinReport — Quick Start  **Last updated:** 2026-02-14  ## What is FinReport? FinReport is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 4 | doc_id=doc_6347289 | doc_type=USER_GUIDE | chunk_id=doc_6347289_chunk_0 | similarity=0.0
  - Excerpt: # OpsFlow — Quick Start  **Last updated:** 2026-02-14  ## What is OpsFlow? OpsFlow is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 5 | doc_id=doc_9493895 | doc_type=USER_GUIDE | chunk_id=doc_9493895_chunk_0 | similarity=0.0
  - Excerpt: # SecureVault — Quick Start  **Last updated:** 2026-02-14  ## What is SecureVault? SecureVault is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::ARCHIVED | false | - |
| term::DEPRECATED | false | - |

### V2-Q27

- Classification: D) EXTRACTION GAP
- Query: Summarize incident INC-0021: what happened and what corrective actions were taken?
- Required evidence: {"must_include_terms": ["INC-0021", "ERR-RATE-429"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["INC-0021", "ERR-RATE-429"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_4112515 | doc_type=USER_GUIDE | chunk_id=doc_4112515_chunk_0 | similarity=0.0
  - Excerpt: # ToolX — Quick Start for New Users  **Last updated:** 2026-02-14    ## What is ToolX? ToolX is a ticketing and job-monitoring interface used to view **Tickets**, run **Jobs**, and check **System Status**.  ## First login 1. Open ToolX. 2. Click **Si ... see `ERR-AUTH-401`, follow the troubleshooting guide:    - `Troubleshoot_ToolX_AUTH401.md`  ## Daily workflow - Check **Tickets** for assignments - Use **Jobs** to rerun a failed batch - Use **Help → Run Connection Test** if the Dashboard looks stale
- Rank 2 | doc_id=doc_5077281 | doc_type=USER_GUIDE | chunk_id=doc_5077281_chunk_0 | similarity=0.0
  - Excerpt: # BatchBridge — Quick Start  **Last updated:** 2026-02-14  ## What is BatchBridge? BatchBridge is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 3 | doc_id=doc_4126911 | doc_type=USER_GUIDE | chunk_id=doc_4126911_chunk_0 | similarity=0.0
  - Excerpt: # DataDesk — Quick Start  **Last updated:** 2026-02-14  ## What is DataDesk? DataDesk is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 4 | doc_id=doc_4277722 | doc_type=USER_GUIDE | chunk_id=doc_4277722_chunk_0 | similarity=0.0
  - Excerpt: # FinReport — Quick Start  **Last updated:** 2026-02-14  ## What is FinReport? FinReport is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 5 | doc_id=doc_6347289 | doc_type=USER_GUIDE | chunk_id=doc_6347289_chunk_0 | similarity=0.0
  - Excerpt: # OpsFlow — Quick Start  **Last updated:** 2026-02-14  ## What is OpsFlow? OpsFlow is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::INC-0021 | false | - |
| term::ERR-RATE-429 | false | - |

### V2-Q29

- Classification: D) EXTRACTION GAP
- Query: Where do I configure BatchBridge retry/backoff defaults? Provide the key YAML fields.
- Required evidence: {"must_include_terms": ["retry", "exponential", "max_concurrency"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["retry", "exponential", "max_concurrency"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_5077281 | doc_type=USER_GUIDE | chunk_id=doc_5077281_chunk_0 | similarity=0.0
  - Excerpt: # BatchBridge — Quick Start  **Last updated:** 2026-02-14  ## What is BatchBridge? BatchBridge is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 2 | doc_id=doc_5878766 | doc_type=TROUBLESHOOT | chunk_id=doc_5878766_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: BatchBridge — ERR-RATE-429 (Backoff required (retry-after: 30s))  **Last updated:** 2026-02-14   **Applies to:** BatchBridge (Web UI + API)  ## Symptoms - User sees `ERR-RATE-429` and cannot complete the workflow. - UI may show a bann ...  end-to-end. 3. Capture evidence for escalation if unresolved.  ### Resolution details for ERR-RATE-429 - If `ERR-RATE-429` relates to **limits**, reduce batch size or split workload. - If `ERR-RATE-429` relates to **identity**, re-auth and validate 
- Rank 3 | doc_id=doc_2156233 | doc_type=TROUBLESHOOT | chunk_id=doc_2156233_chunk_0 | similarity=0.0
  - Excerpt: # LEGACY (OUTDATED): BatchBridge — ERR-TLS-014 Unknown CA  **Last updated:** 2025-08-03   **Status:** DEPRECATED — Use the newer troubleshooting guide.  ## Warning This document contains older steps that no longer apply after the 2026-01 certificate rollout.  ## Old resolution (do not use) - Import certificate manually into Java keystore (legacy JRE)  ## New reference See: `Troubleshoot_BatchBridge_ERR-TLS-014_UnknownCA.md`
- Rank 4 | doc_id=doc_3636746 | doc_type=INCIDENT | chunk_id=doc_3636746_chunk_0 | similarity=0.0
  - Excerpt: # Postmortem: BatchBridge Rate Limiting Spike (INC-0021)  **Date:** 2026-01-18   **Severity:** P1   **Primary signal:** HTTP 429 / ERR-RATE-429  ## Summary A surge in downstream API usage caused rate limiting. Retries without backoff amplified the issue.  ## Corrective actions - Default backoff enabled in 3.1.0 (see release notes) - SOP published: SOP_Rate_Limit_Response_v1.docx  ## Evidence Screenshot: `Reference/images/ui_07.png`
- Rank 5 | doc_id=doc_5365757 | doc_type=TROUBLESHOOT | chunk_id=doc_5365757_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: ToolX — ERR-AUTH-401 (Token expired after SSO redirect)  **Last updated:** 2026-02-14   **Owner:** KTS Test Corpus Team   **Applies to:** ToolX Web UI (Prod / UAT)  ## Symptoms - Users attempt to sign in via SSO and are redirected bac ... ab, then sign back in. 3. In the browser, **allow third‑party cookies** for the identity domain (temporary test). 4. If still failing, run the ToolX built‑in connection test:    - ToolX → **Settings** → **Help** → **Run Connection Test** 5. Validate:

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::retry | true | 2 |
| term::exponential | false | - |
| term::max_concurrency | false | - |

### V2-Q30

- Classification: D) EXTRACTION GAP
- Query: Where is the OpsFlow proxy PAC URL configured and what are timeout defaults?
- Required evidence: {"must_include_terms": ["pac_url", "read_seconds"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["pac_url", "read_seconds"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_6347289 | doc_type=USER_GUIDE | chunk_id=doc_6347289_chunk_0 | similarity=0.0
  - Excerpt: # OpsFlow — Quick Start  **Last updated:** 2026-02-14  ## What is OpsFlow? OpsFlow is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 2 | doc_id=doc_2412097 | doc_type=TROUBLESHOOT | chunk_id=doc_2412097_chunk_0 | similarity=0.0
  - Excerpt: SOP — Proxy Authentication Errors (ERR-AUTH-407) Last updated: 2026-02-14 If users are behind a corporate proxy, ensure the proxy auth handshake is successful. Key data to collect: TraceId, proxy PAC URL, browser version.
- Rank 3 | doc_id=doc_7064022 | doc_type=TROUBLESHOOT | chunk_id=doc_7064022_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: OpsFlow — ERR-AUTH-407 (Proxy authentication required)  **Last updated:** 2026-02-14   **Applies to:** OpsFlow (Web UI + API)  ## Symptoms - User sees `ERR-AUTH-407` and cannot complete the workflow. - UI may show a banner/dialog.  ** ... . Capture evidence for escalation if unresolved.  ### Resolution details for ERR-AUTH-407 - If `ERR-AUTH-407` relates to **limits**, reduce batch size or split workload. - If `ERR-AUTH-407` relates to **identity**, re-auth and validate time sync. - I
- Rank 4 | doc_id=doc_5077281 | doc_type=USER_GUIDE | chunk_id=doc_5077281_chunk_0 | similarity=0.0
  - Excerpt: # BatchBridge — Quick Start  **Last updated:** 2026-02-14  ## What is BatchBridge? BatchBridge is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 5 | doc_id=doc_4126911 | doc_type=USER_GUIDE | chunk_id=doc_4126911_chunk_0 | similarity=0.0
  - Excerpt: # DataDesk — Quick Start  **Last updated:** 2026-02-14  ## What is DataDesk? DataDesk is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::pac_url | true | 2 |
| term::read_seconds | false | - |

### V2-Q31

- Classification: D) EXTRACTION GAP
- Query: What is the max concurrency default for BatchBridge connectors?
- Required evidence: {"must_include_terms": ["max_concurrency"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["max_concurrency"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_5077281 | doc_type=USER_GUIDE | chunk_id=doc_5077281_chunk_0 | similarity=0.0
  - Excerpt: # BatchBridge — Quick Start  **Last updated:** 2026-02-14  ## What is BatchBridge? BatchBridge is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 2 | doc_id=doc_4112515 | doc_type=USER_GUIDE | chunk_id=doc_4112515_chunk_0 | similarity=0.0
  - Excerpt: # ToolX — Quick Start for New Users  **Last updated:** 2026-02-14    ## What is ToolX? ToolX is a ticketing and job-monitoring interface used to view **Tickets**, run **Jobs**, and check **System Status**.  ## First login 1. Open ToolX. 2. Click **Si ... see `ERR-AUTH-401`, follow the troubleshooting guide:    - `Troubleshoot_ToolX_AUTH401.md`  ## Daily workflow - Check **Tickets** for assignments - Use **Jobs** to rerun a failed batch - Use **Help → Run Connection Test** if the Dashboard looks stale
- Rank 3 | doc_id=doc_5878766 | doc_type=TROUBLESHOOT | chunk_id=doc_5878766_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: BatchBridge — ERR-RATE-429 (Backoff required (retry-after: 30s))  **Last updated:** 2026-02-14   **Applies to:** BatchBridge (Web UI + API)  ## Symptoms - User sees `ERR-RATE-429` and cannot complete the workflow. - UI may show a bann ...  end-to-end. 3. Capture evidence for escalation if unresolved.  ### Resolution details for ERR-RATE-429 - If `ERR-RATE-429` relates to **limits**, reduce batch size or split workload. - If `ERR-RATE-429` relates to **identity**, re-auth and validate 
- Rank 4 | doc_id=doc_6633780 | doc_type=TROUBLESHOOT | chunk_id=doc_6633780_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: BatchBridge — ERR-TLS-014 (Unknown CA during TLS handshake)  **Last updated:** 2026-02-14   **Applies to:** BatchBridge (Web UI + API)  ## Symptoms - User sees `ERR-TLS-014` and cannot complete the workflow. - UI may show a banner/dia ... o-end. 3. Capture evidence for escalation if unresolved.  ### Resolution details for ERR-TLS-014 - If `ERR-TLS-014` relates to **limits**, reduce batch size or split workload. - If `ERR-TLS-014` relates to **identity**, re-auth and validate time sync
- Rank 5 | doc_id=doc_4013709 | doc_type=TROUBLESHOOT | chunk_id=doc_4013709_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: BatchBridge+OpsFlow — HTTP 429 (Differentiate HTTP 429 vs ERR-RATE-429)  **Last updated:** 2026-02-14   **Applies to:** BatchBridge+OpsFlow (Web UI + API)  ## Symptoms - User sees `HTTP 429` and cannot complete the workflow. - UI may  ... he workflow end-to-end. 3. Capture evidence for escalation if unresolved.  ### Resolution details for HTTP 429 - If `HTTP 429` relates to **limits**, reduce batch size or split workload. - If `HTTP 429` relates to **identity**, re-auth and validate t

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::max_concurrency | false | - |

### V2-Q32

- Classification: D) EXTRACTION GAP
- Query: What are the backoff base_seconds and max_seconds defaults?
- Required evidence: {"must_include_terms": ["base_seconds", "max_seconds"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["base_seconds", "max_seconds"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_4112515 | doc_type=USER_GUIDE | chunk_id=doc_4112515_chunk_0 | similarity=0.0
  - Excerpt: # ToolX — Quick Start for New Users  **Last updated:** 2026-02-14    ## What is ToolX? ToolX is a ticketing and job-monitoring interface used to view **Tickets**, run **Jobs**, and check **System Status**.  ## First login 1. Open ToolX. 2. Click **Si ... see `ERR-AUTH-401`, follow the troubleshooting guide:    - `Troubleshoot_ToolX_AUTH401.md`  ## Daily workflow - Check **Tickets** for assignments - Use **Jobs** to rerun a failed batch - Use **Help → Run Connection Test** if the Dashboard looks stale
- Rank 2 | doc_id=doc_5077281 | doc_type=USER_GUIDE | chunk_id=doc_5077281_chunk_0 | similarity=0.0
  - Excerpt: # BatchBridge — Quick Start  **Last updated:** 2026-02-14  ## What is BatchBridge? BatchBridge is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 3 | doc_id=doc_4126911 | doc_type=USER_GUIDE | chunk_id=doc_4126911_chunk_0 | similarity=0.0
  - Excerpt: # DataDesk — Quick Start  **Last updated:** 2026-02-14  ## What is DataDesk? DataDesk is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 4 | doc_id=doc_4277722 | doc_type=USER_GUIDE | chunk_id=doc_4277722_chunk_0 | similarity=0.0
  - Excerpt: # FinReport — Quick Start  **Last updated:** 2026-02-14  ## What is FinReport? FinReport is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 5 | doc_id=doc_6347289 | doc_type=USER_GUIDE | chunk_id=doc_6347289_chunk_0 | similarity=0.0
  - Excerpt: # OpsFlow — Quick Start  **Last updated:** 2026-02-14  ## What is OpsFlow? OpsFlow is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::base_seconds | false | - |
| term::max_seconds | false | - |

### V2-Q34

- Classification: D) EXTRACTION GAP
- Query: Find where upload gateway is mentioned in the architecture overview.
- Required evidence: {"must_include_terms": ["Upload Gateway"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["Upload Gateway"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_5077281 | doc_type=USER_GUIDE | chunk_id=doc_5077281_chunk_0 | similarity=0.0
  - Excerpt: # BatchBridge — Quick Start  **Last updated:** 2026-02-14  ## What is BatchBridge? BatchBridge is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 2 | doc_id=doc_4126911 | doc_type=USER_GUIDE | chunk_id=doc_4126911_chunk_0 | similarity=0.0
  - Excerpt: # DataDesk — Quick Start  **Last updated:** 2026-02-14  ## What is DataDesk? DataDesk is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 3 | doc_id=doc_4277722 | doc_type=USER_GUIDE | chunk_id=doc_4277722_chunk_0 | similarity=0.0
  - Excerpt: # FinReport — Quick Start  **Last updated:** 2026-02-14  ## What is FinReport? FinReport is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 4 | doc_id=doc_6347289 | doc_type=USER_GUIDE | chunk_id=doc_6347289_chunk_0 | similarity=0.0
  - Excerpt: # OpsFlow — Quick Start  **Last updated:** 2026-02-14  ## What is OpsFlow? OpsFlow is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 5 | doc_id=doc_9493895 | doc_type=USER_GUIDE | chunk_id=doc_9493895_chunk_0 | similarity=0.0
  - Excerpt: # SecureVault — Quick Start  **Last updated:** 2026-02-14  ## What is SecureVault? SecureVault is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::Upload Gateway | false | - |

### V2-Q36

- Classification: D) EXTRACTION GAP
- Query: In the training deck, what are the two most common SecureVault issues covered?
- Required evidence: {"must_include_terms": ["ERR-ACL-002", "ERR-MFA-009"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["ERR-ACL-002", "ERR-MFA-009"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_9493895 | doc_type=USER_GUIDE | chunk_id=doc_9493895_chunk_0 | similarity=0.0
  - Excerpt: # SecureVault — Quick Start  **Last updated:** 2026-02-14  ## What is SecureVault? SecureVault is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 2 | doc_id=doc_5077281 | doc_type=USER_GUIDE | chunk_id=doc_5077281_chunk_0 | similarity=0.0
  - Excerpt: # BatchBridge — Quick Start  **Last updated:** 2026-02-14  ## What is BatchBridge? BatchBridge is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 3 | doc_id=doc_4126911 | doc_type=USER_GUIDE | chunk_id=doc_4126911_chunk_0 | similarity=0.0
  - Excerpt: # DataDesk — Quick Start  **Last updated:** 2026-02-14  ## What is DataDesk? DataDesk is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 4 | doc_id=doc_4277722 | doc_type=USER_GUIDE | chunk_id=doc_4277722_chunk_0 | similarity=0.0
  - Excerpt: # FinReport — Quick Start  **Last updated:** 2026-02-14  ## What is FinReport? FinReport is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 5 | doc_id=doc_6347289 | doc_type=USER_GUIDE | chunk_id=doc_6347289_chunk_0 | similarity=0.0
  - Excerpt: # OpsFlow — Quick Start  **Last updated:** 2026-02-14  ## What is OpsFlow? OpsFlow is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::ERR-ACL-002 | false | - |
| term::ERR-MFA-009 | false | - |

### V2-Q43

- Classification: D) EXTRACTION GAP
- Query: From the incident CSV, find incidents in the last 14 days and list their codes.
- Required evidence: {"must_include_terms": ["incident_log_sample.csv"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["incident_log_sample.csv"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_7998278 | doc_type=TROUBLESHOOT | chunk_id=doc_7998278_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: ToolY — ERR-UPL-013 (File type not allowed)  **Last updated:** 2026-02-14   **Owner:** KTS Test Corpus Team   **Applies to:** ToolY Upload workflow  ## Symptoms - Upload fails immediately with: `ERR-UPL-013: File type not allowed: .ex ... ion is blocked but business‑required, request policy change:    - Provide: business justification, file type, retention need, malware scanning approach.  ## Validation - Upload succeeds and appears in **Recent uploads** list. - User can open preview.
- Rank 2 | doc_id=doc_3977135 | doc_type=TROUBLESHOOT | chunk_id=doc_3977135_chunk_0 | similarity=0.0
  - Excerpt: SOP — Handling ToolX Login Failures (Tier 1) Last updated: 2026-02-14 Purpose Provide a consistent Tier 1 process for resolving ToolX sign-in issues. Procedure Step 1: Collect the error code and TraceId from the user. Step 2: Ask the user to hard ref ... esh (Ctrl+Shift+R). Step 3: If still failing, have user sign out and sign in again. Step 4: Check third-party cookie setting (temporary test). Step 5: If unresolved, capture browser version and environment and escalate to Tier 2. Reference screenshot
- Rank 3 | doc_id=doc_5365757 | doc_type=TROUBLESHOOT | chunk_id=doc_5365757_chunk_1 | similarity=0.0
  - Excerpt: third‑party cookies** for the identity domain (temporary test). 4. If still failing, run the ToolX built‑in connection test:    - ToolX → **Settings** → **Help** → **Run Connection Test** 5. Validate: user can land on the Dashboard without an error d ... rm user can access Dashboard and open **Tickets** page. - Confirm the **Last login** timestamp updates.  ## Escalation data to capture - Error code: `ERR-AUTH-401` - `TraceId` value from dialog - Timestamp + environment (Prod/UAT) - Browser + version
- Rank 4 | doc_id=doc_3684253 | doc_type=TROUBLESHOOT | chunk_id=doc_3684253_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: ToolX — HTTP 504 Gateway Timeout (Dashboard banner)  **Last updated:** 2026-02-14   **Owner:** KTS Test Corpus Team   **Applies to:** ToolX Web UI  ## Symptoms - Banner on Dashboard shows: `HTTP 504 Gateway Timeout` - Widgets load par ... f the issue is site‑wide, check your incident banner or status page.  ## Validation - Refresh Dashboard; confirm banner disappears. - Open **Jobs** and confirm list loads.  ## Notes - If timeouts occur only on one widget, capture widget name and time
- Rank 5 | doc_id=doc_4112515 | doc_type=USER_GUIDE | chunk_id=doc_4112515_chunk_0 | similarity=0.0
  - Excerpt: # ToolX — Quick Start for New Users  **Last updated:** 2026-02-14    ## What is ToolX? ToolX is a ticketing and job-monitoring interface used to view **Tickets**, run **Jobs**, and check **System Status**.  ## First login 1. Open ToolX. 2. Click **Si ... see `ERR-AUTH-401`, follow the troubleshooting guide:    - `Troubleshoot_ToolX_AUTH401.md`  ## Daily workflow - Check **Tickets** for assignments - Use **Jobs** to rerun a failed batch - Use **Help → Run Connection Test** if the Dashboard looks stale

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::incident_log_sample.csv | false | - |

### V2-Q46

- Classification: D) EXTRACTION GAP
- Query: Create a training path specific to FinReport exports and staleness issues.
- Required evidence: {"must_include_terms": ["FinReport", "ERR-EXP-003", "ERR-SYNC-101"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["FinReport", "ERR-EXP-003", "ERR-SYNC-101"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_4277722 | doc_type=USER_GUIDE | chunk_id=doc_4277722_chunk_0 | similarity=0.0
  - Excerpt: # FinReport — Quick Start  **Last updated:** 2026-02-14  ## What is FinReport? FinReport is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 2 | doc_id=doc_2263379 | doc_type=TROUBLESHOOT | chunk_id=doc_2263379_chunk_1 | similarity=0.0
  - Excerpt: esolution details for ERR-EXP-003 - If `ERR-EXP-003` relates to **limits**, reduce batch size or split workload. - If `ERR-EXP-003` relates to **identity**, re-auth and validate time sync. - If `ERR-EXP-003` relates to **network**, verify proxy/VPN a ... ## Validation - User can reproduce success path and error no longer appears. - A fresh log event confirms completion.  ## Escalation package - code: `ERR-EXP-003` - tool: `FinReport` - timestamp + environment - TraceId/RunId - screenshots/log snippet
- Rank 3 | doc_id=doc_3714313 | doc_type=TROUBLESHOOT | chunk_id=doc_3714313_chunk_1 | similarity=0.0
  - Excerpt: olution details for ERR-SYNC-101 - If `ERR-SYNC-101` relates to **limits**, reduce batch size or split workload. - If `ERR-SYNC-101` relates to **identity**, re-auth and validate time sync. - If `ERR-SYNC-101` relates to **network**, verify proxy/VPN ... # Validation - User can reproduce success path and error no longer appears. - A fresh log event confirms completion.  ## Escalation package - code: `ERR-SYNC-101` - tool: `FinReport` - timestamp + environment - TraceId/RunId - screenshots/log snippet
- Rank 4 | doc_id=doc_5365757 | doc_type=TROUBLESHOOT | chunk_id=doc_5365757_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: ToolX — ERR-AUTH-401 (Token expired after SSO redirect)  **Last updated:** 2026-02-14   **Owner:** KTS Test Corpus Team   **Applies to:** ToolX Web UI (Prod / UAT)  ## Symptoms - Users attempt to sign in via SSO and are redirected bac ... ab, then sign back in. 3. In the browser, **allow third‑party cookies** for the identity domain (temporary test). 4. If still failing, run the ToolX built‑in connection test:    - ToolX → **Settings** → **Help** → **Run Connection Test** 5. Validate:
- Rank 5 | doc_id=doc_5878766 | doc_type=TROUBLESHOOT | chunk_id=doc_5878766_chunk_1 | similarity=0.0
  - Excerpt:  unresolved.  ### Resolution details for ERR-RATE-429 - If `ERR-RATE-429` relates to **limits**, reduce batch size or split workload. - If `ERR-RATE-429` relates to **identity**, re-auth and validate time sync. - If `ERR-RATE-429` relates to **networ ... Validation - User can reproduce success path and error no longer appears. - A fresh log event confirms completion.  ## Escalation package - code: `ERR-RATE-429` - tool: `BatchBridge` - timestamp + environment - TraceId/RunId - screenshots/log snippet

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::FinReport | true | 1 |
| term::ERR-EXP-003 | true | 2 |
| term::ERR-SYNC-101 | true | 3 |

### V2-Q47

- Classification: D) EXTRACTION GAP
- Query: Where is the trust_store configured and what value indicates system store?
- Required evidence: {"must_include_terms": ["trust_store", "system"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["trust_store", "system"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_5077281 | doc_type=USER_GUIDE | chunk_id=doc_5077281_chunk_0 | similarity=0.0
  - Excerpt: # BatchBridge — Quick Start  **Last updated:** 2026-02-14  ## What is BatchBridge? BatchBridge is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 2 | doc_id=doc_4126911 | doc_type=USER_GUIDE | chunk_id=doc_4126911_chunk_0 | similarity=0.0
  - Excerpt: # DataDesk — Quick Start  **Last updated:** 2026-02-14  ## What is DataDesk? DataDesk is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 3 | doc_id=doc_4277722 | doc_type=USER_GUIDE | chunk_id=doc_4277722_chunk_0 | similarity=0.0
  - Excerpt: # FinReport — Quick Start  **Last updated:** 2026-02-14  ## What is FinReport? FinReport is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 4 | doc_id=doc_6347289 | doc_type=USER_GUIDE | chunk_id=doc_6347289_chunk_0 | similarity=0.0
  - Excerpt: # OpsFlow — Quick Start  **Last updated:** 2026-02-14  ## What is OpsFlow? OpsFlow is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 5 | doc_id=doc_9493895 | doc_type=USER_GUIDE | chunk_id=doc_9493895_chunk_0 | similarity=0.0
  - Excerpt: # SecureVault — Quick Start  **Last updated:** 2026-02-14  ## What is SecureVault? SecureVault is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::trust_store | false | - |
| term::system | false | - |

### V2-Q48

- Classification: D) EXTRACTION GAP
- Query: What is the recommended evidence to include when escalating a generic HTTP 5xx gateway issue?
- Required evidence: {"must_include_terms": ["HTTP 502", "HTTP 504"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["HTTP 502", "HTTP 504"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_4468773 | doc_type=TROUBLESHOOT | chunk_id=doc_4468773_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: All Tools — HTTP 502/504 (Gateway errors and triage)  **Last updated:** 2026-02-14   **Applies to:** All Tools (Web UI + API)  ## Symptoms - User sees `HTTP 502/504` and cannot complete the workflow. - UI may show a banner/dialog.  ** ... . Capture evidence for escalation if unresolved.  ### Resolution details for HTTP 502/504 - If `HTTP 502/504` relates to **limits**, reduce batch size or split workload. - If `HTTP 502/504` relates to **identity**, re-auth and validate time sync. - I
- Rank 2 | doc_id=doc_4013709 | doc_type=TROUBLESHOOT | chunk_id=doc_4013709_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: BatchBridge+OpsFlow — HTTP 429 (Differentiate HTTP 429 vs ERR-RATE-429)  **Last updated:** 2026-02-14   **Applies to:** BatchBridge+OpsFlow (Web UI + API)  ## Symptoms - User sees `HTTP 429` and cannot complete the workflow. - UI may  ... he workflow end-to-end. 3. Capture evidence for escalation if unresolved.  ### Resolution details for HTTP 429 - If `HTTP 429` relates to **limits**, reduce batch size or split workload. - If `HTTP 429` relates to **identity**, re-auth and validate t
- Rank 3 | doc_id=doc_5878766 | doc_type=TROUBLESHOOT | chunk_id=doc_5878766_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: BatchBridge — ERR-RATE-429 (Backoff required (retry-after: 30s))  **Last updated:** 2026-02-14   **Applies to:** BatchBridge (Web UI + API)  ## Symptoms - User sees `ERR-RATE-429` and cannot complete the workflow. - UI may show a bann ...  end-to-end. 3. Capture evidence for escalation if unresolved.  ### Resolution details for ERR-RATE-429 - If `ERR-RATE-429` relates to **limits**, reduce batch size or split workload. - If `ERR-RATE-429` relates to **identity**, re-auth and validate 
- Rank 4 | doc_id=doc_6633780 | doc_type=TROUBLESHOOT | chunk_id=doc_6633780_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: BatchBridge — ERR-TLS-014 (Unknown CA during TLS handshake)  **Last updated:** 2026-02-14   **Applies to:** BatchBridge (Web UI + API)  ## Symptoms - User sees `ERR-TLS-014` and cannot complete the workflow. - UI may show a banner/dia ... o-end. 3. Capture evidence for escalation if unresolved.  ### Resolution details for ERR-TLS-014 - If `ERR-TLS-014` relates to **limits**, reduce batch size or split workload. - If `ERR-TLS-014` relates to **identity**, re-auth and validate time sync
- Rank 5 | doc_id=doc_3509776 | doc_type=TROUBLESHOOT | chunk_id=doc_3509776_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: DataDesk — ERR-UPL-021 (Payload too large (max 50MB))  **Last updated:** 2026-02-14   **Applies to:** DataDesk (Web UI + API)  ## Symptoms - User sees `ERR-UPL-021` and cannot complete the workflow. - UI may show a banner/dialog.  **S ...  Capture evidence for escalation if unresolved.  ### Resolution details for ERR-UPL-021 - If `ERR-UPL-021` relates to **limits**, reduce batch size or split workload. - If `ERR-UPL-021` relates to **identity**, re-auth and validate time sync. - If `E

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::HTTP 502 | true | 1 |
| term::HTTP 504 | false | - |

### V2-Q50

- Classification: D) EXTRACTION GAP
- Query: Summarize the SecureVault training deck: key slides and takeaways.
- Required evidence: {"must_include_terms": ["SecureVault", "ERR-ACL-002", "ERR-MFA-009"], "must_not_include_terms": [], "expected_evidence_rules": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}, "parsed_rules": {"all_of_terms": ["SecureVault", "ERR-ACL-002", "ERR-MFA-009"], "any_of_terms": [], "all_of_regex": [], "any_of_regex": [], "raw": {"requires_citation": true, "must_include_terms_in_at_least_one_cited_chunk": true, "prefer_top_doc_type_when_applicable": true}}}

#### Top-5 Chunk Excerpts

- Rank 1 | doc_id=doc_9493895 | doc_type=USER_GUIDE | chunk_id=doc_9493895_chunk_0 | similarity=0.0
  - Excerpt: # SecureVault — Quick Start  **Last updated:** 2026-02-14  ## What is SecureVault? SecureVault is a demo platform used in this synthetic corpus.  ## First login - Use SSO. - If you see an auth error, capture TraceId and follow the troubleshooting guide.  ## Common tasks - View dashboards - Run jobs/queries - Upload files/exports - Request access roles (if required)  ## Where to get help - In-app Help - SOPs folder - Troubleshooting folder
- Rank 2 | doc_id=doc_5624591 | doc_type=TROUBLESHOOT | chunk_id=doc_5624591_chunk_0 | similarity=0.0
  - Excerpt: ToolX Troubleshooting Pack (Training) This training pack is part of the KTS test corpus. It includes common errors, symptoms, and validation steps. Module 1: ERR-AUTH-401 Token expired after SSO redirect  - Symptoms: error modal after redirect  - Fix: hard refresh, re-auth, allow cookies (test), capture TraceId Module 2: HTTP 504 Gateway Timeout  - Symptoms: dashboard banner, partial widget load  - Fix: connection test, clear cache, verify VPN/proxy  Appendix: Sample screenshots (for indexing)
- Rank 3 | doc_id=doc_8753087 | doc_type=TROUBLESHOOT | chunk_id=doc_8753087_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: SecureVault — ERR-ACL-002 (Role missing: vault.read)  **Last updated:** 2026-02-14   **Applies to:** SecureVault (Web UI + API)  ## Symptoms - User sees `ERR-ACL-002` and cannot complete the workflow. - UI may show a banner/dialog.  * ... 3. Capture evidence for escalation if unresolved.  ### Resolution details for ERR-ACL-002 - If `ERR-ACL-002` relates to **limits**, reduce batch size or split workload. - If `ERR-ACL-002` relates to **identity**, re-auth and validate time sync. - If 
- Rank 4 | doc_id=doc_6607544 | doc_type=TROUBLESHOOT | chunk_id=doc_6607544_chunk_0 | similarity=0.0
  - Excerpt: # Troubleshoot: SecureVault — ERR-MFA-009 (Device time out of sync)  **Last updated:** 2026-02-14   **Applies to:** SecureVault (Web UI + API)  ## Symptoms - User sees `ERR-MFA-009` and cannot complete the workflow. - UI may show a banner/dialog.  ** ... . Capture evidence for escalation if unresolved.  ### Resolution details for ERR-MFA-009 - If `ERR-MFA-009` relates to **limits**, reduce batch size or split workload. - If `ERR-MFA-009` relates to **identity**, re-auth and validate time sync. - If `
- Rank 5 | doc_id=doc_4112515 | doc_type=USER_GUIDE | chunk_id=doc_4112515_chunk_0 | similarity=0.0
  - Excerpt: # ToolX — Quick Start for New Users  **Last updated:** 2026-02-14    ## What is ToolX? ToolX is a ticketing and job-monitoring interface used to view **Tickets**, run **Jobs**, and check **System Status**.  ## First login 1. Open ToolX. 2. Click **Si ... see `ERR-AUTH-401`, follow the troubleshooting guide:    - `Troubleshoot_ToolX_AUTH401.md`  ## Daily workflow - Check **Tickets** for assignments - Use **Jobs** to rerun a failed batch - Use **Help → Run Connection Test** if the Dashboard looks stale

#### Per-term Match Table

| Rule | Matched | Chunk Rank |
| :-- | :-- | --: |
| term::SecureVault | true | 1 |
| term::ERR-ACL-002 | true | 3 |
| term::ERR-MFA-009 | true | 4 |

