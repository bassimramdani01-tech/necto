// Types mirroring the server response schemas (server/necto_server/schemas/*).

export interface Health {
  status: string;
  database: string;
  version: string;
}

export interface RunSummary {
  id: string;
  name: string | null;
  status: string;
  schema_version: number;
  framework: string | null;
  started_at: string;
  finished_at: string | null;
  event_count: number;
  cost_usd: number;
  tokens: number;
  error_count: number;
}

export interface RunDetail extends RunSummary {
  sdk_version: string | null;
  meta: Record<string, unknown>;
}

export interface EventOut {
  seq: number;
  ts: string;
  type: string;
  from_ref: string | null;
  to_ref: string | null;
  payload: Record<string, unknown>;
}

export interface EventsPage {
  run_id: string;
  events: EventOut[];
  next_after_seq: number | null;
  has_more: boolean;
}

export interface GraphNode {
  id: string;
  kind: string;
  name: string | null;
  framework: string | null;
  model: string | null;
  provider: string | null;
  cost_usd: number;
  tokens: number;
  error_count: number;
  event_count: number;
  first_ts: string | null;
  last_ts: string | null;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  kind: string;
  count: number;
  cost_usd: number;
  tokens: number;
  latency_ms: number;
  error_count: number;
  error_rate: number;
  first_ts: string | null;
  last_ts: string | null;
}

export interface GraphStats {
  node_count: number;
  edge_count: number;
  event_count: number;
  run_count: number;
  cost_usd: number;
  tokens: number;
  error_count: number;
}

export interface GraphResponse {
  run_id: string | null;
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: GraphStats;
}

export interface ByModel {
  model: string;
  calls: number;
  tokens: number;
  cost_usd: number;
  avg_latency_ms: number | null;
}

export interface ByAgent {
  agent: string;
  calls: number;
  tokens: number;
  cost_usd: number;
}

export interface StatsResponse {
  scope: string;
  run_id: string | null;
  event_count: number;
  run_count: number;
  cost_usd: number;
  tokens: number;
  error_count: number;
  avg_llm_latency_ms: number | null;
  by_type: Record<string, number>;
  by_model: ByModel[];
  by_agent: ByAgent[];
}

export interface AgentOut {
  ref: string;
  name: string | null;
  kind: string;
  framework: string | null;
  first_seen: string;
  last_seen: string;
}

export interface ModelOut {
  ref: string;
  provider: string | null;
  name: string | null;
  first_seen: string;
  last_seen: string;
}
