import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type { EventOut } from "./types";

export const RUN_PAGE_SIZE = 50;

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 5_000,
    retry: 0,
  });
}

export interface RunFilters {
  status?: string;
  q?: string;
  framework?: string;
  sort?: string;
}

export function useRuns(filters: RunFilters = {}) {
  return useInfiniteQuery({
    queryKey: [
      "runs",
      filters.status ?? "all",
      filters.q ?? "",
      filters.framework ?? "",
      filters.sort ?? "recent",
    ],
    queryFn: ({ pageParam }) =>
      api.listRuns({ ...filters, limit: RUN_PAGE_SIZE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((count, page) => count + page.runs.length, 0);
      return loaded < lastPage.total ? loaded : undefined;
    },
    // A running run's status/counters must not go stale while the list is open.
    refetchInterval: 5_000,
  });
}

export function useFrameworks() {
  return useQuery({ queryKey: ["frameworks"], queryFn: api.listFrameworks });
}

export function useRun(runId: string | null) {
  return useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.getRun(runId as string),
    enabled: runId !== null,
    // Poll faster while the run is still going; stop once it finishes.
    refetchInterval: (query) => (query.state.data?.status === "running" ? 4_000 : false),
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

export function useStats(runId?: string | null) {
  return useQuery({
    queryKey: ["stats", runId ?? "global"],
    queryFn: () => api.getStats(runId ?? undefined),
    refetchInterval: 10_000,
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
