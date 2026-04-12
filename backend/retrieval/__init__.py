from .term_resolver import (
    ResolutionCitation,
    TermResolution,
    TermResolver,
    extract_title_case_phrases,
    should_activate_resolver,
)
from .evidence_matcher import (
    EvidenceMatch,
    EvidenceMatcher,
    ProvenanceLedger,
    ProvenanceError,
    ValidationResult,
    validate_strict_mode,
)
from .acronym_resolver import AcronymResolver
from .query_expander import QueryExpander
from .cross_encoder import rerank as cross_encoder_rerank, score_pairs as cross_encoder_score_pairs
from .term_registry import TermRegistry
from .confidence_scorer import ConfidenceScorer, ConfidenceTier, ConfidenceResult
from .gap_detector import GapDetector, GapResult, extract_entities
from .hyde import HyDEProcessor, HyDEResult, HyDEConfig
from .guide_retriever import GuideRetriever, GuideRetrievalConfig, GuideRetrievalResult
from .crag import CRAGProcessor, CRAGConfig, CRAGResult, ClaimVerdict, VerifiedClaim
from .temporal_reasoner import TemporalReasoner, TEMPORAL_SIGNALS, TEMPORAL_SYSTEM_CONTEXT
from .extraction_mode import ExtractionMode, ExtractionConfig, ExtractionResult, EXTRACTION_SCHEMA
from .summary_mode import SummaryMode, SummaryConfig, SummaryResult
from .session_memory import DealSummary
# Phase 15
from .comparison_mode import ComparisonMode, ComparisonResult, ScopeDefinition
from .contradiction_detector import (
    ContradictionDetector,
    ContradictionResult,
    is_contradiction_query,
    CONTRADICTION_SIGNALS,
    CONTRADICTION_PROMPT,
)
from .baseline_corpus import BaselineCorpus, BaselineClause, STANDARD_CLAUSE_TYPES
from .anomaly_scorer import AnomalyScorer, AnomalyResult

__all__ = [
    "ResolutionCitation",
    "TermResolution",
    "TermResolver",
    "extract_title_case_phrases",
    "should_activate_resolver",
    "EvidenceMatch",
    "EvidenceMatcher",
    "ProvenanceLedger",
    "ProvenanceError",
    "ValidationResult",
    "validate_strict_mode",
    "AcronymResolver",
    "QueryExpander",
    "cross_encoder_rerank",
    "cross_encoder_score_pairs",
    "TermRegistry",
    # Phase 13
    "ConfidenceScorer",
    "ConfidenceTier",
    "ConfidenceResult",
    "GapDetector",
    "GapResult",
    "extract_entities",
    "HyDEProcessor",
    "HyDEResult",
    "HyDEConfig",
    "GuideRetriever",
    "GuideRetrievalConfig",
    "GuideRetrievalResult",
    # Phase 19 — Corrective RAG
    "CRAGProcessor",
    "CRAGConfig",
    "CRAGResult",
    "ClaimVerdict",
    "VerifiedClaim",
    # Phase 14
    "TemporalReasoner",
    "TEMPORAL_SIGNALS",
    "TEMPORAL_SYSTEM_CONTEXT",
    "ExtractionMode",
    "ExtractionConfig",
    "ExtractionResult",
    "EXTRACTION_SCHEMA",
    "SummaryMode",
    "SummaryConfig",
    "SummaryResult",
    "DealSummary",
    # Phase 15
    "ComparisonMode",
    "ComparisonResult",
    "ScopeDefinition",
    "ContradictionDetector",
    "ContradictionResult",
    "is_contradiction_query",
    "CONTRADICTION_SIGNALS",
    "CONTRADICTION_PROMPT",
    "BaselineCorpus",
    "BaselineClause",
    "STANDARD_CLAUSE_TYPES",
    "AnomalyScorer",
    "AnomalyResult",
]
