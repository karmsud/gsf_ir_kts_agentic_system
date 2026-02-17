"""Acronym Resolver — TD §6.2.

Expands domain acronyms in queries using a static JSON dictionary.
Gated behind ``config.acronym_resolver_enabled``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_DEFAULT_DICT_PATH = Path(__file__).resolve().parent.parent / "data" / "acronyms.json"


class AcronymResolver:
    """Expand uppercase acronyms in query text using a dictionary."""

    def __init__(self, dict_path: str | Path | None = None):
        path = Path(dict_path) if dict_path else _DEFAULT_DICT_PATH
        if path.exists():
            self._dict: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
        else:
            self._dict = {}

    @property
    def dictionary(self) -> dict[str, str]:
        return dict(self._dict)

    def expand(self, query: str) -> str:
        """Return *query* with acronyms expanded inline.

        Example::

            >>> AcronymResolver().expand("What is a PSA?")
            'What is a PSA (Pooling and Servicing Agreement)?'
        """
        if not self._dict:
            return query

        def _replace(m: re.Match) -> str:
            acronym = m.group(0)
            expansion = self._dict.get(acronym.upper())
            if expansion:
                return f"{acronym} ({expansion})"
            return acronym

        # Match 2-6 letter uppercase tokens that are whole words
        return re.sub(r'\b[A-Z]{2,6}\b', _replace, query)

    def expand_tokens(self, tokens: list[str]) -> list[str]:
        """Given a list of tokens, return expanded tokens (useful for search expansion)."""
        result: list[str] = []
        for token in tokens:
            upper = token.upper()
            if upper in self._dict:
                result.append(token)
                result.append(self._dict[upper])
            else:
                result.append(token)
        return result
