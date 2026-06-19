"""
Load/save helpers for ClaimState.

Kept separate from schemas.py so agents that just need persistence
don't have to import the full schema definitions, and so Sprint 4's
Streamlit app has one obvious place to load a claim's full state from
disk for the reviewer UI.
"""

import json
from pathlib import Path

from core.schemas import ClaimState


def save_claim_state(state: ClaimState, out_path: str) -> None:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        f.write(state.model_dump_json(indent=2))


def load_claim_state(in_path: str) -> ClaimState:
    with open(in_path) as f:
        return ClaimState.model_validate_json(f.read())
