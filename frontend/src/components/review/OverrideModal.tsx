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
  const [sourceDocumentId, setSourceDocumentId] = useState("");
  const [note, setNote] = useState("");

  const fieldId = overrideModalFieldId;
  const field = fieldId ? claim.extracted_fields[fieldId] : undefined;
  const fieldLabel =
    (fieldId &&
      claim.lob_schema?.sections
        .flatMap((s) => s.fields)
        .find((f) => f.field_id === fieldId)?.label) ||
    fieldId;

  // The model's own cited evidence documents, offered first in the
  // dropdown -- an adjuster confirming the model looked in the right
  // place is the common case; picking a different document is the
  // interesting signal worth surfacing prominently too.
  const citedDocIds = new Set(
    (field?.evidence_block_ids ?? [])
      .map((blockId) => claim.documents.find((d) => d.blocks.some((b) => b.block_id === blockId))?.doc_id)
      .filter((id): id is string => Boolean(id)),
  );
  const citedDocs = claim.documents.filter((d) => citedDocIds.has(d.doc_id));
  const otherDocs = claim.documents.filter((d) => !citedDocIds.has(d.doc_id));

  useEffect(() => {
    if (fieldId && field) {
      setValue(formatValue(field.value) === "—" ? "" : String(field.value));
      setSourceDocumentId(citedDocs[0]?.doc_id ?? "");
      setNote("");
      reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fieldId]);

  function handleOpenChange(open: boolean) {
    if (!open) closeOverrideModal();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!fieldId || !value.trim() || !sourceDocumentId) return;
    mutate(
      {
        fieldId,
        body: { value: value.trim(), source_document_id: sourceDocumentId, note: note.trim() || undefined },
      },
      { onSuccess: closeOverrideModal },
    );
  }

  return (
    <Dialog open={Boolean(fieldId)} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Override "{fieldLabel}"</DialogTitle>
          <DialogDescription>
            Enter the correct value after reviewing the evidence, and confirm which document you
            found it in. This is recorded as a human decision and marks the field resolved -- it
            won't re-enter the review queue. Where you say you found it is tracked separately from
            what the model cited, which is exactly the signal that helps find where extraction is
            looking in the wrong place.
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
            <label htmlFor="override-source-doc" className="text-xs font-medium text-slate-600">
              Which document did you find this value in?
            </label>
            <select
              id="override-source-doc"
              value={sourceDocumentId}
              onChange={(e) => setSourceDocumentId(e.target.value)}
              className="flex h-9 w-full rounded-md border border-slate-300 bg-white px-3 py-1 text-sm text-ink-950 focus-visible:border-ink-700"
            >
              <option value="" disabled>
                Select a document…
              </option>
              {citedDocs.length > 0 && (
                <optgroup label="Cited by the model">
                  {citedDocs.map((d) => (
                    <option key={d.doc_id} value={d.doc_id}>
                      {d.source_file.split("/").pop()}
                    </option>
                  ))}
                </optgroup>
              )}
              {otherDocs.length > 0 && (
                <optgroup label={citedDocs.length > 0 ? "Other documents" : "Documents"}>
                  {otherDocs.map((d) => (
                    <option key={d.doc_id} value={d.doc_id}>
                      {d.source_file.split("/").pop()}
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
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
            <Button type="submit" variant="gold" disabled={isPending || !value.trim() || !sourceDocumentId}>
              {isPending ? "Saving…" : "Save override"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
