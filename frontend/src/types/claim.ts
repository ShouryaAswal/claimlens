/**
 * types/claim.ts
 * ----------------
 * Hand-verified TypeScript mirrors of the backend Pydantic models. Source
 * of truth for each type is noted above it -- if the backend model
 * changes, update here to match, not the other way around.
 *
 *   backend/core/schemas.py  -> everything up to ClaimState
 *   backend/core/store.py    -> ClaimRecord, PipelineStatus, AdjusterDecision
 *   backend/app/routers/claims.py::list_claims() -> ClaimSummary
 *
 * Enums are modeled as string union types (not TS `enum`) since every
 * Pydantic `str, Enum` serializes to its `.value` over the wire.
 */

// ---------------------------------------------------------------------------
// Enums (core/schemas.py)
// ---------------------------------------------------------------------------

export type SourceFormat = "pdf" | "docx" | "pptx" | "image" | "html";

export type LOB = "auto" | "property" | "health" | "unknown";

export type MatchMethod =
  | "exact_numeric"
  | "exact_date"
  | "exact_code"
  | "fuzzy_text"
  | "no_evidence"
  | "unparseable";

export type RiskLevel = "ok" | "needs_review" | "high_risk";

export type TriageTier =
  | "stp_candidate"
  | "needs_review"
  | "high_risk_incomplete";

export type FieldType = "text" | "date" | "number" | "boolean" | "code";

export type FieldStatus = "found" | "missing" | "low_confidence" | "conflicting";

// ---------------------------------------------------------------------------
// Enums (core/store.py)
// ---------------------------------------------------------------------------

export type PipelineStatus = "processing" | "complete" | "error";

export type AdjusterDecision = "pending" | "approved" | "rejected";

// ---------------------------------------------------------------------------
// Verification / triage / review-queue models
// ---------------------------------------------------------------------------

export interface TriageVerdict {
  tier: TriageTier;
  score: number;
  forced_review: boolean;
  reasons: string[];
  high_risk_field_ids: string[];
}

export interface LLMVerificationResult {
  supported: boolean;
  confidence: number;
  explanation: string;
}

export interface FieldVerification {
  field_id: string;
  match_method: MatchMethod;
  match_score: number;
  ocr_confidence_avg: number;
  llm_confidence: number;
  composite_confidence: number;
  risk_level: RiskLevel;
  requires_human_review: boolean;
  reasons: string[];
  llm_verification: LLMVerificationResult | null;
  /** URLs already rewritten by core/pipeline.py to `/crops/{claim_id}/{block_id}.png` */
  crop_paths: string[];
}

export interface ReviewQueueItem {
  claim_id: string;
  field_id: string;
  field_label: string;
  value: string | null;
  risk_level: RiskLevel;
  reasons: string[];
  evidence_block_ids: string[];
  crop_paths: string[];
}

// ---------------------------------------------------------------------------
// Ingestion-layer models (Sprint 1)
// ---------------------------------------------------------------------------

export interface ContentBlock {
  block_id: string;
  source_file: string;
  source_format: SourceFormat;
  /** 1-indexed page number; null if the source format isn't paginated (e.g. DOCX). */
  page: number | null;
  locator: string;
  text: string;
  /** (x0, y0, x1, y1) in points -- null for flowing formats with no fixed bbox. */
  bbox: [number, number, number, number] | null;
  confidence: number;
  extraction_method: string;
  extra: Record<string, unknown>;
}

export interface DocumentRecord {
  doc_id: string;
  source_file: string;
  source_format: SourceFormat;
  page_count: number | null;
  doc_type: string | null;
  blocks: ContentBlock[];
  warnings: string[];
  ingested_at: string;
}

// ---------------------------------------------------------------------------
// Schema Resolution layer models (Sprint 0)
// ---------------------------------------------------------------------------

export interface FieldDefinition {
  field_id: string;
  label: string;
  required: boolean;
  field_type: FieldType;
  description: string | null;
  synonyms: string[];
}

export interface SectionDefinition {
  section_id: string;
  fields: FieldDefinition[];
}

export interface LOBSchema {
  lob: LOB;
  source_concept: string;
  mandatory_doc_types: string[];
  sections: SectionDefinition[];
}

// ---------------------------------------------------------------------------
// Claim-level state
// ---------------------------------------------------------------------------

export interface ExtractedField {
  field_id: string;
  value: string | number | null;
  confidence: number;
  evidence_block_ids: string[];
  status: FieldStatus;
  reason: string | null;
}

export interface ClaimState {
  claim_id: string;
  lob: LOB | null;
  lob_confidence: number | null;
  documents: DocumentRecord[];
  lob_schema: LOBSchema | null;
  extracted_fields: Record<string, ExtractedField>;
  field_verifications: Record<string, FieldVerification>;
  missing_mandatory_docs: string[];
  triage: TriageVerdict | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Sprint 5 wrapper (core/store.py::ClaimRecord) -- what
// GET /api/claims/{id} actually returns.
// ---------------------------------------------------------------------------

export interface ClaimRecord {
  claim: ClaimState;
  status: PipelineStatus;
  error: string | null;
  summary: string | null;
  review_queue: ReviewQueueItem[];
  review_queue_counts: ReviewQueueCounts;
  adjuster_decision: AdjusterDecision;
  updated_at: string;
}

export interface ReviewQueueCounts {
  total: number;
  high_risk: number;
  needs_review: number;
  no_visual_evidence: number;
}

export interface CompletionStats {
  total_fields: number;
  fields_found: number;
  required_fields: number;
  required_fields_found: number;
}

// ---------------------------------------------------------------------------
// GET /api/claims (Dashboard list) -- app/routers/claims.py::list_claims()
// ---------------------------------------------------------------------------

export interface ClaimSummary {
  claim_id: string;
  lob: LOB | null;
  status: PipelineStatus;
  adjuster_decision: AdjusterDecision;
  tier: TriageTier | null;
  score: number | null;
  forced_review: boolean | null;
  completion: CompletionStats;
  primary_amount: number | null;
  doc_count: number;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// GET /api/claims/{id}/documents/{doc_id}/page/{n} -- X-Blocks header payload
// (app/routers/documents.py)
// ---------------------------------------------------------------------------

export interface PageBlock {
  block_id: string;
  /** Already in pixel space, top-left origin. No Y-flip, ever -- draw as-is. */
  bbox_px: [number, number, number, number];
}

// ---------------------------------------------------------------------------
// POST /api/claims/{id}/fields/{field_id}/override request body
// (app/routers/review.py::FieldOverrideRequest)
// ---------------------------------------------------------------------------

export interface FieldOverrideRequest {
  value: string;
  note?: string | null;
}

// ---------------------------------------------------------------------------
// SSE stage events (app/sse.py + core/pipeline.py, see docs/SPRINT_5 plan)
// ---------------------------------------------------------------------------

export type StageName =
  | "ingest"
  | "classify"
  | "schema_resolve"
  | "doc_type_tag"
  | "gate_check"
  | "extract"
  | "extract_section"
  | "merge"
  | "verify"
  | "crops"
  | "triage"
  | "summary"
  | "pipeline";

export type StageStatus = "start" | "progress" | "complete" | "done" | "error";

export interface StageEvent {
  stage: StageName;
  status: StageStatus;
  detail?: Record<string, unknown>;
}
