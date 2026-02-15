# Phase 2 — Test Execution Report

## Environment
- OS: Windows
- Python: 3.13.5
- Virtual environment: `gsf_ir_kts_agentic_system/.venv`
- Dependency install: successful via `pip install -r requirements.txt`

## Commands Executed

### Full Automated Suite
```powershell
python -m pytest -q
```

### Smoke + Operational Scenarios
```powershell
python scripts/smoke.py
python -m cli.main ingest --paths tests/fixtures/complex
python -m cli.main search "error AUTH-401 ToolX" --tool-filter ToolX
python -m cli.main describe pending
python -m cli.main status
```

## Results
- `pytest`: **46 passed**, 0 failed
- `scripts/smoke.py`: **passed**
- Complex CLI scenarios: **passed**

## Representative Validations Confirmed
- Retrieval returns context chunks + citations with file URIs
- Taxonomy classification updates retrieval metadata
- Impact report includes direct/indirect/process/recommendation structure
- Freshness report includes scope-aware buckets and recommendations
- Vision workflow supports pending/status/complete and indexes image descriptions
- Status command reports document/manifest/graph stats

## Defects Found and Closed During Phase 2
1. Version test off-by-one expected version
   - Fixed assertion in `tests/test_phase2_taxonomy_version_10x.py`
2. Earlier schema drift from initial implementation to expanded models
   - Resolved by model + agent + CLI updates (documented in gap closure summary)

## Final Status
✅ Phase 2 validation complete. All automated checks and smoke scenarios pass.
