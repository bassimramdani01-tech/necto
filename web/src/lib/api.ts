import type {
  AgentOut,
  EventsPage,
  GraphResponse,
  Health,
  ModelOut,
  RunDetail,
  RunSummary,
  StatsResponse,
} from "./types";

// Empty in dev: Vite proxies /v1 and /healthz to the API server.
const BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function readError(response: Response): Promise<string> {
  try {
    return (await response.text()) || `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    throw new ApiError(response.status, await readError(response));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export interface RunListOptions {
  status?: string;
  q?: string;
  framework?: string;
  sort?: string;
  limit?: number;
  offset?: number;
}

export interface RunListResult {
  runs: RunSummary[];
  total: number;
}

export const api = {
  health: () => request<Health>("/healthz"),

  async listRuns(options: RunListOptions = {}): Promise<RunListResult> {
    const params = new URLSearchParams();
    if (options.status) params.set("status", options.status);
    if (options.q) params.set("q", options.q);
    if (options.framework) params.set("framework", options.framework);
    if (options.sort) params.set("sort", options.sort);
    if (options.limit != null) params.set("limit", String(options.limit));
    if (options.offset != null) params.set("offset", String(options.offset));
    const query = params.toString();

    const response = await fetch(`${BASE}/v1/runs${query ? `?${query}` : ""}`, {
      headers: { "Content-Type": "application/json" },
    });
    if (!response.ok) {
      throw new ApiError(response.status, await readError(response));
    }
    const runs = (await response.json()) as RunSummary[];
    return { runs, total: Number(response.headers.get("X-Total-Count") ?? runs.length) };
  },

  listFrameworks: () => request<string[]>("/v1/frameworks"),

  getRun: (runId: string) => request<RunDetail>(`/v1/runs/${runId}`),

  getEvents: (runId: string, afterSeq = 0, limit = 200) =>
    request<EventsPage>(`/v1/runs/${runId}/events?after_seq=${afterSeq}&limit=${limit}`),

  getGraph: (runId: string) => request<GraphResponse>(`/v1/runs/${runId}/graph`),

  getTopology: () => request<GraphResponse>("/v1/topology"),

  getStats: (runId?: string) =>
    request<StatsResponse>(`/v1/stats${runId ? `?run_id=${runId}` : ""}`),

  listAgents: () => request<AgentOut[]>("/v1/agents"),

  listModels: () => request<ModelOut[]>("/v1/models"),
};
