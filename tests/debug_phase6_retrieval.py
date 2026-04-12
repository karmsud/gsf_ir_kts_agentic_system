#!/usr/bin/env python
"""Debug script to trace Phase 6 retrieval pipeline end-to-end."""

import logging
import sys
from pathlib import Path

# Configure detailed logging BEFORE any imports
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s %(name)s: %(message)s',
    stream=sys.stdout
)

# Suppress noisy third-party logs
for logger_name in ['chromadb', 'urllib3', 'httpcore', 'onnxruntime', 'httpx', 
                    'sentence_transformers', 'transformers', 'filelock']:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

# Now import our code
from config.settings import load_config
from backend.agents.retrieval_service import RetrievalService


def main():
    print('=' * 70)
    print('PHASE 6 RETRIEVAL DEBUG TEST')
    print('=' * 70)
    
    kb_path = Path('C:/Users/Karmsud/Projects/source_1/.kts')
    cfg = load_config(kb_path)
    
    print(f'\nConfiguration:')
    print(f'  KB Path: {cfg.knowledge_base_path}')
    print(f'  Phase6 Enabled: {cfg.phase6_enabled}')
    print(f'  Phase6 Chroma Dir: {cfg.phase6_chroma_dir}')
    print(f'  Phase6 Min Confidence: {cfg.phase6_min_confidence}')
    print(f'  Phase6 Max Iterations: {cfg.phase6_max_iterations}')
    print()
    
    # Verify dual store has data
    from backend.vector.dual_vector_store import DualVectorStore
    store = DualVectorStore(cfg.phase6_chroma_dir)
    print(f'Dual Store: {store.item_collection.count()} items, {store.section_collection.count()} sections')
    print()
    
    if store.item_collection.count() == 0:
        print('ERROR: Dual vector store is empty! Run debug_phase6_ingestion.py first.')
        return
    
    # Test query
    test_query = "allocation of losses"
    print(f'Test Query: "{test_query}"')
    print('=' * 70)
    
    retrieval = RetrievalService(cfg)
    
    result = retrieval.execute({
        'query': test_query,
        'max_results': 5,
        'deep_mode': True,
    })
    
    print('=' * 70)
    print('\nRESULT SUMMARY:')
    print(f'  Success: {result.success}')
    print(f'  Confidence: {result.confidence}')
    print(f'  Reasoning: {result.reasoning}')
    
    # Check if Phase 6 was used
    phase6_info = result.data.get('phase6')
    if phase6_info:
        print()
        print('PHASE 6 INFO:')
        print(f'  Enabled: {phase6_info.get("enabled")}')
        print(f'  Iterations: {phase6_info.get("iterations")}')
        print(f'  Confidence: {phase6_info.get("confidence")}')
        
        trace = phase6_info.get('trace', {})
        steps = trace.get('steps', [])
        print(f'\n  Trace Steps ({len(steps)}):')
        for step in steps:
            name = step.get('step_name', '?')
            msg = step.get('message', '')[:60]
            print(f'    - [{name}] {msg}...')
    else:
        print()
        print('WARNING: Phase 6 was NOT used! Falling back to legacy pipeline.')
    
    # Show results
    search_result = result.data.get('search_result')
    if search_result:
        chunks = search_result.context_chunks
        print()
        print(f'RESULTS ({len(chunks)} chunks):')
        for i, chunk in enumerate(chunks[:5]):
            print(f'\n  [{i+1}] {chunk.doc_type}')
            print(f'      ID: {chunk.chunk_id}')
            print(f'      Content: {chunk.content[:100]}...')
    
    # Also test direct Phase 6 orchestrator
    print()
    print('=' * 70)
    print('DIRECT ORCHESTRATOR TEST')
    print('=' * 70)
    
    from backend.common.config_phase6 import Phase6Config
    from backend.retrieval.iterative_orchestrator import IterativeOrchestrator
    from backend.graph.persistence import GraphStore
    
    phase6_cfg = Phase6Config(
        enabled=True,
        chroma_dir=cfg.phase6_chroma_dir,
        max_iterations=5,
        min_confidence=0.85,
        result_threshold=0.70,
        verbose_logging=True,
    )
    
    gs = GraphStore(cfg.graph_path)
    graph = gs.load()
    
    print(f'Graph nodes: {graph.number_of_nodes()}')
    print(f'Graph edges: {graph.number_of_edges()}')
    
    orchestrator = IterativeOrchestrator(store, graph, phase6_cfg, kb_path=str(kb_path))
    
    print(f'\nRunning orchestrator.retrieve("{test_query}")...')
    orch_result = orchestrator.retrieve(test_query, max_results=5)
    
    print(f'\nOrchestrator Results:')
    print(f'  Iterations: {orch_result.get("iterations")}')
    print(f'  Confidence: {orch_result.get("confidence")}')
    print(f'  Results: {len(orch_result.get("results", []))}')
    
    trace = orch_result.get('trace', {})
    steps = trace.get('steps', [])
    print(f'\n  Trace Steps ({len(steps)}):')
    for step in steps:
        name = step.get('step_name', '?')
        msg = step.get('message', '')
        why = step.get('why', '')
        detail = step.get('detail', {})
        print(f'\n    [{name}]')
        print(f'      {msg}')
        if why:
            print(f'      WHY: {why}')
        if detail:
            for k, v in list(detail.items())[:3]:
                print(f'      {k}: {v}')
    
    print()
    print('Top Results:')
    for i, r in enumerate(orch_result.get('results', [])[:3]):
        print(f'\n  [{i+1}] Score: {r.get("hybrid_score", r.get("similarity", 0)):.4f}')
        print(f'      Type: {r.get("item_type", r.get("type", "?"))}')
        print(f'      Section: {r.get("section_number", "?")}')
        text = r.get('text', '')[:100]
        print(f'      Text: {text}...')


if __name__ == '__main__':
    main()
