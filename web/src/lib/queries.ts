import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

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
