# Evaluation Report: Mixed (Realism)

**Date**: Sat 02/14/2026
**Corpora**: kts_test_corpus, kts_synthetic_corpus_v2
**Knowledge Base**: knowledge_base_mixed
**Query Pack**: tests/golden_queries_v2.json

## Raw Scoring Output

```text

================================================================================
QUERY ACCURACY SCORING REPORT
================================================================================

--- TUNE SET (40 queries) ---
  Top-1 Accuracy: 0.0% (0/40) [TARGET: >=99%]
  Top-3 Accuracy: 0.0% (0/40)
  Evidence Found: 0.0%
  Status: FAIL

--- HOLDOUT SET (10 queries) ---
  Top-1 Accuracy: 0.0% (0/10) [TARGET: >=90%]
  Top-3 Accuracy: 0.0% (0/10)
  Evidence Found: 0.0%
  Status: FAIL

--- OVERALL (50 queries) ---
  Top-1 Accuracy: 0.0% (0/50)
  Top-3 Accuracy: 0.0% (0/50) [TARGET: >=98%]
  Evidence Found: 0.0%
  Status: FAIL

--- SAFE TARGETS STATUS ---
  Tune Top-1 >= 99%:     FAIL (0.0%)
  Holdout Top-1 >= 90%:  FAIL (0.0%)
  Overall Top-3 >= 98%:  FAIL (0.0%)

  ALL TARGETS MET: NO

================================================================================

Detailed scores saved to: tests\accuracy_tuning_output_v2\accuracy_scores.json


```
