# KTS Synthetic Corpus v2 — Golden Query Pack (Top 50)

- Purpose: validate retrieval evidence accuracy + doc_type alignment on a harder corpus.
- Split: Tune 40 / Holdout 10

## Queries

### V2-Q01 (tune, QUESTION)
OpsFlow shows ERR-RUN-204. What does it mean and what's the fastest safe fix?

- Must include: ERR-RUN-204, OOM
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q02 (tune, QUESTION)
How do I troubleshoot OpsFlow ERR-AUTH-407 during SSO redirect behind a proxy?

- Must include: ERR-AUTH-407, HTTP 407
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q03 (tune, AUDIT)
What evidence should I capture when OpsFlow fails a run due to OOM?

- Must include: ERR-RUN-204, RunId
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q04 (tune, QUESTION)
DataDesk upload failed with ERR-UPL-021. What's the limit and how do I resolve?

- Must include: ERR-UPL-021, 50MB
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q05 (tune, QUESTION)
DataDesk Query Runner error SQLSTATE 22001: what causes string truncation and how to fix?

- Must include: SQLSTATE 22001, truncation
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q06 (tune, QUESTION)
How do I reduce the chance of ERR-UPL-021 when uploading PDFs?

- Must include: ERR-UPL-021, Compress
- Expected doc type priority: USER_GUIDE, SOP, TROUBLESHOOT, TRAINING, RELEASE_NOTES, REFERENCE, ARCHITECTURE, CONFIG, INCIDENT

### V2-Q07 (tune, QUESTION)
SecureVault access request denied ERR-ACL-002 role missing vault.read. What should I do?

- Must include: ERR-ACL-002, vault.read
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q08 (tune, QUESTION)
SecureVault MFA failing with ERR-MFA-009: device time out of sync. Fix steps?

- Must include: ERR-MFA-009, sync
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q09 (tune, QUESTION)
If SecureVault ERR-ACL-002 keeps happening, what role do I request?

- Must include: vault.read, ERR-ACL-002
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q10 (tune, QUESTION)
BatchBridge connector hits HTTP 429 and ERR-RATE-429. How do I enable backoff and stop retries from amplifying load?

- Must include: HTTP 429, ERR-RATE-429, backoff
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q11 (tune, QUESTION)
Differentiate HTTP 429 vs ERR-RATE-429: when do I treat it as connector config vs downstream rate limit?

- Must include: HTTP 429, ERR-RATE-429
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q12 (tune, QUESTION)
BatchBridge ERR-RATE-429: what does retry-after mean and how should I respect it?

- Must include: retry-after, ERR-RATE-429
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q13 (tune, QUESTION)
BatchBridge TLS handshake failed ERR-TLS-014 unknown CA. What's the modern fix and what should I avoid?

- Must include: ERR-TLS-014, Unknown CA
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q14 (tune, QUESTION)
BatchBridge ERR-TLS-014: what is a corporate root certificate store and why does it matter?

- Must include: ERR-TLS-014, root
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q15 (tune, QUESTION)
FinReport export failed ERR-EXP-003 Excel template missing. Where is the template path and resolution steps?

- Must include: ERR-EXP-003, template
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q16 (tune, QUESTION)
FinReport dashboard says ERR-SYNC-101 data stale. How do I refresh and verify schedule?

- Must include: ERR-SYNC-101, stale
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q17 (tune, QUESTION)
FinReport ERR-SYNC-101: what threshold is implied and what does 'staleness' mean here?

- Must include: ERR-SYNC-101, 24h
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q18 (tune, QUESTION)
I am seeing HTTP 504 on a dashboard. What's the generic gateway triage and what evidence should I capture?

- Must include: HTTP 504, gateway
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q19 (tune, QUESTION)
Differentiate generic HTTP 502 vs 504 in triage steps.

- Must include: HTTP 502, HTTP 504
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q20 (tune, QUESTION)
Find the SOP for rate limits and summarize the procedure.

- Must include: ERR-RATE-429, backoff
- Expected doc type priority: SOP, TROUBLESHOOT, USER_GUIDE, TRAINING, RELEASE_NOTES, REFERENCE, INCIDENT, ARCHITECTURE, CONFIG

### V2-Q21 (tune, QUESTION)
Find the SOP for proxy authentication errors and list required data to collect.

- Must include: ERR-AUTH-407, TraceId
- Expected doc type priority: SOP, TROUBLESHOOT, USER_GUIDE, TRAINING, RELEASE_NOTES, REFERENCE, INCIDENT, ARCHITECTURE, CONFIG

### V2-Q22 (tune, QUESTION)
Find the SOP for data staleness ERR-SYNC-101 and summarize.

- Must include: ERR-SYNC-101
- Expected doc type priority: SOP, TROUBLESHOOT, USER_GUIDE, TRAINING, RELEASE_NOTES, REFERENCE, INCIDENT, ARCHITECTURE, CONFIG

### V2-Q23 (tune, QUESTION)
What changed in BatchBridge 2026 Q1 that affects ERR-TLS-014 and rate limiting behavior?

- Must include: 2026 Q1, ERR-TLS-014, ERR-RATE-429
- Expected doc type priority: RELEASE_NOTES, TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, REFERENCE, INCIDENT, ARCHITECTURE, CONFIG

### V2-Q24 (tune, QUESTION)
What does DataDesk 2026 Q1 release notes say about upload limits and SQLSTATE 22001?

- Must include: ERR-UPL-021, SQLSTATE 22001
- Expected doc type priority: RELEASE_NOTES, TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, REFERENCE, INCIDENT, ARCHITECTURE, CONFIG

### V2-Q25 (tune, FRESHNESS)
I found a LEGACY BatchBridge ERR-TLS-014 doc. Is it outdated? What doc should I use instead?

- Must include: LEGACY, DEPRECATED, ERR-TLS-014
- Expected doc type priority: TROUBLESHOOT, RELEASE_NOTES, SOP, INCIDENT, USER_GUIDE, REFERENCE, ARCHITECTURE, CONFIG, TRAINING

### V2-Q26 (tune, FRESHNESS)
Which documents in this corpus look archived or outdated based on dates?

- Must include: ARCHIVED, DEPRECATED
- Expected doc type priority: TROUBLESHOOT, RELEASE_NOTES, SOP, INCIDENT, USER_GUIDE, REFERENCE, ARCHITECTURE, CONFIG, TRAINING

### V2-Q27 (tune, IMPACT)
Summarize incident INC-0021: what happened and what corrective actions were taken?

- Must include: INC-0021, ERR-RATE-429
- Expected doc type priority: INCIDENT, TROUBLESHOOT, SOP, RELEASE_NOTES, USER_GUIDE, TRAINING, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q28 (tune, AUDIT)
From incident log CSV, list top 3 error codes by count and the most affected tool.

- Must include: incident_log_sample.csv
- Expected doc type priority: INCIDENT, TROUBLESHOOT, SOP, RELEASE_NOTES, USER_GUIDE, TRAINING, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q29 (tune, QUESTION)
Where do I configure BatchBridge retry/backoff defaults? Provide the key YAML fields.

- Must include: retry, exponential, max_concurrency
- Expected doc type priority: CONFIG, TROUBLESHOOT, SOP, USER_GUIDE, REFERENCE, RELEASE_NOTES, TRAINING, ARCHITECTURE, INCIDENT

### V2-Q30 (tune, QUESTION)
Where is the OpsFlow proxy PAC URL configured and what are timeout defaults?

- Must include: pac_url, read_seconds
- Expected doc type priority: CONFIG, TROUBLESHOOT, SOP, USER_GUIDE, REFERENCE, RELEASE_NOTES, TRAINING, ARCHITECTURE, INCIDENT

### V2-Q31 (tune, QUESTION)
What is the max concurrency default for BatchBridge connectors?

- Must include: max_concurrency
- Expected doc type priority: CONFIG, TROUBLESHOOT, SOP, USER_GUIDE, REFERENCE, RELEASE_NOTES, TRAINING, ARCHITECTURE, INCIDENT

### V2-Q32 (tune, QUESTION)
What are the backoff base_seconds and max_seconds defaults?

- Must include: base_seconds, max_seconds
- Expected doc type priority: CONFIG, TROUBLESHOOT, SOP, USER_GUIDE, REFERENCE, RELEASE_NOTES, TRAINING, ARCHITECTURE, INCIDENT

### V2-Q33 (tune, QUESTION)
Explain the Connector Pipeline components and which ones relate to TLS trust store and backoff.

- Must include: TLS Trust Store, Retry/Backoff
- Expected doc type priority: ARCHITECTURE, USER_GUIDE, SOP, TROUBLESHOOT, RELEASE_NOTES, REFERENCE, TRAINING, CONFIG, INCIDENT

### V2-Q34 (tune, QUESTION)
Find where upload gateway is mentioned in the architecture overview.

- Must include: Upload Gateway
- Expected doc type priority: ARCHITECTURE, USER_GUIDE, SOP, TROUBLESHOOT, RELEASE_NOTES, REFERENCE, TRAINING, CONFIG, INCIDENT

### V2-Q35 (tune, TRAINING)
Create a short training path for Tier-1 support on connector triage (Auth/Rate/TLS/Limits/Data).

- Must include: Connector Triage Playbook
- Expected doc type priority: TRAINING, SOP, TROUBLESHOOT, USER_GUIDE, RELEASE_NOTES, REFERENCE, INCIDENT, ARCHITECTURE, CONFIG

### V2-Q36 (tune, QUESTION)
In the training deck, what are the two most common SecureVault issues covered?

- Must include: ERR-ACL-002, ERR-MFA-009
- Expected doc type priority: TRAINING, SOP, TROUBLESHOOT, USER_GUIDE, RELEASE_NOTES, REFERENCE, INCIDENT, ARCHITECTURE, CONFIG

### V2-Q37 (tune, QUESTION)
What does the glossary define TraceId and RunId as?

- Must include: TraceId, RunId
- Expected doc type priority: REFERENCE, TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, ARCHITECTURE, CONFIG

### V2-Q38 (tune, QUESTION)
In the error code catalog, what category and severity is ERR-TLS-014?

- Must include: ERR-TLS-014, severity
- Expected doc type priority: REFERENCE, TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, ARCHITECTURE, CONFIG

### V2-Q39 (tune, QUESTION)
Which doc should rank lower for error-code queries: architecture overview or troubleshooting guide?

- Must include: rank lower, conceptual
- Expected doc type priority: ARCHITECTURE, USER_GUIDE, SOP, TROUBLESHOOT, RELEASE_NOTES, REFERENCE, TRAINING, CONFIG, INCIDENT

### V2-Q40 (tune, QUESTION)
Does BatchBridge 3.1.0 deprecate the Java keystore workaround? Summarize.

- Must include: Deprecated, keystore
- Expected doc type priority: RELEASE_NOTES, TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, REFERENCE, INCIDENT, ARCHITECTURE, CONFIG

### V2-Q41 (holdout, QUESTION)
I see SQLSTATE 22001 and ERR-UPL-021 in the same day. Are these related?

- Must include: SQLSTATE 22001, ERR-UPL-021
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q42 (holdout, FRESHNESS)
Which release notes are archived and why might they still be useful?

- Must include: ARCHIVED
- Expected doc type priority: RELEASE_NOTES, TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, REFERENCE, INCIDENT, ARCHITECTURE, CONFIG

### V2-Q43 (holdout, AUDIT)
From the incident CSV, find incidents in the last 14 days and list their codes.

- Must include: incident_log_sample.csv
- Expected doc type priority: INCIDENT, TROUBLESHOOT, SOP, RELEASE_NOTES, USER_GUIDE, TRAINING, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q44 (holdout, QUESTION)
What proxy settings could cause ERR-AUTH-407 and where are they documented?

- Must include: ERR-AUTH-407, proxy
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q45 (holdout, QUESTION)
If I must pick one doc to start for HTTP 429 issues, which should it be and why?

- Must include: HTTP 429, ERR-RATE-429
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q46 (holdout, TRAINING)
Create a training path specific to FinReport exports and staleness issues.

- Must include: FinReport, ERR-EXP-003, ERR-SYNC-101
- Expected doc type priority: TRAINING, SOP, TROUBLESHOOT, USER_GUIDE, RELEASE_NOTES, REFERENCE, INCIDENT, ARCHITECTURE, CONFIG

### V2-Q47 (holdout, QUESTION)
Where is the trust_store configured and what value indicates system store?

- Must include: trust_store, system
- Expected doc type priority: CONFIG, TROUBLESHOOT, SOP, USER_GUIDE, REFERENCE, RELEASE_NOTES, TRAINING, ARCHITECTURE, INCIDENT

### V2-Q48 (holdout, AUDIT)
What is the recommended evidence to include when escalating a generic HTTP 5xx gateway issue?

- Must include: HTTP 502, HTTP 504
- Expected doc type priority: TROUBLESHOOT, SOP, USER_GUIDE, TRAINING, RELEASE_NOTES, INCIDENT, REFERENCE, ARCHITECTURE, CONFIG

### V2-Q49 (holdout, FRESHNESS)
Does the legacy TLS guide conflict with the 2026 Q1 release notes? Explain.

- Must include: LEGACY, ERR-TLS-014, 2026 Q1
- Expected doc type priority: TROUBLESHOOT, RELEASE_NOTES, SOP, INCIDENT, USER_GUIDE, REFERENCE, ARCHITECTURE, CONFIG, TRAINING

### V2-Q50 (holdout, QUESTION)
Summarize the SecureVault training deck: key slides and takeaways.

- Must include: SecureVault, ERR-ACL-002, ERR-MFA-009
- Expected doc type priority: TRAINING, SOP, TROUBLESHOOT, USER_GUIDE, RELEASE_NOTES, REFERENCE, INCIDENT, ARCHITECTURE, CONFIG
