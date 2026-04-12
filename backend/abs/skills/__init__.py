# backend/abs/skills/__init__.py
"""ABS skill layer — reusable functions shared across agents."""

from backend.abs.skills.cashflow_engine import run_projections
from backend.abs.skills.csv_validator import validate_csv, validate_extraction_json
from backend.abs.skills.deal_comparator import compare_deals
from backend.abs.skills.deal_setup_extractor import DealSetup, ClassSetup
from backend.abs.skills.document_classifier import classify_document, classify_all_documents
from backend.abs.skills.document_hasher import compute_content_hash, check_duplicates
from backend.abs.skills.document_tools import analyze_document
from backend.abs.skills.amendment_manager import (
    snapshot_original,
    apply_amendment,
    get_active_version,
)
from backend.abs.skills.parsers import (
    parse_section,
    get_available_parsers,
    split_into_sections,
)
from backend.abs.skills.report_generator import (
    generate_report,
    generate_governing_docs,
    generate_excel_report,
)
from backend.abs.skills.output_comparator import compare_outputs, compare_extractions
from backend.abs.skills.embedder import chunk_text, embed, embed_query, embed_and_store
from backend.abs.skills.vector_search import (
    SearchResult,
    vector_search,
    search_by_section,
    search_definitions,
    search_waterfall_rules,
    search_cross_deal,
)
from backend.abs.skills.graph_builder import (
    NODE_TYPES,
    build_graph,
    save_graph,
    load_graph,
    query_graph,
    get_neighbors,
    find_dependencies,
    find_dependents,
    detect_cycles,
    get_waterfall_order,
)

__all__ = [
    # cashflow_engine
    "run_projections",
    # csv_validator
    "validate_csv",
    "validate_extraction_json",
    # deal_comparator
    "compare_deals",
    # deal_setup_extractor
    "DealSetup",
    "ClassSetup",
    # document_classifier
    "classify_document",
    "classify_all_documents",
    # document_hasher
    "compute_content_hash",
    "check_duplicates",
    # document_tools
    "analyze_document",
    # amendment_manager
    "snapshot_original",
    "apply_amendment",
    "get_active_version",
    # parsers
    "parse_section",
    "get_available_parsers",
    "split_into_sections",
    # report_generator
    "generate_report",
    "generate_governing_docs",
    "generate_excel_report",
    # output_comparator
    "compare_outputs",
    "compare_extractions",
    # embedder (Phase 22 adapter)
    "chunk_text",
    "embed",
    "embed_query",
    "embed_and_store",
    # vector_search (Phase 22 adapter)
    "SearchResult",
    "vector_search",
    "search_by_section",
    "search_definitions",
    "search_waterfall_rules",
    "search_cross_deal",
    # graph_builder (Phase 22 adapter)
    "NODE_TYPES",
    "build_graph",
    "save_graph",
    "load_graph",
    "query_graph",
    "get_neighbors",
    "find_dependencies",
    "find_dependents",
    "detect_cycles",
    "get_waterfall_order",
]
