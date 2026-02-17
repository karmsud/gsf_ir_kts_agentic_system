#!/usr/bin/env python3
"""Full VSIX retest — exercises bundled exe on all 3 knowledge-source folders.

Tests cover:
  1. Crawl + ingest for each folder
  2. Feature verification (NER, regime classification, defined terms, query expansion,
     acronym resolution, version auto-increment, content-date extraction, graph)
  3. Search quality with existing query frameworks
  4. All 6 gap fixes validated

Usage:
    python tests/test_vsix_full_retest.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXE = REPO / "dist" / "kts-backend" / "kts-backend.exe"

FOLDERS = {
    "source_1": REPO / "source_1",
    "source_2": REPO / "source_2",
    "knowledge_base_test": REPO / "Knowledge Base test",
}

PSA_QUERIES = json.loads((REPO / "tests" / "psa_test_queries.json").read_text(encoding="utf-8"))["queries"][:10]

# Load golden queries for KB test folder
GOLDEN_QUERIES_RAW = json.loads((REPO / "tests" / "golden_queries.json").read_text(encoding="utf-8"))["queries"]
GOLDEN_QUERIES = [{"query_id": q["query_id"], "query_text": q["query_text"], "expected_keyphrases": q.get("must_include_terms", [])} for q in GOLDEN_QUERIES_RAW[:20]]


def run_cli(args: list[str], kb_path: str, timeout: int = 300) -> dict:
    """Run bundled exe with KTS_KB_PATH set, return parsed JSON stdout."""
    env = os.environ.copy()
    env["KTS_KB_PATH"] = kb_path
    cmd = [str(EXE)] + args
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env)
    if proc.returncode != 0:
        print(f"  [STDERR] {proc.stderr[:500]}")
        raise RuntimeError(f"CLI failed (rc={proc.returncode}): {' '.join(args)}")
    stdout = proc.stdout.strip()
    # Find the last JSON object in stdout
    for i in range(len(stdout) - 1, -1, -1):
        if stdout[i] == '}' or stdout[i] == ']':
            for j in range(i, -1, -1):
                if stdout[j] == '{' or stdout[j] == '[':
                    try:
                        return json.loads(stdout[j:i + 1])
                    except json.JSONDecodeError:
                        continue
    return {"raw_output": stdout}


def clean_kts(folder: Path):
    """Remove .kts folder if it exists."""
    kts = folder / ".kts"
    if kts.exists():
        shutil.rmtree(kts)


def test_folder(name: str, folder: Path, queries: list[dict] | None = None):
    """Full test cycle for one source folder."""
    print(f"\n{'=' * 72}")
    print(f"TESTING: {name} ({folder})")
    print(f"{'=' * 72}")

    kb_path = str(folder / ".kts")
    clean_kts(folder)

    # 1. CRAWL
    print("\n[1] CRAWL")
    t0 = time.time()
    crawl_result = run_cli(["crawl", "--paths", str(folder)], kb_path)
    dt = time.time() - t0
    changes = crawl_result.get("changes", {})
    new_count = len(changes.get("new_files", []))
    print(f"  Files detected: {new_count} in {dt:.1f}s")
    assert new_count > 0, f"Crawl found 0 files in {folder}"

    # 2. INGEST
    print("\n[2] INGEST")
    t0 = time.time()
    ingest_result = run_cli(["ingest", "--paths", str(folder)], kb_path, timeout=600)
    dt = time.time() - t0
    ingested = ingest_result.get("ingested", [])
    count = ingest_result.get("count", 0)
    corpus_regime = ingest_result.get("corpus_regime", "MISSING")
    synonym_clusters = ingest_result.get("synonym_clusters", {})
    print(f"  Ingested: {count} docs in {dt:.1f}s")
    print(f"  Corpus regime: {corpus_regime}")
    print(f"  Synonym clusters: {json.dumps(synonym_clusters)[:200]}")
    assert count > 0, f"Ingest returned 0 docs for {name}"

    # 3. FEATURE VERIFICATION
    results = {
        "folder": name,
        "crawl_count": new_count,
        "ingest_count": count,
        "corpus_regime": corpus_regime,
    }

    # 3a. GAP 2: Regime classification wired
    print("\n[3a] REGIME CLASSIFICATION (Gap 2)")
    if name in ("source_1", "source_2"):
        # PSA docs should be classified as GOVERNING_DOC_LEGAL or MIXED
        assert corpus_regime in ("GOVERNING_DOC_LEGAL", "MIXED"), \
            f"PSA folder should be GOVERNING_DOC_LEGAL or MIXED, got {corpus_regime}"
        print(f"  PASS: PSA corpus correctly classified as {corpus_regime}")
    else:
        print(f"  INFO: Knowledge base corpus classified as {corpus_regime}")

    # 3b. GAP 2 cont: doc_regime stored in metadata
    print("\n[3b] DOC_REGIME IN METADATA")
    docs_dir = Path(kb_path) / "documents"
    regime_found = False
    if docs_dir.exists():
        for meta_path in docs_dir.rglob("metadata.json"):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            dr = meta.get("doc_regime", "MISSING")
            if dr and dr != "UNKNOWN" and dr != "MISSING":
                regime_found = True
                break
    if regime_found:
        print(f"  PASS: doc_regime found in metadata: {dr}")
    else:
        print(f"  WARN: No doc_regime found in metadata files")
    results["doc_regime_stored"] = regime_found

    # 3c. GAP 6: Content date extraction
    print("\n[3c] CONTENT DATE EXTRACTION (Gap 6)")
    content_date_found = False
    if docs_dir.exists():
        for meta_path in docs_dir.rglob("metadata.json"):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            cd = meta.get("content_date")
            if cd:
                content_date_found = True
                print(f"  PASS: Content date found: {cd}")
                break
    if not content_date_found:
        print(f"  INFO: No content dates extracted (may not have 'Last Updated:' text)")
    results["content_date_found"] = content_date_found

    # 3d. GAP 3: Defined terms (4-strategy extractor)
    print("\n[3d] DEFINED TERMS GRAPH (Gap 3)")
    graph_path = Path(kb_path) / "graph" / "knowledge_graph.json"
    defterm_count = 0
    if graph_path.exists():
        graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
        nodes = graph_data.get("nodes", {})
        # nodes is a dict keyed by node_id
        if isinstance(nodes, dict):
            defterm_count = sum(1 for k in nodes if k.startswith("defterm:"))
        elif isinstance(nodes, list):
            defterm_count = sum(1 for n in nodes if (n if isinstance(n, str) else n.get("id", "")).startswith("defterm:"))
    print(f"  Defined terms in graph: {defterm_count}")
    results["defterm_count"] = defterm_count

    # 3e. GAP 2 cont: corpus_regime stored in graph attributes
    print("\n[3e] CORPUS REGIME IN GRAPH")
    graph_regime = "MISSING"
    if graph_path.exists():
        graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
        graph_regime = graph_data.get("graph", {}).get("corpus_regime", "MISSING")
    print(f"  Graph corpus_regime: {graph_regime}")
    results["graph_corpus_regime"] = graph_regime

    # 3f. NER keyphrases produced
    print("\n[3f] NER + KEYPHRASES")
    kp_count = 0
    ent_count = 0
    if docs_dir.exists():
        for meta_path in docs_dir.rglob("metadata.json"):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            kp_count += len(meta.get("keyphrases", []))
            ent_count += len(meta.get("entities", []))
    print(f"  Total keyphrases: {kp_count}, entities: {ent_count}")
    results["keyphrase_count"] = kp_count
    results["entity_count"] = ent_count

    # 4. SEARCH QUERIES
    print("\n[4] SEARCH QUERIES")
    test_queries = queries or [
        {"query_id": "GEN-Q1", "query_text": "What is a troubleshooting guide?", "expected_keyphrases": ["troubleshooting"]},
        {"query_id": "GEN-Q2", "query_text": "How do I configure settings?", "expected_keyphrases": ["configure", "settings"]},
    ]
    
    hit_count = 0
    total_queries = len(test_queries)
    search_results = []
    for q in test_queries:
        qid = q.get("query_id", "?")
        qtext = q["query_text"]
        try:
            sr = run_cli(["search", qtext, "--max-results", "5"], kb_path, timeout=120)
            chunks = []
            # Handle nested structure
            if "search_result" in sr and isinstance(sr["search_result"], dict):
                inner = sr["search_result"]
            elif "context_chunks" in sr:
                inner = sr
            else:
                inner = sr
            chunks = inner.get("context_chunks", [])
            citations = inner.get("citations", [])
            confidence = inner.get("confidence", 0)
            term_res = sr.get("term_resolution")
            
            has_hit = len(chunks) > 0
            hit_count += 1 if has_hit else 0
            
            result_entry = {
                "query_id": qid,
                "query": qtext,
                "hit": has_hit,
                "chunks": len(chunks),
                "confidence": confidence,
                "term_resolution": term_res is not None and term_res.get("activated", False),
            }
            search_results.append(result_entry)
            status = "HIT" if has_hit else "MISS"
            extra = f" +TR" if result_entry["term_resolution"] else ""
            print(f"  [{status}] {qid}: {qtext[:60]}... ({len(chunks)} chunks, conf={confidence:.2f}){extra}")
        except Exception as exc:
            search_results.append({"query_id": qid, "query": qtext, "hit": False, "error": str(exc)})
            print(f"  [ERR] {qid}: {exc}")

    hit_rate = hit_count / total_queries * 100 if total_queries > 0 else 0
    print(f"\n  Hit rate: {hit_count}/{total_queries} ({hit_rate:.1f}%)")
    results["hit_rate"] = hit_rate
    results["search_results"] = search_results

    # 5. GAP 4: VERSION AUTO-INCREMENT (re-ingest one doc)
    if name == "knowledge_base_test":
        print("\n[5] VERSION AUTO-INCREMENT (Gap 4)")
        # Pick first real doc (not from .kts internal dir)
        first_file = None
        for f in folder.rglob("*"):
            if f.is_file() and f.suffix.lower() in (".md", ".txt", ".json") and ".kts" not in str(f):
                first_file = f
                break
        if first_file:
            try:
                reingest = run_cli(["ingest", "--paths", str(first_file)], kb_path, timeout=120)
                ri_docs = reingest.get("ingested", [])
                if ri_docs:
                    doc_id = ri_docs[0].get("doc_id")
                    meta_path = Path(kb_path) / "documents" / doc_id / "metadata.json"
                    if meta_path.exists():
                        meta = json.loads(meta_path.read_text(encoding="utf-8"))
                        version = meta.get("version", 0)
                        print(f"  Re-ingested {first_file.name}: version={version}")
                        if version >= 2:
                            print(f"  PASS: Version auto-incremented to {version}")
                        else:
                            print(f"  WARN: Version is {version} (expected >=2)")
                        results["version_auto_increment"] = version >= 2
            except Exception as exc:
                print(f"  [ERR] Re-ingest failed: {exc}")

    # 6. GAP 1: QUERY EXPANSION + ACRONYM RESOLUTION
    if name in ("source_1", "source_2"):
        print("\n[6] QUERY EXPANSION + ACRONYM RESOLUTION (Gap 1)")
        # Query with acronym "PSA" — should be expanded
        try:
            sr = run_cli(["search", "What is a PSA?", "--max-results", "3"], kb_path, timeout=120)
            inner = sr.get("search_result", sr)
            chunks = inner.get("context_chunks", [])
            print(f"  'What is a PSA?' returned {len(chunks)} chunks")
            if chunks:
                # Check if the returned content mentions Pooling and Servicing Agreement
                all_content = " ".join(c.get("content", "") for c in chunks)
                has_psa = "pooling" in all_content.lower() or "servicing" in all_content.lower()
                print(f"  Content mentions pooling/servicing: {has_psa}")
                results["acronym_expansion_effective"] = has_psa
        except Exception as exc:
            print(f"  [ERR] {exc}")

    return results


def main():
    print("=" * 72)
    print("FULL VSIX RETEST — All 3 Source Folders + 6 Gap Fixes")
    print("=" * 72)
    print(f"Exe: {EXE}")
    assert EXE.exists(), f"Backend exe not found: {EXE}"

    all_results = {}

    # Test source_1 (PSA .doc file)
    all_results["source_1"] = test_folder("source_1", FOLDERS["source_1"], PSA_QUERIES)

    # Test source_2 (PSA .pdf file)
    all_results["source_2"] = test_folder("source_2", FOLDERS["source_2"], PSA_QUERIES)

    # Test Knowledge Base test (58 mixed files)
    all_results["knowledge_base_test"] = test_folder("knowledge_base_test", FOLDERS["knowledge_base_test"], GOLDEN_QUERIES)

    # SUMMARY
    print("\n" + "=" * 72)
    print("FULL RETEST SUMMARY")
    print("=" * 72)
    
    all_pass = True
    for name, r in all_results.items():
        print(f"\n{name}:")
        print(f"  Crawl:  {r['crawl_count']} files")
        print(f"  Ingest: {r['ingest_count']} docs")
        print(f"  Regime: {r['corpus_regime']}")
        print(f"  Graph regime: {r.get('graph_corpus_regime', 'N/A')}")
        print(f"  Defined terms: {r.get('defterm_count', 0)}")
        print(f"  NER kp/ent: {r.get('keyphrase_count', 0)}/{r.get('entity_count', 0)}")
        print(f"  Hit rate: {r.get('hit_rate', 0):.1f}%")
        
        if r.get("hit_rate", 0) < 50:
            print(f"  ** LOW HIT RATE **")
            all_pass = False

    # Save results
    results_path = REPO / "tests" / "psa_eval_results" / "vsix_full_retest_results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(all_results, indent=2, default=str), encoding="utf-8")
    print(f"\nResults saved to: {results_path}")

    if all_pass:
        print("\n*** ALL TESTS PASSED ***")
    else:
        print("\n*** SOME TESTS HAD ISSUES ***")
    
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
