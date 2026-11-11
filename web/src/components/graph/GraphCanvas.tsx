import { useEffect, useMemo } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { formatCompact, formatMoney } from "../../lib/format";
import { nodeLabel } from "../../lib/graph";
import type { GraphEdge, GraphNode, GraphResponse } from "../../lib/types";

const KIND_ORDER = ["agent", "model", "tool", "state", "external"];

const KIND_STYLE: Record<string, { ring: string; chip: string; dot: string }> = {
  agent: { ring: "border-sky-500/60", chip: "bg-sky-500/15 text-sky-300", dot: "#0ea5e9" },
  model: { ring: "border-violet-500/60", chip: "bg-violet-500/15 text-violet-300", dot: "#8b5cf6" },
  tool: { ring: "border-amber-500/60", chip: "bg-amber-500/15 text-amber-300", dot: "#f59e0b" },
  state: { ring: "border-emerald-500/60", chip: "bg-emerald-500/15 text-emerald-300", dot: "#10b981" },
  external: { ring: "border-slate-500/60", chip: "bg-slate-500/15 text-slate-300", dot: "#64748b" },
};

const EDGE_STYLE: Record<string, { color: string; animated: boolean }> = {
  handoff: { color: "#38bdf8", animated: true },
  llm_call: { color: "#a78bfa", animated: false },
  tool_call: { color: "#fbbf24", animated: false },
  tool_result: { color: "#f59e0b", animated: false },
  message: { color: "#94a3b8", animated: false },
  state_write: { color: "#34d399", animated: false },
  error: { color: "#fb7185", animated: false },
};

interface NodeData extends Record<string, unknown> {
  node: GraphNode;
}

// node labelling lives in lib/graph so the inspector can share it

function NectoNode({ data }: NodeProps) {
  const node = (data as NodeData).node;
  const style = KIND_STYLE[node.kind] ?? KIND_STYLE.external;

  return (
    <div className={`min-w-[190px] rounded-lg border ${style.ring} bg-slate-900/95 px-3 py-2 shadow-xl`}>
      <Handle id="target-left" type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-slate-600" />
      <Handle id="target-right" type="target" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-slate-600" />
      <div className="flex items-center justify-between gap-2">
        <span className="max-w-[130px] truncate text-sm font-medium text-slate-100">
          {nodeLabel(node)}
        </span>
        <span className={`rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${style.chip}`}>
          {node.kind}
        </span>
      </div>
      <div className="mt-1 flex items-center gap-2 text-[11px] text-slate-400">
        <span>{formatCompact(node.event_count)} ev</span>
        {node.cost_usd > 0 ? <span>{formatMoney(node.cost_usd)}</span> : null}
        {node.tokens > 0 ? <span>{formatCompact(node.tokens)} tok</span> : null}
        {node.error_count > 0 ? <span className="text-rose-300">{node.error_count} err</span> : null}
      </div>
      <Handle id="source-right" type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-slate-600" />
      <Handle id="source-left" type="source" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-slate-600" />
    </div>
  );
}

const nodeTypes: NodeTypes = { necto: NectoNode };

/**
 * Ranks nodes by dependency depth (longest path from a source), so the graph reads
 * left-to-right as the workflow actually ran. Columns are ranks, not node kinds —
 * a handoff between two agents then flows forward instead of looping backwards.
 */
const COLUMN: Record<string, number> = { agent: 0, model: 1, tool: 2, state: 3, external: 4 };

function firstSeen(node: GraphNode): number {
  const value = node.first_ts ? new Date(node.first_ts).getTime() : 0;
  return Number.isFinite(value) ? value : 0;
}

/**
 * Readable layout: agents form the left column in execution order; every other node
 * sits in its kind's column, aligned to the row of the agent that first used it.
 * That keeps calls/tool uses short and horizontal, while agent-to-agent handoffs read
 * as vertical steps down the agent column.
 */
function byFirstSeen(a: GraphNode, b: GraphNode): number {
  return firstSeen(a) - firstSeen(b) || a.id.localeCompare(b.id);
}

/** Order agents by walking handoff edges: the order control actually changed hands. */
function orderAgents(agents: GraphNode[], edges: GraphEdge[]): GraphNode[] {
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

function layout(nodes: GraphNode[], edges: GraphEdge[], selectedId: string | null): Node[] {
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

  const positioned: Node[] = [];
  const push = (node: GraphNode, column: number, row: number) => {
    const spot = place(column, row);
    positioned.push({
      id: node.id,
      type: "necto",
      position: { x: 40 + spot.column * 300, y: 40 + spot.row * 140 },
      data: { node } as NodeData,
      selected: node.id === selectedId,
    });
  };

  agents.forEach((agent, row) => push(agent, COLUMN.agent, row));

  for (const node of others) {
    const column = COLUMN[node.kind] ?? COLUMN.external;
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

const NO_HIGHLIGHT: ReadonlySet<string> = new Set<string>();

function buildEdges(
  graph: GraphResponse,
  columnOf: Map<string, number>,
  highlight: ReadonlySet<string>,
  selectedId: string | null,
): Edge[] {
  return graph.edges.map((edge) => {
    const style = EDGE_STYLE[edge.kind] ?? { color: "#64748b", animated: false };
    const baseLabel = edge.count > 1 ? `${edge.kind} ×${edge.count}` : edge.kind;
    const hasError = edge.error_count > 0;
    const label = hasError ? `${baseLabel} · ${edge.error_count} err` : baseLabel;
    const backward = (columnOf.get(edge.target) ?? 0) < (columnOf.get(edge.source) ?? 0);
    const isHot = highlight.has(edge.id);
    const color = hasError ? "#fb7185" : style.color;
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: "smoothstep",
      sourceHandle: backward ? "source-left" : "source-right",
      targetHandle: backward ? "target-right" : "target-left",
      animated: style.animated || isHot,
      label,
      labelStyle: { fill: "#cbd5e1", fontSize: 10 },
      labelBgStyle: { fill: "#0f172a", fillOpacity: 0.95 },
      labelBgPadding: [4, 2] as [number, number],
      labelBgBorderRadius: 4,
      style: { stroke: color, strokeWidth: hasError ? 2.4 : isHot ? 3 : 1.6 },
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
      selected: edge.id === selectedId,
    } as Edge;
  });
}

export function GraphCanvas(props: {
  graph: GraphResponse;
  highlightEdgeIds?: ReadonlySet<string>;
  selectedId?: string | null;
  onSelectNode?: (nodeId: string) => void;
  onSelectEdge?: (edgeId: string) => void;
  onClearSelection?: () => void;
}) {
  return (
    <ReactFlowProvider>
      <GraphCanvasInner {...props} />
    </ReactFlowProvider>
  );
}

function GraphCanvasInner({
  graph,
  highlightEdgeIds = NO_HIGHLIGHT,
  selectedId = null,
  onSelectNode,
  onSelectEdge,
  onClearSelection,
}: {
  graph: GraphResponse;
  highlightEdgeIds?: ReadonlySet<string>;
  selectedId?: string | null;
  onSelectNode?: (nodeId: string) => void;
  onSelectEdge?: (edgeId: string) => void;
  onClearSelection?: () => void;
}) {
  const { fitView } = useReactFlow();

  // A live run grows the graph; keep everything in frame instead of letting it drift off-canvas.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      void fitView({ padding: 0.18, duration: 220 });
    }, 80);
    return () => window.clearTimeout(timer);
  }, [fitView, graph.nodes.length, graph.edges.length]);
  const nodes = useMemo(
    () => layout(graph.nodes, graph.edges, selectedId),
    [graph.nodes, graph.edges, selectedId],
  );
  const edges = useMemo(() => {
    const columnOf = new Map<string, number>();
    for (const node of nodes) {
      columnOf.set(node.id, Math.round((node.position.x - 40) / 300));
    }
    return buildEdges(graph, columnOf, highlightEdgeIds, selectedId);
  }, [graph, nodes, highlightEdgeIds, selectedId]);

  return (
    <div className="h-[600px] w-full overflow-hidden rounded-lg border border-slate-800 bg-slate-950">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.18 }}
        minZoom={0.2}
        maxZoom={1.6}
        nodesConnectable={false}
        elementsSelectable
        onNodeClick={(_, node) => onSelectNode?.(node.id)}
        onEdgeClick={(_, edge) => onSelectEdge?.(edge.id)}
        onPaneClick={() => onClearSelection?.()}
      >
        <Background color="#1e293b" gap={20} />
        <Controls showInteractive={false} position="bottom-left" />
      </ReactFlow>
    </div>
  );
}

export const GRAPH_LEGEND = {
  nodes: KIND_ORDER.map((kind) => ({
    label: kind,
    color: KIND_STYLE[kind]?.dot ?? "#64748b",
  })),
  edges: [
    ...Object.entries(EDGE_STYLE)
      .filter(([kind]) => kind !== "error")
      .map(([kind, style]) => ({ label: kind, color: style.color })),
    { label: "with errors", color: "#fb7185" },
  ],
};