import { describe, expect, it } from "vitest";

import { projectGraph } from "./projectGraph";
import type { EventOut } from "./types";

let seq = 0;

function ev(partial: Partial<EventOut> & Pick<EventOut, "type">): EventOut {
  seq += 1;
  return {
    seq,
    ts: partial.ts ?? new Date(Date.UTC(2026, 0, 1, 0, 0, seq)).toISOString(),
    type: partial.type,
    from_ref: partial.from_ref ?? null,
    to_ref: partial.to_ref ?? null,
    payload: partial.payload ?? {},
  };
}

describe("projectGraph", () => {
  it("returns an empty graph for no events", () => {
    const graph = projectGraph([], "run-1");

    expect(graph.nodes).toEqual([]);
    expect(graph.edges).toEqual([]);
    expect(graph.stats).toMatchObject({
      node_count: 0,
      edge_count: 0,
      event_count: 0,
      run_count: 1,
      tokens: 0,
    });
  });

  it("registers an agent from agent_start with its name and framework", () => {
    const graph = projectGraph(
      [
        ev({
          type: "agent_start",
          to_ref: "agent:planner",
          payload: { name: "Planner", framework: "langgraph" },
        }),
      ],
      "run-1",
    );

    const agent = graph.nodes.find((node) => node.id === "agent:planner");
    expect(agent).toBeDefined();
    expect(agent?.kind).toBe("agent");
    expect(agent?.name).toBe("Planner");
    expect(agent?.framework).toBe("langgraph");
    expect(agent?.event_count).toBe(1);
    expect(agent?.first_ts).toBeTruthy();
    expect(agent?.last_ts).toBe(agent?.first_ts);
  });

  it("attributes an llm_call to both ends but counts totals once", () => {
    const graph = projectGraph(
      [
        ev({ type: "agent_start", to_ref: "agent:planner", payload: { name: "Planner" } }),
        ev({
          type: "llm_call",
          from_ref: "agent:planner",
          to_ref: "model:openai:gpt-4o-mini",
          payload: {
            provider: "openai",
            model: "gpt-4o-mini",
            input_tokens: 100,
            output_tokens: 20,
            cost_usd: 0.0005,
            latency_ms: 300,
          },
        }),
      ],
      "run-1",
    );

    const edge = graph.edges.find((item) => item.kind === "llm_call");
    expect(edge).toMatchObject({
      source: "agent:planner",
      target: "model:openai:gpt-4o-mini",
      count: 1,
      tokens: 120,
      cost_usd: 0.0005,
      latency_ms: 300,
    });

    const model = graph.nodes.find((node) => node.id === "model:openai:gpt-4o-mini");
    expect(model?.kind).toBe("model");
    expect(model?.model).toBe("gpt-4o-mini");
    expect(model?.provider).toBe("openai");
    // both ends carry the tokens so node cards look right …
    expect(model?.tokens).toBe(120);
    expect(graph.nodes.find((node) => node.id === "agent:planner")?.tokens).toBe(120);
    // … while the totals are summed from the edge, so nothing is double counted
    expect(graph.stats.tokens).toBe(120);
    expect(graph.stats.cost_usd).toBeCloseTo(0.0005);
  });

  it("counts a failed tool result as an edge error", () => {
    const graph = projectGraph(
      [
        ev({
          type: "tool_call",
          from_ref: "agent:planner",
          to_ref: "tool:web_search",
          payload: { name: "web_search" },
        }),
        ev({
          type: "tool_result",
          from_ref: "tool:web_search",
          to_ref: "agent:planner",
          payload: { ok: false },
        }),
      ],
      "run-1",
    );

    const failed = graph.edges.find((item) => item.kind === "tool_result");
    expect(failed?.error_count).toBe(1);
    expect(failed?.error_rate).toBe(1);
  });

  it("counts error events against the originating node", () => {
    const graph = projectGraph(
      [
        ev({ type: "agent_start", to_ref: "agent:planner", payload: { name: "Planner" } }),
        ev({
          type: "error",
          from_ref: "agent:planner",
          payload: { message: "tool blew up" },
        }),
      ],
      "run-1",
    );

    const agent = graph.nodes.find((node) => node.id === "agent:planner");
    expect(agent?.error_count).toBe(1);
    expect(graph.stats.error_count).toBe(1);
  });

  it("projects exactly the replay slice it is given", () => {
    const events = [
      ev({ type: "agent_start", to_ref: "agent:a", payload: { name: "A" } }),
      ev({ type: "handoff", from_ref: "agent:a", to_ref: "agent:b" }),
      ev({ type: "agent_start", to_ref: "agent:b", payload: { name: "B" } }),
    ];

    expect(projectGraph(events.slice(0, 1), "run-1").edges).toHaveLength(0);

    const full = projectGraph(events, "run-1");
    expect(full.nodes).toHaveLength(2);
    expect(full.edges).toHaveLength(1);
    expect(full.stats.event_count).toBe(3);
  });

  it("reports no runs for the aggregate topology", () => {
    const graph = projectGraph([ev({ type: "agent_start", to_ref: "agent:a" })], null);
    expect(graph.run_id).toBeNull();
    expect(graph.stats.run_count).toBe(0);
  });
});
