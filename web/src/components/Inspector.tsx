import { useMemo } from "react";
import { formatMoney, formatNumber, formatRelative } from "../lib/format";
import { labelFor, nodeLabel } from "../lib/graph";
import type { EventOut, GraphEdge, GraphNode, GraphResponse } from "../lib/types";

export interface Selection {
  kind: "node" | "edge";
  id: string;
}

interface InspectorProps {
  selection: Selection;
  graph: GraphResponse;
  events: EventOut[];
  onClose: () => void;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-slate-800/60 py-1.5 text-xs last:border-0">
      <span className="shrink-0 text-slate-500">{label}</span>
      <span className="truncate font-medium text-slate-200" title={value}>
        {value}
      </span>
    </div>
  );
}

function EventRow({ event }: { event: EventOut }) {
  return (
    <details className="group rounded border border-slate-800/70 bg-slate-900/40 px-2 py-1.5 text-xs">
      <summary className="cursor-pointer list-none">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] text-slate-500">#{event.seq}</span>
          <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300">
            {event.type}
          </span>
          <span className="ml-auto text-[10px] text-slate-500">
            {new Date(event.ts).toLocaleTimeString([], { hour12: false })}
          </span>
        </div>
        <div className="mt-1 truncate text-[11px] text-slate-400">
          {event.from_ref ?? "—"} → {event.to_ref ?? "—"}
        </div>
      </summary>
      <pre className="mt-2 max-h-56 overflow-auto rounded bg-slate-950/80 p-2 text-[10px] leading-relaxed text-slate-400">
        {JSON.stringify(event.payload, null, 2)}
      </pre>
    </details>
  );
}

function NodeDetails({ node }: { node: GraphNode }) {
  return (
    <>
      <Row label="id" value={node.id} />
      <Row label="kind" value={node.kind} />
      {node.framework ? <Row label="framework" value={node.framework} /> : null}
      {node.model ? <Row label="model" value={node.model} /> : null}
      {node.provider ? <Row label="provider" value={node.provider} /> : null}
      <Row label="events" value={formatNumber(node.event_count)} />
      <Row label="tokens" value={formatNumber(node.tokens)} />
      <Row label="cost" value={formatMoney(node.cost_usd)} />
      <Row label="errors" value={formatNumber(node.error_count)} />
      <Row label="first seen" value={formatRelative(node.first_ts)} />
      <Row label="last seen" value={formatRelative(node.last_ts)} />
    </>
  );
}

function EdgeDetails({ edge, graph }: { edge: GraphEdge; graph: GraphResponse }) {
  return (
    <>
      <Row label="kind" value={edge.kind} />
      <Row label="from" value={labelFor(graph, edge.source)} />
      <Row label="to" value={labelFor(graph, edge.target)} />
      <Row label="calls" value={formatNumber(edge.count)} />
      <Row label="tokens" value={formatNumber(edge.tokens)} />
      <Row label="cost" value={formatMoney(edge.cost_usd)} />
      <Row
        label="latency"
        value={edge.latency_ms > 0 ? `${formatNumber(edge.latency_ms)} ms` : "—"}
      />
      <Row
        label="errors"
        value={`${formatNumber(edge.error_count)} (${(edge.error_rate * 100).toFixed(0)}%)`}
      />
      <Row label="first seen" value={formatRelative(edge.first_ts)} />
      <Row label="last seen" value={formatRelative(edge.last_ts)} />
    </>
  );
}

export function Inspector({ selection, graph, events, onClose }: InspectorProps) {
  const node = selection.kind === "node" ? graph.nodes.find((item) => item.id === selection.id) : undefined;
  const edge = selection.kind === "edge" ? graph.edges.find((item) => item.id === selection.id) : undefined;

  const matching = useMemo(() => {
    if (node) {
      return events.filter((event) => event.from_ref === node.id || event.to_ref === node.id);
    }
    if (edge) {
      return events.filter(
        (event) =>
          event.from_ref === edge.source && event.to_ref === edge.target && event.type === edge.kind,
      );
    }
    return [];
  }, [node, edge, events]);

  const missing = !node && !edge;
  const title = node
    ? nodeLabel(node)
    : edge
      ? `${labelFor(graph, edge.source)} → ${labelFor(graph, edge.target)}`
      : selection.id;

  return (
    <aside className="w-full shrink-0 overflow-hidden rounded-lg border border-slate-800 bg-slate-950/60 xl:w-[380px]">
      <header className="flex items-start justify-between gap-3 border-b border-slate-800 px-4 py-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-100" title={title}>
            {title}
          </div>
          <div className="mt-0.5 text-[11px] uppercase tracking-wider text-slate-500">
            {node ? `${node.kind} node` : edge ? `${edge.kind} edge` : "selection"}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="close inspector"
          className="rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-400 transition-colors hover:border-slate-600 hover:text-slate-200"
        >
          ×
        </button>
      </header>

      <div className="max-h-[560px] overflow-y-auto px-4 py-3">
        {missing ? (
          <p className="text-xs text-slate-500">
            This selection is not visible at the current replay position.
          </p>
        ) : (
          <>
            <div className="mb-4">{node ? <NodeDetails node={node} /> : edge ? <EdgeDetails edge={edge} graph={graph} /> : null}</div>

            <div className="mb-2 flex items-baseline justify-between">
              <h3 className="text-[11px] uppercase tracking-wider text-slate-500">Events</h3>
              <span className="text-[11px] text-slate-500">{matching.length}</span>
            </div>

            {matching.length === 0 ? (
              <p className="text-xs text-slate-500">No events at this replay position.</p>
            ) : (
              <div className="space-y-1.5">
                {matching.slice(0, 50).map((event) => (
                  <EventRow key={event.seq} event={event} />
                ))}
                {matching.length > 50 ? (
                  <p className="pt-1 text-[11px] text-slate-500">
                    showing 50 of {matching.length}
                  </p>
                ) : null}
              </div>
            )}
          </>
        )}
      </div>
    </aside>
  );
}
