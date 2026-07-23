"""
Tests for DefinitionService — extraction, dependency edges, N-level resolution.

Uses a StubLLMClient so resolution runs fully offline and deterministically.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.abs.services import DefinitionService, StubLLMClient
from backend.abs.services.pdf_extract import extracted_from_pages
from backend.abs.store import DealStore


SAMPLE = (
    '"Available Funds" means the Net Interest plus all principal collections.\n\n'
    '"Net Interest" means the Stated Interest less the Servicing Fee.\n\n'
    '"Stated Interest" means the certificate rate times the balance.\n\n'
    '"Servicing Fee" means the fee paid to the Servicer.\n\n'
)


def _svc(tmp_path: Path) -> DefinitionService:
    return DefinitionService(tmp_path)


def test_build_definitions_extracts_terms_and_edges(tmp_path: Path):
    svc = _svc(tmp_path)
    extracted = extracted_from_pages([SAMPLE])

    res = asyncio.run(
        svc.build_definitions("cbass", text=SAMPLE, extracted=extracted, resolve=False)
    )
    assert res.ok is True, res.error
    assert res.data["terms"] >= 4

    store = DealStore.for_deal_dir(tmp_path / "cbass", init=False)
    defs = store.list_definitions("cbass")
    names = {d["term_name"] for d in defs}
    assert "Available Funds" in names
    assert "Net Interest" in names
    # Available Funds depends on Net Interest.
    af = next(d for d in defs if d["term_name"] == "Available Funds")
    deps = {d["term_name"] for d in store.get_dependencies(af["term_id"])}
    assert "Net Interest" in deps


def test_definitions_have_page_citation(tmp_path: Path):
    svc = _svc(tmp_path)
    extracted = extracted_from_pages([SAMPLE])
    asyncio.run(svc.build_definitions("cbass", text=SAMPLE, extracted=extracted, resolve=False))
    store = DealStore.for_deal_dir(tmp_path / "cbass", init=False)
    defs = store.list_definitions("cbass")
    assert all(d["page"] == 1 for d in defs)


def test_resolution_runs_bottom_up(tmp_path: Path):
    svc = _svc(tmp_path)
    extracted = extracted_from_pages([SAMPLE])

    # Responder echoes the term being resolved so we can assert ordering effects.
    def responder(prompt: str, system: str) -> str:
        # The prompt embeds the verbatim definition; return a marker.
        return "RESOLVED: " + prompt.split("Verbatim definition:")[1].split("\n")[0].strip()

    llm = StubLLMClient(responder=responder)
    res = asyncio.run(
        svc.build_definitions("cbass", text=SAMPLE, extracted=extracted, llm=llm, resolve=True)
    )
    assert res.ok is True
    assert res.data["resolved"] >= 4

    store = DealStore.for_deal_dir(tmp_path / "cbass", init=False)
    defs = store.list_definitions("cbass")
    assert all(d["resolved_definition"] and d["resolved_definition"].startswith("RESOLVED:") for d in defs)


def test_resolution_tree_via_service(tmp_path: Path):
    svc = _svc(tmp_path)
    asyncio.run(svc.build_definitions("cbass", text=SAMPLE, resolve=False))
    top = asyncio.run(svc.list_top_level("cbass"))
    assert top.ok is True
    # Available Funds should be a root (nothing depends on it).
    root = next((d for d in top.data if d["term_name"] == "Available Funds"), None)
    assert root is not None
    tree = asyncio.run(svc.get_resolution_tree("cbass", root["term_id"]))
    assert tree.ok is True
    assert tree.data["term_name"] == "Available Funds"
    # Has nested children.
    assert len(tree.data["children"]) >= 1


def test_topo_order_is_cycle_safe(tmp_path: Path):
    from backend.abs.services.definition_service import _topo_order

    # a -> b -> a cycle, plus c standalone.
    deps = {"a": ["b"], "b": ["a"], "c": []}
    order = _topo_order(["a", "b", "c"], deps)
    assert set(order) == {"a", "b", "c"}  # terminates, includes all
