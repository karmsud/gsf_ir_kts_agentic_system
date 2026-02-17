"""
PSA VSIX Integration Test
Runs 10 PSA queries against the bundled backend exe and scores results.
Uses the first 10 queries from tests/psa_test_queries.json.
"""
import json
import subprocess
import sys
import os
import re
from pathlib import Path

EXE = Path("dist/kts-backend/kts-backend.exe")
QUERIES_FILE = Path("tests/psa_test_queries.json")
OUTPUT_FILE = Path("tests/psa_eval_results/vsix_psa_test_results.json")

os.environ["KTS_KB_PATH"] = "source_1\\.kts"


def run_search(query_text: str) -> dict:
    """Execute a search query via the bundled backend exe."""
    result = subprocess.run(
        [str(EXE), "search", query_text],
        capture_output=True, text=True, timeout=120,
        env={**os.environ}
    )
    # Output may have stderr warnings before JSON
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()

    # Find JSON in stdout
    json_start = stdout.find("{")
    if json_start == -1:
        return {"error": f"No JSON in output. stderr={stderr}", "context_chunks": [], "citations": []}
    try:
        return json.loads(stdout[json_start:])
    except json.JSONDecodeError as e:
        return {"error": str(e), "context_chunks": [], "citations": []}


def score_query(query: dict, result: dict) -> dict:
    """Score a single query result against expected keyphrases/entities."""
    chunks = result.get("context_chunks", [])
    if not chunks:
        return {
            "query_id": query["query_id"],
            "query_text": query["query_text"],
            "hit": False,
            "keyphrase_recall": 0.0,
            "entity_recall": 0.0,
            "chunk_count": 0,
            "top_doc_type": None,
            "evidence_preview": None,
            "notes": "NO RESULTS"
        }

    # Combine all chunk content for keyphrase/entity matching
    all_content = " ".join(c.get("content", "") for c in chunks).lower()

    # Keyphrase recall
    expected_kp = query.get("expected_keyphrases", [])
    kp_found = [kp for kp in expected_kp if kp.lower() in all_content]
    kp_recall = len(kp_found) / len(expected_kp) if expected_kp else 1.0

    # Entity recall
    expected_ent = query.get("expected_entities", [])
    ent_found = [e for e in expected_ent if e.lower() in all_content]
    ent_recall = len(ent_found) / len(expected_ent) if expected_ent else 1.0

    top_chunk = chunks[0]
    preview = top_chunk.get("content", "")[:200]

    return {
        "query_id": query["query_id"],
        "query_text": query["query_text"],
        "hit": True,
        "keyphrase_recall": round(kp_recall, 2),
        "entity_recall": round(ent_recall, 2),
        "chunk_count": len(chunks),
        "top_doc_type": top_chunk.get("doc_type", "?"),
        "keyphrases_found": kp_found,
        "keyphrases_missing": [kp for kp in expected_kp if kp.lower() not in all_content],
        "entities_found": ent_found,
        "entities_missing": [e for e in expected_ent if e.lower() not in all_content],
        "evidence_preview": preview
    }


def main():
    print("=" * 70)
    print("PSA VSIX INTEGRATION TEST — Bundled Backend Exe")
    print("=" * 70)
    print()

    # Load queries (first 10)
    with open(QUERIES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    queries = data["queries"][:10]

    print(f"Running {len(queries)} PSA queries against bundled exe...")
    print(f"Exe: {EXE}")
    print(f"KB:  {os.environ['KTS_KB_PATH']}")
    print()

    results = []
    for i, q in enumerate(queries, 1):
        qid = q["query_id"]
        qtxt = q["query_text"]
        print(f"[{i:2d}/10] {qid}: {qtxt}")
        search_result = run_search(qtxt)
        score = score_query(q, search_result)
        results.append(score)

        status = "PASS" if score["hit"] else "MISS"
        kp = f"KP={score['keyphrase_recall']:.0%}"
        ent = f"ENT={score['entity_recall']:.0%}"
        print(f"        {status} | {kp} | {ent} | chunks={score['chunk_count']}")

    # Summary
    print()
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    hits = sum(1 for r in results if r["hit"])
    avg_kp = sum(r["keyphrase_recall"] for r in results) / len(results)
    avg_ent = sum(r["entity_recall"] for r in results) / len(results)

    print(f"  Queries:           {len(results)}")
    print(f"  Hits (non-empty):  {hits}/{len(results)}")
    print(f"  Avg KP Recall:     {avg_kp:.1%}")
    print(f"  Avg ENT Recall:    {avg_ent:.1%}")
    print()

    # Per-query detail
    print(f"{'QID':<10} {'Hit':>4} {'KP':>6} {'ENT':>6}  Query")
    print("-" * 70)
    for r in results:
        hit = "YES" if r["hit"] else "NO"
        print(f"{r['query_id']:<10} {hit:>4} {r['keyphrase_recall']:>5.0%} {r['entity_recall']:>5.0%}  {r['query_text'][:45]}")

    # Missing details
    print()
    print("KEYPHRASE GAPS:")
    for r in results:
        missing = r.get("keyphrases_missing", [])
        if missing:
            print(f"  {r['query_id']}: missing {missing}")

    print()
    print("ENTITY GAPS:")
    for r in results:
        missing = r.get("entities_missing", [])
        if missing:
            print(f"  {r['query_id']}: missing {missing}")

    # Save results
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "test_run": "vsix_bundled_exe_psa",
            "queries_tested": len(results),
            "hits": hits,
            "avg_keyphrase_recall": round(avg_kp, 3),
            "avg_entity_recall": round(avg_ent, 3),
            "results": results
        }, f, indent=2)
    print(f"\nDetailed results saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
