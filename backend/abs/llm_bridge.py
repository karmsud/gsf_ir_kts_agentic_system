"""
LLM Bridge — Injectable LLM callable factory.

Responsibilities:
1. Create LLM callables for different runtime environments
2. Handle IPC with VS Code extension (primary mode)
3. Provide mock callables for testing
4. Track token usage and latency
"""

import json
import sys
import time
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMUsageStats:
    """Track LLM usage across a session."""
    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_latency_ms: float = 0.0
    errors: int = 0
    call_log: list[dict] = field(default_factory=list)

    def record(self, input_tokens: int, output_tokens: int, latency_ms: float):
        self.total_calls += 1
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_latency_ms += latency_ms

    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / max(self.total_calls, 1)


# Global usage tracker
_usage = LLMUsageStats()

LLMCallable = Callable[[str, Optional[str]], str]


def create_llm_callable(
    mode: str = "none",
    model: str = "gpt-4.1",
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> Optional[LLMCallable]:
    """Factory for LLM callables.

    Args:
        mode: "vscode" | "mock" | "none"
        model: Model identifier (used in vscode mode)
        temperature: Default temperature
        max_tokens: Default max tokens

    Returns:
        LLMCallable or None if mode="none"
    """
    if mode == "vscode":
        return _create_vscode_callable(model, temperature, max_tokens)
    elif mode == "mock":
        return _create_mock_callable()
    elif mode == "none":
        return None
    else:
        logger.warning(f"Unknown LLM mode: {mode}, returning None")
        return None


def get_usage_stats() -> LLMUsageStats:
    """Get global LLM usage statistics."""
    return _usage


def reset_usage_stats() -> None:
    """Reset global usage statistics (for testing)."""
    global _usage
    _usage = LLMUsageStats()


def _create_vscode_callable(
    model: str,
    temperature: float,
    max_tokens: int,
) -> LLMCallable:
    """Create callable that communicates with VS Code extension via IPC.

    Protocol:
    1. Write JSON request to stdout (one line)
    2. Read JSON response from stdin (one line)
    3. Response contains "text" field with LLM output
    """
    def call_llm(prompt: str, system_prompt: Optional[str] = None) -> str:
        global _usage
        start = time.time()

        request = {
            "type": "llm_request",
            "model": model,
            "prompt": prompt,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            # Send request
            sys.stdout.write(json.dumps(request) + "\n")
            sys.stdout.flush()

            # Read response
            response_line = sys.stdin.readline()
            if not response_line:
                _usage.errors += 1
                return ""

            response = json.loads(response_line)
            text = response.get("text", "")

            # Track usage
            latency = (time.time() - start) * 1000
            _usage.record(
                input_tokens=response.get("input_tokens", len(prompt) // 4),
                output_tokens=response.get("output_tokens", len(text) // 4),
                latency_ms=latency,
            )

            return text

        except Exception as e:
            _usage.errors += 1
            logger.error(f"LLM call failed: {e}")
            return ""

    return call_llm


def _create_mock_callable() -> LLMCallable:
    """Mock callable for testing.

    Returns deterministic responses based on prompt content.
    Useful for unit tests and CI/CD pipelines.
    """
    def mock_llm(prompt: str, system_prompt: Optional[str] = None) -> str:
        global _usage
        _usage.record(input_tokens=len(prompt) // 4, output_tokens=50, latency_ms=1.0)

        prompt_lower = prompt.lower()

        # Payment model generation
        if "payment model" in prompt_lower or "waterfall" in prompt_lower:
            return (
                "def calculate_distribution(deal_data, period):\n"
                "    '''Mock distribution waterfall.'''\n"
                "    available = deal_data['available_funds']\n"
                "    distributions = {}\n"
                "    # Step 1: Trustee fees\n"
                "    trustee_fee = min(available, deal_data['trustee_fee'])\n"
                "    distributions['trustee'] = trustee_fee\n"
                "    available -= trustee_fee\n"
                "    return distributions\n"
            )

        # Q&A
        elif "question" in prompt_lower or "query" in prompt_lower:
            return (
                "Based on Section 5.02 of the PSA, the Trustee shall establish "
                "and maintain the Distribution Account for the benefit of "
                "Certificateholders. Distributions shall be made on each "
                "Distribution Date in accordance with the priority of payments "
                "set forth in Section 5.04."
            )

        # Multi-query expansion
        elif "generate" in prompt_lower and "queries" in prompt_lower:
            return json.dumps([
                "distribution waterfall payment priority",
                "trustee responsibilities distribution account",
                "certificateholder payment schedule",
                "overcollateralization trigger events",
            ])

        # Governing doc generation
        elif "governing" in prompt_lower:
            return (
                "# Distribution Waterfall\n\n"
                "## Priority of Payments\n\n"
                "1. Trustee Fee\n"
                "2. Servicer Fee\n"
                "3. Class A Interest\n"
                "4. Class A Principal\n"
                "5. Class B Interest\n"
            )

        # CRAG verification
        elif "verify" in prompt_lower or "claim" in prompt_lower:
            return json.dumps({
                "verified": True,
                "confidence": 0.92,
                "evidence": "Section 5.02 confirms...",
            })

        # Default
        else:
            return f"Mock LLM response for: {prompt[:80]}..."

    return mock_llm
