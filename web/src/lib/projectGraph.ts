import type { EventOut, GraphEdge, GraphNode, GraphResponse, GraphStats } from "./types";

const REF_KINDS = new Set(["agent", "tool", "model", "external", "state"]);

function kindOf(ref: string): string {
  const prefix = ref.split(":")[0];
  return REF_KINDS.has(prefix) ? prefix : "external";
}

function num(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function str(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

/**
 * Rebuilds a run graph from raw events up to a point in time — the same projection
 * the server performs (docs/SCHEMA.md §7), so a replay looks like the live graph.
 */
export function projectGraph(events: EventOut[], runId: string | null): GraphResponse {
  const nodes = new Map<string, GraphNode>();
  const edges = new Map<string, GraphEdge>();

  const touch = (ref: string | null): GraphNode | null => {
    if (!ref) return null;
    let node = nodes.get(ref);
    if (!node) {
      node = {
        id: ref,
        kind: kindOf(ref),
        name: null,
        framework: null,
        model: null,
        provider: null,
        cost_usd: 0,
        tokens: 0,
        error_count: 0,
        event_count: 0,
        first_ts: null,
        last_ts: null,
      };
      nodes.set(ref, node);
    }
    return node;
  };

  for (const event of events) {
    const from = touch(event.from_ref);
    const to = touch(event.to_ref);

    for (const node of [from, to]) {
      if (!node) continue;
      node.event_count += 1;
      node.first_ts = node.first_ts ?? event.ts;
      node.last_ts = event.ts;
    }

    const payload = event.payload ?? {};
    const tokens = num(payload.input_tokens) + num(payload.output_tokens);
    const cost = num(payload.cost_usd);

    if (event.type === "agent_start" && to) {
      to.name = str(payload.name) ?? to.id;
      to.framework = str(payload.framework) ?? to.framework;
    }

    if (event.type === "llm_call" && to && to.name === null) {
      to.name = str(payload.model) ?? to.id.split(":").pop() ?? to.id;
    }

    if (event.type === "tool_call" && to && to.name === null) {
      to.name = str(payload.name) ?? to.id.split(":").pop() ?? to.id;
    }

    if (event.type === "llm_call") {
      if (to) {
        to.tokens += tokens;
        to.cost_usd += cost;
        to.model = str(payload.model) ?? to.model;
        to.provider = str(payload.provider) ?? to.provider;
      }
    }

    if (event.type === "error" && from) {
      from.error_count += 1;
    }

    if (from && to && from.id !== to.id) {
      const id = `${from.id}->${to.id}:${event.type}`;
      let edge = edges.get(id);
      if (!edge) {
        edge = {
          id,
          source: from.id,
          target: to.id,
          kind: event.type,
          count: 0,
          cost_usd: 0,
          tokens: 0,
          latency_ms: 0,
          error_count: 0,
          error_rate: 0,
          first_ts: null,
          last_ts: null,
        };
        edges.set(id, edge);
      }
      edge.count += 1;
      edge.first_ts = edge.first_ts ?? event.ts;
      edge.last_ts = event.ts;
      if (event.type === "llm_call") {
        edge.tokens += tokens;
        edge.cost_usd += cost;
        edge.latency_ms = num(payload.latency_ms);
      }
      if (event.type === "tool_result" && payload.ok === false) {
        edge.error_count += 1;
      }
    }
  }

  const edgeList = [...edges.values()].map((edge) => ({
    ...edge,
    error_rate: edge.count > 0 ? edge.error_count / edge.count : 0,
  }));
  const nodeList = [...nodes.values()].sort((a, b) =>
    String(a.first_ts ?? "").localeCompare(String(b.first_ts ?? "")),
  );

  const stats: GraphStats = {
    node_count: nodeList.length,
    edge_count: edgeList.length,
    event_count: events.length,
    run_count: runId ? 1 : 0,
    cost_usd: edgeList.reduce((sum, edge) => sum + edge.cost_usd, 0),
    tokens: edgeList
      .filter((edge) => edge.kind === "llm_call")
      .reduce((sum, edge) => sum + edge.tokens, 0),
    error_count: nodeList.reduce((sum, node) => sum + node.error_count, 0),
  };

  return { run_id: runId, nodes: nodeList, edges: edgeList, stats };
}
