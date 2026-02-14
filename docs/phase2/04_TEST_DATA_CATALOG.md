# Phase 2 — Test Data Catalog

## Fixture Sources

### Simple Fixtures (`tests/fixtures/simple/`)
- `toolx_user_guide.md`
  - Password reset steps
  - User-guide style language
- `toolx_troubleshoot.md`
  - Error handling and troubleshooting language

### Complex Fixtures (`tests/fixtures/complex/`)
- `enterprise_onboarding.md`
  - Multi-tool, multi-topic content
  - Auth + deployment + incident + training references
- `release_notes_q1.md`
  - Release note semantics and impact trigger terms

## Synthetic Runtime Data (Generated During Tests)
- Temporary markdown/txt/html files
- Empty and unsupported-extension files
- Missing path references
- Large-file conditions (size-gated scan)
- Image placeholders and manifest state transitions
- Graph-linked metadata permutations for tool/process/topic relationships

## Data Dimensions Covered
- Document type variation: SOP, USER_GUIDE, TROUBLESHOOT, TRAINING, RELEASE_NOTE, UNKNOWN
- Query variation: how-to, error, deployment, unknown token, filtered queries
- Freshness variation: all scope, type scope, threshold override, include/exclude image checks
- Impact variation: known entity, partially linked entity, unknown entity

## Negative/Edge Data Patterns
- Empty text content
- Unsupported extension (`.xlsx`)
- Missing source file/path
- Over-size scan threshold behavior
- Short image description rejection
- Unknown operation invocation in vision workflow
