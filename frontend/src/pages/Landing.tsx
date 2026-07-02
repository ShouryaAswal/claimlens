import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/**
 * Day 2 scaffold stub. Day 3 replaces this with the real two-button
 * Adjuster/Client Portal landing page per the Sprint 5 plan. For now this
 * exists so `/` renders something and doubles as the Day 2 checkpoint
 * tool: "open the review page for yesterday's processed claim (hardcode
 * the ID in the URL for now)" without editing the URL bar by hand.
 */
export default function Landing() {
  const navigate = useNavigate();
  const [claimId, setClaimId] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (claimId.trim()) navigate(`/claims/${claimId.trim()}`);
  }

  return (
    <div className="flex h-screen flex-col items-center justify-center gap-6 bg-slate-50 px-4">
      <div className="text-center">
        <h1 className="text-xl font-semibold text-ink-950">ClaimLens</h1>
        <p className="mt-1 text-sm text-slate-500">Adjuster review scaffold &middot; Day 2</p>
      </div>
      <form onSubmit={handleSubmit} className="flex w-full max-w-sm gap-2">
        <Input
          value={claimId}
          onChange={(e) => setClaimId(e.target.value)}
          placeholder="CLM-xxxxxxxx"
          className="font-data"
        />
        <Button type="submit">Open review</Button>
      </form>
      <p className="max-w-sm text-center text-xs text-slate-400">
        Start/Processing/Dashboard pages land in Day 3. Paste a claim ID from a completed
        pipeline run to jump straight into the review page.
      </p>
    </div>
  );
}
