"""
Enterprise Corpus E2E Test Runner
Ingests the enterprise corpus, runs 100 golden queries, scores results.
"""
import json
import shutil
import sys
import time
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import load_config
from backend.agents import IngestionAgent, RetrievalService, TaxonomyAgent, GraphBuilderAgent, VisionAgent
from backend.common.manifest import ManifestStore
from backend.common.models import FileInfo
from backend.vector import VectorStore
from backend.vector.embedding_provider import get_embedding_provider

# Import scoring functions
from tests.score_queries import (
    load_golden_queries,
    parse_evidence_rules,
    evaluate_evidence_on_text,
    get_chunk_text,
    normalize_text,
    extract_doc_type,
)


CORPUS_DIR = ROOT / "Knowledge Base test" / "enterprise_corpus"
GOLDEN_QUERIES_PATH = ROOT / "tests" / "golden_queries_enterprise.json"
RESULTS_PATH = ROOT / "tests" / "enterprise_test_results.json"
KB_PATH = ROOT / ".kts_enterprise_test"


def clean_kb():
    """Remove previous test knowledge base."""
    if KB_PATH.exists():
        shutil.rmtree(KB_PATH)
    print(f"[CLEAN] Knowledge base at {KB_PATH} cleared.")


def ingest_corpus():
    """Ingest all enterprise corpus documents."""
    import os
    os.environ["KTS_KB_PATH"] = str(KB_PATH)
    
    config = load_config(ROOT)
    ingestion = IngestionAgent(config)
    taxonomy = TaxonomyAgent(config)
    graph_builder = GraphBuilderAgent(config)
    vision = VisionAgent(config)
    manifest = ManifestStore(config.manifest_path)
    
    from backend.retrieval.term_registry import TermRegistry
    term_registry = TermRegistry(config.knowledge_base_path)
    
    # Collect all corpus files
    source_paths = sorted([
        f for f in CORPUS_DIR.rglob("*")
        if f.is_file() and f.suffix.lower() in config.supported_extensions
    ])
    
    print(f"[INGEST] Found {len(source_paths)} files to ingest")
    ingested = []
    
    for source in source_paths:
        print(f"  Ingesting {source.name}...", end=" ")
        result = ingestion.execute({"path": str(source)})
        
        if not result.success or "document" not in result.data:
            print(f"FAILED: {result.data.get('error', 'Unknown')}")
            continue
        
        document = result.data["document"]
        
        # Classify document type
        classify_result = taxonomy.execute({"text": document.extracted_text, "filename": source.name})
        
        # Update metadata
        metadata_path = Path(document.metadata_path)
        metadata = {}
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["doc_type"] = classify_result.data.get("doc_type", "UNKNOWN")
            metadata["tags"] = classify_result.data.get("tags", [])
            metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            
            ingestion.vector_store.update_doc_metadata(
                document.doc_id, 
                doc_type=metadata["doc_type"], 
                tags=metadata["tags"]
            )
            
            graph_builder.execute({"document": document, "metadata": metadata})
            
            keyphrases = metadata.get("keyphrases", [])
            if keyphrases:
                term_texts = [kp["text"] for kp in keyphrases]
                term_registry.register_terms(term_texts, document.doc_id, metadata.get("doc_type", "UNKNOWN"))
        
        vision.execute({
            "operation": "initialize", 
            "doc_id": document.doc_id,
            "image_paths": document.image_paths, 
            "descriptions": {}
        })
        
        chunk_count = result.data.get("chunk_count", 0)
        doc_type = metadata.get("doc_type", "UNKNOWN")
        print(f"OK ({chunk_count} chunks, type={doc_type})")
        
        ingested.append({
            "doc_id": document.doc_id,
            "path": str(source),
            "filename": source.name,
            "chunk_count": chunk_count,
            "doc_type": doc_type,
        })
    
    # Rebuild synonyms
    term_registry.rebuild_synonyms()
    
    print(f"\n[INGEST] Complete: {len(ingested)} documents, "
          f"{sum(d['chunk_count'] for d in ingested)} total chunks")
    return ingested


def run_queries():
    """Run all golden queries and collect results."""
    import os
    os.environ["KTS_KB_PATH"] = str(KB_PATH)
    
    config = load_config(ROOT)
    retrieval = RetrievalService(config)
    
    with open(GOLDEN_QUERIES_PATH, "r", encoding="utf-8") as f:
        golden_data = json.load(f)
    
    queries = golden_data["queries"]
    print(f"\n[SEARCH] Running {len(queries)} queries...")
    
    results = []
    for i, gq in enumerate(queries, 1):
        query_text = gq["query_text"]
        query_id = gq["query_id"]
        
        print(f"  [{i:3d}/100] {query_id}: {query_text[:60]}...", end=" ")
        
        t0 = time.time()
        result = retrieval.execute({
            "query": query_text,
            "max_results": 5,
            "max_chunks_per_doc": 3,
            "deep_mode": False,
            "explain": False,
        })
        elapsed = time.time() - t0
        
        if not result.success:
            print(f"FAILED ({elapsed:.1f}s)")
            results.append({
                "query_id": query_id,
                "query_text": query_text,
                "success": False,
                "error": str(result.data.get("error", "Unknown")),
                "elapsed_ms": int(elapsed * 1000),
                "chunks": [],
            })
            continue
        
        search_result = result.data.get("search_result")
        chunks_raw = search_result.context_chunks if search_result else []
        
        # Convert TextChunk dataclass to dict for evidence evaluation
        chunks = []
        for tc in chunks_raw:
            chunks.append({
                "content": tc.content,
                "chunk_id": tc.chunk_id,
                "doc_id": tc.doc_id,
                "doc_type": tc.doc_type,
                "source_path": tc.source_path,
            })
        
        # SearchResult.confidence is the overall retrieval confidence (0-1)
        # Per-chunk scores are not exposed on TextChunk; use overall confidence
        confidence = search_result.confidence if search_result else 0.0
        
        # Evaluate evidence
        evidence_rules = parse_evidence_rules(gq)
        
        top1_text = ""
        top1_score = 0.0
        top1_doc_type = "UNKNOWN"
        evidence_found = False
        matched_rank = None
        
        for rank, chunk in enumerate(chunks[:5], 1):
            chunk_text, _ = get_chunk_text(chunk)
            eval_result = evaluate_evidence_on_text(evidence_rules, chunk_text)
            
            if rank == 1:
                top1_text = chunk_text[:200]
                top1_score = confidence
                top1_doc_type = chunk.get("doc_type", "UNKNOWN")
            
            if eval_result["chunk_satisfies"] and matched_rank is None:
                evidence_found = True
                matched_rank = rank
        
        status = "HIT" if evidence_found and matched_rank == 1 else ("PARTIAL" if evidence_found else "MISS")
        print(f"{status} (rank={matched_rank}, score={top1_score:.3f}, {elapsed:.1f}s)")
        
        results.append({
            "query_id": query_id,
            "query_text": query_text,
            "success": True,
            "elapsed_ms": int(elapsed * 1000),
            "top1_score": top1_score,
            "top1_doc_type": top1_doc_type,
            "top1_excerpt": top1_text,
            "evidence_found": evidence_found,
            "matched_rank": matched_rank,
            "chunk_count": len(chunks),
            "confidence": confidence,
            "chunks": [
                {
                    "rank": r + 1,
                    "doc_type": c.get("doc_type", "UNKNOWN"),
                    "source": c.get("source_path", ""),
                    "chunk_id": c.get("chunk_id", ""),
                }
                for r, c in enumerate(chunks[:5])
            ],
        })
    
    return results


def score_results(results):
    """Score and summarize the test results."""
    total = len(results)
    successful = [r for r in results if r.get("success")]
    
    top1_hits = [r for r in successful if r.get("evidence_found") and r.get("matched_rank") == 1]
    top3_hits = [r for r in successful if r.get("evidence_found") and r.get("matched_rank") is not None and r.get("matched_rank") <= 3]
    top5_hits = [r for r in successful if r.get("evidence_found")]
    misses = [r for r in successful if not r.get("evidence_found")]
    
    # Split by tune/holdout
    with open(GOLDEN_QUERIES_PATH, "r", encoding="utf-8") as f:
        golden_data = json.load(f)
    split_map = {q["query_id"]: q.get("split", "tune") for q in golden_data["queries"]}
    
    tune_results = [r for r in successful if split_map.get(r["query_id"]) == "tune"]
    holdout_results = [r for r in successful if split_map.get(r["query_id"]) == "holdout"]
    
    tune_top1 = sum(1 for r in tune_results if r.get("evidence_found") and r.get("matched_rank") == 1)
    holdout_top1 = sum(1 for r in holdout_results if r.get("evidence_found") and r.get("matched_rank") == 1)
    
    avg_score_hits = sum(r["top1_score"] for r in top1_hits) / len(top1_hits) if top1_hits else 0
    avg_latency = sum(r["elapsed_ms"] for r in successful) / len(successful) if successful else 0
    
    summary = {
        "total_queries": total,
        "successful_queries": len(successful),
        "top1_accuracy": len(top1_hits) / len(successful) if successful else 0,
        "top3_accuracy": len(top3_hits) / len(successful) if successful else 0,
        "top5_accuracy": len(top5_hits) / len(successful) if successful else 0,
        "top1_hits": len(top1_hits),
        "top3_hits": len(top3_hits),
        "top5_hits": len(top5_hits),
        "misses": len(misses),
        "avg_top1_score": avg_score_hits,
        "avg_latency_ms": avg_latency,
        "tune_split": {
            "total": len(tune_results),
            "top1_hits": tune_top1,
            "top1_accuracy": tune_top1 / len(tune_results) if tune_results else 0,
        },
        "holdout_split": {
            "total": len(holdout_results),
            "top1_hits": holdout_top1,
            "top1_accuracy": holdout_top1 / len(holdout_results) if holdout_results else 0,
        },
    }
    
    # Identify misses for diagnostic
    miss_details = []
    for r in misses:
        miss_details.append({
            "query_id": r["query_id"],
            "query_text": r["query_text"],
            "top1_score": r.get("top1_score", 0),
            "top1_doc_type": r.get("top1_doc_type", "UNKNOWN"),
        })
    
    # Partial hits (evidence found but not rank 1)
    partial_details = []
    for r in successful:
        if r.get("evidence_found") and r.get("matched_rank") and r["matched_rank"] > 1:
            partial_details.append({
                "query_id": r["query_id"],
                "query_text": r["query_text"],
                "matched_rank": r["matched_rank"],
                "top1_score": r.get("top1_score", 0),
            })
    
    return summary, miss_details, partial_details


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Enterprise Corpus E2E Test")
    parser.add_argument("--skip-ingest", action="store_true",
                        help="Skip ingestion if KB already exists")
    args = parser.parse_args()
    
    print("=" * 70)
    print("ENTERPRISE CORPUS E2E TEST")
    print("=" * 70)
    
    ingested = []
    if args.skip_ingest and KB_PATH.exists():
        print(f"\n[SKIP] Knowledge base already exists at {KB_PATH}")
    else:
        # Step 1: Clean
        clean_kb()
        
        # Step 2: Ingest
        print("\n" + "=" * 70)
        print("PHASE 1: INGESTION")
        print("=" * 70)
        ingested = ingest_corpus()
    
    # Step 3: Run queries
    print("\n" + "=" * 70)
    print("PHASE 2: RETRIEVAL")
    print("=" * 70)
    results = run_queries()
    
    # Step 4: Score
    print("\n" + "=" * 70)
    print("PHASE 3: SCORING")
    print("=" * 70)
    summary, misses, partials = score_results(results)
    
    # Print summary
    print(f"\n{'='*50}")
    print(f"  TOP-1 ACCURACY: {summary['top1_accuracy']:.1%} ({summary['top1_hits']}/{summary['successful_queries']})")
    print(f"  TOP-3 ACCURACY: {summary['top3_accuracy']:.1%} ({summary['top3_hits']}/{summary['successful_queries']})")
    print(f"  TOP-5 ACCURACY: {summary['top5_accuracy']:.1%} ({summary['top5_hits']}/{summary['successful_queries']})")
    print(f"  AVG TOP-1 SCORE: {summary['avg_top1_score']:.4f}")
    print(f"  AVG LATENCY: {summary['avg_latency_ms']:.0f}ms")
    print(f"{'='*50}")
    print(f"  TUNE SPLIT: {summary['tune_split']['top1_accuracy']:.1%} ({summary['tune_split']['top1_hits']}/{summary['tune_split']['total']})")
    print(f"  HOLDOUT SPLIT: {summary['holdout_split']['top1_accuracy']:.1%} ({summary['holdout_split']['top1_hits']}/{summary['holdout_split']['total']})")
    print(f"{'='*50}")
    
    if misses:
        print(f"\n  MISSES ({len(misses)}):")
        for m in misses:
            print(f"    {m['query_id']}: {m['query_text'][:60]}... (score={m['top1_score']:.3f})")
    
    if partials:
        print(f"\n  PARTIAL HITS ({len(partials)}):")
        for p in partials:
            print(f"    {p['query_id']}: rank={p['matched_rank']}, {p['query_text'][:50]}...")
    
    # Save full results
    output = {
        "summary": summary,
        "misses": misses,
        "partial_hits": partials,
        "ingested_docs": ingested,
        "results": results,
    }
    RESULTS_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\n[SAVED] Full results → {RESULTS_PATH}")


if __name__ == "__main__":
    main()
