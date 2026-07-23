"""
ABS service layer — stateless, async integration boundary.

Public API::

    from backend.abs.services import (
        ABSService, ServiceContext, ServiceResult,
        LLMClient, CallableLLMClient, StubLLMClient, LLMResult,
        DealService,
    )
"""

from __future__ import annotations

from backend.abs.services.base import ABSService, ServiceContext, ServiceResult
from backend.abs.services.deal_service import DealService
from backend.abs.services.definition_service import DefinitionService
from backend.abs.services.embedding import Embedder, HashEmbedder, cosine, get_default_embedder
from backend.abs.services.governance_service import GovernanceService
from backend.abs.services.governing_doc_service import GoverningDocService
from backend.abs.services.ingestion_service import IngestionService
from backend.abs.services.json_utils import extract_items, parse_json_lenient
from backend.abs.services.model_service import ModelService
from backend.abs.services.model_run_service import ModelRunService
from backend.abs.services.llm_client import (
    CallableLLMClient,
    LLMClient,
    LLMResult,
    StubLLMClient,
)
from backend.abs.services.pdf_extract import ExtractedDoc, char_to_page, extracted_from_pages
from backend.abs.services.qa_service import QAService, capitalized_terms
from backend.abs.services.regeneration_service import RegenerationService
from backend.abs.services.reporting_service import ReportingService
from backend.abs.services.retrieval_service import RetrievalService
from backend.abs.services.sep_profiles import CORE_PROFILES, SEPProfile, get_profile
from backend.abs.services.sep_service import SEPService

__all__ = [
    "ABSService",
    "ServiceContext",
    "ServiceResult",
    "LLMClient",
    "LLMResult",
    "CallableLLMClient",
    "StubLLMClient",
    "DealService",
    "IngestionService",
    "DefinitionService",
    "GoverningDocService",
    "SEPService",
    "QAService",
    "ModelService",
    "ModelRunService",
    "ReportingService",
    "RetrievalService",
    "GovernanceService",
    "RegenerationService",
    "Embedder",
    "HashEmbedder",
    "get_default_embedder",
    "cosine",
    "capitalized_terms",
    "SEPProfile",
    "CORE_PROFILES",
    "get_profile",
    "parse_json_lenient",
    "extract_items",
    "ExtractedDoc",
    "char_to_page",
    "extracted_from_pages",
]
