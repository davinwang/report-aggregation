// SSE subscription to /api/stream (ingestion progress + freshness).
// Returns connection status and the latest event.
import { useEffect, useRef, useState } from "react";

export interface SSEEvent {
  event: string;
  data: unknown;
  ts?: string;
}

export type SSEStatus = "connecting" | "open" | "closed" | "error";

export function useSSE(onEvent?: (evt: SSEEvent) => void): { status: SSEStatus; last: SSEEvent | null } {
  const [status, setStatus] = useState<SSEStatus>("connecting");
  const [last, setLast] = useState<SSEEvent | null>(null);
  const cbRef = useRef(onEvent);
  cbRef.current = onEvent;

  useEffect(() => {
    let es: EventSource | null = null;
    let retry: number | undefined;
    let closed = false;

    const connect = () => {
      if (closed) return;
      es = new EventSource("/api/stream");
      setStatus("connecting");
      es.onopen = () => setStatus("open");
      es.onerror = () => {
        setStatus("error");
        es?.close();
        // reconnect with backoff (EventSource auto-reconnect is disabled after close)
        retry = window.setTimeout(connect, 5000);
      };
      const handler = (e: MessageEvent) => {
        let data: unknown = e.data;
        try {
          data = JSON.parse(e.data);
        } catch {
          /* keep raw */
        }
        const evt: SSEEvent = { event: e.type || "message", data };
        setLast(evt);
        cbRef.current?.(evt);
      };
      // named events emitted by the backend
      ["hello", "ingest:start", "ingest:end", "message"].forEach((name) =>
        es!.addEventListener(name, handler as EventListener),
      );
    };

    connect();
    return () => {
      closed = true;
      if (retry) window.clearTimeout(retry);
      es?.close();
      setStatus("closed");
    };
  }, []);

  return { status, last };
}
