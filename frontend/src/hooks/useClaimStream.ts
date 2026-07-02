import { useEffect, useRef, useState } from "react";

import { API_BASE_URL } from "@/lib/api";
import type { StageEvent } from "@/types/claim";

interface UseClaimStreamOptions {
  /** Called once a `stage=pipeline, status=done` event arrives. */
  onDone?: () => void;
  /** Called once a `stage=pipeline, status=error` event arrives. */
  onError?: (detail: Record<string, unknown> | undefined) => void;
}

interface UseClaimStreamResult {
  events: StageEvent[];
  latest: StageEvent | null;
  connected: boolean;
}

/**
 * Subscribes to GET /api/claims/{id}/stream and accumulates every stage
 * event for the lifetime of the pipeline run. Closes itself on the
 * terminal `stage=pipeline, status=done|error` event (the backend also
 * closes the stream at that point -- see app/sse.py's sentinel).
 *
 * Known gap (documented in app/sse.py): events published before this
 * hook subscribes are missed, not buffered. Callers that need a gapless
 * progress bar should mount this immediately after the POST /api/claims
 * response, same as the backend's own doc note.
 */
export function useClaimStream(
  claimId: string | undefined,
  { onDone, onError }: UseClaimStreamOptions = {},
): UseClaimStreamResult {
  const [events, setEvents] = useState<StageEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const onDoneRef = useRef(onDone);
  const onErrorRef = useRef(onError);
  onDoneRef.current = onDone;
  onErrorRef.current = onError;

  useEffect(() => {
    if (!claimId) return;
    setEvents([]);

    const source = new EventSource(`${API_BASE_URL}/api/claims/${claimId}/stream`);
    setConnected(true);

    source.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as StageEvent;
        setEvents((prev) => [...prev, event]);
        if (event.stage === "pipeline" && event.status === "done") {
          onDoneRef.current?.();
          source.close();
          setConnected(false);
        } else if (event.stage === "pipeline" && event.status === "error") {
          onErrorRef.current?.(event.detail);
          source.close();
          setConnected(false);
        }
      } catch {
        // Heartbeat/comment lines (": keep-alive") never reach onmessage,
        // but ignore anything unparseable defensively.
      }
    };

    source.onerror = () => {
      setConnected(false);
    };

    return () => {
      source.close();
      setConnected(false);
    };
  }, [claimId]);

  return { events, latest: events[events.length - 1] ?? null, connected };
}
