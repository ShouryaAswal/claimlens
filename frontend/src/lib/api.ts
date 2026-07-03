/**
 * lib/api.ts
 * -----------
 * Thin fetch wrapper for the ClaimLens FastAPI backend. Base URL comes
 * from VITE_API_BASE_URL (see .env.example) -- never hardcode localhost
 * here so the same build works against a deployed backend.
 *
 * Endpoints mirror the API surface table in the Sprint 5 plan exactly.
 */
import type {
  ClaimRecord,
  ClaimSummary,
  FieldOverrideRequest,
  PageBlock,
} from "@/types/claim";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: init?.body instanceof FormData
      ? undefined
      : { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // response wasn't JSON -- fall back to statusText
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

// -- Claims -------------------------------------------------------------

export function createClaim(files: File[]): Promise<{ claim_id: string }> {
  const formData = new FormData();
  for (const file of files) {
    // Folder uploads (see StartClaim.tsx's webkitdirectory input) carry
    // their subfolder path in webkitRelativePath (e.g.
    // "ClaimFolder/evidence/photo1.jpg"). Passing that as the upload
    // filename lets the backend preserve it under
    // claimlens_uploads/{claim_id}/... (see claims.py's
    // _save_uploads_to_temp) instead of flattening every file to its
    // bare name, which would silently collide same-named files from
    // different subfolders.
    const relativePath = (file as File & { webkitRelativePath?: string }).webkitRelativePath;
    formData.append("files", file, relativePath || file.name);
  }
  return request("/api/claims", { method: "POST", body: formData });
}

export function listClaims(): Promise<ClaimSummary[]> {
  return request("/api/claims");
}

export function getClaim(claimId: string): Promise<ClaimRecord> {
  return request(`/api/claims/${claimId}`);
}

// -- Review actions -------------------------------------------------------

export function overrideField(
  claimId: string,
  fieldId: string,
  body: FieldOverrideRequest,
): Promise<ClaimRecord> {
  return request(`/api/claims/${claimId}/fields/${fieldId}/override`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function approveClaim(claimId: string): Promise<ClaimRecord> {
  return request(`/api/claims/${claimId}/approve`, { method: "POST" });
}

export function rejectClaim(claimId: string): Promise<ClaimRecord> {
  return request(`/api/claims/${claimId}/reject`, { method: "POST" });
}

// -- Document page render ------------------------------------------------

export interface DocumentPageResult {
  /** Object URL for the rendered page PNG. Caller must revokeObjectURL when done. */
  imageUrl: string;
  blocks: PageBlock[];
}

/**
 * Fetches a rendered page as a PNG + its X-Blocks header (per-block pixel
 * bboxes). The backend guarantees no Y-flip -- bbox_px is already in the
 * same top-left-origin space as the image, so this just parses and hands
 * both back together for the SVG overlay to draw directly.
 */
export async function getDocumentPage(
  claimId: string,
  docId: string,
  pageNumber: number,
): Promise<DocumentPageResult> {
  const res = await fetch(
    `${API_BASE_URL}/api/claims/${claimId}/documents/${docId}/page/${pageNumber}`,
  );
  if (!res.ok) {
    throw new ApiError(res.status, res.statusText);
  }
  const blocksHeader = res.headers.get("X-Blocks");
  const blocks: PageBlock[] = blocksHeader ? JSON.parse(blocksHeader) : [];
  const blob = await res.blob();
  return { imageUrl: URL.createObjectURL(blob), blocks };
}

// -- Crops ------------------------------------------------------------------

/** crop_paths on FieldVerification are already full `/crops/...` URLs
 * rewritten server-side -- this just resolves them against the API base. */
export function resolveAssetUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${API_BASE_URL}${path.startsWith("/") ? "" : "/"}${path}`;
}

export { API_BASE_URL };
