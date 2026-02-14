"""
Golden Query Accuracy Scorer
Computes Top-1, Top-3 accuracy with evidence-based validation.
NO corpus-specific hardcoding - all scoring is feature-based.
"""
import json
import sys
import re
from pathlib import Path
from typing import Dict, List, Any

# Import canonical doc_type normalization
sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.common.doc_types import normalize_doc_type

def load_golden_queries(golden_path: Path) -> List[Dict[str, Any]]:
    """Load golden query pack"""
    with open(golden_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data['queries']

def load_search_results(results_path: Path) -> Dict[str, Any]:
    """Load search results JSON (supports v1 and v2 formats)"""
    with open(results_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # V2 format: {"queries": [{query_id, retrieved_chunks}, ...]}
    # V1 format: {"Q1": {retrieved_chunks}, "Q2": {...}, ...}
    if "queries" in data and isinstance(data["queries"], list):
        # Convert v2 to v1 format
        return {q["query_id"]: q for q in data["queries"]}
    else:
        # Already v1 format
        return data

def extract_doc_type(chunk_meta: Dict[str, Any]) -> str:
    """Extract and normalize document type from chunk metadata"""
    raw_type = chunk_meta.get("doc_type", "UNKNOWN")
    return normalize_doc_type(raw_type)

def check_term_presence(text: str, terms: List[str]) -> bool:
    """Check if at least one term appears in text (case-insensitive, partial match)"""
    if not terms:
        return True  # No terms required = pass
    text_lower = text.lower()
    for term in terms:
        # Allow partial match with stem (e.g., "auth" matches "authentication")
        if term.lower() in text_lower:
            return True
    return False

def score_single_query(
    golden_query: Dict[str, Any],
    search_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Score a single query's search result against golden standard.
    Returns:
        {
            "query_id": str,
            "top1_match": bool,  # Expected doc_type in rank 1
            "top3_match": bool,  # Expected doc_type in ranks 1-3
            "evidence_found": bool,  # must_include_terms present
            "top1_doc_type": str,
            "top3_doc_types": List[str],
            "matched_terms": List[str],
            "errors": List[str]
        }
    """
    query_id = golden_query["query_id"]
    
    # Schema-tolerant loading (v1 vs v2 format)
    # V1: expected_doc_types_priority, allow_any_result
    # V2: expected_doc_types, expected_evidence_rules
    expected_doc_types_raw = (
        golden_query.get("expected_doc_types_priority") or 
        golden_query.get("expected_doc_types") or 
        []
    )
    # Normalize all expected doc_types to canonical form
    expected_doc_types = [normalize_doc_type(dt) for dt in expected_doc_types_raw]
    
    must_include_terms = golden_query.get("must_include_terms", [])
    must_not_include_terms = golden_query.get("must_not_include_terms", [])
    
    # Allow_any: v1 explicit boolean or infer from v2 evidence rules
    allow_any = golden_query.get("allow_any_result", False)
    evidence_rules = golden_query.get("expected_evidence_rules", {})
    if not allow_any and evidence_rules:
        # V2 format: requires_citation=false means allow_any=true
        allow_any = not evidence_rules.get("requires_citation", True)
    
    errors = []
    
    # Schema validation warning
    if not expected_doc_types and not allow_any:
        errors.append("WARN: No expected_doc_types found (check query schema)")
    
    # Extract retrieved chunks
    if "error" in search_result:
        return {
            "query_id": query_id,
            "top1_match": False,
            "top3_match": False,
            "evidence_found": False,
            "top1_doc_type": "ERROR",
            "top3_doc_types": [],
            "matched_terms": [],
            "errors": [f"Search failed: {search_result['error']}"]
        }
    
    chunks = search_result.get("retrieved_chunks", [])
    if not chunks:
        return {
            "query_id": query_id,
            "top1_match": False if not allow_any else True,
            "top3_match": False if not allow_any else True,
            "evidence_found": allow_any,
            "top1_doc_type": "NONE",
            "top3_doc_types": [],
            "matched_terms": [],
            "errors": ["No chunks retrieved"] if not allow_any else []
        }
    
    # Extract doc types from top 3 chunks
    top_doc_types = []
    for i, chunk in enumerate(chunks[:3]):
        doc_type = extract_doc_type(chunk)
        top_doc_types.append(doc_type)
    
    top1_doc_type = top_doc_types[0] if top_doc_types else "NONE"
    
    # Check Top-1 match (is rank 1 doc_type in expected priority list?)
    top1_match = False
    if allow_any:
        top1_match = True
    elif expected_doc_types and top1_doc_type in expected_doc_types:
        top1_match = True
    
    # Check Top-3 match (is ANY of ranks 1-3 in expected priority list?)
    top3_match = False
    if allow_any:
        top3_match = True
    elif expected_doc_types:
        for doc_type in top_doc_types:
            if doc_type in expected_doc_types:
                top3_match = True
                break
    
    # Check evidence terms in top 3 chunks
    evidence_found = False
    matched_terms = []
    all_text = ""
    for chunk in chunks[:3]:
        all_text += " " + chunk.get("content", "") + " " + chunk.get("doc_name", "")
    
    if not must_include_terms or allow_any:
        evidence_found = True
    else:
        for term in must_include_terms:
            if term.lower() in all_text.lower():
                matched_terms.append(term)
        if matched_terms:
            evidence_found = True
    
    # Check prohibited terms
    if must_not_include_terms:
        for term in must_not_include_terms:
            if term.lower() in all_text.lower():
                errors.append(f"Prohibited term '{term}' found in results")
    
    return {
        "query_id": query_id,
        "top1_match": top1_match,
        "top3_match": top3_match,
        "evidence_found": evidence_found,
        "top1_doc_type": top1_doc_type,
        "top3_doc_types": top_doc_types,
        "matched_terms": matched_terms,
        "errors": errors
    }

def compute_aggregate_metrics(
    all_scores: List[Dict[str, Any]],
    golden_queries: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Compute aggregate metrics for Tune, Holdout, and Overall"""
    tune_scores = [s for s in all_scores if get_split(s["query_id"], golden_queries) == "tune"]
    holdout_scores = [s for s in all_scores if get_split(s["query_id"], golden_queries) == "holdout"]
    
    def compute_for_split(scores: List[Dict[str, Any]]) -> Dict[str, float]:
        if not scores:
            return {"top1_accuracy": 0.0, "top3_accuracy": 0.0, "evidence_accuracy": 0.0}
        top1_correct = sum(1 for s in scores if s["top1_match"])
        top3_correct = sum(1 for s in scores if s["top3_match"])
        evidence_correct = sum(1 for s in scores if s["evidence_found"])
        total = len(scores)
        return {
            "top1_accuracy": round(100.0 * top1_correct / total, 2),
            "top3_accuracy": round(100.0 * top3_correct / total, 2),
            "evidence_accuracy": round(100.0 * evidence_correct / total, 2),
            "total_queries": total,
            "top1_correct": top1_correct,
            "top3_correct": top3_correct,
            "evidence_correct": evidence_correct
        }
    
    tune_metrics = compute_for_split(tune_scores)
    holdout_metrics = compute_for_split(holdout_scores)
    overall_metrics = compute_for_split(all_scores)
    
    return {
        "tune": tune_metrics,
        "holdout": holdout_metrics,
        "overall": overall_metrics
    }

def get_split(query_id: str, golden_queries: List[Dict[str, Any]]) -> str:
    """Get split (tune/holdout) for a query"""
    for q in golden_queries:
        if q["query_id"] == query_id:
            return q.get("split", "tune")
    return "tune"

def check_safe_targets(metrics: Dict[str, Any]) -> Dict[str, bool]:
    """
    Check if SAFE TARGETS are met:
    - Tune Top-1 >= 99%
    - Holdout Top-1 >= 90%
    - Overall Top-3 >= 98%
    """
    tune_top1 = metrics["tune"]["top1_accuracy"]
    holdout_top1 = metrics["holdout"]["top1_accuracy"]
    overall_top3 = metrics["overall"]["top3_accuracy"]
    
    return {
        "tune_top1_pass": tune_top1 >= 99.0,
        "tune_top1_value": tune_top1,
        "holdout_top1_pass": holdout_top1 >= 90.0,
        "holdout_top1_value": holdout_top1,
        "overall_top3_pass": overall_top3 >= 98.0,
        "overall_top3_value": overall_top3,
        "all_targets_met": (tune_top1 >= 99.0) and (holdout_top1 >= 90.0) and (overall_top3 >= 98.0)
    }

def main():
    if len(sys.argv) < 3:
        print("Usage: python score_queries.py <golden_queries.json> <search_results.json> [--verbose]")
        sys.exit(1)
    
    golden_path = Path(sys.argv[1])
    results_path = Path(sys.argv[2])
    verbose = "--verbose" in sys.argv
    
    if not golden_path.exists():
        print(f"ERROR: Golden queries file not found: {golden_path}")
        sys.exit(1)
    
    if not results_path.exists():
        print(f"ERROR: Search results file not found: {results_path}")
        sys.exit(1)
    
    # Load data
    golden_queries = load_golden_queries(golden_path)
    search_results = load_search_results(results_path)
    
    # Score each query
    all_scores = []
    for golden_query in golden_queries:
        query_id = golden_query["query_id"]
        if query_id in search_results:
            score = score_single_query(golden_query, search_results[query_id])
            all_scores.append(score)
        else:
            all_scores.append({
                "query_id": query_id,
                "top1_match": False,
                "top3_match": False,
                "evidence_found": False,
                "top1_doc_type": "MISSING",
                "top3_doc_types": [],
                "matched_terms": [],
                "errors": ["Query not executed"]
            })
    
    # Compute aggregate metrics
    metrics = compute_aggregate_metrics(all_scores, golden_queries)
    safe_targets = check_safe_targets(metrics)
    
    # Output report
    print("\n" + "=" * 80)
    print("QUERY ACCURACY SCORING REPORT")
    print("=" * 80)
    
    print("\n--- TUNE SET (40 queries) ---")
    print(f"  Top-1 Accuracy: {metrics['tune']['top1_accuracy']}% ({metrics['tune']['top1_correct']}/{metrics['tune']['total_queries']}) [TARGET: >=99%]")
    print(f"  Top-3 Accuracy: {metrics['tune']['top3_accuracy']}% ({metrics['tune']['top3_correct']}/{metrics['tune']['total_queries']})")
    print(f"  Evidence Found: {metrics['tune']['evidence_accuracy']}%")
    print(f"  Status: {'PASS' if safe_targets['tune_top1_pass'] else 'FAIL'}")
    
    print("\n--- HOLDOUT SET (10 queries) ---")
    print(f"  Top-1 Accuracy: {metrics['holdout']['top1_accuracy']}% ({metrics['holdout']['top1_correct']}/{metrics['holdout']['total_queries']}) [TARGET: >=90%]")
    print(f"  Top-3 Accuracy: {metrics['holdout']['top3_accuracy']}% ({metrics['holdout']['top3_correct']}/{metrics['holdout']['total_queries']})")
    print(f"  Evidence Found: {metrics['holdout']['evidence_accuracy']}%")
    print(f"  Status: {'PASS' if safe_targets['holdout_top1_pass'] else 'FAIL'}")
    
    print("\n--- OVERALL (50 queries) ---")
    print(f"  Top-1 Accuracy: {metrics['overall']['top1_accuracy']}% ({metrics['overall']['top1_correct']}/{metrics['overall']['total_queries']})")
    print(f"  Top-3 Accuracy: {metrics['overall']['top3_accuracy']}% ({metrics['overall']['top3_correct']}/{metrics['overall']['total_queries']}) [TARGET: >=98%]")
    print(f"  Evidence Found: {metrics['overall']['evidence_accuracy']}%")
    print(f"  Status: {'PASS' if safe_targets['overall_top3_pass'] else 'FAIL'}")
    
    print("\n--- SAFE TARGETS STATUS ---")
    tune_status = 'PASS' if safe_targets['tune_top1_pass'] else f"FAIL ({safe_targets['tune_top1_value']}%)"
    holdout_status = 'PASS' if safe_targets['holdout_top1_pass'] else f"FAIL ({safe_targets['holdout_top1_value']}%)"
    overall_status = 'PASS' if safe_targets['overall_top3_pass'] else f"FAIL ({safe_targets['overall_top3_value']}%)"
    print(f"  Tune Top-1 >= 99%:     {tune_status}")
    print(f"  Holdout Top-1 >= 90%:  {holdout_status}")
    print(f"  Overall Top-3 >= 98%:  {overall_status}")
    print(f"\n  ALL TARGETS MET: {'YES' if safe_targets['all_targets_met'] else 'NO'}")
    
    if verbose:
        print("\n--- DETAILED FAILURES ---")
        for score in all_scores:
            if not score["top1_match"]:
                query = next(q for q in golden_queries if q["query_id"] == score["query_id"])
                split = query.get("split", "tune").upper()
                print(f"\n  [{split}] {score['query_id']}: {query['query_text']}")
                print(f"    Expected doc_types: {query.get('expected_doc_types_priority', [])}")
                print(f"    Actual Top-1: {score['top1_doc_type']}")
                print(f"    Actual Top-3: {score['top3_doc_types']}")
                print(f"    Evidence found: {score['evidence_found']} (terms: {score['matched_terms']})")
                if score['errors']:
                    print(f"    Errors: {', '.join(score['errors'])}")
    
    print("\n" + "=" * 80)
    
    # Save detailed scores
    output_path = results_path.parent / "accuracy_scores.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            "metrics": metrics,
            "safe_targets": safe_targets,
            "detailed_scores": all_scores
        }, f, indent=2)
    
    print(f"\nDetailed scores saved to: {output_path}")
    
    # Exit code: 0 if all targets met, 1 otherwise
    sys.exit(0 if safe_targets['all_targets_met'] else 1)

if __name__ == "__main__":
    main()
