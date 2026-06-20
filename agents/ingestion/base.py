"""
agents/ingestion/base.py
--------------------------
Shared exceptions and small helpers used by every format-specific parser.
"""

from __future__ import annotations


class IngestionError(Exception):
    """Base class for all ingestion failures."""


class UnsupportedFormatError(IngestionError):
    """Raised when a file extension / content-type has no registered parser."""


class FetchError(IngestionError):
    """Raised when a hyperlink could not be fetched (network error, 4xx/5xx,
    payload too large, etc.)."""


def next_block_id(prefix: str, counter: int) -> str:
    """Stable, human-readable block id, e.g. 'p2_b007', 'slide3_b002'."""
    return f"{prefix}_b{counter:03d}"
