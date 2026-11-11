import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type { EventOut } from "./types";

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 5_000,
    retry: 0,
  });
}

export function useRuns(status?: string) {
  return useQuery({
    queryKey: ["runs", status ?? "all"],
    queryFn: () => api.listRuns({ status }),
  });
}

export function useRun(runId: string | null) {
  return useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.getRun(runId as string),
    enabled: runId !== null,
  });
}

export function useRunGraph(runId: string | null) {
  return useQuery({
    queryKey: ["graph", runId],
    queryFn: () => api.getGraph(runId as string),
    enabled: runId !== null,
  });
}

/** Every event of a run, paged through the API — the basis for replay. */
export function useRunEvents(runId: string | null) {
  return useQuery({
    queryKey: ["events", runId],
    queryFn: async () => {
      const all: EventOut[] = [];
      let afterSeq = 0;
      for (let page = 0; page < 50; page += 1) {
        const result = await api.getEvents(runId as string, afterSeq, 1000);
        all.push(...result.events);
        if (!result.has_more || result.next_after_seq === null) break;
        afterSeq = result.next_after_seq;
      }
      return all;
    },
    enabled: runId !== null,
  });
}

export function useGlobalStats() {
  return useQuery({
    queryKey: ["stats", "global"],
    queryFn: () => api.getStats(),
    refetchInterval: 10_000,
  });
}

export function useTopology() {
  return useQuery({ queryKey: ["topology"], queryFn: api.getTopology });
}
