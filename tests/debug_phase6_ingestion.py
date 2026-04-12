#!/usr/bin/env python
"""Debug script to trace Phase 6 ingestion pipeline end-to-end."""

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
from backend.agents.ingestion_agent import IngestionAgent


def main():
    print('=' * 70)
    print('PHASE 6 INGESTION DEBUG TEST')
    print('=' * 70)
    
    kb_path = Path('C:/Users/Karmsud/Projects/source_1/.kts')
    source_path = Path('C:/Users/Karmsud/Projects/source_1')
    
    # Ensure KB directory exists
    kb_path.mkdir(parents=True, exist_ok=True)
    
    cfg = load_config(kb_path)
    
    print(f'\nConfiguration:')
    print(f'  KB Path: {cfg.knowledge_base_path}')
    print(f'  Phase6 Enabled: {cfg.phase6_enabled}')
    print(f'  Phase6 Chroma Dir: {cfg.phase6_chroma_dir}')
    print(f'  Phase6 Verbose Logging: {cfg.phase6_verbose_logging}')
    print()
    
    agent = IngestionAgent(cfg)
    
    # Find the PSA file
    psa_files = list(source_path.glob('*.doc'))
    if not psa_files:
        print('ERROR: No .doc files found in source_1')
        return
    
    psa_file = psa_files[0]
    print(f'Ingesting: {psa_file.name}')
    print('=' * 70)
    
    result = agent.execute({'path': str(psa_file)})
    
    print('=' * 70)
    print('\nRESULT SUMMARY:')
    print(f'  Success: {result.success}')
    print(f'  Confidence: {result.confidence}')
    if result.data:
        print(f'  Chunk count: {result.data.get("chunk_count", 0)}')
        print(f'  Word count: {result.data.get("word_count", 0)}')
        doc = result.data.get("document")
        if doc:
            print(f'  Doc ID: {doc.doc_id}')
    print(f'  Reasoning: {result.reasoning}')
    
    # Now verify Phase 6 artifacts were created
    print()
    print('=' * 70)
    print('VERIFYING PHASE 6 ARTIFACTS')
    print('=' * 70)
    
    # Check dual vector store
    from backend.vector.dual_vector_store import DualVectorStore
    chroma_dir = cfg.phase6_chroma_dir
    print(f'\nDual Vector Store ({chroma_dir}):')
    
    try:
        store = DualVectorStore(chroma_dir)
        item_count = store.item_collection.count()
        section_count = store.section_collection.count()
        print(f'  Items: {item_count}')
        print(f'  Sections: {section_count}')
        
        if item_count > 0:
            print('\n  Sample items:')
            sample = store.item_collection.peek(3)
            for i, (doc, meta) in enumerate(zip(sample.get('documents', []), sample.get('metadatas', []))):
                print(f'    [{i}] {meta.get("item_type", "?")} - {doc[:80]}...')
                
        if section_count > 0:
            print('\n  Sample sections:')
            sample = store.section_collection.peek(3)
            for i, (doc, meta) in enumerate(zip(sample.get('documents', []), sample.get('metadatas', []))):
                print(f'    [{i}] {meta.get("section_heading", "?")} - {doc[:60]}...')
    except Exception as e:
        print(f'  ERROR: {e}')
    
    # Check graph
    from backend.graph.persistence import GraphStore
    print(f'\nGraph ({cfg.graph_path}):')
    
    try:
        gs = GraphStore(cfg.graph_path)
        graph = gs.load()
        print(f'  Total nodes: {graph.number_of_nodes()}')
        print(f'  Total edges: {graph.number_of_edges()}')
        
        # Count node types
        node_types = {}
        for node, data in graph.nodes(data=True):
            ntype = data.get('type', 'UNKNOWN')
            node_types[ntype] = node_types.get(ntype, 0) + 1
        
        print('  Node types:')
        for ntype, count in sorted(node_types.items(), key=lambda x: -x[1]):
            print(f'    {ntype}: {count}')
    except Exception as e:
        print(f'  ERROR: {e}')


if __name__ == '__main__':
    main()
