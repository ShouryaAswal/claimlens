import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  approveClaim,
  createClaim,
  getClaim,
  listClaims,
  overrideField,
  rejectClaim,
} from "@/lib/api";
import type { FieldOverrideRequest } from "@/types/claim";

export const claimKeys = {
  all: ["claims"] as const,
  list: () => [...claimKeys.all, "list"] as const,
  detail: (claimId: string) => [...claimKeys.all, "detail", claimId] as const,
};

/** GET /api/claims/{id} -- the full ClaimRecord backing the review page. */
export function useClaim(claimId: string | undefined) {
  return useQuery({
    queryKey: claimKeys.detail(claimId ?? ""),
    queryFn: () => getClaim(claimId!),
    enabled: Boolean(claimId),
  });
}

/** GET /api/claims -- the Dashboard's claims list. */
export function useClaimsList() {
  return useQuery({
    queryKey: claimKeys.list(),
    queryFn: listClaims,
  });
}

/** POST /api/claims -- upload files and kick off the pipeline. */
export function useCreateClaim() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (files: File[]) => createClaim(files),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: claimKeys.list() });
    },
  });
}

/** POST /api/claims/{id}/fields/{field_id}/override */
export function useOverrideField(claimId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ fieldId, body }: { fieldId: string; body: FieldOverrideRequest }) =>
      overrideField(claimId, fieldId, body),
    onSuccess: (record) => {
      queryClient.setQueryData(claimKeys.detail(claimId), record);
      queryClient.invalidateQueries({ queryKey: claimKeys.list() });
    },
  });
}

/** POST /api/claims/{id}/approve | /reject */
export function useAdjusterDecision(claimId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (decision: "approve" | "reject") =>
      decision === "approve" ? approveClaim(claimId) : rejectClaim(claimId),
    onSuccess: (record) => {
      queryClient.setQueryData(claimKeys.detail(claimId), record);
      queryClient.invalidateQueries({ queryKey: claimKeys.list() });
    },
  });
}
