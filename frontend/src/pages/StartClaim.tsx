import { useRef, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { AlertCircle, ArrowLeft, File, Loader2, UploadCloud, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useCreateClaim } from "@/hooks/useClaim";

/**
 * Upload entry point. Deliberately has NO "line of business" picker --
 * POST /api/claims (app/routers/claims.py) doesn't accept one; LOB is
 * classified automatically from the documents themselves
 * (agents/lob_classifier_agent.py, the "classify" pipeline stage). A
 * dropdown here that the backend silently ignored would be worse than no
 * dropdown at all.
 */
export default function StartClaim() {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const { mutate, isPending, error } = useCreateClaim();

  function addFiles(incoming: FileList | null) {
    if (!incoming) return;
    setFiles((prev) => {
      const existingNames = new Set(prev.map((f) => f.name));
      const additions = Array.from(incoming).filter((f) => !existingNames.has(f.name));
      return [...prev, ...additions];
    });
  }

  function removeFile(name: string) {
    setFiles((prev) => prev.filter((f) => f.name !== name));
  }

  function handleSubmit() {
    if (files.length === 0) return;
    mutate(files, {
      onSuccess: ({ claim_id }) => navigate(`/processing/${claim_id}`),
    });
  }

  return (
    <div className="flex h-screen flex-col items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-lg">
        <Link to="/claims" className="mb-4 inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-ink-900">
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to dashboard
        </Link>

        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-panel">
          <h1 className="text-lg font-semibold text-ink-950">Submit a new claim</h1>
          <p className="mt-1 text-sm text-slate-500">
            Upload every document for this claim -- FNOL, photos, correspondence, estimates.
            ClaimLens will classify the line of business and extract fields automatically.
          </p>

          <div
            className={cn(
              "mt-5 flex flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed p-8 text-center transition-colors",
              isDragging ? "border-gold-500 bg-gold-500/5" : "border-slate-300 bg-slate-50",
            )}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setIsDragging(false);
              addFiles(e.dataTransfer.files);
            }}
          >
            <UploadCloud className="h-6 w-6 text-slate-400" />
            <p className="text-sm text-slate-600">Drag files here, or</p>
            <Button type="button" size="sm" variant="outline" onClick={() => inputRef.current?.click()}>
              Browse files
            </Button>
            <input
              ref={inputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => addFiles(e.target.files)}
              accept=".pdf,.docx,.pptx,.png,.jpg,.jpeg,.html,.htm"
            />
          </div>

          {files.length > 0 && (
            <ul className="mt-4 flex flex-col gap-1.5">
              {files.map((file) => (
                <li
                  key={file.name}
                  className="flex items-center justify-between gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm"
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <File className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                    <span className="truncate text-ink-900">{file.name}</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => removeFile(file.name)}
                    className="shrink-0 text-slate-400 hover:text-risk-high"
                    aria-label={`Remove ${file.name}`}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}

          {error && (
            <div className="mt-4 flex items-start gap-2 rounded-md border border-risk-high/30 bg-risk-high-bg p-3 text-sm text-risk-high">
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{error.message || "Failed to submit claim."}</span>
            </div>
          )}

          <Button
            className="mt-5 w-full"
            variant="gold"
            disabled={files.length === 0 || isPending}
            onClick={handleSubmit}
          >
            {isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Uploading…
              </>
            ) : (
              `Submit ${files.length > 0 ? `(${files.length} file${files.length === 1 ? "" : "s"})` : ""}`
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
