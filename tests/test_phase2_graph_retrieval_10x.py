from __future__ import annotations

import json
from pathlib import Path

from backend.agents import GraphBuilderAgent, IngestionAgent, RetrievalService
from backend.graph import GraphQueries, GraphStore
from config import load_config


def test_graph_and_retrieval_10_scenarios(tmp_path: Path):
    cfg = load_config()
    cfg.knowledge_base_path = str(tmp_path / "kb")
    cfg.graph_path = str(tmp_path / "kb" / "graph" / "knowledge_graph.json")
    cfg.chroma_persist_dir = str(tmp_path / "kb" / "vectors" / "chroma")

    ingest = IngestionAgent(cfg)
    builder = GraphBuilderAgent(cfg)
    retrieve = RetrievalService(cfg)

    src = tmp_path / "doc.md"
    src.write_text("# ToolX onboarding\nToolX deployment support incident", encoding="utf-8")

    ing = ingest.execute({"path": str(src)})
    doc = ing.data["document"]
    mpath = Path(doc.metadata_path)
    meta = json.loads(mpath.read_text(encoding="utf-8"))
    meta["doc_type"] = "SOP"
    meta["tools"] = ["ToolX"]
    meta["topics"] = ["onboarding"]
    meta["processes"] = ["DeployProcess"]
    mpath.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    ingest.vector_store.update_doc_metadata(doc.doc_id, doc_type="SOP", tags=["onboarding"])
    builder.execute({"document": doc, "metadata": meta})

    graph = GraphStore(cfg.graph_path).load()

    r1 = retrieve.execute({"query": "ToolX onboarding"})
    r2 = retrieve.execute({"query": "deployment", "doc_type_filter": "SOP"})
    r3 = retrieve.execute({"query": "incident", "tool_filter": "ToolX"})
    r4 = retrieve.execute({"query": "unknown token zzqq"})

    docs_tool = GraphQueries.find_docs_for_tool(graph, "ToolX")
    docs_topic = GraphQueries.find_docs_for_topic(graph, "onboarding")
    procs_tool = GraphQueries.find_processes_for_tool(graph, "ToolX")
    docs_proc = GraphQueries.find_docs_for_process(graph, "DeployProcess")
    stats = GraphQueries.doc_stats(graph)
    r10 = retrieve.execute({"query": "How to deployment support"})

    assert r1.success and r1.data["search_result"].context_chunks
    assert r2.success
    assert r3.success
    assert r4.data["search_result"].confidence <= 0.4
    assert len(docs_tool) >= 1
    assert len(docs_topic) >= 1
    assert len(procs_tool) >= 1
    assert len(docs_proc) >= 1
    assert stats["documents"] >= 1
    assert r10.success
