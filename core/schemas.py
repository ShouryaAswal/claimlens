"""
core/schemas.py
----------------
Pydantic v2 data models shared across every agent in the ClaimLens pipeline.

Design notes (Sprint 0):
- `ContentBlock` is the universal unit of evidence. Every ingestion parser
  (PDF, DOCX, PPTX, image, HTML) emits a list of these, regardless of source
  format. This is what later sprints cite for provenance — block_id is the
  ONLY thing an LLM is ever allowed to reference; bbox/page are filled in
  deterministically by the parser, never by a model.
- Not every format has a pixel-accurate bounding box (a flowing .docx
  paragraph doesn't live at a fixed (x, y) the way a PDF block or a PPTX
  shape does). `bbox` and `page` are therefore Optional — provenance
  degrades gracefully to `locator` (a human-readable position string) rather
  than silently inventing a coordinate.
- `LOBSchema` / `SectionDefinition` / `FieldDefinition` model the
  ACORD-inspired (Auto/Property) and CMS-1500/UB-04-inspired (Health) field
  schemas defined in schemas/*.json. This is the "Schema Resolution" layer
  that was missing from the v1 design.
- `ClaimState` is the single object that flows through the whole pipeline,
  growing as later sprints (classification, extraction, triage) attach more
  data to it. Sprint 0/1 only populate `documents`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SourceFormat(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    IMAGE = "image"
    HTML = "html"


class LOB(str, Enum):
    AUTO = "auto"
    PROPERTY = "property"
    HEALTH = "health"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Ingestion-layer models (Sprint 1)
# ---------------------------------------------------------------------------

class ContentBlock(BaseModel):
    """The universal unit of evidence. One per OCR block / PDF text block /
    DOCX paragraph / PPTX shape / HTML element / OCR line."""

    block_id: str
    source_file: str
    source_format: SourceFormat
    page: Optional[int] = None                      # 1-indexed; None if not paginated
    locator: str                                     # e.g. "page_2_block_5", "paragraph_12",
                                                       # "slide_3_shape_1", "html_p_4"
    text: str
    bbox: Optional[tuple[float, float, float, float]] = None  # (x0, y0, x1, y1) in points
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    extraction_method: str                            # "pymupdf_text" | "pytesseract_ocr" |
                                                       # "docx_paragraph" | "docx_table_row" |
                                                       # "pptx_shape_text" | "html_text_element"
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def _non_empty_text(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("ContentBlock.text must not be empty")
        return v


class DocumentRecord(BaseModel):
    """One ingested file (or one fetched URL), with all of its blocks."""

    doc_id: str
    source_file: str
    source_format: SourceFormat
    page_count: Optional[int] = None
    doc_type: Optional[str] = None        # set later by the doc-type tagger agent
    blocks: list[ContentBlock] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def full_text(self) -> str:
        return "\n".join(b.text for b in self.blocks)

    @property
    def block_count(self) -> int:
        return len(self.blocks)


# ---------------------------------------------------------------------------
# Schema Resolution layer models (Sprint 0 — the new ACORD/CMS-1500 mapping)
# ---------------------------------------------------------------------------

class FieldDefinition(BaseModel):
    field_id: str
    label: str
    required: bool = False
    field_type: Literal["text", "date", "number", "boolean", "code"] = "text"
    description: Optional[str] = None
    synonyms: list[str] = Field(default_factory=list)  # helps section-extraction prompts


class SectionDefinition(BaseModel):
    section_id: str
    fields: list[FieldDefinition]

    @property
    def required_fields(self) -> list[FieldDefinition]:
        return [f for f in self.fields if f.required]


class LOBSchema(BaseModel):
    lob: LOB
    source_concept: str          # honesty marker: which real-world form this is inspired by
    mandatory_doc_types: list[str]
    sections: list[SectionDefinition]

    @property
    def all_fields(self) -> list[FieldDefinition]:
        return [f for s in self.sections for f in s.fields]

    @property
    def required_fields(self) -> list[FieldDefinition]:
        return [f for f in self.all_fields if f.required]

    def get_section(self, section_id: str) -> Optional[SectionDefinition]:
        return next((s for s in self.sections if s.section_id == section_id), None)


# ---------------------------------------------------------------------------
# Claim-level state (grows in later sprints — extraction/triage/summary)
# ---------------------------------------------------------------------------

class ExtractedField(BaseModel):
    """Populated in Sprint 2+. Scaffolded now so ClaimState has a stable shape."""

    field_id: str
    value: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_block_ids: list[str] = Field(default_factory=list)
    status: Literal["found", "missing", "low_confidence", "conflicting"] = "missing"
    reason: Optional[str] = None


class ClaimState(BaseModel):
    """The single object that flows through ingestion -> classification ->
    schema resolution -> extraction -> triage -> reviewer summary."""

    claim_id: str
    lob: Optional[LOB] = None
    lob_confidence: Optional[float] = None
    documents: list[DocumentRecord] = Field(default_factory=list)
    lob_schema: Optional[LOBSchema] = None
    extracted_fields: dict[str, ExtractedField] = Field(default_factory=dict)
    missing_mandatory_docs: list[str] = Field(default_factory=list)
    triage: Optional[dict[str, Any]] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def all_blocks(self) -> list[ContentBlock]:
        return [b for d in self.documents for b in d.blocks]

    @property
    def total_page_count(self) -> int:
        return sum(d.page_count or 0 for d in self.documents)

    def get_block(self, block_id: str) -> Optional[ContentBlock]:
        return next((b for b in self.all_blocks if b.block_id == block_id), None)
