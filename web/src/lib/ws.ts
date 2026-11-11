import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { EventOut } from "./types";

export type LiveMessage =
  | { type: "hello"; run_id: string; run_status: string; last_seq: number }
  | { type: "events"; run_id: string; events: EventOut[] }
  | { type: "run_finished"; run_id: string; status: string; finished_at: string };

export interface LiveState {
  connected: boolean;
  finished: boolean;
  lastSeq: number;
  /** Events from the most recent push — used to briefly highlight new edges. */
  recentEvents: EventOut[];
}

function liveUrl(runId: string): string {
  const configured = import.meta.env.VITE_WS_BASE;
  if (configured) {
    return `${configured.replace(/\/$/, "")}/v1/live/runs/${runId}`;
  }
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/v1/live/runs/${runId}`;
}

/**
 * Subscribes to a run's live event stream. New events invalidate the relevant
 * queries, so the graph, header metrics and the replay timeline all refresh.
 */
export function useLiveRun(runId: string | null, enabled: boolean): LiveState {
  const queryClient = useQueryClient();
  const [state, setState] = useState<LiveState>({
    connected: false,
    finished: false,
    lastSeq: 0,
    recentEvents: [],
  });
  const highlightTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!runId || !enabled) {
      return;
    }

    let socket: WebSocket | null = null;
    let stopped = false;
    let retryTimer: number | undefined;

    const connect = () => {
      socket = new WebSocket(liveUrl(runId));

      socket.onopen = () => {
        setState((previous) => ({ ...previous, connected: true }));
      };

      socket.onmessage = (event) => {
        let message: LiveMessage;
        try {
          message = JSON.parse(event.data as string) as LiveMessage;
        } catch {
          return;
        }

        if (message.type === "hello") {
          setState((previous) => ({ ...previous, connected: true, lastSeq: message.last_seq }));
          return;
        }

        if (message.type === "events") {
          const lastSeq = message.events.reduce(
            (highest, item) => Math.max(highest, item.seq),
            0,
          );
          setState((previous) => ({
            ...previous,
            lastSeq: Math.max(previous.lastSeq, lastSeq),
            recentEvents: message.events,
          }));
          void queryClient.invalidateQueries({ queryKey: ["graph", runId] });
          void queryClient.invalidateQueries({ queryKey: ["events", runId] });
          void queryClient.invalidateQueries({ queryKey: ["run", runId] });
          void queryClient.invalidateQueries({ queryKey: ["runs"] });

          window.clearTimeout(highlightTimer.current);
          highlightTimer.current = window.setTimeout(() => {
            setState((previous) => ({ ...previous, recentEvents: [] }));
          }, 2500);
          return;
        }

        if (message.type === "run_finished") {
          setState((previous) => ({ ...previous, finished: true }));
          void queryClient.invalidateQueries({ queryKey: ["run", runId] });
          void queryClient.invalidateQueries({ queryKey: ["runs"] });
          void queryClient.invalidateQueries({ queryKey: ["stats", "global"] });
        }
      };

      socket.onclose = () => {
        setState((previous) => ({ ...previous, connected: false }));
        if (!stopped) {
          retryTimer = window.setTimeout(connect, 1500);
        }
      };

      socket.onerror = () => {
        socket?.close();
      };
    };

    connect();

    return () => {
      stopped = true;
      window.clearTimeout(retryTimer);
      window.clearTimeout(highlightTimer.current);
      socket?.close();
    };
  }, [runId, enabled, queryClient]);

  return state;
}
