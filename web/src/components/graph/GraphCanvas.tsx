import { useEffect, useMemo } from "react";
import {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  getSmoothStepPath,
  useReactFlow,
  type Edge,
  type EdgeProps,
  type EdgeTypes,
  type NodeProps,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { formatCompact, formatMoney } from "../../lib/format";
import { nodeLabel } from "../../lib/graph";
import {
  COLUMN_WIDTH,
  GRAPH_ORIGIN,
  layoutGraph,
  type GraphNodeData,
} from "../../lib/layout";
import type { GraphResponse } from "../../lib/types";

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

interface EdgeData extends Record<string, unknown> {
  metrics: string;
}

/** Edge with a hoverable label whose tooltip carries the full metrics. */
function NectoEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
  label,
  data,
}: EdgeProps) {
  const [path, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });
  const metrics = (data as EdgeData | undefined)?.metrics;

  return (
    <>
      <BaseEdge id={id} path={path} style={style} markerEnd={markerEnd} />
      <EdgeLabelRenderer>
        <div
          className="nodrag nopan absolute rounded bg-slate-950/95 px-1.5 py-0.5 text-[10px] text-slate-300 ring-1 ring-slate-800 transition-colors hover:ring-sky-600"
          title={metrics}
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            pointerEvents: "all",
          }}
        >
          {typeof label === "string" ? label : null}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

const edgeTypes: EdgeTypes = { necto: NectoEdge };

// node labelling lives in lib/graph so the inspector can share it

function NectoNode({ data }: NodeProps) {
  const { node, dimmed } = data as GraphNodeData;
  const style = KIND_STYLE[node.kind] ?? KIND_STYLE.external;

  return (
    <div
      className={`min-w-[190px] rounded-lg border ${style.ring} bg-slate-900/95 px-3 py-2 shadow-xl transition-opacity ${
        dimmed ? "opacity-30" : "opacity-100"
      }`}
    >
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

const NO_HIGHLIGHT: ReadonlySet<string> = new Set<string>();

function buildEdges(
  graph: GraphResponse,
  columnOf: Map<string, number>,
  highlight: ReadonlySet<string>,
  selectedId: string | null,
  neighbours: ReadonlySet<string> | null,
): Edge[] {
  return graph.edges.map((edge) => {
    const style = EDGE_STYLE[edge.kind] ?? { color: "#64748b", animated: false };
    const baseLabel = edge.count > 1 ? `${edge.kind} ×${edge.count}` : edge.kind;
    const hasError = edge.error_count > 0;
    const label = hasError ? `${baseLabel} · ${edge.error_count} err` : baseLabel;
    const backward = (columnOf.get(edge.target) ?? 0) < (columnOf.get(edge.source) ?? 0);
    const isHot = highlight.has(edge.id);
    const color = hasError ? "#fb7185" : style.color;
    const incident = edge.source === selectedId || edge.target === selectedId;
    const dimmed = neighbours !== null && !incident;

    const metrics = [
      `${edge.kind} · ${edge.count} call${edge.count === 1 ? "" : "s"}`,
      edge.tokens > 0 ? `${formatCompact(edge.tokens)} tokens` : "",
      edge.cost_usd > 0 ? formatMoney(edge.cost_usd) : "",
      edge.latency_ms > 0 ? `${edge.latency_ms} ms` : "",
      edge.error_count > 0
        ? `${edge.error_count} errors (${(edge.error_rate * 100).toFixed(0)}%)`
        : "",
    ]
      .filter(Boolean)
      .join(" · ");

    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: "necto",
      sourceHandle: backward ? "source-left" : "source-right",
      targetHandle: backward ? "target-right" : "target-left",
      animated: style.animated || isHot,
      label,
      data: { metrics } as EdgeData,
      style: {
        stroke: color,
        strokeWidth: hasError ? 2.4 : isHot ? 3 : 1.6,
        opacity: dimmed ? 0.15 : 1,
      },
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
  if (props.graph.nodes.length === 0) {
    return (
      <div className="flex h-[600px] w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-slate-800 bg-slate-950 px-6 text-center">
        <p className="text-sm font-medium text-slate-300">No events yet</p>
        <p className="max-w-sm text-xs text-slate-500">
          Send events to this run (or start a live one) and the architecture will build here.
        </p>
      </div>
    );
  }

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
  // When something is selected, dim everything that is not directly connected to it.
  const neighbours = useMemo(() => {
    if (!selectedId) return null;
    const connected = new Set<string>([selectedId]);
    for (const edge of graph.edges) {
      if (edge.source === selectedId) connected.add(edge.target);
      if (edge.target === selectedId) connected.add(edge.source);
    }
    return connected;
  }, [selectedId, graph.edges]);

  const nodes = useMemo(
    () => layoutGraph(graph.nodes, graph.edges, selectedId, neighbours),
    [graph.nodes, graph.edges, selectedId, neighbours],
  );
  const edges = useMemo(() => {
    const columnOf = new Map<string, number>();
    for (const node of nodes) {
      columnOf.set(node.id, Math.round((node.position.x - GRAPH_ORIGIN) / COLUMN_WIDTH));
    }
    return buildEdges(graph, columnOf, highlightEdgeIds, selectedId, neighbours);
  }, [graph, nodes, highlightEdgeIds, selectedId, neighbours]);

  return (
    <div
      className="h-[600px] w-full overflow-hidden rounded-lg border border-slate-800 bg-slate-950"
      role="img"
      aria-label={`architecture graph: ${nodes.length} nodes, ${edges.length} edges`}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
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