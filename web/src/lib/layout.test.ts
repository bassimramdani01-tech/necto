import { describe, expect, it } from "vitest";

import {
  COLUMN_WIDTH,
  GRAPH_ORIGIN,
  KIND_COLUMN,
  ROW_HEIGHT,
  layoutGraph,
  orderAgents,
} from "./layout";
import type { GraphEdge, GraphNode } from "./types";

function node(
  id: string,
  kind: string,
  firstTs: string | null = "2026-01-01T00:00:00.000Z",
): GraphNode {
  return {
    id,
    kind,
    name: null,
    framework: null,
    model: null,
    provider: null,
    cost_usd: 0,
    tokens: 0,
    error_count: 0,
    event_count: 0,
    first_ts: firstTs,
    last_ts: firstTs,
  };
}

function edge(source: string, target: string, kind = "handoff"): GraphEdge {
  return {
    id: `${source}->${target}:${kind}`,
    source,
    target,
    kind,
    count: 1,
    cost_usd: 0,
    tokens: 0,
    latency_ms: 0,
    error_count: 0,
    error_rate: 0,
    first_ts: null,
    last_ts: null,
  };
}

const positionOf = (laid: ReturnType<typeof layoutGraph>, id: string) => {
  const found = laid.find((item) => item.id === id);
  if (!found) throw new Error(`no node ${id}`);
  return found.position;
};

describe("orderAgents", () => {
  it("follows the handoff chain regardless of input order", () => {
    const agents = [node("agent:c", "agent"), node("agent:a", "agent"), node("agent:b", "agent")];
    const edges = [edge("agent:a", "agent:b"), edge("agent:b", "agent:c")];

    expect(orderAgents(agents, edges).map((agent) => agent.id)).toEqual([
      "agent:a",
      "agent:b",
      "agent:c",
    ]);
  });

  it("keeps every agent exactly once even in a handoff cycle", () => {
    const agents = [node("agent:a", "agent"), node("agent:b", "agent")];
    const edges = [edge("agent:a", "agent:b"), edge("agent:b", "agent:a")];

    const ordered = orderAgents(agents, edges);
    expect(ordered).toHaveLength(2);
    expect(new Set(ordered.map((agent) => agent.id))).toEqual(new Set(["agent:a", "agent:b"]));
  });
});

describe("layoutGraph", () => {
  it("puts each kind in its own column", () => {
    const laid = layoutGraph(
      [node("agent:a", "agent"), node("model:m", "model"), node("tool:t", "tool")],
      [],
      null,
      null,
    );

    expect(positionOf(laid, "agent:a").x).toBe(GRAPH_ORIGIN + KIND_COLUMN.agent * COLUMN_WIDTH);
    expect(positionOf(laid, "model:m").x).toBe(GRAPH_ORIGIN + KIND_COLUMN.model * COLUMN_WIDTH);
    expect(positionOf(laid, "tool:t").x).toBe(GRAPH_ORIGIN + KIND_COLUMN.tool * COLUMN_WIDTH);
  });

  it("never places two nodes on the same spot", () => {
    const nodes = Array.from({ length: 6 }, (_, index) => node(`agent:${index}`, "agent"));
    const laid = layoutGraph(nodes, [], null, null);

    const spots = new Set(laid.map((item) => `${item.position.x}:${item.position.y}`));
    expect(spots.size).toBe(laid.length);
  });

  it("aligns a model with the agent that calls it", () => {
    const laid = layoutGraph(
      [node("agent:a", "agent"), node("model:m", "model")],
      [edge("agent:a", "model:m", "llm_call")],
      null,
      null,
    );

    expect(positionOf(laid, "model:m").y).toBe(positionOf(laid, "agent:a").y);
  });

  it("stacks unanchored nodes below the agent column", () => {
    const laid = layoutGraph(
      [node("agent:a", "agent"), node("tool:t", "tool")],
      [],
      null,
      null,
    );

    expect(positionOf(laid, "tool:t").y).toBe(GRAPH_ORIGIN + (1 + KIND_COLUMN.tool) * ROW_HEIGHT);
  });

  it("marks the selection and dims everything outside its neighbourhood", () => {
    const laid = layoutGraph(
      [node("agent:a", "agent"), node("agent:b", "agent"), node("agent:c", "agent")],
      [edge("agent:a", "agent:b")],
      "agent:a",
      new Set(["agent:a", "agent:b"]),
    );

    const dataOf = (id: string) =>
      laid.find((item) => item.id === id)?.data as { dimmed?: boolean } | undefined;

    expect(laid.find((item) => item.id === "agent:a")?.selected).toBe(true);
    expect(dataOf("agent:a")?.dimmed).toBe(false);
    expect(dataOf("agent:b")?.dimmed).toBe(false);
    expect(dataOf("agent:c")?.dimmed).toBe(true);
  });
});
