"""
ABS Deal Store — per-deal SQLite structured spine.

Public API::

    from backend.abs.store import DealStore, new_id, SCHEMA_VERSION
"""

from __future__ import annotations

from backend.abs.store.deal_store import DealStore, new_id
from backend.abs.store.schema import SCHEMA_VERSION, STATUS_VALUES, all_table_names

__all__ = [
    "DealStore",
    "new_id",
    "SCHEMA_VERSION",
    "STATUS_VALUES",
    "all_table_names",
]
