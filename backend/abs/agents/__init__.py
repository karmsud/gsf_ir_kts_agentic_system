# backend/abs/agents/__init__.py
"""ABS agent implementations — domain-specific agents for deal processing."""

from backend.abs.agents.cashflow_projection_agent import CashflowProjectionAgent
from backend.abs.agents.deal_amendment_agent import DealAmendmentAgent
from backend.abs.agents.deal_lifecycle_agent import DealLifecycleAgent
from backend.abs.agents.document_comparison_agent import DocumentComparisonAgent
from backend.abs.agents.document_quality_agent import DocumentQualityAgent
from backend.abs.agents.ingestion_pipeline_agent import IngestionPipelineAgent
from backend.abs.agents.investor_reporting_agent import InvestorReportingAgent
from backend.abs.agents.model_auditor_agent import ModelAuditorAgent
from backend.abs.agents.model_creation_agent import ModelCreationAgent
from backend.abs.agents.qa_agent import QAAgent
from backend.abs.agents.regression_testing_agent import RegressionTestingAgent
from backend.abs.agents.stress_testing_agent import StressTestingAgent

__all__ = [
    "CashflowProjectionAgent",
    "DealAmendmentAgent",
    "DealLifecycleAgent",
    "DocumentComparisonAgent",
    "DocumentQualityAgent",
    "IngestionPipelineAgent",
    "InvestorReportingAgent",
    "ModelAuditorAgent",
    "ModelCreationAgent",
    "QAAgent",
    "RegressionTestingAgent",
    "StressTestingAgent",
]
