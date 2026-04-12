"""
IPC protocol type definitions for ABS extension ↔ Python backend communication.

Each message type is a TypedDict so the VS Code extension TypeScript layer
and Python CLI layer share the same contract.  All messages are serialised
as newline-delimited JSON (one JSON object per line).

Message flow:
  CLI stdout  ──(JSON lines)──►  Extension TypeScript
  Extension   ──(JSON lines)──►  CLI stdin  (llm_response only)
"""

from __future__ import annotations

from typing import Literal, Optional

try:
    from typing import TypedDict  # Python 3.8+
except ImportError:
    from typing_extensions import TypedDict  # type: ignore[assignment]


# ─── Extension → Backend ─────────────────────────────────────────────────────


class LLMResponse(TypedDict):
    """LLM response sent from the VS Code extension to the Python backend."""

    type: Literal["llm_response"]
    text: str
    input_tokens: int
    output_tokens: int


# ─── Backend → Extension ─────────────────────────────────────────────────────


class ProgressMessage(TypedDict):
    """Emitted by the Python backend for each pipeline step."""

    type: Literal["progress"]
    step: str
    status: str  # "in-progress" | "done" | "error"
    step_number: int
    total_steps: int


class LLMRequest(TypedDict):
    """Emitted when the Python backend needs an LLM completion."""

    type: Literal["llm_request"]
    model: str
    prompt: str
    system_prompt: Optional[str]
    temperature: float
    max_tokens: int


class StreamMessage(TypedDict):
    """Incremental text fragment — for streaming answers."""

    type: Literal["stream"]
    text: str


class CodeMessage(TypedDict):
    """A generated code block."""

    type: Literal["code"]
    language: str
    code: str


class ResultMessage(TypedDict):
    """Final result payload — structure varies by command."""

    type: Literal["result"]
    command: str
    # ingest fields
    item_count: Optional[int]
    section_count: Optional[int]
    node_count: Optional[int]
    # generate fields
    output_path: Optional[str]
    quality_score: Optional[float]
    validation: Optional[str]
    # audit fields
    report: Optional[str]
    # status fields
    status_report: Optional[str]
    # qa fields
    answer: Optional[str]
    sources: Optional[list]


class ErrorMessage(TypedDict):
    """Error payload — emitted on unrecoverable failures."""

    type: Literal["error"]
    message: str
    code: str


# ─── Union type (informational) ──────────────────────────────────────────────

# All possible message types sent from backend to extension.
BackendMessage = (
    ProgressMessage
    | LLMRequest
    | StreamMessage
    | CodeMessage
    | ResultMessage
    | ErrorMessage
)
