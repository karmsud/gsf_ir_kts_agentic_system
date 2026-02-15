# Repository Documentation & Script Triage Report
Date: 2026-02-14
Source of Truth: Current verification of Option A2/A3 codebase.

## 1. Inventory Summary
- **Top Level**: 14 folders. `.venv` and `node_modules` are largest. `extension` contains 88MB.
- **Docs**: Mixed state. Many `phase2`/`phase3` artifacts and duplicate audit reports.
- **Scripts**: heavy accumulation of `autopilot` logs and one-off analysis scripts.

## 2. Classification & Action Plan

### A. MUST KEEP (Source of Truth)
These files describe the system as it exists today.
- `README.md` (Top-level entry point)
- `docs/Data_Model.md` (seems core)
- `docs/System_Design.md` (seems core)
- `docs/Agent_Catalog.md` (if accurate)
- `docs/TEST_QUERIES_TOP_50.json` (Canonical test set)

*Action: Rewrite/Verify these in Phase 2.*

### B. KEEP BUT UPDATE
Concepts valid, content might be stale.
- `docs/EXTENSION_USER_GUIDE.md` -> Merge into `docs/EXTENSION.md`
- `docs/TROUBLESHOOTING/*.md` -> Keep as KB, maybe consolidated.
- `docs/Reference/error_code_catalog_v2.json` -> Keep as reference.

### C. ARCHIVE (History)
Move to `docs/archive/20260214/`.
- `docs/phase2/*` (Project history)
- `docs/phase3/*` (Project history)
- `docs/archive/*` (Existing archive - move into nested folder)
- `docs/*_PLAN.md` (Implementation plans executed)
- `docs/*_REPORT.md` (Old execution reports)
- `docs/EXTENSION_OPTION_A_PHASE1.md` (Superseded by A2/A3)
- `docs/BUILD_OPTION_A2_ON_FRESH_CLONE_WINDOWS.md` -> Merge into `docs/EXTENSION.md`

### D. DELETE (Generated/Temporary)
- `scripts/logs/*` (Run artifacts)
- `scripts/autopilot_*/*` (Run artifacts)
- `tests/__pycache__`
- `audit_artifacts/*` (if strictly generated)

## 3. Script Pruning Plan

### Keep (Core Workflow)
- `scripts/build_backend_exe.ps1` (Build)
- `scripts/package_vsix.ps1` (Package)
- `scripts/run_full_eval_suite.py` (Test)
- `scripts/run_accuracy_tuning.ps1` (If used)
- `scripts/check_q7_candidates.py` (Specific diagnostic tool)

### Archive/Delete
- `scripts/evaluate_v1.py` (Legacy)
- `scripts/evaluate_v2.py` (Legacy provided v1/v2 unified suite exists)
- `scripts/analyze_evidence_failures.py`
- `scripts/generate_evidence_heatmap.py`
- `scripts/seed_demo.py` (Unless needed for quickstart)
- `scripts/smoke.py`

## 4. Updates Required
- **Tiered Builds**: `EXTENSION.md` must document A2 vs A3.
- **Image Pipeline**: `ARCHITECTURE.md` must describe the ingestion flow with caching & dedup.
- **CLI**: `CLI_REFERENCE.md` must cover `describe pending` and `crawl/ingest` changes.
