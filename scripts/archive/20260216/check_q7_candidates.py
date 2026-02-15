#!/usr/bin/env python3
"""Quick Q7 candidate check for regression validation."""
import sys
import io
from config import load_config
from backend.agents import RetrievalService

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

cfg = load_config()
retrieval = RetrievalService(cfg)

query = "List all error codes for ToolX"
agent_result = retrieval.execute({"query": query, "max_results": 10})

search_result = agent_result.data["search_result"]
chunks = search_result.context_chunks

print("\n=== Q7 CANDIDATE CHECK ===")
print(f"Query: {query}")
print(f"Candidates: {len(chunks)}\n")

for i, c in enumerate(chunks[:10]):
    doc_type = c.doc_type if hasattr(c, 'doc_type') else "N/A"
    doc_id = c.doc_id if hasattr(c, 'doc_id') else "N/A"
    # Note: similarity score not in TextChunk - this is just doc_type check
    print(f"  {i+1}. doc_id={doc_id:12s}, doc_type={doc_type:15s}")

# Gate check
reference_in_top5 = any(hasattr(c, 'doc_type') and c.doc_type == "REFERENCE" for c in chunks[:5])
check_mark = "PASS" if reference_in_top5 else "FAIL"
print(f"\n[{check_mark}] GATE CHECK: REFERENCE in top-5 = {reference_in_top5}")
if not reference_in_top5:
    print("[FAIL] Q7 will fail - no REFERENCE candidates in top-5")
