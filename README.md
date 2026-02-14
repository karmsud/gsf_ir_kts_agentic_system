# GSF IR KTS Agentic System

GSF IR KTS is a localized multi-agent knowledge system for ingestion, retrieval, training, impact analysis, and freshness auditing.

## Local-only scope
- All code is self-contained under `gsf_ir_kts_agentic_system`
- Local vector index and graph store under `knowledge_base/`
- No external API keys required for core retrieval flow

## Quickstart
```powershell
cd gsf_ir_kts_agentic_system
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m cli.main --help
```

## Extension + Chat Setup (Business Users)

Prerequisites:
- VS Code with GitHub Copilot Chat enabled
- Access to the workspace where KTS knowledge base is maintained

Install extension from VSIX:
1. Open VS Code
2. Extensions view → `...` menu → `Install from VSIX...`
3. Select `gsf-ir-kts-extension-<version>.vsix`
4. Reload VS Code

Use in chat:
1. Open Copilot Chat
2. Invoke `@kts` participant
3. Ask your question (include tool names/error codes)
4. Optionally attach screenshot and include visible error text in prompt

Expected behavior:
- KTS retrieves context + citations from ingested corpus
- Chat responds with grounded context and source links

## Maintenance Engineer Workflow (Network Corpus)

1. Place source docs on network folder (supported: PDF/DOCX/PPTX/HTML/MD/TXT)
2. Run ingestion:

```powershell
python -m cli.main crawl --paths "\\server\IR_KTS"
python -m cli.main ingest --paths "\\server\IR_KTS"
python -m cli.main status
```

3. Complete image-description queue:

```powershell
python -m cli.main describe pending
python -m cli.main describe complete --doc-id <doc_id> --descriptions-file <descriptions.json>
```

4. Validate retrieval quality:

```powershell
python -m cli.main search "How do I fix AUTH-401 in ToolX?"
python -m cli.main freshness
```

Detailed operational guidance: [docs/MAINTENANCE_ENGINEER_GUIDE.md](docs/MAINTENANCE_ENGINEER_GUIDE.md)
Go-live checklist: [docs/LAUNCH_CHECKLIST.md](docs/LAUNCH_CHECKLIST.md)

## Core Commands
```powershell
python -m cli.main crawl --paths tests/fixtures/simple
python -m cli.main ingest --paths tests/fixtures/simple
python -m cli.main search "How do I reset password?"
python -m cli.main training --topic onboarding
python -m cli.main impact --entity "ToolX"
python -m cli.main freshness
python scripts/smoke.py
pytest -q
```

## Validation

```powershell
python -m pytest -q
python scripts/smoke.py
```
