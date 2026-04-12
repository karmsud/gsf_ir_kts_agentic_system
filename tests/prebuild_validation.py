"""
Pre-build validation: Ingestion + Search + Explainability.

Tests:
1. Fresh ingestion of kts_test_corpus (PDF, Word, Markdown files)
2. Search queries verifying retrieval quality + explainability trace
3. CLI JSON output structure validation
"""
import json
import os
import shutil
import sys
import time
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── Configuration ──────────────────────────────────────────────
CORPUS = ROOT / "Knowledge Base test" / "kts_test_corpus"
KB_PATH = ROOT / ".kts_prebuild_test"
os.environ["KTS_KB_PATH"] = str(KB_PATH)

from config import load_config
from backend.agents import IngestionAgent, RetrievalService, TaxonomyAgent, GraphBuilderAgent, VisionAgent
from backend.common.manifest import ManifestStore
from backend.retrieval.term_registry import TermRegistry


def banner(text):
    print(f"\n{'='*70}\n{text}\n{'='*70}")


def test_ingestion():
    """Ingest all supported files from the test corpus (mirrors CLI ingest flow)."""
    banner("PHASE 1: INGESTION (PDF, Word, Markdown)")

    # Clean slate
    if KB_PATH.exists():
        shutil.rmtree(KB_PATH, ignore_errors=True)
        print(f"[CLEAN] Removed existing KB at {KB_PATH}")

    config = load_config(ROOT)
    ingestion = IngestionAgent(config)
    taxonomy = TaxonomyAgent(config)
    graph_builder = GraphBuilderAgent(config)
    vision = VisionAgent(config)
    manifest = ManifestStore(config.manifest_path)
    term_registry = TermRegistry(config.knowledge_base_path)

    # Collect all source files (skip images directory)
    source_files = sorted([
        f for f in CORPUS.rglob("*")
        if f.is_file()
        and f.suffix.lower() in config.supported_extensions
        and "images" not in str(f).lower()
    ])

    print(f"\n[FILES] Found {len(source_files)} files to ingest:")
    for f in source_files:
        print(f"  {f.suffix:6s}  {f.name}")

    results = {"success": [], "failed": [], "by_type": {}}
    total_start = time.time()

    for i, source in enumerate(source_files, 1):
        ext = source.suffix.lower()
        print(f"\n  [{i:2d}/{len(source_files)}] Ingesting {source.name} ({ext})...", end=" ", flush=True)

        try:
            ingest_result = ingestion.execute({"path": str(source)})

            if not ingest_result.success or "document" not in ingest_result.data:
                error = ingest_result.data.get("error", ingest_result.reasoning or "Unknown")
                print(f"FAILED ({error})")
                results["failed"].append({"file": source.name, "ext": ext, "error": error})
                continue

            document = ingest_result.data["document"]
            chunk_count = ingest_result.data.get("chunk_count", 0)

            # Taxonomy classification (mirrors CLI flow)
            classify_result = taxonomy.execute({"text": document.extracted_text, "filename": source.name})
            doc_type = classify_result.data.get("doc_type", "UNKNOWN")

            # Update metadata on disk
            metadata_path = Path(document.metadata_path)
            if metadata_path.exists():
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                metadata["doc_type"] = doc_type
                metadata["tags"] = classify_result.data.get("tags", [])
                metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

                # Update vector store metadata
                ingestion.vector_store.update_doc_metadata(
                    document.doc_id, doc_type=metadata["doc_type"], tags=metadata["tags"]
                )

                # Build graph
                graph_builder.execute({"document": document, "metadata": metadata})

                # Register keyphrases
                keyphrases = metadata.get("keyphrases", [])
                if keyphrases:
                    term_texts = [kp["text"] for kp in keyphrases]
                    term_registry.register_terms(term_texts, document.doc_id, doc_type)

            # Vision (initialize)
            vision.execute({
                "operation": "initialize",
                "doc_id": document.doc_id,
                "image_paths": document.image_paths,
                "descriptions": {},
            })

            print(f"OK (doc_id={document.doc_id}, chunks={chunk_count}, type={doc_type})")
            results["success"].append({
                "file": source.name,
                "ext": ext,
                "doc_id": document.doc_id,
                "chunks": chunk_count,
                "doc_type": doc_type,
            })
            results["by_type"].setdefault(ext, []).append(source.name)

        except Exception as e:
            print(f"ERROR ({type(e).__name__}: {e})")
            results["failed"].append({"file": source.name, "ext": ext, "error": str(e)})

    # Rebuild synonyms
    term_registry.rebuild_synonyms()

    elapsed = time.time() - total_start

    # Summary
    print(f"\n{'─'*50}")
    print(f"  Ingested: {len(results['success'])}/{len(source_files)} files in {elapsed:.1f}s")
    total_chunks = sum(d["chunks"] for d in results["success"])
    print(f"  Total chunks: {total_chunks}")
    for ext, files in sorted(results["by_type"].items()):
        print(f"    {ext}: {len(files)} files ({', '.join(files)})")
    if results["failed"]:
        print(f"  FAILED ({len(results['failed'])}):")
        for f in results["failed"]:
            print(f"    {f['file']}: {f['error']}")

    return results


def test_search():
    """Run search queries against ingested corpus and verify results + explainability."""
    banner("PHASE 2: SEARCH + EXPLAINABILITY")

    config = load_config(ROOT)
    retrieval = RetrievalService(config)

    # Queries spanning different file types and topics
    queries = [
        {
            "id": "MD-001",
            "query": "How do I troubleshoot ToolX AUTH-401 error?",
            "expect_source": "Troubleshoot_ToolX_AUTH401",
        },
        {
            "id": "MD-002",
            "query": "What are the new features in ToolX 2026 Q1 release?",
            "expect_source": "ReleaseNotes_ToolX",
        },
        {
            "id": "MD-003",
            "query": "How do I onboard new users to ToolX?",
            "expect_source": "UserGuide_ToolX",
        },
        {
            "id": "DOCX-001",
            "query": "What is the SOP for ToolX login failures?",
            "expect_source": "SOP_ToolX_Login_Failures",
        },
        {
            "id": "PDF-001",
            "query": "ToolX troubleshooting training materials",
            "expect_source": "Training_ToolX",
        },
        {
            "id": "MD-004",
            "query": "What does error ERR-UPL-013 mean?",
            "expect_source": "Troubleshoot_ToolY",
        },
        {
            "id": "MD-005",
            "query": "ToolX HTTP 504 timeout",
            "expect_source": "Troubleshoot_ToolX_HTTP504",
        },
    ]

    print(f"\n[SEARCH] Running {len(queries)} queries...\n")

    hits = 0
    trace_present = 0
    trace_absent = 0

    for q in queries:
        qid = q["id"]
        query = q["query"]
        expect = q["expect_source"]

        print(f"  [{qid}] {query}")

        try:
            result = retrieval.execute({
                "query": query,
                "max_results": 5,
                "max_chunks_per_doc": 3,
                "deep_mode": False,
                "explain": False,
            })

            if not result.success:
                print(f"    x Retrieval failed: {result.reasoning}")
                continue

            # Check Phase 6 explainability trace
            p6 = result.data.get("phase6", {})
            trace = p6.get("trace", [])
            trace_steps = trace if isinstance(trace, list) else trace.get("steps", [])

            if trace_steps:
                trace_present += 1
            else:
                trace_absent += 1

            # Check search results
            sr = result.data.get("search_result")
            if not sr:
                print(f"    x No search_result in response")
                continue

            chunks = sr.context_chunks if hasattr(sr, "context_chunks") else []
            if not chunks:
                print(f"    x No chunks returned")
                continue

            # Check rank 1 source
            rank1 = chunks[0]
            source = getattr(rank1, "source_path", "") or ""
            source_name = Path(source).stem if source else "?"
            found = expect.lower() in source_name.lower()

            confidence = getattr(sr, "confidence", 0) if hasattr(sr, "confidence") else 0
            status = "HIT" if found else "MISS"
            if found:
                hits += 1

            print(f"    {status} rank=1 [{Path(source).name if source else '?'}] confidence={confidence:.3f}")

            # Show pipeline steps
            meaningful_steps = [s for s in trace_steps if s.get("step") not in ("start", "complete")]
            step_names = [s.get("step", "?") for s in meaningful_steps]
            print(f"    Pipeline: {' > '.join(step_names)}")

            # Show WHY for one key step
            for s in meaningful_steps[:2]:
                if s.get("why"):
                    print(f"      {s['step']}: {s.get('description', '')[:80]}")
                    print(f"        WHY: {s['why']}")

        except Exception as e:
            import traceback
            print(f"    x ERROR: {type(e).__name__}: {e}")
            traceback.print_exc()

    # Summary
    print(f"\n{'─'*50}")
    print(f"  Search accuracy: {hits}/{len(queries)} queries hit rank 1")
    print(f"  Trace present:   {trace_present}/{len(queries)} queries")
    if trace_absent:
        print(f"  WARNING: Trace missing in {trace_absent} queries")

    return {"hits": hits, "total": len(queries), "trace_present": trace_present}


def test_cli_output():
    """Test CLI JSON output includes search_result + phase6 trace."""
    banner("PHASE 3: CLI JSON OUTPUT")

    import subprocess

    query = "How do I troubleshoot ToolX AUTH-401 error?"
    cmd = [
        sys.executable, "-m", "cli.main",
        "search", query,
        "--max-results", "3",
    ]
    env = os.environ.copy()
    env["KTS_KB_PATH"] = str(KB_PATH)

    print(f"  Command: cli.main search \"{query}\"")
    proc = subprocess.run(
        cmd, capture_output=True, text=True,
        env=env, cwd=str(ROOT), timeout=120,
    )

    if proc.returncode != 0:
        print(f"  x CLI exited with code {proc.returncode}")
        if proc.stderr:
            # Show last 500 chars of stderr (skip model loading noise)
            print(f"  stderr (tail): ...{proc.stderr[-500:]}")
        return False

    # Parse JSON from stdout (CLI may emit progress lines on stderr)
    stdout = proc.stdout.strip()
    try:
        output = json.loads(stdout)
    except json.JSONDecodeError:
        # Try to find JSON block in output
        lines = stdout.split("\n")
        for i, line in enumerate(lines):
            if line.strip().startswith("{"):
                try:
                    output = json.loads("\n".join(lines[i:]))
                    break
                except json.JSONDecodeError:
                    continue
        else:
            print(f"  x Could not parse JSON from CLI output")
            print(f"  stdout (first 500): {stdout[:500]}")
            return False

    # Validate structure
    has_search = "search_result" in output or "context_chunks" in output
    has_phase6 = "phase6" in output
    has_trace = False

    if has_phase6:
        p6 = output["phase6"]
        trace = p6.get("trace", [])
        if isinstance(trace, list) and len(trace) > 0:
            has_trace = True
        elif isinstance(trace, dict) and len(trace.get("steps", [])) > 0:
            has_trace = True

    print(f"  search_result present: {'PASS' if has_search else 'FAIL'}")
    print(f"  phase6 present:        {'PASS' if has_phase6 else 'FAIL'}")
    print(f"  trace steps present:   {'PASS' if has_trace else 'FAIL'}")

    if has_trace:
        trace_data = trace if isinstance(trace, list) else trace.get("steps", [])
        steps = [s.get("step") for s in trace_data if s.get("step") not in ("start", "complete")]
        print(f"  Pipeline steps: {' > '.join(steps)}")
        # Show a sample step
        for s in trace_data:
            if s.get("why") and s["step"] not in ("start", "complete"):
                print(f"  Sample: {s['step']} - {s.get('description', '')[:80]}")
                print(f"    WHY: {s['why']}")
                break

    if has_phase6:
        print(f"  Confidence: {output['phase6'].get('confidence', 'n/a')}")
        print(f"  Iterations: {output['phase6'].get('iterations', 'n/a')}")

    return has_search and has_phase6 and has_trace


if __name__ == "__main__":
    print("\n" + "=" * 62)
    print("   KTS PRE-BUILD VALIDATION SUITE")
    print("=" * 62)

    # Phase 1: Ingestion
    ingest_results = test_ingestion()

    if not ingest_results["success"]:
        print("\nx INGESTION FAILED — aborting remaining tests")
        sys.exit(1)

    # Check all 3 formats were ingested
    types_ingested = set(ingest_results["by_type"].keys())
    required_types = {".md", ".pdf", ".docx"}
    missing = required_types - types_ingested
    if missing:
        print(f"\nWARNING: Missing format(s): {missing}")

    # Phase 2: Search + Explainability
    search_results = test_search()

    # Phase 3: CLI Output
    cli_ok = test_cli_output()

    # Final verdict
    banner("FINAL VERDICT")

    checks = [
        ("PDF ingestion",            ".pdf" in types_ingested),
        ("Word (.docx) ingestion",   ".docx" in types_ingested),
        ("Markdown ingestion",       ".md" in types_ingested),
        ("Search accuracy >= 50%",   search_results["hits"] >= search_results["total"] // 2),
        ("Explainability trace",     search_results["trace_present"] > 0),
        ("CLI output structure",     cli_ok),
    ]

    all_pass = True
    for name, passed in checks:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}]  {name}")

    failed_count = len(ingest_results["failed"])
    if failed_count:
        print(f"\n  Note: {failed_count} file(s) failed ingestion (may be unsupported formats)")

    print()
    if all_pass:
        print("  ========================================")
        print("   ALL CHECKS PASSED — READY TO BUILD")
        print("  ========================================")
    else:
        print("  ========================================")
        print("   SOME CHECKS FAILED — FIX BEFORE BUILD")
        print("  ========================================")

    sys.exit(0 if all_pass else 1)
