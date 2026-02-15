#!/usr/bin/env python3
"""Analyze evidence failures for V2 queries"""

import json
import sys
from pathlib import Path

def main():
    # Load golden queries
    with open('tests/golden_queries_v2.json', 'r', encoding='utf-8') as f:
        golden_data = json.load(f)
        golden_queries = {q['query_id']: q for q in golden_data['queries']}
    
    # Load search results
    with open('tests/accuracy_tuning_output_v2/search_results.json', 'r', encoding='utf-8') as f:
        results_data = json.load(f)
        search_results = {r['query_id']: r for r in results_data['queries']}
    
    # Load accuracy scores
    with open('tests/accuracy_tuning_output_v2/accuracy_scores.json', 'r', encoding='utf-8') as f:
        scores = json.load(f)
    
    # Find all evidence failures
    failures = [s for s in scores['detailed_scores'] if not s['evidence_found']]
    
    print("=" * 80)
    print(f"EVIDENCE FAILURES REPORT - V2 CORPUS")
    print("=" * 80)
    print(f"\nTotal Evidence Failures: {len(failures)}/50 queries")
    print(f"Evidence Found Rate: {scores['metrics']['overall']['evidence_accuracy']:.1f}%\n")
    
    for idx, failure in enumerate(failures, 1):
        qid = failure['query_id']
        golden = golden_queries.get(qid, {})
        result = search_results.get(qid, {})
        
        print(f"\n{'=' * 80}")
        print(f"FAILURE {idx}: {qid}")
        print(f"{'=' * 80}")
        print(f"Query: {golden.get('query_text', 'N/A')}")
        print(f"\nExpected doc_types: {', '.join(golden.get('expected_doc_types', [])[:3])}")
        print(f"Must_include_terms: {golden.get('must_include_terms', [])}")
        
        chunks = result.get('retrieved_chunks', [])
        print(f"\nRetrieved: {len(chunks)} chunks")
        print(f"Top-1 doc_type: {failure.get('top1_doc_type', 'N/A')}")
        print(f"Top-3 doc_types: {failure.get('top3_doc_types', [])}")
        
        # Check content for must_include_terms
        must_terms = golden.get('must_include_terms', [])
        print(f"\n--- TOP-3 CHUNK CONTENT ANALYSIS ---")
        
        for i, chunk in enumerate(chunks[:3], 1):
            content = chunk.get('content', '')
            doc_name = chunk.get('doc_name', 'N/A')
            doc_type = chunk.get('doc_type', 'N/A')
            
            print(f"\n[Chunk {i}]")
            print(f"  doc_name: {doc_name}")
            print(f"  doc_type: {doc_type}")
            print(f"  content_length: {len(content)} chars")
            print(f"  content_preview: {content[:200]}...")
            
            # Case-insensitive term matching
            content_lower = content.lower()
            found_terms = []
            for term in must_terms:
                if term.lower() in content_lower:
                    found_terms.append(term)
            
            if found_terms:
                print(f"  ✓ FOUND TERMS (case-insensitive): {found_terms}")
            else:
                print(f"  ✗ MISSING ALL TERMS: {must_terms}")
        
        # Classify failure
        print(f"\n--- FAILURE CLASSIFICATION ---")
        
        # Check if ANY chunk in top-3 has the terms
        any_chunk_has_terms = False
        for chunk in chunks[:3]:
            content_lower = chunk.get('content', '').lower()
            for term in must_terms:
                if term.lower() in content_lower:
                    any_chunk_has_terms = True
                    break
            if any_chunk_has_terms:
                break
        
        if any_chunk_has_terms:
            print("TYPE: Evidence exists in top-3 but scorer didn't match (case/format issue)")
        elif len(chunks) > 0 and len(chunks[0].get('content', '')) >= 490:
            print("TYPE: Content truncated at 500 chars - evidence may be beyond cutoff")
        elif failure.get('top1_doc_type') in golden.get('expected_doc_types', [])[:3]:
            print("TYPE: Correct doc_type but wrong chunk selected (chunking/ranking issue)")
        else:
            print("TYPE: Wrong document retrieved (retrieval/ranking issue)")
    
    print("\n" + "=" * 80)
    print("END OF REPORT")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
