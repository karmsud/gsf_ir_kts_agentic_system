import networkx as nx

from backend.retrieval.term_resolver import TermResolver, should_activate_resolver


def _build_term_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node("defterm:certificateholder", name="Certificateholder", defined_text="Any Person holding a Certificate")
    graph.add_node("defterm:person", name="Person", defined_text="An individual or entity")
    graph.add_edge("defterm:certificateholder", "defterm:person", type="REFERS_TO")
    return graph


def test_should_not_activate_resolver_for_generic_regime():
    graph = _build_term_graph()
    activate, reason = should_activate_resolver(
        query="What is Release Window",
        intent="concept",
        corpus_regime="GENERIC_GUIDE",
        initial_results=[],
        term_graph=graph,
    )
    assert activate is False
    assert "GENERIC" in reason


def test_should_activate_for_definitional_title_case_match():
    graph = _build_term_graph()
    activate, reason = should_activate_resolver(
        query="What is Certificateholder",
        intent="definition",
        corpus_regime="GOVERNING_DOC_LEGAL",
        initial_results=[],
        term_graph=graph,
    )
    assert activate is True
    assert "title_case_match" in reason or "intent=" in reason


def test_should_activate_from_high_confidence_legal_chunk_metadata():
    graph = _build_term_graph()
    activate, reason = should_activate_resolver(
        query="Certificateholder meaning",
        intent="general",
        corpus_regime="MIXED",
        initial_results=[
            {
                "score": 0.82,
                "metadata": {
                    "doc_regime": "GOVERNING_DOC_LEGAL",
                    "defterm_ref": ["certificateholder"],
                },
            }
        ],
        term_graph=graph,
    )
    assert activate is True
    assert "high_conf_legal_chunks" in reason


def test_term_resolver_handles_cycles_without_infinite_loop():
    graph = nx.DiGraph()
    graph.add_node("defterm:a", name="A", defined_text="A means B")
    graph.add_node("defterm:b", name="B", defined_text="B means A")
    graph.add_edge("defterm:a", "defterm:b", type="REFERS_TO")
    graph.add_edge("defterm:b", "defterm:a", type="REFERS_TO")

    resolver = TermResolver(max_depth=5, max_token_budget=1000)
    resolution = resolver.resolve_term("A", graph)

    assert "A" in resolution.closure
    assert "B" in resolution.closure
    assert len(resolution.cycles_detected) >= 1
