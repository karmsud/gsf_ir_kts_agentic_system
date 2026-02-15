# KTS Testing & Quality Assurance

**Source of Truth**: `scripts/run_full_eval_suite.py`

## 1. Unit Tests

Core backend logic is tested using `pytest`.

```bash
# Clean previous state
python -m pytest tests/
```

- **Scope**:
  - Converter fidelity (PDF, DOCX extraction)
  - Agent orchestration
  - Graph builder logic
  - Vector store interfaces

## 2. Integration / Evaluation Suite

The `run_full_eval_suite.py` script orchestrates a comprehensive 3-stage validation against known corpora.

### Scenarios
1.  **V1 Isolated**: Tests baseline retrieval on legacy corpus (`kts_test_corpus`).
2.  **V2 Isolated**: Tests new features on synthetic corpus (`kts_synthetic_corpus_v2`).
3.  **Mixed (Realism)**: Combined corpus to simulate messy real-world data.

### Running the Suite
```bash
python scripts/run_full_eval_suite.py
```
**Artifacts**:
- Generates `docs/EVAL_REPORT_*.md` files.
- Creates temporary knowledge bases (`knowledge_base_v1`, `knowledge_base_v2`).

## 3. Image Extraction Verification

To verify image deduplication and extraction:

1.  **Setup**: Use `scripts/run_kts_test_corpus.ps1`.
2.  **Run**: `kts-backend ingest --paths <test_corpus>`.
3.  **Inspect**: Check `.kts/documents/<doc_id>/images/` for extracted files.
4.  **Validate**: Ensure `total_images_pending` match expected count (e.g., 25 unique images in standard test corpus).

## 4. Pre-Release Quality Gates

Before tagging a release:
- [ ] Unit tests pass (`pytest`).
- [ ] Evaluation suite completes without critical failures.
- [ ] Documentation updated to reflect new features (e.g., Tier A3).
- [ ] VSIX builds successfully for both tiers.
