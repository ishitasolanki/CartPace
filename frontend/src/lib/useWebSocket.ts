/** WebSocket hook with reconnect.
 *
 * The backend does not replay history to a reconnecting client -- it only
 * ever broadcasts live events (backend/ws.py). So "reconnect without
 * duplicating feed entries" (build spec Phase 7, integration point 3) can't
 * be solved by de-duplicating a replayed stream, because there is none: a
 * gap while disconnected is a genuine gap. `onReconnect` exists so the
 * caller can refetch current state (decisions, day stats, certificate) over
 * the REST API to close that gap, rather than silently showing a feed with a
 * hole in it.
 */

import { useEffect, useRef, useState } from "react";
import { wsUrl } from "./api";
import type { WsMessage } from "./types";

export type WsStatus = "connecting" | "open" | "closed";

const BACKOFF_MS = [500, 1000, 2000, 4000, 8000];

export function useWebSocket(
  runId: number | null,
  onMessage: (msg: WsMessage) => void,
  onReconnect?: () => void,
) {
  const [status, setStatus] = useState<WsStatus>("connecting");
  const onMessageRef = useRef(onMessage);
  const onReconnectRef = useRef(onReconnect);

  // Assigning a ref's `.current` belongs in an effect, not the render body:
  // React may render without committing (e.g. an interrupted concurrent
  // render), and a mutation during that discarded render would still have
  // happened as a side effect. Two effects, not one, so a change to either
  // callback updates its own ref without re-running the other's.
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);
  useEffect(() => {
    onReconnectRef.current = onReconnect;
  }, [onReconnect]);

  useEffect(() => {
    if (runId === null) return;

    let attempt = 0;
    let closedByUs = false;
    let ws: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;

    function connect() {
      setStatus("connecting");
      ws = new WebSocket(wsUrl(runId!));

      ws.onopen = () => {
        setStatus("open");
        if (attempt > 0) onReconnectRef.current?.();
        attempt = 0;
      };

      ws.onmessage = (ev) => {
        try {
          onMessageRef.current(JSON.parse(ev.data) as WsMessage);
        } catch {
          // A malformed frame should not take down the connection.
        }
      };

      ws.onclose = (ev) => {
        setStatus("closed");
        // 4401/4404: the server rejected auth or the run doesn't exist.
        // Retrying would just repeat the rejection.
        if (closedByUs || ev.code === 4401 || ev.code === 4404) return;
        const delay = BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)];
        attempt += 1;
        timer = setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      closedByUs = true;
      if (timer) clearTimeout(timer);
      ws?.close();
    };
  }, [runId]);

  return status;
}
