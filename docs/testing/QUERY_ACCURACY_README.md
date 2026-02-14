# Query Accuracy Tuning System

## Overview
Comprehensive accuracy optimization framework for the GSF IR KTS agentic retrieval system. Measures and improves query accuracy using a **golden query pack** with Tune/Holdout split.

## SAFE TARGETS
- **Tune Set Top-1 Accuracy**: ≥ 99% (40 queries)
- **Holdout Set Top-1 Accuracy**: ≥ 90% (10 queries)  
- **Overall Top-3 Accuracy**: ≥ 98% (50 queries)

## Anti-Overfitting Constraints
❌ **PROHIBITED**: Hardcoding corpus-specific identifiers (filenames, doc_ids, absolute paths, tool names)  
✅ **ALLOWED**: Feature-based ranking (doc_type boosting, intent matching, term presence, error code patterns)

## Files

### 1. `tests/golden_queries.json` (50 queries)
Golden query pack with evidence-based validation:
```json
{
  "query_id": "Q1",
  "query_text": "What does error AUTH401 mean for ToolX?",
  "split": "tune",
  "expected_doc_types_priority": ["TROUBLESHOOT", "REFERENCE"],
  "must_include_terms": ["AUTH401", "ERR-AUTH-401"],
  "expected_evidence_rules": {
    "at_least_one_chunk_has_terms": true,
    "at_least_one_chunk_from_top_doc_type": true
  }
}
```

**Split Distribution**:
- Tune: 40 queries (training set for parameter optimization)
- Holdout: 10 queries (validation set to detect overfitting)

**Evidence Rules**:
- `must_include_terms`: Required terms in top-3 chunks (e.g., error codes, key phrases)
- `must_not_include_terms`: Prohibited terms (for negative test cases)
- `expected_doc_types_priority`: Ranked list of acceptable doc_types
- `allow_any_result`: True for escalation/missing info cases

### 2. `tests/score_queries.py`
Python scorer computing Top-1, Top-3 accuracy with evidence validation:

**Usage**:
```bash
python tests/score_queries.py tests/golden_queries.json tests/accuracy_tuning_output/search_results.json --verbose
```

**Output**:
```
--- TUNE SET (40 queries) ---
  Top-1 Accuracy: 85.0% (34/40) [TARGET: ≥99%]  ❌ FAIL
  Top-3 Accuracy: 92.5% (37/40)
  Evidence Found: 87.5%

--- HOLDOUT SET (10 queries) ---
  Top-1 Accuracy: 80.0% (8/10) [TARGET: ≥90%]  ❌ FAIL
  Top-3 Accuracy: 90.0% (9/10)
  Evidence Found: 85.0%

--- OVERALL (50 queries) ---
  Top-1 Accuracy: 84.0% (42/50)
  Top-3 Accuracy: 92.0% (46/50) [TARGET: ≥98%]  ❌ FAIL

  ALL TARGETS MET: ❌ NO
```

**Scoring Logic**:
1. **Top-1 Match**: Rank 1 doc_type ∈ expected_doc_types_priority
2. **Top-3 Match**: Any of ranks 1-3 doc_type ∈ expected_doc_types_priority
3. **Evidence Found**: At least one must_include_term present in top-3 chunks

### 3. `scripts/run_accuracy_tuning.ps1`
One-command orchestrator for end-to-end accuracy evaluation:

**Usage**:
```powershell
# Baseline run (current configuration)
.\scripts\run_accuracy_tuning.ps1 -Mode baseline

# Skip ingestion (use existing KB)
.\scripts\run_accuracy_tuning.ps1 -Mode baseline -SkipIngest

# Verbose output (show all failures)
.\scripts\run_accuracy_tuning.ps1 -Mode baseline -Verbose

# Full sweep (future: automated parameter optimization)
.\scripts\run_accuracy_tuning.ps1 -Mode full
```

**What it does**:
1. Cleans knowledge base (unless `-SkipIngest`)
2. Ingests all documents from `kts_test_corpus/`
3. Executes all 50 golden queries via `cli/main.py search`
4. Scores results against golden standards
5. Reports Tune vs Holdout accuracy
6. Saves detailed failure analysis to `tests/accuracy_tuning_output/`

**Output Files**:
- `search_results.json`: Raw retrieval results for all 50 queries
- `accuracy_scores.json`: Detailed scoring with per-query breakdown

### 4. `backend/agents/retrieval_service.py`
The **tuning target** - contains `rerank()` function controlling ranking logic.

**Current Implementation** (BASELINE):
```python
def rerank(row: dict) -> float:
    score = float(row.get("similarity", 0.0))
    query_lower = query.lower()
    row_type = str(row.get("doc_type", "UNKNOWN"))
    
    # Rule 1: "how" queries prefer SOP/USER_GUIDE
    if "how" in query_lower and row_type in {"SOP", "USER_GUIDE"}:
        score *= 1.2
    
    # Rule 2: Error queries prefer TROUBLESHOOT
    if any(word in query_lower for word in ("error", "fail", "broken", "fix")) and row_type == "TROUBLESHOOT":
        score *= 1.3
    
    # Rule 3: De-boost image descriptions
    if row.get("is_image_desc"):
        score *= 0.95
    
    return score
```

**Tuning Strategy**:
1. Add **exact match boosting**: If query term in doc_name → score *= 1.5
2. Add **error code detection**: Regex for ERR-XXX-000 → score *= 2.0
3. Expand **intent boosting**: "what" → REFERENCE, "why" → TRAINING
4. Add **doc_type priority alignment**: Match against expected_doc_types
5. Add **title/heading boosting**: First chunk from doc → score *= 1.1

## Workflow

### Phase 1: Baseline Evaluation
```powershell
# Run baseline to establish current accuracy
.\scripts\run_accuracy_tuning.ps1 -Mode baseline

# Expected first run: ~62% Top-1 accuracy (from autopilot legacy scoring)
# Goal: Identify which query types are failing
```

### Phase 2: Iterative Tuning
```powershell
# 1. Review failures
cat tests\accuracy_tuning_output\accuracy_scores.json

# 2. Identify patterns (e.g., "All error code queries failing")

# 3. Edit backend\agents\retrieval_service.py rerank() function
# Example: Add error code boosting
#   if re.search(r'ERR-[A-Z]+-\d+', query):
#       if 'ERR' in row.get('doc_name', ''):
#           score *= 2.0

# 4. Rerun (skip ingestion for speed)
.\scripts\run_accuracy_tuning.ps1 -Mode baseline -SkipIngest -Verbose

# 5. Check if accuracy improved for target query type
# 6. Repeat until SAFE TARGETS met
```

### Phase 3: Validation
```powershell
# Final validation with fresh KB
.\scripts\run_accuracy_tuning.ps1 -Mode baseline -Verbose

# Verify:
# - Tune Top-1 ≥ 99%
# - Holdout Top-1 ≥ 90%
# - Overall Top-3 ≥ 98%
# - No overfitting (Holdout not significantly worse than Tune)
```

## Debugging Failed Queries

### Step 1: Run with verbose
```powershell
.\scripts\run_accuracy_tuning.ps1 -Mode baseline -Verbose
```

### Step 2: Review detailed failures
```json
// accuracy_scores.json excerpt
{
  "query_id": "Q1",
  "top1_match": false,
  "top3_match": true,
  "evidence_found": true,
  "top1_doc_type": "TRAINING",      // ❌ Should be TROUBLESHOOT
  "top3_doc_types": ["TRAINING", "TROUBLESHOOT", "SOP"],
  "matched_terms": ["AUTH401"],
  "errors": []
}
```

**Diagnosis**: Q1 returned TRAINING as rank 1, but expected TROUBLESHOOT. Need to boost TROUBLESHOOT for error queries.

### Step 3: Check raw search output
```powershell
python cli\main.py search --query "What does error AUTH401 mean for ToolX?"
```

### Step 4: Tune rerank() function
```python
# Add to retrieval_service.py rerank()
if re.search(r'ERR-[A-Z]+-\d+|error \w+\d+', query_lower):
    if row_type == "TROUBLESHOOT":
        score *= 1.8  # Strong boost for TROUBLESHOOT on error queries
```

### Step 5: Retest specific query
```powershell
python cli\main.py search --query "What does error AUTH401 mean for ToolX?"
# Verify TROUBLESHOOT now rank 1
```

## Anti-Overfitting Checklist

Before declaring tuning complete, verify:

✅ **No hardcoded filenames**: Search `retrieval_service.py` for corpus-specific strings  
✅ **No doc_id matching**: Don't boost based on specific document IDs  
✅ **No path-based logic**: Don't check absolute file paths  
✅ **Holdout accuracy reasonable**: Holdout Top-1 within 10% of Tune Top-1  
✅ **Feature-based only**: All ranking logic uses doc_type, content, metadata, patterns  

## Expected Accuracy Progression

| Iteration | Change | Tune Top-1 | Holdout Top-1 | Overall Top-3 |
|-----------|--------|------------|---------------|---------------|
| Baseline | None | 62% | 50% | 78% |
| +1 | Error code boosting | 75% | 70% | 86% |
| +2 | Exact match boosting | 85% | 80% | 92% |
| +3 | Intent-based doc_type alignment | 95% | 88% | 96% |
| +4 | Title boosting + term matching | **99%** ✅ | **92%** ✅ | **98%** ✅ |

## Troubleshooting

### Scorer fails to parse search output
**Symptom**: All queries scored as "No chunks retrieved"  
**Cause**: CLI output format changed or JSON parsing failed  
**Fix**: Check `search_results.json` format, update scorer's chunk extraction logic

### Accuracy drops on holdout after tuning
**Symptom**: Tune Top-1 = 99%, Holdout Top-1 = 60%  
**Cause**: Overfitting - tuned too specifically to tune set queries  
**Fix**: Remove corpus-specific hardcoding, use more general feature-based boosting

### All queries fail with error
**Symptom**: 0/50 queries executed successfully  
**Cause**: CLI command syntax error or KB not ingested  
**Fix**: Manually run `python cli\main.py search --query "test"` to debug

### Targets met but results don't make sense
**Symptom**: 100% Top-1 accuracy but reviewing results shows wrong docs  
**Cause**: Scorer logic mismatch with expected_doc_types definition  
**Fix**: Manually review `accuracy_scores.json` detailed_scores, verify doc_type extraction

## Contact
For issues with tuning system: Review `tests/score_queries.py` scorer logic and `scripts/run_accuracy_tuning.ps1` orchestration.

---
**Last Updated**: 2026-02-14  
**Version**: 1.0 (Baseline implementation)
