"""
Golden Query Accuracy Scorer
Computes Top-1/Top-3 accuracy and strict evidence validation.
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.common.doc_types import normalize_doc_type


def load_golden_queries(golden_path: Path) -> List[Dict[str, Any]]:
    with open(golden_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["queries"]


def load_search_results(results_path: Path) -> Dict[str, Any]:
    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "queries" in data and isinstance(data["queries"], list):
        return {q["query_id"]: q for q in data["queries"]}
    return data


def extract_doc_type(chunk_meta: Dict[str, Any]) -> str:
    return normalize_doc_type(chunk_meta.get("doc_type", "UNKNOWN"))


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_for_tokens(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").lower()
    text = text.replace("_", "-")
    text = re.sub(r"[-\u2010-\u2015]+", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(value: str) -> List[str]:
    cleaned = normalize_for_tokens(value)
    if not cleaned:
        return []
    return cleaned.split(" ")


def token_equivalent(a: str, b: str) -> bool:
    if a == b:
        return True
    return a in {b + "s", b + "es"} or b in {a + "s", a + "es"}


def phrase_match_with_plural_tolerance(text: str, phrase: str) -> bool:
    phrase_tokens = tokenize(phrase)
    if not phrase_tokens:
        return False
    text_tokens = tokenize(text)
    if len(phrase_tokens) > len(text_tokens):
        return False
    window = len(phrase_tokens)
    for idx in range(0, len(text_tokens) - window + 1):
        if all(token_equivalent(text_tokens[idx + j], phrase_tokens[j]) for j in range(window)):
            return True
    return False


def parse_evidence_rules(golden_query: Dict[str, Any]) -> Dict[str, Any]:
    rules = golden_query.get("expected_evidence_rules", {}) or {}

    all_of_terms: List[str] = list(golden_query.get("must_include_terms", []) or [])
    any_of_terms: List[str] = []
    all_of_regex: List[str] = []
    any_of_regex: List[str] = []

    all_of_terms.extend(rules.get("all_of_terms", []) or [])
    any_of_terms.extend(rules.get("any_of_terms", []) or [])
    all_of_terms.extend(rules.get("must_include_terms_all", []) or [])
    any_of_terms.extend(rules.get("must_include_terms_any", []) or [])
    all_of_regex.extend(rules.get("all_of_regex", []) or [])
    any_of_regex.extend(rules.get("any_of_regex", []) or [])

    if isinstance(rules.get("regex"), list):
        all_of_regex.extend(rules.get("regex", []))

    for group in rules.get("all_of", []) or []:
        if isinstance(group, str):
            all_of_terms.append(group)
        elif isinstance(group, dict):
            all_of_terms.extend(group.get("terms", []) or [])
            all_of_regex.extend(group.get("regex", []) or [])

    for group in rules.get("any_of", []) or []:
        if isinstance(group, str):
            any_of_terms.append(group)
        elif isinstance(group, dict):
            any_of_terms.extend(group.get("terms", []) or [])
            any_of_regex.extend(group.get("regex", []) or [])

    return {
        "all_of_terms": [t for t in all_of_terms if isinstance(t, str) and t.strip()],
        "any_of_terms": [t for t in any_of_terms if isinstance(t, str) and t.strip()],
        "all_of_regex": [t for t in all_of_regex if isinstance(t, str) and t.strip()],
        "any_of_regex": [t for t in any_of_regex if isinstance(t, str) and t.strip()],
        "raw": rules,
    }


def read_pointer_text(pointer: str) -> str:
    if not pointer:
        return ""
    path = Path(pointer)
    if not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def get_chunk_text(chunk: Dict[str, Any]) -> Tuple[str, Dict[str, bool]]:
    content = str(chunk.get("content", "") or "")
    excerpt_head = str(chunk.get("excerpt_head", "") or "")
    excerpt_tail = str(chunk.get("excerpt_tail", "") or "")
    pointer = str(chunk.get("content_pointer", "") or "")

    flags = {
        "has_content": bool(content.strip()),
        "has_excerpt": bool(excerpt_head.strip() or excerpt_tail.strip()),
        "has_pointer": bool(pointer.strip()),
    }

    if flags["has_content"]:
        return content, flags

    excerpt_text = "\n".join([part for part in [excerpt_head, excerpt_tail] if part.strip()])
    if excerpt_text.strip():
        return excerpt_text, flags

    if flags["has_pointer"]:
        pointed = read_pointer_text(pointer)
        if pointed.strip():
            return pointed, flags

    return "", flags


def evaluate_term_rule(term: str, text: str) -> bool:
    if phrase_match_with_plural_tolerance(text, term):
        return True
    text_norm = normalize_for_tokens(text)
    term_norm = normalize_for_tokens(term)
    if not term_norm:
        return False
    return term_norm in text_norm


def evaluate_regex_rule(pattern: str, text: str) -> bool:
    try:
        return re.search(pattern, text, flags=re.IGNORECASE) is not None
    except re.error:
        return False


def evaluate_evidence_on_text(evidence_rules: Dict[str, Any], text: str) -> Dict[str, Any]:
    normalized = normalize_text(text)

    term_matches: Dict[str, bool] = {}
    regex_matches: Dict[str, bool] = {}

    for term in evidence_rules["all_of_terms"]:
        term_matches[f"term::{term}"] = evaluate_term_rule(term, normalized)
    for term in evidence_rules["any_of_terms"]:
        term_matches[f"any_term::{term}"] = evaluate_term_rule(term, normalized)

    for pattern in evidence_rules["all_of_regex"]:
        regex_matches[f"regex::{pattern}"] = evaluate_regex_rule(pattern, normalized)
    for pattern in evidence_rules["any_of_regex"]:
        regex_matches[f"any_regex::{pattern}"] = evaluate_regex_rule(pattern, normalized)

    all_of_ok = all(
        term_matches[f"term::{term}"] for term in evidence_rules["all_of_terms"]
    ) and all(
        regex_matches[f"regex::{pattern}"] for pattern in evidence_rules["all_of_regex"]
    )

    any_of_requirements_present = bool(evidence_rules["any_of_terms"] or evidence_rules["any_of_regex"])
    if any_of_requirements_present:
        any_of_ok = any(
            term_matches.get(f"any_term::{term}", False) for term in evidence_rules["any_of_terms"]
        ) or any(
            regex_matches.get(f"any_regex::{pattern}", False) for pattern in evidence_rules["any_of_regex"]
        )
    else:
        any_of_ok = True

    return {
        "all_of_ok": all_of_ok,
        "any_of_ok": any_of_ok,
        "chunk_satisfies": all_of_ok and any_of_ok,
        "term_matches": term_matches,
        "regex_matches": regex_matches,
    }


def build_chunk_evidence_map(
    chunks: List[Dict[str, Any]], evidence_rules: Dict[str, Any], top_k: int
) -> Dict[str, Any]:
    chunk_rows = []
    for idx, chunk in enumerate(chunks[:top_k], start=1):
        text, flags = get_chunk_text(chunk)
        evidence_eval = evaluate_evidence_on_text(evidence_rules, text)

        if not evidence_eval["chunk_satisfies"] and flags["has_pointer"] and not flags["has_content"]:
            pointed_text = read_pointer_text(str(chunk.get("content_pointer", "")))
            if pointed_text:
                evidence_eval = evaluate_evidence_on_text(evidence_rules, pointed_text)

        chunk_rows.append(
            {
                "rank": idx,
                "chunk_id": chunk.get("chunk_id"),
                "doc_id": chunk.get("doc_id"),
                "doc_type": chunk.get("doc_type", "UNKNOWN"),
                "similarity": chunk.get("score", chunk.get("similarity")),
                "source": chunk.get("source", chunk.get("source_path", "")),
                "flags": flags,
                "evidence_eval": evidence_eval,
            }
        )

    matched_rank = None
    for row in chunk_rows:
        if row["evidence_eval"]["chunk_satisfies"]:
            matched_rank = row["rank"]
            break

    return {
        "chunk_rows": chunk_rows,
        "evidence_found": matched_rank is not None,
        "matched_rank": matched_rank,
    }


def score_single_query(
    golden_query: Dict[str, Any],
    search_result: Dict[str, Any],
    evidence_ks: Tuple[int, int] = (3, 5),
) -> Dict[str, Any]:
    query_id = golden_query["query_id"]

    expected_doc_types_raw = (
        golden_query.get("expected_doc_types_priority")
        or golden_query.get("expected_doc_types")
        or []
    )
    expected_doc_types = [normalize_doc_type(dt) for dt in expected_doc_types_raw]

    must_not_include_terms = golden_query.get("must_not_include_terms", [])
    allow_any = golden_query.get("allow_any_result", False)

    evidence_rules = parse_evidence_rules(golden_query)
    raw_rules = golden_query.get("expected_evidence_rules", {}) or {}
    if not allow_any and raw_rules:
        allow_any = not raw_rules.get("requires_citation", True)

    errors: List[str] = []

    if "error" in search_result:
        return {
            "query_id": query_id,
            "top1_match": False,
            "top3_match": False,
            "evidence_found": False,
            "evidence_found_top3": False,
            "evidence_found_top5": False,
            "top1_doc_type": "ERROR",
            "top3_doc_types": [],
            "matched_terms": [],
            "errors": [f"Search failed: {search_result['error']}"]
        }

    chunks = search_result.get("retrieved_chunks", []) or []
    if not chunks:
        return {
            "query_id": query_id,
            "top1_match": allow_any,
            "top3_match": allow_any,
            "evidence_found": allow_any,
            "evidence_found_top3": allow_any,
            "evidence_found_top5": allow_any,
            "top1_doc_type": "NONE",
            "top3_doc_types": [],
            "matched_terms": [],
            "errors": [] if allow_any else ["No chunks retrieved"],
            "evidence_debug": {
                "top3": {"chunk_rows": [], "evidence_found": allow_any, "matched_rank": None},
                "top5": {"chunk_rows": [], "evidence_found": allow_any, "matched_rank": None},
                "evidence_rules": evidence_rules,
            }
        }

    top_doc_types = [extract_doc_type(chunk) for chunk in chunks[:3]]
    top1_doc_type = top_doc_types[0] if top_doc_types else "NONE"

    if allow_any:
        top1_match = True
        top3_match = True
    else:
        top1_match = bool(expected_doc_types and top1_doc_type in expected_doc_types)
        top3_match = bool(expected_doc_types and any(dt in expected_doc_types for dt in top_doc_types))

    top3_eval = build_chunk_evidence_map(chunks, evidence_rules, top_k=evidence_ks[0])
    top5_eval = build_chunk_evidence_map(chunks, evidence_rules, top_k=evidence_ks[1])

    if allow_any or (
        not evidence_rules["all_of_terms"]
        and not evidence_rules["all_of_regex"]
        and not evidence_rules["any_of_terms"]
        and not evidence_rules["any_of_regex"]
    ):
        evidence_found_top3 = True
        evidence_found_top5 = True
    else:
        evidence_found_top3 = top3_eval["evidence_found"]
        evidence_found_top5 = top5_eval["evidence_found"]

    matched_terms: List[str] = []
    if evidence_found_top3:
        matched_rank = top3_eval["matched_rank"]
        if matched_rank:
            row = next((r for r in top3_eval["chunk_rows"] if r["rank"] == matched_rank), None)
            if row:
                for key, is_match in row["evidence_eval"]["term_matches"].items():
                    if is_match:
                        matched_terms.append(key.split("::", 1)[-1])
                for key, is_match in row["evidence_eval"]["regex_matches"].items():
                    if is_match:
                        matched_terms.append(key.split("::", 1)[-1])

    for term in must_not_include_terms:
        banned_found = False
        for chunk in chunks[: evidence_ks[1]]:
            text, _ = get_chunk_text(chunk)
            if phrase_match_with_plural_tolerance(text, term):
                banned_found = True
                break
        if banned_found:
            errors.append(f"Prohibited term '{term}' found in top-{evidence_ks[1]} results")

    return {
        "query_id": query_id,
        "top1_match": top1_match,
        "top3_match": top3_match,
        "evidence_found": evidence_found_top3,
        "evidence_found_top3": evidence_found_top3,
        "evidence_found_top5": evidence_found_top5,
        "top1_doc_type": top1_doc_type,
        "top3_doc_types": top_doc_types,
        "matched_terms": matched_terms,
        "errors": errors,
        "evidence_debug": {
            "top3": top3_eval,
            "top5": top5_eval,
            "evidence_rules": evidence_rules,
        },
    }


def get_split(query_id: str, golden_queries: List[Dict[str, Any]]) -> str:
    for q in golden_queries:
        if q["query_id"] == query_id:
            return q.get("split", "tune")
    return "tune"


def compute_aggregate_metrics(
    all_scores: List[Dict[str, Any]],
    golden_queries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    tune_scores = [s for s in all_scores if get_split(s["query_id"], golden_queries) == "tune"]
    holdout_scores = [s for s in all_scores if get_split(s["query_id"], golden_queries) == "holdout"]

    def compute_for_split(scores: List[Dict[str, Any]]) -> Dict[str, float]:
        if not scores:
            return {
                "top1_accuracy": 0.0,
                "top3_accuracy": 0.0,
                "evidence_accuracy_top3": 0.0,
                "evidence_accuracy_top5": 0.0,
                "total_queries": 0,
                "top1_correct": 0,
                "top3_correct": 0,
                "evidence_correct_top3": 0,
                "evidence_correct_top5": 0,
            }

        top1_correct = sum(1 for s in scores if s["top1_match"])
        top3_correct = sum(1 for s in scores if s["top3_match"])
        evidence_correct_top3 = sum(1 for s in scores if s["evidence_found_top3"])
        evidence_correct_top5 = sum(1 for s in scores if s["evidence_found_top5"])
        total = len(scores)

        return {
            "top1_accuracy": round(100.0 * top1_correct / total, 2),
            "top3_accuracy": round(100.0 * top3_correct / total, 2),
            "evidence_accuracy_top3": round(100.0 * evidence_correct_top3 / total, 2),
            "evidence_accuracy_top5": round(100.0 * evidence_correct_top5 / total, 2),
            "evidence_accuracy": round(100.0 * evidence_correct_top3 / total, 2),
            "total_queries": total,
            "top1_correct": top1_correct,
            "top3_correct": top3_correct,
            "evidence_correct_top3": evidence_correct_top3,
            "evidence_correct_top5": evidence_correct_top5,
            "evidence_correct": evidence_correct_top3,
        }

    return {
        "tune": compute_for_split(tune_scores),
        "holdout": compute_for_split(holdout_scores),
        "overall": compute_for_split(all_scores),
    }


def check_safe_targets(metrics: Dict[str, Any]) -> Dict[str, bool]:
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
        "all_targets_met": (tune_top1 >= 99.0) and (holdout_top1 >= 90.0) and (overall_top3 >= 98.0),
    }


def build_evidence_ledger(
    golden_queries: List[Dict[str, Any]],
    search_results: Dict[str, Any],
    all_scores: List[Dict[str, Any]],
    scenario_name: str,
) -> Dict[str, Any]:
    score_by_query = {score["query_id"]: score for score in all_scores}
    ledger_rows: List[Dict[str, Any]] = []

    for query in golden_queries:
        query_id = query["query_id"]
        result = search_results.get(query_id, {})
        chunks = result.get("retrieved_chunks", []) or []
        score = score_by_query.get(query_id, {})
        evidence_debug = score.get("evidence_debug", {})

        term_where_found: Dict[str, Optional[int]] = {}
        evidence_rules = evidence_debug.get("evidence_rules", parse_evidence_rules(query))

        all_rule_names: List[str] = []
        all_rule_names.extend([f"term::{t}" for t in evidence_rules["all_of_terms"]])
        all_rule_names.extend([f"regex::{p}" for p in evidence_rules["all_of_regex"]])
        all_rule_names.extend([f"any_term::{t}" for t in evidence_rules["any_of_terms"]])
        all_rule_names.extend([f"any_regex::{p}" for p in evidence_rules["any_of_regex"]])

        top5_rows = evidence_debug.get("top5", {}).get("chunk_rows", [])
        for rule_name in all_rule_names:
            found_idx = None
            for row in top5_rows:
                ev = row.get("evidence_eval", {})
                term_matches = ev.get("term_matches", {})
                regex_matches = ev.get("regex_matches", {})
                if rule_name in term_matches and term_matches[rule_name]:
                    found_idx = row.get("rank")
                    break
                if rule_name in regex_matches and regex_matches[rule_name]:
                    found_idx = row.get("rank")
                    break
            term_where_found[rule_name] = found_idx

        chunk_summaries = []
        for idx, chunk in enumerate(chunks[:5], start=1):
            content, flags = get_chunk_text(chunk)
            excerpt = content
            if len(excerpt) > 500:
                excerpt = excerpt[:250] + "\n...\n" + excerpt[-250:]

            chunk_summaries.append(
                {
                    "rank": idx,
                    "doc_id": chunk.get("doc_id"),
                    "doc_type": chunk.get("doc_type", "UNKNOWN"),
                    "chunk_id": chunk.get("chunk_id"),
                    "similarity": chunk.get("score", chunk.get("similarity")),
                    "source": chunk.get("source", chunk.get("source_path", "")),
                    "flags": flags,
                    "excerpt": excerpt,
                }
            )

        ledger_rows.append(
            {
                "query_id": query_id,
                "query_text": query.get("query_text", ""),
                "split": query.get("split", "tune"),
                "evidence_requirements": {
                    "must_include_terms": query.get("must_include_terms", []),
                    "must_not_include_terms": query.get("must_not_include_terms", []),
                    "expected_evidence_rules": query.get("expected_evidence_rules", {}),
                    "parsed_rules": evidence_rules,
                },
                "evidence_found_top3": score.get("evidence_found_top3", False),
                "evidence_found_top5": score.get("evidence_found_top5", False),
                "matched_rank_top3": evidence_debug.get("top3", {}).get("matched_rank"),
                "matched_rank_top5": evidence_debug.get("top5", {}).get("matched_rank"),
                "rule_match_where": term_where_found,
                "top5_chunks": chunk_summaries,
            }
        )

    return {
        "scenario": scenario_name,
        "query_count": len(ledger_rows),
        "queries": ledger_rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score golden queries against search results with strict evidence matching."
    )
    parser.add_argument("golden_queries", type=Path)
    parser.add_argument("search_results", type=Path)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--scenario-name", default="unspecified")
    parser.add_argument("--ledger-out", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    golden_path = args.golden_queries
    results_path = args.search_results

    if not golden_path.exists():
        print(f"ERROR: Golden queries file not found: {golden_path}")
        sys.exit(1)
    if not results_path.exists():
        print(f"ERROR: Search results file not found: {results_path}")
        sys.exit(1)

    golden_queries = load_golden_queries(golden_path)
    search_results = load_search_results(results_path)

    all_scores: List[Dict[str, Any]] = []
    for golden_query in golden_queries:
        query_id = golden_query["query_id"]
        if query_id in search_results:
            score = score_single_query(golden_query, search_results[query_id], evidence_ks=(3, 5))
            all_scores.append(score)
        else:
            all_scores.append(
                {
                    "query_id": query_id,
                    "top1_match": False,
                    "top3_match": False,
                    "evidence_found": False,
                    "evidence_found_top3": False,
                    "evidence_found_top5": False,
                    "top1_doc_type": "MISSING",
                    "top3_doc_types": [],
                    "matched_terms": [],
                    "errors": ["Query not executed"],
                    "evidence_debug": {
                        "top3": {"chunk_rows": [], "evidence_found": False, "matched_rank": None},
                        "top5": {"chunk_rows": [], "evidence_found": False, "matched_rank": None},
                        "evidence_rules": parse_evidence_rules(golden_query),
                    },
                }
            )

    metrics = compute_aggregate_metrics(all_scores, golden_queries)
    safe_targets = check_safe_targets(metrics)

    print("\n" + "=" * 80)
    print("QUERY ACCURACY SCORING REPORT")
    print("=" * 80)

    print("\n--- TUNE SET (40 queries) ---")
    print(
        f"  Top-1 Accuracy: {metrics['tune']['top1_accuracy']}% ({metrics['tune']['top1_correct']}/{metrics['tune']['total_queries']}) [TARGET: >=99%]"
    )
    print(
        f"  Top-3 Accuracy: {metrics['tune']['top3_accuracy']}% ({metrics['tune']['top3_correct']}/{metrics['tune']['total_queries']})"
    )
    print(
        f"  Evidence Found @Top-3: {metrics['tune']['evidence_accuracy_top3']}% ({metrics['tune']['evidence_correct_top3']}/{metrics['tune']['total_queries']})"
    )
    print(
        f"  Evidence Found @Top-5: {metrics['tune']['evidence_accuracy_top5']}% ({metrics['tune']['evidence_correct_top5']}/{metrics['tune']['total_queries']})"
    )
    print(f"  Status: {'PASS' if safe_targets['tune_top1_pass'] else 'FAIL'}")

    print("\n--- HOLDOUT SET (10 queries) ---")
    print(
        f"  Top-1 Accuracy: {metrics['holdout']['top1_accuracy']}% ({metrics['holdout']['top1_correct']}/{metrics['holdout']['total_queries']}) [TARGET: >=90%]"
    )
    print(
        f"  Top-3 Accuracy: {metrics['holdout']['top3_accuracy']}% ({metrics['holdout']['top3_correct']}/{metrics['holdout']['total_queries']})"
    )
    print(
        f"  Evidence Found @Top-3: {metrics['holdout']['evidence_accuracy_top3']}% ({metrics['holdout']['evidence_correct_top3']}/{metrics['holdout']['total_queries']})"
    )
    print(
        f"  Evidence Found @Top-5: {metrics['holdout']['evidence_accuracy_top5']}% ({metrics['holdout']['evidence_correct_top5']}/{metrics['holdout']['total_queries']})"
    )
    print(f"  Status: {'PASS' if safe_targets['holdout_top1_pass'] else 'FAIL'}")

    print("\n--- OVERALL (50 queries) ---")
    print(
        f"  Top-1 Accuracy: {metrics['overall']['top1_accuracy']}% ({metrics['overall']['top1_correct']}/{metrics['overall']['total_queries']})"
    )
    print(
        f"  Top-3 Accuracy: {metrics['overall']['top3_accuracy']}% ({metrics['overall']['top3_correct']}/{metrics['overall']['total_queries']}) [TARGET: >=98%]"
    )
    print(
        f"  Evidence Found @Top-3: {metrics['overall']['evidence_accuracy_top3']}% ({metrics['overall']['evidence_correct_top3']}/{metrics['overall']['total_queries']})"
    )
    print(
        f"  Evidence Found @Top-5: {metrics['overall']['evidence_accuracy_top5']}% ({metrics['overall']['evidence_correct_top5']}/{metrics['overall']['total_queries']})"
    )
    print(f"  Status: {'PASS' if safe_targets['overall_top3_pass'] else 'FAIL'}")

    print("\n--- SAFE TARGETS STATUS ---")
    tune_status = "PASS" if safe_targets["tune_top1_pass"] else f"FAIL ({safe_targets['tune_top1_value']}%)"
    holdout_status = "PASS" if safe_targets["holdout_top1_pass"] else f"FAIL ({safe_targets['holdout_top1_value']}%)"
    overall_status = "PASS" if safe_targets["overall_top3_pass"] else f"FAIL ({safe_targets['overall_top3_value']}%)"
    print(f"  Tune Top-1 >= 99%:     {tune_status}")
    print(f"  Holdout Top-1 >= 90%:  {holdout_status}")
    print(f"  Overall Top-3 >= 98%:  {overall_status}")
    print(f"\n  ALL TARGETS MET: {'YES' if safe_targets['all_targets_met'] else 'NO'}")

    if args.verbose:
        print("\n--- DETAILED FAILURES ---")
        for score in all_scores:
            if not score["top1_match"] or not score["evidence_found_top5"]:
                query = next((q for q in golden_queries if q["query_id"] == score["query_id"]), None)
                if not query:
                    continue
                split = query.get("split", "tune").upper()
                print(f"\n  [{split}] {score['query_id']}: {query.get('query_text', '')}")
                print(f"    Expected doc_types: {query.get('expected_doc_types_priority') or query.get('expected_doc_types') or []}")
                print(f"    Actual Top-1: {score['top1_doc_type']}")
                print(f"    Actual Top-3: {score['top3_doc_types']}")
                print(f"    Evidence @Top-3: {score['evidence_found_top3']}")
                print(f"    Evidence @Top-5: {score['evidence_found_top5']}")
                if score["errors"]:
                    print(f"    Errors: {', '.join(score['errors'])}")

    print("\n" + "=" * 80)

    output_path = args.output_json or (results_path.parent / "accuracy_scores.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "scenario": args.scenario_name,
        "metrics": metrics,
        "safe_targets": safe_targets,
        "detailed_scores": all_scores,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"\nDetailed scores saved to: {output_path}")

    if args.ledger_out:
        ledger = build_evidence_ledger(
            golden_queries=golden_queries,
            search_results=search_results,
            all_scores=all_scores,
            scenario_name=args.scenario_name,
        )
        args.ledger_out.parent.mkdir(parents=True, exist_ok=True)
        with open(args.ledger_out, "w", encoding="utf-8") as f:
            json.dump(ledger, f, indent=2)
        print(f"Evidence ledger saved to: {args.ledger_out}")

    sys.exit(0 if safe_targets["all_targets_met"] else 1)


if __name__ == "__main__":
    main()
