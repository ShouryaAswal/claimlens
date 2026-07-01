"""
core/schema_loader.py
----------------------
Deterministic loader for the per-LOB field schemas in schemas/*.json.

This is intentionally NOT an LLM call -- it's a plain dictionary lookup, by
design (see ClaimLens v2 Design Doc, section 2: "Schema Resolution"). Given a
classified LOB, we already know exactly which fields to look for; there's
nothing for a model to decide here.
"""

from __future__ import annotations

import json
from functools import lru_cache

from core.config import SCHEMAS_DIR
from core.schemas import LOB, LOBSchema

_FILENAME_BY_LOB = {
    LOB.AUTO: "auto.json",
    LOB.PROPERTY: "property.json",
    LOB.HEALTH: "health.json",
}


class SchemaNotFoundError(Exception):
    pass


@lru_cache(maxsize=None)
def load_lob_schema(lob: LOB) -> LOBSchema:
    """Load and validate the field schema for a given LOB. Cached -- LOBs
    don't change at runtime, so there's no reason to re-read/re-parse the
    JSON file on every claim."""
    if lob not in _FILENAME_BY_LOB:
        raise SchemaNotFoundError(
            f"No schema file mapped for LOB={lob!r}. "
            f"Known LOBs: {list(_FILENAME_BY_LOB)}"
        )
    path = SCHEMAS_DIR / _FILENAME_BY_LOB[lob]
    if not path.exists():
        raise SchemaNotFoundError(f"Schema file not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return LOBSchema.model_validate(raw)


def load_all_schemas() -> dict[LOB, LOBSchema]:
    return {lob: load_lob_schema(lob) for lob in _FILENAME_BY_LOB}
