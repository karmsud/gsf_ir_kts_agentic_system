"""
ABSStream — dual-mode output for ABS CLI and VS Code IPC.

Two modes:
  terminal   — human-readable text/emoji printed to stdout
  ipc        — newline-delimited JSON flushed to stdout (for extension)

The VS Code extension spawns the Python CLI subprocess and reads these
JSON lines to drive the chat-participant UI.
"""

from __future__ import annotations

import json
import sys
from typing import Optional


class ABSStream:
    """
    Stream ABS operation output to either a human terminal or VS Code IPC.

    Parameters
    ----------
    mode:
        ``"terminal"`` (default) — pretty-printed human output.
        ``"ipc"``      — newline-delimited JSON for VS Code extension.
    """

    def __init__(self, mode: str = "terminal") -> None:
        if mode not in ("terminal", "ipc"):
            raise ValueError(f"ABSStream mode must be 'terminal' or 'ipc', got {mode!r}")
        self.mode = mode
        self._step_number: int = 0
        self._total_steps: int = 0

    # ------------------------------------------------------------------
    # Core message emitters
    # ------------------------------------------------------------------

    def progress(
        self,
        step: str,
        status: str = "in-progress",
        *,
        step_num: Optional[int] = None,
        total: Optional[int] = None,
    ) -> None:
        """Emit a pipeline-progress message."""
        self._step_number = step_num if step_num is not None else self._step_number + 1
        if total is not None:
            self._total_steps = total

        if self.mode == "ipc":
            self._write({
                "type": "progress",
                "step": step,
                "status": status,
                "step_number": self._step_number,
                "total_steps": self._total_steps,
            })
        else:
            emoji = "✅" if status == "done" else ("❌" if status == "error" else "▸")
            print(f"  {emoji} {step}", flush=True)

    def markdown(self, text: str) -> None:
        """Emit a markdown/text fragment."""
        if self.mode == "ipc":
            self._write({"type": "stream", "text": text})
        else:
            print(text, end="", flush=True)

    def code(self, code: str, language: str = "python") -> None:
        """Emit a code block."""
        if self.mode == "ipc":
            self._write({"type": "code", "language": language, "code": code})
        else:
            print(f"```{language}\n{code}\n```", flush=True)

    def result(self, data: dict) -> None:
        """Emit a final result payload."""
        if self.mode == "ipc":
            self._write({"type": "result", **data})
        else:
            for k, v in data.items():
                if k != "type":
                    print(f"  {k}: {v}", flush=True)

    def error(self, message: str, code: str = "UNKNOWN") -> None:
        """Emit an error message."""
        if self.mode == "ipc":
            self._write({"type": "error", "message": message, "code": code})
        else:
            print(f"❌ Error ({code}): {message}", file=sys.stderr, flush=True)

    def llm_request(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        model: str = "gpt-4.1",
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Optional[str]:
        """
        Request an LLM completion.

        In IPC mode: write the request and block on a response line from stdin.
        In terminal mode: log and return None (no actual LLM in terminal mode).
        """
        if self.mode == "ipc":
            self._write({
                "type": "llm_request",
                "model": model,
                "prompt": prompt,
                "system_prompt": system_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            })
            # Block for response from extension
            line = sys.stdin.readline()
            if line:
                try:
                    resp = json.loads(line)
                    if resp.get("type") == "llm_response":
                        return resp.get("text", "")
                except json.JSONDecodeError:
                    pass
            return None
        else:
            print(f"  [LLM skipped in terminal mode: {prompt[:60]}...]", flush=True)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write(self, obj: dict) -> None:
        """Serialise *obj* as a single-line JSON record and flush."""
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()
