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
from typing import Any, Literal, Optional, Union

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


class MatchMethod(str, Enum):
    """How a field's claimed value was checked against its cited evidence
    text. Numeric/date/code fields use exact (zero-tolerance) matching --
    see agents/evidence_verifier.py's module docstring for why a single
    digit of "close enough" is not acceptable for a dollar amount or a VIN.
    """

    EXACT_NUMERIC = "exact_numeric"
    EXACT_DATE = "exact_date"
    EXACT_CODE = "exact_code"
    FUZZY_TEXT = "fuzzy_text"
    NO_EVIDENCE = "no_evidence"
    UNPARSEABLE = "unparseable"


class RiskLevel(str, Enum):
    OK = "ok"
    NEEDS_REVIEW = "needs_review"
    HIGH_RISK = "high_risk"


class TriageTier(str, Enum):
    STP_CANDIDATE = "stp_candidate"
    NEEDS_REVIEW = "needs_review"
    HIGH_RISK_INCOMPLETE = "high_risk_incomplete"


class TriageVerdict(BaseModel):
    """Sprint 4's triage output. `forced_review` is the field that matters
    most: it's True whenever a REQUIRED field landed on RiskLevel.HIGH_RISK
    during Sprint 3's verification -- in that case the tier can never be
    "stp_candidate" no matter how good the rest of the composite score
    looks. See agents/triage_agent.py for the full rule set."""

    tier: TriageTier
    score: int
    forced_review: bool
    reasons: list[str] = Field(default_factory=list)
    high_risk_field_ids: list[str] = Field(default_factory=list)


class LLMVerificationResult(BaseModel):
    """Output of the optional LLM-based secondary check (semantic
    cross-check on top of the deterministic fuzzy/exact match -- catches
    things string matching can't, e.g. '5:45 PM' vs '17:45' meaning the
    same thing, or text matching exactly but actually being contradicted by
    context elsewhere in the same block)."""

    supported: bool
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str


class FieldVerification(BaseModel):
    """The full verification + confidence-rating record for one extracted
    field. This is the structure the future reviewer UI (Sprint 5) reads
    from -- everything a human needs to either trust a field at a glance or
    understand exactly why it's flagged."""

    field_id: str
    match_method: MatchMethod
    match_score: float = Field(ge=0.0, le=1.0)
    ocr_confidence_avg: float = Field(ge=0.0, le=1.0)
    llm_confidence: float = Field(ge=0.0, le=1.0)
    composite_confidence: float = Field(ge=0.0, le=1.0)
    risk_level: RiskLevel
    requires_human_review: bool
    reasons: list[str] = Field(default_factory=list)
    llm_verification: Optional[LLMVerificationResult] = None
    crop_paths: list[str] = Field(default_factory=list)
    # Populated only when a human overrode this field (app/routers/review.py).
    # doc_id the adjuster says they actually found the value in -- distinct
    # from evidence_block_ids, which only ever reflects what the MODEL
    # cited. Keeping the two separate is the point: a mismatch between them
    # (model cited doc A, adjuster says doc B) is itself a signal worth
    # mining later to find where extraction is looking in the wrong place.
    adjuster_source_doc_id: Optional[str] = None


class ReviewQueueItem(BaseModel):
    """One line item in the human-in-the-loop review queue -- the basis for
    Sprint 5's reviewer UI. Self-contained: a reviewer should be able to
    make a decision from this record plus the crop images alone, without
    needing to dig back through the raw claim state."""

    claim_id: str
    field_id: str
    field_label: str
    value: Optional[str]
    risk_level: RiskLevel
    reasons: list[str]
    evidence_block_ids: list[str]
    crop_paths: list[str] = Field(default_factory=list)


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
    """Populated in Sprint 2+. Scaffolded now so ClaimState has a stable shape.

    ``value`` is typed as ``Union[str, int, float, None]`` so that LLM responses
    that return numbers (e.g. ``4250.0``) are stored with the right Python type
    instead of crashing Pydantic validation.  The validator below coerces:
      - whole-number floats → int  (e.g. ``4250.0`` → ``4250``)
      - fractional floats   → float (unchanged)
      - everything else     → str  (via ``str()`` coercion)
    ``None`` passes through unchanged (field not found).
    """

    field_id: str
    value: Optional[Union[str, int, float]] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_block_ids: list[str] = Field(default_factory=list)
    status: Literal["found", "missing", "low_confidence", "conflicting"] = "missing"
    reason: Optional[str] = None

    @field_validator("value", mode="before")
    @classmethod
    def coerce_value(cls, v: Any) -> Optional[Union[str, int, float]]:
        """Accept whatever the LLM returns and normalise to a sensible Python type."""
        if v is None:
            return None
        if isinstance(v, bool):          # bool is a subclass of int — keep as str
            return str(v).lower()
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            # Store whole-number floats as int (e.g. 4250.0 → 4250)
            return int(v) if v == int(v) else v
        # Anything else (list, dict, …) — stringify rather than crash
        return str(v) if not isinstance(v, str) else v


class ClaimState(BaseModel):
    """The single object that flows through ingestion -> classification ->
    schema resolution -> extraction -> triage -> reviewer summary."""

    claim_id: str
    lob: Optional[LOB] = None
    lob_confidence: Optional[float] = None
    documents: list[DocumentRecord] = Field(default_factory=list)
    lob_schema: Optional[LOBSchema] = None
    extracted_fields: dict[str, ExtractedField] = Field(default_factory=dict)
    field_verifications: dict[str, FieldVerification] = Field(default_factory=dict)
    missing_mandatory_docs: list[str] = Field(default_factory=list)
    triage: Optional[TriageVerdict] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def all_blocks(self) -> list[ContentBlock]:
        return [b for d in self.documents for b in d.blocks]

    @property
    def total_page_count(self) -> int:
        return sum(d.page_count or 0 for d in self.documents)

    def get_block(self, block_id: str) -> Optional[ContentBlock]:
        return next((b for b in self.all_blocks if b.block_id == block_id), None)
