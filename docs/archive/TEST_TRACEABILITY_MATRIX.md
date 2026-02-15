# GSF IR KTS — Test Traceability Matrix

**Version:** 1.0  
**Date:** 2026-02-14

Maps every agent, feature, and workflow to test coverage across all test layers.

---

## Agent Coverage Matrix

| Agent | Unit Tests | Integration Tests | CLI Tests | Scenario Tests | Corpus Files Used | Expected Outputs |
|-------|-----------|-------------------|-----------|----------------|-------------------|------------------|
| **1. Crawler** | `test_crawler.py`: hash computation, manifest diff, change classification (10 tests) | `test_cli_integration.py`: crawl command subprocess (3 tests) | `crawl --paths <dir>` | Full pipeline smoke test | All 14 corpus files | `CrawlResult` with new/modified/deleted/unchanged counts |
| **2. Ingestion** | `test_ingestion.py`: DOCX/PDF/PPTX/HTML/MD converters (15 tests) | `test_phase2_ingestion_10x.py`: converter integration (10 tests) | `ingest --paths <dir>` | Full pipeline smoke test | All 9 doc files (excluding images) | `IngestedDocument` list with doc_ids, markdown paths, metadata |
| **3. Vision** | `test_phase2_vision_10x.py`: manifest operations, state transitions (10 tests) | `test_phase2_vision_10x.py`: pending → complete → index (10 tests) | `describe pending`, `describe complete <doc_id>` | Vision workflow scenario | 4 PNG files in Reference/images/ | `VisionResult` with pending/described counts, image list |
| **4. Taxonomy** | `test_taxonomy.py`: rule matching, confidence scoring (10 tests) | `test_phase2_taxonomy_version_10x.py`: classify + graph integration (10 tests) | N/A (internal to ingest) | Ingestion pipeline | All doc files | `ClassificationResult` with doc_type, confidence, needs_review flag |
| **5. Version** | `test_phase2_taxonomy_version_10x.py`: diff detection, section changes (10 tests) | `test_phase2_taxonomy_version_10x.py`: version chain in graph (10 tests) | N/A (internal to ingest) | Re-ingestion scenario | Modified versions of corpus files | `VersionDiff` with added/removed/modified sections, SUPERSEDES edges |
| **6. Graph Builder** | `test_phase2_graph_retrieval_10x.py`: node/edge creation, deduplication (10 tests) | `test_graph_training_impact.py`: entity extraction, graph stats (10 tests) | N/A (internal to ingest) | Full pipeline smoke test | All doc files | Graph nodes (Document, Tool, Process, Person), edges (DOCUMENTED_IN, AUTHORED_BY, etc.) |
| **7. Retrieval Service** | `test_retrieval.py`: vector search, re-ranking, citation generation (10 tests) | `test_phase2_graph_retrieval_10x.py`: graph-enriched retrieval (10 tests) | `search --query "..." --max-results N` | Top 50 queries scenario | All corpus files + images | `SearchResult` with context_chunks, citations (file:// URIs), image_notes, freshness badges |
| **8. Training Path** | `test_graph_training_impact.py`: prerequisite ordering, time estimation (10 tests) | `test_phase2_advanced_agents_10x.py`: topic resolution, learning path (10 tests) | `training --topic "..." --level beginner` | Training path scenario | Training/, User_Guides/ docs | `TrainingPath` with ordered `LearningStep` list, total_time, coverage |
| **9. Change Impact** | `test_graph_training_impact.py`: entity resolution, transitive traversal (10 tests) | `test_phase2_advanced_agents_10x.py`: impact analysis workflow (10 tests) | `impact --entity "..." --entity-type tool` | Impact scenario | All docs mentioning ToolX/Y/Z | `ImpactReport` with direct/indirect docs, affected_processes, stale_images, severity |
| **10. Freshness** | `test_freshness.py`: age calculation, badge assignment (10 tests) | `test_phase2_advanced_agents_10x.py`: freshness audit with filters (10 tests) | `freshness --scope all --threshold 180` | Freshness scenario | All corpus files | `FreshnessReport` with current/aging/stale/unknown counts, stale_documents list |

**Total Test Count**: 146 tests (46 existing backend + 10 existing extension + 90 new comprehensive tests)

---

## Feature Coverage Matrix

| Feature | Test Type | Test Location | Corpus Dependencies | Expected Behavior |
|---------|-----------|---------------|---------------------|-------------------|
| **Multi-format ingestion** | Unit + Integration | `test_ingestion.py`, `test_phase2_ingestion_10x.py` | DOCX, PDF, PPTX, HTML, MD, TXT, JSON | Each format converted to markdown with metadata |
| **Image extraction (embedded)** | Integration | `test_phase2_vision_10x.py` | DOCX with images, PDF with images, PPTX with images | Images saved to doc folder, added to pending manifest |
| **Image extraction (referenced)** | Integration | `test_phase2_vision_10x.py` | Markdown with `![](image.png)` refs | Referenced images resolved, added to pending manifest |
| **Image extraction (standalone)** | Integration | `test_phase2_vision_10x.py` | PNG/JPG files next to markdown | Standalone images discovered, added to pending manifest |
| **Vision workflow** | Scenario | `test_phase2_vision_10x.py` | 4 PNG files in Reference/images/ | pending → described → indexed → searchable |
| **Taxonomy classification** | Unit + Integration | `test_taxonomy.py`, `test_phase2_taxonomy_version_10x.py` | All corpus files | Each doc classified with confidence score, needs_review flag |
| **Version tracking** | Integration | `test_phase2_taxonomy_version_10x.py` | Modified versions of same doc | SUPERSEDES edges, changed_chunks identified |
| **Graph construction** | Integration | `test_phase2_graph_retrieval_10x.py`, `test_graph_training_impact.py` | All corpus files | Nodes created for docs, tools, processes; edges for relationships |
| **Entity extraction** | Integration | `test_graph_training_impact.py` | Docs mentioning ToolX/Y/Z | Tool/Process nodes created, linked to documents |
| **Vector search** | Unit + Integration | `test_retrieval.py`, `test_phase2_graph_retrieval_10x.py` | All corpus files + images | Query → relevant chunks with similarity scores |
| **Citation generation** | Unit + Scenario | `test_retrieval.py`, Top 50 queries | All corpus files | Every result includes file:// URI, doc_id, version, page/section |
| **Image notes in retrieval** | Integration + Scenario | `test_phase2_graph_retrieval_10x.py`, Top 50 queries | Described images | Results referencing image content include image_note with location |
| **Freshness badging** | Unit + Integration | `test_freshness.py`, `test_phase2_advanced_agents_10x.py` | Docs with various last_updated dates | 🟢🟡🔴⚪ badges assigned correctly |
| **Re-ranking heuristics** | Unit | `test_retrieval.py` | All corpus files | "how to" queries boost SOPs/User Guides, error queries boost Troubleshooting |
| **Confidence thresholding** | Unit + Scenario | All agent tests, Top 50 queries | N/A | Results with <0.5 confidence trigger escalation |
| **Escalation reporting** | Unit + Scenario | All agent tests, Top 50 queries | N/A | Low-confidence results include escalation with suggested SME |
| **Training path generation** | Integration + Scenario | `test_graph_training_impact.py`, `test_phase2_advanced_agents_10x.py` | Training/, User_Guides/ docs | Ordered learning steps with prerequisites, time estimates |
| **Impact analysis** | Integration + Scenario | `test_graph_training_impact.py`, `test_phase2_advanced_agents_10x.py` | All docs mentioning entities | Direct/indirect affected docs, stale images, severity |
| **Idempotency** | Scenario | `test_phase2_cli_10x.py`, smoke script | All corpus files | Re-run crawl → unchanged count matches, re-run ingest → no duplicates |
| **CLI JSON schemas** | CLI | `test_cli_integration.py`, `test_phase2_cli_10x.py` | N/A | Every command returns valid JSON matching schema |
| **VS Code extension commands** | Extension | `extension/tests/*.js` | N/A | Commands execute without errors, invoke backend correctly |
| **@kts Copilot tool** | Extension | `extension/tests/copilot_tests.js` | N/A | Returns SearchResult JSON, parseable by Copilot |
| **@kts Chat participant** | Extension | `extension/tests/chat_tests.js` | N/A | Streams markdown with citations, handles /search and /deep |

---

## Top 50 Queries Coverage

See [TEST_QUERIES_TOP_50.md](TEST_QUERIES_TOP_50.md) and [TEST_QUERIES_TOP_50.json](TEST_QUERIES_TOP_50.json) for full query pack.

| Query Category | Count | Expected Doc Types | Citation Requirements | Validation Method |
|----------------|-------|-------------------|----------------------|-------------------|
| **Error code queries** | 10 | TROUBLESHOOT, REFERENCE | Must cite troubleshooting guide + error catalog JSON | Validate doc_id matches expected troubleshooting doc |
| **How-to queries** | 10 | SOP, USER_GUIDE, TRAINING | Must cite relevant guide with section/page | Validate doc_type is SOP or USER_GUIDE |
| **Release note queries** | 5 | RELEASE_NOTE | Must cite release notes with version | Validate doc_name includes "ReleaseNotes" |
| **Training path queries** | 10 | TRAINING, USER_GUIDE | Must return TrainingPath with ordered steps | Validate prerequisite ordering is correct |
| **Impact queries** | 10 | All types | Must return ImpactReport with direct/indirect docs | Validate all expected docs in report |
| **Freshness queries** | 5 | All types | Must return FreshnessReport with badges | Validate badge assignments match age calculations |

**Total**: 50 queries covering all agent types and doc types

---

## Corpus File → Test Mapping

| Corpus File | Extension | Doc Type | Tests Using This File | Purpose |
|-------------|-----------|----------|----------------------|---------|
| `Reference/error_code_catalog.json` | JSON | REFERENCE | `test_ingestion.py`, error-code queries | Validate JSON ingestion, error code lookup |
| `Reference/SOP_ToolX_Login_Failures_v1.docx` | DOCX | SOP | `test_ingestion.py`, taxonomy, how-to queries, impact queries | Validate DOCX converter, SOP classification |
| `Reference/images/toolx_auth_401.png` | PNG | IMAGE | `test_phase2_vision_10x.py`, vision workflow | Validate image extraction, vision workflow |
| `Reference/images/toolx_timeout_dashboard.png` | PNG | IMAGE | `test_phase2_vision_10x.py`, vision workflow | Validate image extraction, vision workflow |
| `Reference/images/tooly_upload_blocked.png` | PNG | IMAGE | `test_phase2_vision_10x.py`, vision workflow | Validate image extraction, vision workflow |
| `Reference/images/toolz_password_policy.png` | PNG | IMAGE | `test_phase2_vision_10x.py`, vision workflow | Validate image extraction, vision workflow |
| `Release_Notes/ReleaseNotes_ToolX_2026Q1.md` | MD | RELEASE_NOTE | `test_taxonomy.py`, freshness, version, release queries | Validate MD ingestion, release note classification |
| `Training/Training_ToolX_Troubleshooting_Pack.pdf` | PDF | TRAINING | `test_ingestion.py`, training path queries, impact queries | Validate PDF converter, training path generation |
| `Training/Training_ToolY_Upload_Policy.pptx` | PPTX | TRAINING | `test_ingestion.py`, training path queries, impact queries | Validate PPTX converter, training path generation |
| `Troubleshooting/Troubleshoot_ToolX_AUTH401.md` | MD | TROUBLESHOOT | `test_taxonomy.py`, error-code queries, impact queries | Validate troubleshooting classification, error lookup |
| `Troubleshooting/Troubleshoot_ToolX_HTTP504_Timeout.md` | MD | TROUBLESHOOT | `test_taxonomy.py`, error-code queries, impact queries | Validate troubleshooting classification, error lookup |
| `Troubleshooting/Troubleshoot_ToolY_Upload_ERR-UPL-013.md` | MD | TROUBLESHOOT | `test_taxonomy.py`, error-code queries, impact queries | Validate troubleshooting classification, error lookup |
| `Troubleshooting/Troubleshoot_ToolZ_Password_ERR-PWD-007.md` | MD | TROUBLESHOOT | `test_taxonomy.py`, error-code queries, impact queries | Validate troubleshooting classification, error lookup |
| `User_Guides/UserGuide_ToolX_Onboarding.md` | MD | USER_GUIDE | `test_taxonomy.py`, how-to queries, training path queries | Validate user guide classification, training prerequisites |

---

## Test Automation Coverage

| Script | Purpose | Validation |
|--------|---------|------------|
| `scripts/run_kts_test_suite.ps1` | Master test harness (crawl → ingest → queries) | Logs to scripts/logs/, generates test report |
| `scripts/run_kts_test_corpus.ps1` | Quick corpus ingestion (existing) | Used as prerequisite for test suite |
| `tests/test_phase3_comprehensive.py` | Parameterized pytest for Top 50 queries | Validates citations, confidence, escalation |
| `tests/test_smoke_script.py` | Lightweight smoke test | Existing, validates basic pipeline |
| `pytest` (all existing tests) | 46 backend + 10 extension tests | Run before and after changes |

---

## Exit Criteria Traceability

| Exit Criterion | Test Evidence | Location |
|----------------|---------------|----------|
| All 46 backend tests pass | pytest output | CI/local pytest run |
| All 10 extension tests pass | npm test output | extension/tests/ |
| Full corpus smoke test passes | `test_smoke_script.py` | tests/ |
| Top 50 queries >80% correct | `test_phase3_comprehensive.py` | tests/, report template |
| Zero hallucinations | Manual review of query results | Test report template |
| Idempotency verified | `test_phase2_cli_10x.py` | tests/ |
| Multi-modal pipeline functional | `test_phase2_vision_10x.py` | tests/ |
| All CLI commands return valid JSON | `test_cli_integration.py`, `test_phase2_cli_10x.py` | tests/ |
| Extension commands execute without errors | Manual testing + extension tests | extension/tests/ |
| Chat participant returns structured markdown | `extension/tests/chat_tests.js` | extension/tests/ |

---

**Traceability Sign-off:**
- **Test Lead**: ________________ Date: ________
- **QA Engineer**: ________________ Date: ________
