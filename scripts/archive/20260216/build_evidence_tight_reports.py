import json
from pathlib import Path
from typing import Any, Dict, List

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from tests.score_queries import parse_evidence_rules, evaluate_term_rule, evaluate_regex_rule, normalize_text


SCENARIOS = {
    "v1": {
        "name": "V1 Isolated",
        "golden": Path("tests/golden_queries.json"),
        "search_baseline": Path("data/search_results_baseline_v1.json"),
        "score_baseline": Path("data/accuracy_scores_baseline_v1.json"),
        "ledger_baseline": Path("data/evidence_ledger_baseline_v1.json"),
        "search_after": Path("data/search_results_after_v1.json"),
        "score_after": Path("data/accuracy_scores_after_v1.json"),
        "ledger_after": Path("data/evidence_ledger_after_v1.json"),
    },
    "v2": {
        "name": "V2 Isolated",
        "golden": Path("tests/golden_queries_v2.json"),
        "search_baseline": Path("data/search_results_baseline_v2.json"),
        "score_baseline": Path("data/accuracy_scores_baseline_v2.json"),
        "ledger_baseline": Path("data/evidence_ledger_baseline_v2.json"),
        "search_after": Path("data/search_results_after_v2.json"),
        "score_after": Path("data/accuracy_scores_after_v2.json"),
        "ledger_after": Path("data/evidence_ledger_after_v2.json"),
    },
    "mixed": {
        "name": "Mixed (Realism)",
        "golden": Path("tests/golden_queries_v2.json"),
        "search_baseline": Path("data/search_results_baseline_mixed.json"),
        "score_baseline": Path("data/accuracy_scores_baseline_mixed.json"),
        "ledger_baseline": Path("data/evidence_ledger_baseline_mixed.json"),
        "search_after": Path("data/search_results_after_mixed.json"),
        "score_after": Path("data/accuracy_scores_after_mixed.json"),
        "ledger_after": Path("data/evidence_ledger_after_mixed.json"),
    },
}


def load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_queries_map(search_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    if "queries" in search_data and isinstance(search_data["queries"], list):
        return {row["query_id"]: row for row in search_data["queries"]}
    return search_data


def compute_citation_rate(ledger: Dict[str, Any]) -> float:
    total = len(ledger.get("queries", []))
    if total == 0:
        return 0.0
    with_chunk = sum(1 for q in ledger.get("queries", []) if q.get("top5_chunks"))
    return round(100.0 * with_chunk / total, 2)


def classify_failure(
    ledger_query: Dict[str, Any],
    golden_query: Dict[str, Any],
    search_query: Dict[str, Any],
) -> str:
    top5_chunks = search_query.get("retrieved_chunks", [])[:5]
    rules = parse_evidence_rules(golden_query)
    all_rules = [f"term::{t}" for t in rules["all_of_terms"]] + [f"regex::{r}" for r in rules["all_of_regex"]]

    if not all_rules:
        return "A) SCORER BUG"

    for chunk in top5_chunks:
        content = str(chunk.get("content", "") or "")
        if not content.strip():
            continue
        normalized = normalize_text(content)
        term_ok = all(evaluate_term_rule(t, normalized) for t in rules["all_of_terms"])
        regex_ok = all(evaluate_regex_rule(p, normalized) for p in rules["all_of_regex"])
        if term_ok and regex_ok:
            return "A) SCORER BUG"

    has_incomplete_text = False
    for chunk in ledger_query.get("top5_chunks", []):
        flags = chunk.get("flags", {})
        if not flags.get("has_content", False) and (flags.get("has_excerpt", False) or flags.get("has_pointer", False)):
            has_incomplete_text = True
            break
    if has_incomplete_text:
        return "B) SERIALIZATION/TRUNCATION"

    by_doc: Dict[str, set] = {}
    for rank, chunk in enumerate(top5_chunks, start=1):
        doc_id = str(chunk.get("doc_id", ""))
        if not doc_id:
            continue
        text = normalize_text(str(chunk.get("content", "") or ""))
        matched = set()
        for term in rules["all_of_terms"]:
            if evaluate_term_rule(term, text):
                matched.add(f"term::{term}")
        for pattern in rules["all_of_regex"]:
            if evaluate_regex_rule(pattern, text):
                matched.add(f"regex::{pattern}")
        if matched:
            by_doc.setdefault(doc_id, set()).update(matched)

    for matched_rules in by_doc.values():
        if all(rule in matched_rules for rule in all_rules):
            return "C) CHUNKING DILUTION"

    return "D) EXTRACTION GAP"


def build_baseline_report() -> str:
    lines: List[str] = []
    lines.append("# Evidence Baseline (Tight / Safe)")
    lines.append("")
    lines.append("## Baseline Metrics")
    lines.append("")
    lines.append("| Scenario | Top-1 | Top-3 | Evidence @Top-3 | Evidence @Top-5 | Citations |")
    lines.append("| :-- | --: | --: | --: | --: | --: |")

    for key in ["v1", "v2", "mixed"]:
        cfg = SCENARIOS[key]
        score = load_json(cfg["score_baseline"])
        ledger = load_json(cfg["ledger_baseline"])
        overall = score["metrics"]["overall"]
        citation_rate = compute_citation_rate(ledger)

        lines.append(
            f"| {cfg['name']} | {overall['top1_accuracy']}% | {overall['top3_accuracy']}% | {overall['evidence_accuracy_top3']}% | {overall['evidence_accuracy_top5']}% | {citation_rate}% |"
        )

    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- Evidence matching uses strict per-chunk ALL-of evaluation with NFKC, whitespace normalization, punctuation tolerance, hyphen/underscore equivalence, and simple plural equivalence.")
    lines.append("- Baseline artifacts were produced without ranking-weight or answer-generation changes.")
    lines.append("- Raw console logs are in data/raw_console/.")
    return "\n".join(lines) + "\n"


def build_failure_report() -> str:
    lines: List[str] = []
    lines.append("# Evidence Failures (Tight)")
    lines.append("")

    for key in ["v1", "v2", "mixed"]:
        cfg = SCENARIOS[key]
        golden = load_json(cfg["golden"])
        golden_map = {q["query_id"]: q for q in golden["queries"]}
        ledger = load_json(cfg["ledger_baseline"])
        search = extract_queries_map(load_json(cfg["search_baseline"]))

        failures = [q for q in ledger.get("queries", []) if not q.get("evidence_found_top5", False)]

        lines.append(f"## {cfg['name']}")
        lines.append("")
        lines.append(f"- Failures: {len(failures)}")
        lines.append("")

        for failure in failures:
            qid = failure["query_id"]
            gq = golden_map.get(qid, {})
            sq = search.get(qid, {"retrieved_chunks": []})
            classification = classify_failure(failure, gq, sq)

            lines.append(f"### {qid}")
            lines.append("")
            lines.append(f"- Classification: {classification}")
            lines.append(f"- Query: {gq.get('query_text', '')}")
            lines.append(f"- Required evidence: {json.dumps(failure.get('evidence_requirements', {}), ensure_ascii=False)}")
            lines.append("")
            lines.append("#### Top-5 Chunk Excerpts")
            lines.append("")

            for chunk in failure.get("top5_chunks", []):
                excerpt = chunk.get("excerpt", "")
                lines.append(
                    f"- Rank {chunk.get('rank')} | doc_id={chunk.get('doc_id')} | doc_type={chunk.get('doc_type')} | chunk_id={chunk.get('chunk_id')} | similarity={chunk.get('similarity')}"
                )
                lines.append(f"  - Excerpt: {excerpt.replace(chr(10), ' ')}")

            lines.append("")
            lines.append("#### Per-term Match Table")
            lines.append("")
            lines.append("| Rule | Matched | Chunk Rank |")
            lines.append("| :-- | :-- | --: |")
            for rule_name, rank in failure.get("rule_match_where", {}).items():
                lines.append(f"| {rule_name} | {'true' if rank is not None else 'false'} | {rank if rank is not None else '-'} |")
            lines.append("")

    return "\n".join(lines) + "\n"


def build_fix_log() -> str:
    lines: List[str] = []
    lines.append("# Evidence Fix Log (Tight)")
    lines.append("")
    lines.append("| Change | Scope | Failing Query IDs | Proof Artifact |")
    lines.append("| :-- | :-- | :-- | :-- |")
    lines.append("| Fix 1: Strict matcher + schema-tolerant evidence parsing | tests/score_queries.py | Populated after after-ledgers are generated | data/evidence_ledger_after_*.json |")
    lines.append("| Fix 2: Retrieval output completeness checks in scorer (content/excerpt/pointer fallback) | tests/score_queries.py | Populated after after-ledgers are generated | data/evidence_ledger_after_*.json |")
    return "\n".join(lines) + "\n"


def main() -> None:
    baseline_md = build_baseline_report()
    failure_md = build_failure_report()
    fix_log_md = build_fix_log()

    Path("docs/EVIDENCE_BASELINE_TIGHT.md").write_text(baseline_md, encoding="utf-8")
    Path("docs/EVIDENCE_FAILURES_TIGHT.md").write_text(failure_md, encoding="utf-8")
    Path("docs/EVIDENCE_FIX_LOG_TIGHT.md").write_text(fix_log_md, encoding="utf-8")

    print("Generated docs/EVIDENCE_BASELINE_TIGHT.md")
    print("Generated docs/EVIDENCE_FAILURES_TIGHT.md")
    print("Generated docs/EVIDENCE_FIX_LOG_TIGHT.md")


if __name__ == "__main__":
    main()
