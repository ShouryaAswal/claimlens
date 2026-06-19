"""
ClaimLens core schemas.

These are the shared data contracts every agent reads/writes.
Keeping them in one place means every agent in agents/ speaks the
same language and we can validate at every hand-off (OCR -> chunking
-> LLM extraction -> provenance -> verifier -> triage).
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator


class OCRBlock(BaseModel):
    """A single text region detected on a page.

    OCR (or, for digital PDFs, direct text extraction) OWNS coordinates.
    Nothing downstream is allowed to invent a bbox -- they can only
    reference an existing block_id.
    """

    block_id: str  # e.g. "p1_b007"
    page: int
    text: str
    # x1, y1, x2, y2 in PDF points / pixel coords. None for source types
    # with no native spatial layout (e.g. .docx paragraphs) -- provenance
    # for those falls back to source_file + paragraph index + snippet
    # instead of a visual crop.
    bbox: Optional[Tuple[float, float, float, float]] = None
    ocr_confidence: float = Field(ge=0.0, le=1.0)
    source_file: str
    source_type: str = "digital_pdf"  # digital_pdf | scanned_pdf | image | docx

    @field_validator("bbox")
    @classmethod
    def _bbox_is_valid_box(cls, v):
        if v is None:
            return v
        x1, y1, x2, y2 = v
        if x2 < x1 or y2 < y1:
            raise ValueError(f"Invalid bbox, x2/y2 must be >= x1/y1: {v}")
        return v


class ExtractedField(BaseModel):
    """One field produced by the LLM Extraction Agent (Sprint 2)."""

    value: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_block_ids: List[str] = Field(default_factory=list)
    reason: Optional[str] = None


class ProvenanceRecord(BaseModel):
    """Field -> exact source location, produced by the Provenance Agent
    (Sprint 3) by resolving evidence_block_ids against ocr_blocks."""

    field: str
    value: Optional[str]
    source_file: str
    page: int
    bbox: Tuple[float, float, float, float]
    snippet: str
    crop_path: Optional[str] = None
    confidence: float


class VerificationFlag(BaseModel):
    field: str
    status: str  # "verified" | "low_confidence" | "missing" | "unsupported"
    detail: Optional[str] = None


class ClaimState(BaseModel):
    """The single shared object that flows through every agent in the
    pipeline. Each agent reads what it needs and appends its own output;
    nothing is mutated destructively, so we always retain a full audit
    trail of what happened at each stage."""

    claim_id: str
    claim_type: str  # "auto" | "property" | "health"
    source_files: List[str] = Field(default_factory=list)

    # Sprint 1 output
    ocr_blocks: List[OCRBlock] = Field(default_factory=list)

    # Sprint 2 output
    extracted_fields: Dict[str, ExtractedField] = Field(default_factory=dict)

    # Sprint 3 output
    provenance: Dict[str, ProvenanceRecord] = Field(default_factory=dict)
    verification: List[VerificationFlag] = Field(default_factory=list)

    # Sprint 4 output
    triage_score: Optional[int] = None
    triage_route: Optional[str] = None
    reviewer_summary: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)

    def blocks_for_page(self, page: int) -> List[OCRBlock]:
        return [b for b in self.ocr_blocks if b.page == page]

    def block_by_id(self, block_id: str) -> Optional[OCRBlock]:
        for b in self.ocr_blocks:
            if b.block_id == block_id:
                return b
        return None
