import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useOverrideField } from "@/hooks/useClaim";
import { formatValue } from "@/lib/utils";
import { useReviewUiStore } from "@/store/reviewUiStore";
import type { ClaimState } from "@/types/claim";

interface OverrideModalProps {
  claim: ClaimState;
}

export function OverrideModal({ claim }: OverrideModalProps) {
  const overrideModalFieldId = useReviewUiStore((s) => s.overrideModalFieldId);
  const closeOverrideModal = useReviewUiStore((s) => s.closeOverrideModal);
  const { mutate, isPending, error, reset } = useOverrideField(claim.claim_id);

  const [value, setValue] = useState("");
  const [note, setNote] = useState("");

  const fieldId = overrideModalFieldId;
  const field = fieldId ? claim.extracted_fields[fieldId] : undefined;
  const fieldLabel =
    (fieldId &&
      claim.lob_schema?.sections
        .flatMap((s) => s.fields)
        .find((f) => f.field_id === fieldId)?.label) ||
    fieldId;

  useEffect(() => {
    if (fieldId && field) {
      setValue(formatValue(field.value) === "—" ? "" : String(field.value));
      setNote("");
      reset();
    }
  }, [fieldId, field, reset]);

  function handleOpenChange(open: boolean) {
    if (!open) closeOverrideModal();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!fieldId || !value.trim()) return;
    mutate(
      { fieldId, body: { value: value.trim(), note: note.trim() || undefined } },
      { onSuccess: closeOverrideModal },
    );
  }

  return (
    <Dialog open={Boolean(fieldId)} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Override "{fieldLabel}"</DialogTitle>
          <DialogDescription>
            Enter the correct value after reviewing the evidence. This is recorded as a human
            decision and marks the field resolved -- it won't re-enter the review queue.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="override-value" className="text-xs font-medium text-slate-600">
              Correct value
            </label>
            <Input
              id="override-value"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="Enter the value shown in the evidence"
              autoFocus
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="override-note" className="text-xs font-medium text-slate-600">
              Note (optional)
            </label>
            <Textarea
              id="override-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Why this value is correct, or anything worth flagging"
            />
          </div>

          {error && (
            <p className="text-sm text-risk-high">{error.message || "Failed to save override."}</p>
          )}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={closeOverrideModal}>
              Cancel
            </Button>
            <Button type="submit" variant="gold" disabled={isPending || !value.trim()}>
              {isPending ? "Saving…" : "Save override"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
