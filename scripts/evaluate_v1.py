
import json
import sys
from pathlib import Path
from tqdm import tqdm

# Add root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.agents.retrieval_service import RetrievalService
from config.settings import load_config

def evaluate_v1():
    config = load_config()
    service = RetrievalService(config)
    
    # Load queries
    with open('tests/golden_queries.json', 'r', encoding='utf-8') as f:
        golden = json.load(f)
    
    results = {"queries": []}
    
    print(f"Evaluating {len(golden['queries'])} V1 queries...")
    
    for q in tqdm(golden['queries']):
        query_text = q['query_text']
        # Retrieve
        result = service.execute({"query": query_text})
        search_res = result.data["search_result"]
        
        # Format chunks
        chunks = []
        for chunk in search_res.context_chunks:
             chunks.append({
                 "chunk_id": chunk.chunk_id,
                 "doc_id": chunk.doc_id,
                 "content": chunk.content,
                 "doc_type": getattr(chunk, "doc_type", "UNKNOWN"),
                 "source": getattr(chunk, "source_path", ""),
                 "score": 0.0
             })
             
        results["queries"].append({
            "query_id": q.get("query_id") or str(hash(query_text)),
            "query_text": query_text,
            "retrieved_chunks": chunks
        })
        
    output_dir = Path('tests/accuracy_tuning_output')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / 'search_results.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
        
    print(f"Results saved to {output_path}")

if __name__ == "__main__":
    evaluate_v1()
