# GSF IR KTS — Launch Checklist

Use this checklist for production go-live approval and periodic re-certification.

---

## 1) Ownership and Governance

- [ ] Product owner assigned (business accountability)
- [ ] Maintenance engineer(s) assigned (ingestion + corpus quality)
- [ ] Technical owner assigned (extension/backend operations)
- [ ] Support escalation path documented (L1/L2/L3)
- [ ] Change approval process defined for corpus and extension updates

Owner table:

| Function | Primary | Backup | Contact |
|---|---|---|---|
| Product Owner |  |  |  |
| Maintenance Engineer |  |  |  |
| Technical Owner |  |  |  |
| Support Lead |  |  |  |

---

## 2) Environment and Access

- [ ] Target VS Code version validated for extension
- [ ] GitHub Copilot Chat enabled for target users
- [ ] Network share access validated for service/workstation accounts
- [ ] Workspace path and permissions validated for `knowledge_base/`
- [ ] Python runtime and dependency installation repeatable

---

## 3) Corpus Readiness

- [ ] Source folders defined and stable
- [ ] Naming convention adopted (SOP/Tool/Error patterns)
- [ ] High-value document sets present (SOP, troubleshooting, release notes, training)
- [ ] Duplicate/stale drafts removed or archived
- [ ] Minimum metadata quality met (title, recency, ownership where possible)

Reference: [MAINTENANCE_ENGINEER_GUIDE.md](MAINTENANCE_ENGINEER_GUIDE.md)

---

## 4) Ingestion and Vision Completion

- [ ] `crawl` and `ingest` run successfully on production corpus path
- [ ] `status` reflects expected document and graph growth
- [ ] Pending image description queue reviewed
- [ ] Image descriptions completed for priority tools/processes
- [ ] `describe complete` indexing confirmed

Operational commands:

```powershell
python -m cli.main crawl --paths "\\server\IR_KTS"
python -m cli.main ingest --paths "\\server\IR_KTS"
python -m cli.main describe pending
python -m cli.main status
```

---

## 5) Quality and Acceptance

- [ ] `python -m pytest -q` passes
- [ ] `python scripts/smoke.py` passes
- [ ] Top 20–30 real user queries evaluated
- [ ] Citation quality accepted by SMEs
- [ ] Freshness output reviewed and actioned for critical stale docs
- [ ] Error-code and screenshot-heavy use cases validated

Acceptance summary:

| Area | Pass/Fail | Notes |
|---|---|---|
| Retrieval relevance |  |  |
| Citation trustworthiness |  |  |
| Troubleshooting coverage |  |  |
| Training-path usefulness |  |  |
| Change-impact accuracy |  |  |

---

## 6) User Rollout and Enablement

- [ ] `.vsix` package built and tested
- [ ] Extension installation guide shared with users
- [ ] `@kts` usage examples shared (good prompts, expected outputs)
- [ ] “How to include screenshot context” guide shared
- [ ] Office hours / support channel announced

---

## 7) Reliability and Recovery

- [ ] Backup procedure defined for `knowledge_base/` (manifest, graph, vectors, docs)
- [ ] Restore drill completed and documented
- [ ] Rollback plan for extension version documented
- [ ] Rollback plan for corpus snapshot documented
- [ ] Incident response owner and timeline defined

Backup/restore notes:

| Component | Backup Method | Restore Verified (Y/N) | Frequency |
|---|---|---|---|
| `knowledge_base/manifest.json` |  |  |  |
| `knowledge_base/graph/` |  |  |  |
| `knowledge_base/vectors/` |  |  |  |
| `knowledge_base/documents/` |  |  |  |

---

## 8) Operating Cadence and SLA

- [ ] Daily/weekly ingestion cadence agreed
- [ ] Freshness audit cadence agreed
- [ ] Query quality review cadence agreed
- [ ] SLA/SLO targets agreed (response quality and incident turnaround)

Suggested baseline:
- Daily: ingest delta for active folders
- Weekly: close image-description backlog, freshness review
- Monthly: corpus cleanup + quality scorecard review

---

## 9) Go / No-Go Decision

Go-live recommendation:

- [ ] **GO**
- [ ] **NO-GO**

Decision notes:

```

```

Approvals:

| Role | Name | Date | Signature |
|---|---|---|---|
| Product Owner |  |  |  |
| Technical Owner |  |  |  |
| Maintenance Lead |  |  |  |
