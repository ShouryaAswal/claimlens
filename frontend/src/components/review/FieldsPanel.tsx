import { AlertCircle } from "lucide-react";

import { RiskBadge } from "@/components/shared/RiskBadge";
import { cn, formatValue, titleCase } from "@/lib/utils";
import { useReviewUiStore } from "@/store/reviewUiStore";
import type { ClaimState } from "@/types/claim";

interface FieldsPanelProps {
  claim: ClaimState;
}

export function FieldsPanel({ claim }: FieldsPanelProps) {
  const selectedFieldId = useReviewUiStore((s) => s.selectedFieldId);
  const selectField = useReviewUiStore((s) => s.selectField);

  if (!claim.lob_schema) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-slate-500">
        No schema resolved for this claim yet.
      </div>
    );
  }

  return (
    <div className="scrollbar-thin flex h-full flex-col overflow-y-auto">
      <div className="border-b border-slate-200 px-4 py-3">
        <h2 className="text-sm font-semibold text-ink-950">Fields</h2>
        <p className="text-xs text-slate-500">
          {claim.lob_schema.sections.length} sections ·{" "}
          {claim.lob_schema.sections.reduce((sum, s) => sum + s.fields.length, 0)} fields
        </p>
      </div>

      {claim.lob_schema.sections.map((section) => (
        <div key={section.section_id} className="border-b border-slate-100">
          <div className="sticky top-0 bg-slate-50 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            {titleCase(section.section_id)}
          </div>
          <ul>
            {section.fields.map((fieldDef) => {
              const extracted = claim.extracted_fields[fieldDef.field_id];
              const verification = claim.field_verifications[fieldDef.field_id];
              const isSelected = selectedFieldId === fieldDef.field_id;
              const isMissingRequired =
                fieldDef.required && (!extracted || extracted.status === "missing");

              return (
                <li key={fieldDef.field_id}>
                  <button
                    type="button"
                    onClick={() => selectField(fieldDef.field_id)}
                    className={cn(
                      "flex w-full items-start justify-between gap-3 border-l-2 border-transparent px-4 py-2.5 text-left transition-colors hover:bg-slate-50",
                      isSelected && "border-l-gold-500 bg-slate-100/80",
                    )}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="truncate text-sm font-medium text-ink-950">
                          {fieldDef.label}
                        </span>
                        {fieldDef.required && (
                          <span className="text-xs text-gold-600" title="Required field">
                            *
                          </span>
                        )}
                      </div>
                      <p className="font-data truncate text-xs text-slate-500">
                        {formatValue(extracted?.value)}
                      </p>
                    </div>
                    {verification ? (
                      <RiskBadge risk={verification.risk_level} compact />
                    ) : isMissingRequired ? (
                      <AlertCircle className="h-4 w-4 shrink-0 text-risk-high" />
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}
