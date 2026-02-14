# GSF IR KTS — Test Master Plan

**Version:** 1.0  
**Date:** 2026-02-14  
**Corpus Path:** `C:\Users\Karmsud\Projects\gsf_ir_kts_agentic_system\kts_test_corpus`

---

## 1. Test Objectives

### Primary Goals
1. **Validate Agent Contracts**: Confirm each of the 10 agents adheres to its specified input/output contract and error handling behavior
2. **Validate End-to-End Workflows**: Verify complete pipelines from crawl → ingest → index → retrieve → analyze
3. **Validate Multi-Modal Integration**: Confirm image extraction, human-in-loop description, and image-based retrieval
4. **Validate Copilot Integration**: Ensure @kts tool and chat participant return context (not answers) that Copilot can use
5. **Validate CLI Usability**: Confirm all commands are operational, output structured data, and handle errors gracefully
6. **Minimize Hallucination Risk**: Enforce citation requirements, confidence thresholding, escalation triggers
7. **Establish Operational Confidence**: Provide repeatable test harness that can be re-run after any code change

### Success Criteria
- **Zero hallucinations**: Every retrieval result includes citations with file:// URIs
- **Confidence honesty**: Low-confidence results trigger escalation with suggested SME
- **Idempotency**: Re-running crawl/ingest does NOT create duplicates or corrupt state
- **Coverage**: Every agent has at least 10 test scenarios (positive, negative, edge, boundary)
- **Operational readiness**: All CLI commands tested with real corpus, scripts run unattended

### Non-Goals
- **Performance benchmarking**: Not measuring throughput or latency in this phase
- **Scale testing**: Corpus has ~14 files; scale testing deferred
- **Security/compliance testing**: Out of scope for this plan
- **Cross-platform testing**: Windows-only for this iteration

---

## 2. Test Layers

### Layer 1: Unit-Level Functional Tests
**Scope**: Pure functions, converters, utilities  
**Tools**: pytest, mocks  
**Coverage**:
- Text cleaning, chunking, hashing (backend/common/)
- Format converters (DOCX, PDF, PPTX, HTML, MD, TXT)
- Quality gates (confidence thresholding, escalation triggers)
- Manifest operations (read/write/update)

**Example Tests**:
- `test_docx_converter_extracts_text()`
- `test_chunker_preserves_section_boundaries()`
- `test_hash_digest_stable_for_same_content()`
- `test_quality_gate_rejects_low_confidence()`

### Layer 2: Agent Integration Tests
**Scope**: Agent-to-agent interactions, data flow  
**Tools**: pytest with shared fixtures, real temp storage  
**Coverage**:
- Crawler → Ingestion → Taxonomy → Graph → Vector Store
- Vision → Image indexing → Retrieval
- Version → Graph update (SUPERSEDES edges)
- Retrieval → Citation generation → Freshness badging

**Example Tests**:
- `test_ingest_then_classify_then_graph()`
- `test_version_update_triggers_reindex()`
- `test_retrieval_includes_image_notes()`
- `test_impact_traverses_transitive_docs()`

### Layer 3: CLI Integration Tests
**Scope**: Command execution, JSON output schemas, error handling  
**Tools**: subprocess, JSON schema validation  
**Coverage**:
- `crawl --paths <dir>` → CrawlResult JSON
- `ingest --paths <dir>` → IngestedDocument list JSON
- `search --query "..." --max-results N` → SearchResult JSON
- `training --topic "..." --level beginner` → TrainingPath JSON
- `impact --entity "..." --entity-type tool` → ImpactReport JSON
- `freshness --scope all --threshold 180` → FreshnessReport JSON
- `describe pending` → VisionResult JSON
- `describe complete <doc_id> --descriptions-file <path>` → VisionResult JSON

**Example Tests**:
- `test_cli_crawl_returns_valid_json()`
- `test_cli_ingest_fails_on_missing_path()`
- `test_cli_search_includes_citations()`
- `test_cli_training_sorts_by_prerequisites()`

### Layer 4: Scenario & Smoke Tests
**Scope**: Real-world workflows, complex sequences  
**Tools**: pytest + automation scripts  
**Coverage**:
- Full ingestion pipeline (crawl → ingest → status)
- Full retrieval workflow (search → citations → freshness)
- Full vision workflow (pending → complete → search for image content)
- Full training workflow (request path → validate order → verify time estimates)
- Full impact workflow (entity change → identify affected docs → suggest actions)
- Idempotency (re-run crawl → no new files, re-run ingest → no duplicates)

**Example Tests**:
- `test_full_corpus_ingestion_smoke()`
- `test_retrieval_workflow_with_filters()`
- `test_vision_workflow_end_to_end()`
- `test_idempotent_crawl()`

### Layer 5: UX Acceptance Tests
**Scope**: VS Code extension commands, Copilot Chat integration  
**Tools**: Manual + automated extension tests  
**Coverage**:
- `KTS: Crawl & Ingest from File Shares` command
- `KTS: View Status Report` panel
- `KTS: Generate Training Path` command
- `KTS: Analyze Change Impact` command
- `KTS: Run Freshness Audit` command
- `KTS: Review Image Descriptions` panel
- `KTS: Complete Image Descriptions` command
- `@kts` tool callable from code (returns context JSON)
- `@kts` chat participant in Copilot Chat (streams markdown with citations)

**Example Tests**:
- `test_chat_participant_returns_citations()`
- `test_kts_tool_parse_response()`
- `test_status_panel_renders_html()`

---

## 3. Pass/Fail Criteria

### Hallucination Prevention
✅ **PASS** if:
- Every retrieval result includes at least one citation with `file://` URI
- Every citation includes `doc_id`, `doc_name`, `source_path`, `version`
- Image notes reference specific images in specific documents (no generic "see image" text)
- Low-confidence results (<0.5) trigger escalation with suggested SME

❌ **FAIL** if:
- Any retrieval result lacks citations
- Any citation missing required fields
- Generic or vague image notes ("see related screenshot")
- High-confidence result for clearly unknown query

### Confidence Thresholding
✅ **PASS** if:
- Retrieval results with similarity <0.5 include escalation report
- Classification with confidence <0.5 sets `needs_review=True`
- Unknown entities in impact/training return escalation with suggestions

❌ **FAIL** if:
- Low-confidence results returned without escalation
- No-match searches return fabricated results

### Idempotency
✅ **PASS** if:
- Re-running `crawl` on unchanged directory reports all files as `unchanged`
- Re-running `ingest` on already-ingested files skips them (unless `--force`)
- Document count in status remains stable after re-crawl
- Graph node/edge counts remain stable after re-ingest

❌ **FAIL** if:
- Duplicate doc_ids created
- Graph nodes duplicated
- Vector store accumulates duplicate embeddings

### Citation Quality
✅ **PASS** if:
- URIs are valid `file://` format with correct paths
- Version numbers match ingested document versions
- Section/page numbers (if present) are accurate
- Freshness badges (🟢🟡🔴⚪) reflect actual age calculations

❌ **FAIL** if:
- URIs point to non-existent files
- Version numbers are wrong or missing
- Page numbers are off by >1 page
- Freshness badges incorrect

### Multi-Modal Validation
✅ **PASS** if:
- `describe pending` returns images from ingested docs with embedded/linked images
- Completed descriptions are indexed and retrievable via vector search
- Image notes in retrieval results reference specific image IDs and locations
- Standalone image files (PNG/JPG) next to markdown are discovered

❌ **FAIL** if:
- Images not extracted from DOCX/PDF/PPTX
- Markdown `![](image.png)` references not parsed
- Standalone images ignored
- Described images not searchable

---

## 4. Exit Criteria

### Mandatory Exit Gates
1. ✅ All 46 existing backend tests pass
2. ✅ All 10 existing extension tests pass
3. ✅ Full corpus smoke test passes (crawl → ingest → 5 sample queries)
4. ✅ Top 50 user queries achieve >80% correct retrieval (citations match expected docs)
5. ✅ Zero hallucinations across all test scenarios
6. ✅ Idempotency verified (3 consecutive runs produce identical results)
7. ✅ Multi-modal pipeline functional (vision workflow end-to-end)
8. ✅ All CLI commands return valid JSON schemas
9. ✅ Extension commands execute without errors
10. ✅ Chat participant returns structured markdown with citations

### Optional Enhancement Gates (Phase 3+)
- Performance: <2s retrieval latency for 90th percentile queries
- Scale: Successfully ingest 1000+ document corpus
- Advanced NER: >90% accuracy on entity extraction for impact/training
- Semantic embedding: Migration from keyword to semantic vector search

---

## 5. Test Data Strategy

### Test Corpus Composition
- **14 files** across 5 doc types (SOP, RELEASE_NOTE, TRAINING, TROUBLESHOOT, USER_GUIDE, REFERENCE)
- **3 tools** mentioned (ToolX, ToolY, ToolZ)
- **4 error codes** (AUTH401, HTTP504, ERR-UPL-013, ERR-PWD-007)
- **4 images** (PNG screenshots in Reference/images/)
- **Multi-format coverage**: Markdown (8), DOCX (1), PDF (1), PPTX (1), JSON (1), PNG (4)

### Corpus Coverage Matrix
| Doc Type | Count | Extensions | Purpose |
|----------|-------|------------|---------|
| SOP | 1 | DOCX | Validate DOCX converter, taxonomy classification |
| RELEASE_NOTE | 1 | MD | Validate version parsing, freshness tracking |
| TRAINING | 2 | PDF, PPTX | Validate complex format converters, training path agent |
| TROUBLESHOOT | 4 | MD | Validate retrieval for error-code queries, taxonomy |
| USER_GUIDE | 1 | MD | Validate training path prerequisites |
| REFERENCE | 5 | JSON, PNG | Validate JSON parsing, image extraction, vision workflow |

### Edge Cases Required
1. **Empty directory**: Test crawler behavior on empty path
2. **Unsupported extension**: Test ingestion rejection (.xlsx, .zip)
3. **Corrupt file**: Test error handling (truncated DOCX)
4. **Missing images**: Test vision workflow when referenced image missing
5. **No-match query**: Test escalation when no relevant results
6. **Circular prerequisites**: Test training path handling of loops
7. **Unknown entity**: Test impact/training with non-existent tool
8. **Stale content**: Test freshness agent on old documents
9. **Duplicate ingestion**: Test idempotency
10. **Short/invalid descriptions**: Test vision agent description validation

---

## 6. Automation Strategy

### Harness Components
1. **scripts/run_kts_test_suite.ps1**: Master test runner
   - Runs full pipeline smoke test
   - Executes Top 50 queries
   - Validates outputs against expected baselines
   - Generates timestamped logs

2. **tests/test_phase3_comprehensive.py**: Parameterized pytest suite
   - Runs all 50+ query scenarios
   - Validates citation presence/quality
   - Checks confidence thresholds
   - Verifies idempotency

3. **scripts/logs/**: Timestamped execution logs
   - `crawl_YYYYMMDD_HHMMSS.json`
   - `ingest_YYYYMMDD_HHMMSS.json`
   - `queries_YYYYMMDD_HHMMSS.json`
   - `status_YYYYMMDD_HHMMSS.json`

4. **docs/TEST_REPORT_TEMPLATE.md**: Manual completion after runs
   - Pass/fail summary tables
   - Defect tracking
   - Citation quality scorecard

### CI/CD Integration (Future)
- GitHub Actions: Run test suite on every push to `main`
- Pre-commit hooks: Run unit tests before commit
- Scheduled freshness runs: Weekly audit of all content

---

## 7. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Image extraction not implemented | **HIGH** | HIGH | Implement markdown parsing, embedded extraction, standalone discovery (see diagnostics doc) |
| Insufficient test corpus diversity | MEDIUM | MEDIUM | Supplement with synthetic edge cases |
| Copilot answer quality varies | MEDIUM | HIGH | Document that backend only provides context; Copilot quality is external |
| Vector search accuracy (keyword-only) | MEDIUM | MEDIUM | Document limitation; plan semantic upgrade |
| Known entity list incomplete | MEDIUM | LOW | Provide admin tooling to update known_tools.json |
| Circular prerequisites in graph | LOW | MEDIUM | Implement cycle detection in training path agent |
| Extension packaging/distribution | LOW | HIGH | Create detailed VSIX build/deploy guide |

---

## 8. Test Execution Schedule

### Phase 1: Foundation (Current)
- ✅ All existing unit tests passing (46)
- ✅ All existing extension tests passing (10)
- ✅ Smoke script passing

### Phase 2: Corpus Validation (This Plan)
- **Week 1**: Execute automated test suite, validate Top 50 queries
- **Week 2**: Fix image extraction gap, re-run multi-modal tests
- **Week 3**: Complete test report, document defects
- **Week 4**: Regression run, exit criteria validation

### Phase 3: Production Hardening (Future)
- Scale testing (1000+ docs)
- Performance profiling
- Security review
- Backup/restore validation

---

## 9. Roles & Responsibilities

| Role | Responsibilities |
|------|------------------|
| **Test Author** | Create test plan, scripts, query packs, templates |
| **Execution Engineer** | Run test harness, collect logs, fill out report template |
| **Backend Developer** | Fix defects in agents/CLI, implement missing features (image extraction) |
| **Extension Developer** | Fix defects in VS Code extension, improve UX |
| **Maintenance Engineer** | Review freshness reports, complete image descriptions, update corpus |
| **Business Stakeholder** | Review test report, approve/reject go-live |

---

## 10. References

- [Agent Catalog](Agent_Catalog.md) - Complete agent specifications
- [Data Model](Data_Model.md) - All dataclasses and contracts
- [Test Strategy (Phase 2)](phase2/03_TEST_STRATEGY.md) - Original testing approach
- [Maintenance Engineer Guide](MAINTENANCE_ENGINEER_GUIDE.md) - Operational playbook
- [Launch Checklist](LAUNCH_CHECKLIST.md) - Go-live approval document
- [Traceability Matrix](TEST_TRACEABILITY_MATRIX.md) - Feature-to-test mapping
- [Top 50 Queries](TEST_QUERIES_TOP_50.md) - User query pack
- [Test Report Template](TEST_REPORT_TEMPLATE.md) - Results documentation

---

**Document Approval:**
- **Test Lead**: ________________ Date: ________
- **Engineering Lead**: ________________ Date: ________
- **Business Owner**: ________________ Date: ________
