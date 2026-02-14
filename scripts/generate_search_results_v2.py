"""
Generate search results for V2 queries with content field included.
This script runs all V2 golden queries and saves results with chunk content for evidence validation.
"""
import sys
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import KTSConfig
from backend.agents.retrieval_service import RetrievalService


def main():
    if len(sys.argv) < 3:
        print("Usage: python generate_search_results_v2.py <golden_queries.json> <output_path.json>")
        sys.exit(1)
    
    queries_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    
    if not queries_path.exists():
        print(f"ERROR: Queries file not found: {queries_path}")
        sys.exit(1)
    
    # Load queries
    with open(queries_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    queries = data['queries']
    
    print(f"\n===== GENERATING SEARCH RESULTS WITH CONTENT =====")
    print(f"Queries: {len(queries)}")
    print(f"Output: {output_path}\n")
    
    # Initialize retrieval service
    config = KTSConfig()
    retrieval = RetrievalService(config)
    
    # Execute queries
    results = []
    for i, query in enumerate(queries):
        query_id = query['query_id']
        query_text = query['query_text']
        
        print(f"  [{i+1}/{len(queries)}] {query_id}: {query_text[:60]}...", end='', flush=True)
        
        try:
            # Execute retrieval
            result = retrieval.execute({
                "query": query_text,
                "max_results": 5
            })
            
            if result.success:
                # Extract chunks with ALL fields including content
                # result.data['search_result'] is a SearchResult dataclass
                search_result = result.data['search_result']
                chunks = []
                for chunk in search_result.context_chunks:
                    chunks.append({
                        "chunk_id": chunk.chunk_id,
                        "doc_id": chunk.doc_id,
                        "doc_type": chunk.doc_type,  # Already normalized
                        "source_path": chunk.source_path,
                        "chunk_index": chunk.chunk_index,
                        "content": chunk.content[:500] if len(chunk.content) > 500 else chunk.content,  # Truncate for size
                        "doc_name": Path(chunk.source_path).name
                    })
                
                results.append({
                    "query_id": query_id,
                    "query_text": query_text,
                    "retrieved_chunks": chunks
                })
                print(f" ✓ ({len(chunks)} chunks)")
            else:
                results.append({
                    "query_id": query_id,
                    "query_text": query_text,
                    "error": result.reasoning,
                    "retrieved_chunks": []
                })
                print(f" ✗ Error: {result.reasoning}")
        
        except Exception as e:
            results.append({
                "query_id": query_id,
                "query_text": query_text,
                "error": str(e),
                "retrieved_chunks": []
            })
            print(f" ✗ Exception: {e}")
    
    # Save results in V2 format
    output_data = {"queries": results}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Results saved to: {output_path}")
    print(f"   Total queries: {len(results)}")
    print(f"   With chunks: {sum(1 for r in results if r['retrieved_chunks'])}")
    print(f"   Errors: {sum(1 for r in results if 'error' in r)}\n")


if __name__ == "__main__":
    main()
