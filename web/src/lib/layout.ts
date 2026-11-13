import type { Node } from "@xyflow/react";

import type { GraphEdge, GraphNode } from "./types";

/** Data carried by every node in the React Flow canvas. */
export interface GraphNodeData extends Record<string, unknown> {
  node: GraphNode;
  dimmed?: boolean;
}

export type GraphFlowNode = Node<GraphNodeData>;

/** Canvas geometry, exported so tests and the edge builder agree on the grid. */
export const GRAPH_ORIGIN = 40;
export const COLUMN_WIDTH = 300;
export const ROW_HEIGHT = 140;

/** Which column each kind of node occupies, left to right. */
export const KIND_COLUMN: Record<string, number> = {
  agent: 0,
  model: 1,
  tool: 2,
  state: 3,
  external: 4,
};

export function firstSeen(node: GraphNode): number {
  const value = node.first_ts ? new Date(node.first_ts).getTime() : 0;
  return Number.isFinite(value) ? value : 0;
}

export function byFirstSeen(a: GraphNode, b: GraphNode): number {
  return firstSeen(a) - firstSeen(b) || a.id.localeCompare(b.id);
}

/** Order agents by walking handoff edges: the order control actually changed hands. */
export function orderAgents(agents: GraphNode[], edges: GraphEdge[]): GraphNode[] {
  const byId = new Map(agents.map((agent) => [agent.id, agent]));
  const indegree = new Map<string, number>();
  const outgoing = new Map<string, string[]>();
  for (const agent of agents) {
    indegree.set(agent.id, 0);
    outgoing.set(agent.id, []);
  }
  for (const edge of edges) {
    if (edge.kind !== "handoff") continue;
    if (!byId.has(edge.source) || !byId.has(edge.target) || edge.source === edge.target) continue;
    outgoing.get(edge.source)?.push(edge.target);
    indegree.set(edge.target, (indegree.get(edge.target) ?? 0) + 1);
  }

  const queue = agents
    .filter((agent) => (indegree.get(agent.id) ?? 0) === 0)
    .sort(byFirstSeen);
  const ordered: GraphNode[] = [];
  const seen = new Set<string>();

  while (queue.length > 0) {
    const agent = queue.shift() as GraphNode;
    if (seen.has(agent.id)) continue;
    seen.add(agent.id);
    ordered.push(agent);
    for (const nextId of outgoing.get(agent.id) ?? []) {
      indegree.set(nextId, (indegree.get(nextId) ?? 0) - 1);
      if ((indegree.get(nextId) ?? 0) === 0) {
        const next = byId.get(nextId);
        if (next) queue.push(next);
      }
    }
  }

  const rest = agents.filter((agent) => !seen.has(agent.id)).sort(byFirstSeen);
  return [...ordered, ...rest];
}

/**
 * Readable layout: agents form the left column in execution order; every other node
 * sits in its kind's column, aligned to the row of the agent that first used it.
 * That keeps calls/tool uses short and horizontal, while agent-to-agent handoffs read
 * as vertical steps down the agent column.
 */
export function layoutGraph(
  nodes: GraphNode[],
  edges: GraphEdge[],
  selectedId: string | null,
  neighbours: ReadonlySet<string> | null,
): GraphFlowNode[] {
  const agents = orderAgents(
    nodes.filter((node) => node.kind === "agent"),
    edges,
  );
  const others = nodes.filter((node) => node.kind !== "agent").sort(byFirstSeen);

  const rowOfAgent = new Map<string, number>();
  agents.forEach((agent, row) => rowOfAgent.set(agent.id, row));

  const occupied = new Set<string>();
  const place = (column: number, row: number): { column: number; row: number } => {
    let candidate = row;
    while (occupied.has(column + ":" + candidate)) candidate += 1;
    occupied.add(column + ":" + candidate);
    return { column, row: candidate };
  };

  const positioned: GraphFlowNode[] = [];
  const push = (node: GraphNode, column: number, row: number) => {
    const spot = place(column, row);
    positioned.push({
      id: node.id,
      type: "necto",
      position: {
        x: GRAPH_ORIGIN + spot.column * COLUMN_WIDTH,
        y: GRAPH_ORIGIN + spot.row * ROW_HEIGHT,
      },
      data: { node, dimmed: neighbours ? !neighbours.has(node.id) : false } as GraphNodeData,
      selected: node.id === selectedId,
    });
  };

  agents.forEach((agent, row) => push(agent, KIND_COLUMN.agent, row));

  for (const node of others) {
    const column = KIND_COLUMN[node.kind] ?? KIND_COLUMN.external;
    let row = 0;
    let anchored = false;
    for (const edge of edges) {
      if (edge.target === node.id && rowOfAgent.has(edge.source)) {
        row = rowOfAgent.get(edge.source) as number;
        anchored = true;
        break;
      }
    }
    if (!anchored) row = agents.length + column;
    push(node, column, row);
  }

  return positioned;
}
