from __future__ import annotations

from abc import ABC, abstractmethod

from backend.common.models import AgentResult
from backend.common.quality_gate import QualityGate
from config import KTSConfig


class AgentBase(ABC):
    agent_name: str = "base-agent"
    agent_version: str = "1.0.0"

    def __init__(self, config: KTSConfig):
        self.config = config
        self.quality_gate = QualityGate(config)

    @abstractmethod
    def execute(self, request: dict) -> AgentResult:
        raise NotImplementedError

    def quality_check(self, result: AgentResult) -> AgentResult:
        return self.quality_gate.apply(result)
