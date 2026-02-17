# Phase 2 Test Results - PSA 2006-HE1

## Document Details
- **File**: Pooling and Servicing Agreement Series 2006-HE1 (final pdf).pdf
- **Document ID**: doc_0218203
- **Chunks**: 1394

## Test Metrics by Tier

### S1 - Core Only
- Average Latency: 2116.5ms
- Top-1 Entity Match: **30.0%** (6/20)
- Top-1 Keyphrase Match: **90.0%** (18/20)
- Top-5 Entity Match: 30.0%
- Top-5 Keyphrase Match: 90.0%

### S2 - Core + spaCy NER
- Average Latency: 2236.6ms (+120ms, +6%)
- Top-1 Entity Match: **30.0%** (6/20) [same as S1]
- Top-1 Keyphrase Match: **80.0%** (16/20) [-10% vs S1] ⚠️
- Top-5 Entity Match: 30.0%
- Top-5 Keyphrase Match: 80.0%

### S3 - Full Stack (Core + spaCy + Cross-Encoder)
- Average Latency: ~2200-3200ms (variable, cross-encoder confirmed working)
- Top-1 Entity Match: **30.0%** (6/20) [same as S1/S2]
- Top-1 Keyphrase Match: **80.0%** (16/20) [same as S2]
- Top-5 Entity Match: 30.0%
- Top-5 Keyphrase Match: 80.0%

## Key Findings

###  Positive
1. **Entity extraction WORKING**: Verified in ChromaDB metadata
   - Example entities: "Master Servicer" (ORG), "Trustee" (ORG), "Pooling and Servicing Agreement Series 2006-HE1" (WORK_OF_ART)
   - Keyphrases: "master servicer" (score 1.0), "legal action", etc.

2. **Cross-encoder WORKING**: Confirmed via logging
   - Reranks 20 candidates per query
   - Scores range: 1.102 to 6.733
   - Adds ~1-2s latency as expected

3. **Complete pipeline functional**: All components loading and executing

### ⚠️ Unexpected
1. **S2 keyphrase match DECREASED**:  90% → 80% (-10%)
   - S1 had better keyphrase matching than S2/S3
   - Possible cause: Query expansion or entity overlap scoring changing retrieval ranking
   - Needs investigation

2. **Entity match UNCHANGED across tiers**: 30% for all
   - Expected S2/S3 to improve entity matching
   - Suggests entity overlap boost (1.5x) may be insufficient
   - Or entity extraction not finding expected entities in these queries

3. **Latency variance**:
   - Some runs: 1.5s average (fast)
   - Other runs: 2.2s average (baseline)
   - Single query test: 3.3s (cross-encoder confirmed)
   - Likely caching/warmup effects

## Configuration Issues Identified

1. **Environment variable naming inconsistency**:
   - Code expects: `KTS_CROSS_ENCODER_ENABLED` (with underscore)
   - Initially used: `KTS_CROSSENCODER_ENABLED` (without underscore)
   - **FIXED**: Now using correct variable name

2. **spaCy model location**:
   - Model was in `.venv/` but not in `extension-models-spacy/models/`
   - **FIXED**: Copied model to extension folder (14.54 MB)

## Test Queries
- Created 20 PSA-specific test queries covering:
  - Entity-rich queries: Master Servicer, Trustee, Depositor, etc.
  - Procedural queries: distributions, defaults, foreclosures
  - Definitional queries: representations, warranties, fees
  - Reference queries: governing law, amendments

## Next Steps for Phase 2b
1. ~~Test with second PSA document (2006-HE2)~~ **BLOCKED**: .doc format not supported
   - File is legacy binary .doc format (not ZIP-based .docx)
   - python-docx library cannot parse it
   - **Recommendation**: Add .doc support using `pywin32` (Windows COM) or `antiword` converter
   - **Workaround for now**: Convert .doc to .docx/PDF manually or skip this test
2. Compare results across both documents
3. Investigate why S2 keyphrase match decreased
4. Consider tuning entity overlap boost (currently 1.5x)
5. Consider tuning keyphrase overlap boost (currently 1.3x)

## Phase 2b Status
- **SKIPPED** due to .doc format limitation
- Continuing with Phase 3-8 using PSA 2006-HE1 as test corpus
- .doc support can be added post-deployment as enhancement
