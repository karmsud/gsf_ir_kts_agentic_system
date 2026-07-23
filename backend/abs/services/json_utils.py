"""
Lenient JSON parsing for LLM output.

LLMs often wrap JSON in markdown fences or add prose. These helpers recover the
structured payload robustly so agents/services can rely on typed data.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def parse_json_lenient(text: str) -> Optional[Any]:
    """Best-effort parse of JSON possibly embedded in prose / code fences."""
    if not text or not text.strip():
        return None

    # 1. Direct parse.
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Inside a fenced code block.
    m = _FENCE_RE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            text = m.group(1)

    # 3. Substring from the first bracket to the matching last bracket.
    for open_ch, close_ch in (("[", "]"), ("{", "}")):
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                continue
    return None


def extract_items(text: str, list_key: Optional[str] = None) -> list[dict[str, Any]]:
    """Return a list of dict items from LLM output.

    Accepts a bare JSON array, a single object, or an object wrapping the array
    under ``list_key`` (or the first list-valued key found).
    """
    parsed = parse_json_lenient(text)
    if parsed is None:
        return []
    if isinstance(parsed, list):
        return [x for x in parsed if isinstance(x, dict)]
    if isinstance(parsed, dict):
        if list_key and isinstance(parsed.get(list_key), list):
            return [x for x in parsed[list_key] if isinstance(x, dict)]
        for value in parsed.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value
        return [parsed]  # a single item
    return []
