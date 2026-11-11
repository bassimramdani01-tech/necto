import { useEffect, useMemo, useState } from "react";
import { GRAPH_LEGEND, GraphCanvas } from "../components/graph/GraphCanvas";
import { Metric } from "../components/Metric";
import { Timeline } from "../components/Timeline";
import { formatDuration, formatMoney, formatNumber, formatRelative } from "../lib/format";
import { projectGraph } from "../lib/projectGraph";
import { useRun, useRunEvents, useRunGraph } from "../lib/queries";
import { useLiveRun } from "../lib/ws";
import { useUiStore } from "../store/ui";

const statusStyles: Record<string, string> = {
  running: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  ok: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  error: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  cancelled: "bg-slate-500/15 text-slate-300 ring-slate-500/30",
};

type Mode = "live" | "replay";

function StatusChip({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ${
        statusStyles[status] ?? statusStyles.cancelled
      }`}
    >
      {status}
    </span>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border border-slate-800 bg-slate-900/40 px-4 py-3 text-[11px] text-slate-400">
      <div className="flex items-center gap-3">
        <span className="uppercase tracking-wider text-slate-500">Nodes</span>
        {GRAPH_LEGEND.nodes.map((item) => (
          <span key={item.label} className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ background: item.color }} />
            {item.label}
          </span>
        ))}
      </div>
      <div className="flex items-center gap-3">
        <span className="uppercase tracking-wider text-slate-500">Edges</span>
        {GRAPH_LEGEND.edges.map((item) => (
          <span key={item.label} className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded" style={{ background: item.color }} />
            {item.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function readReplayPoint(): number | null {
  if (typeof window === "undefined") return null;
  const raw = new URLSearchParams(window.location.search).get("at");
  if (raw === null) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? Math.max(0, Math.trunc(parsed)) : null;
}

export function RunDetailView({ runId }: { runId: string }) {
  const selectRun = useUiStore((state) => state.selectRun);
  const run = useRun(runId);
  const graphQuery = useRunGraph(runId);
  const eventsQuery = useRunEvents(runId);

  const isRunning = run.data?.status === "running";
  const live = useLiveRun(runId, isRunning);

  const events = eventsQuery.data ?? [];
  const total = events.length;
  const [mode, setMode] = useState<Mode>("live");
  const [cursor, setCursor] = useState(0);
  const [replayInitialised, setReplayInitialised] = useState(false);

  // Deep link: ?run=<id>&at=<n> opens replay at a specific event.
  useEffect(() => {
    if (replayInitialised || total === 0) return;
    const point = readReplayPoint();
    if (point !== null && point < total) {
      setMode("replay");
      setCursor(point);
    }
    setReplayInitialised(true);
  }, [replayInitialised, total]);

  // In live mode the cursor is simply the end of the event list — no state to race with.
  const liveCursor = mode === "live" ? total : cursor;

  const replayGraph = useMemo(() => {
    if (mode !== "replay" || total === 0) return null;
    return projectGraph(events.slice(0, cursor), runId);
  }, [mode, total, events, cursor, runId]);

  const highlightEdgeIds = useMemo(() => {
    const set = new Set<string>();
    for (const event of live.recentEvents) {
      if (event.from_ref && event.to_ref) {
        set.add(`${event.from_ref}->${event.to_ref}:${event.type}`);
      }
    }
    return set;
  }, [live.recentEvents]);

  if (run.isLoading) {
    return <div className="px-8 py-10 text-sm text-slate-500">Loading run…</div>;
  }
  if (run.isError || !run.data) {
    const message = run.error instanceof Error ? run.error.message : "Could not load this run";
    return (
      <div className="px-8 py-10">
        <div className="rounded-lg border border-rose-900/60 bg-rose-950/30 px-4 py-3 text-sm text-rose-200">
          {message}
        </div>
        <button
          type="button"
          onClick={() => selectRun(null)}
          className="mt-4 text-sm text-slate-400 underline-offset-4 hover:text-slate-200 hover:underline"
        >
          ← back to runs
        </button>
      </div>
    );
  }

  const detail = run.data;
  const graph = mode === "replay" && replayGraph ? replayGraph : graphQuery.data;
  const cursorLabel = Math.min(liveCursor, total);
  const timestamps = events.map((event) => event.ts);

  return (
    <div className="px-8 py-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold text-slate-100">{detail.name ?? "untitled run"}</h1>
            <StatusChip status={detail.status} />
          </div>
          <p className="mt-1 font-mono text-xs text-slate-500">{detail.id}</p>
        </div>
        <button
          type="button"
          onClick={() => selectRun(null)}
          className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 transition-colors hover:border-slate-600 hover:bg-slate-900"
        >
          ← All runs
        </button>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Metric label="Events" value={formatNumber(detail.event_count)} />
        <Metric label="Cost" value={formatMoney(detail.cost_usd)} />
        <Metric label="Tokens" value={formatNumber(detail.tokens)} />
        <Metric
          label="Errors"
          value={formatNumber(detail.error_count)}
          tone={detail.error_count > 0 ? "danger" : "default"}
        />
        <Metric label="Framework" value={detail.framework ?? "—"} hint={detail.sdk_version ?? undefined} />
        <Metric
          label="Duration"
          value={formatDuration(detail.started_at, detail.finished_at)}
          hint={formatRelative(detail.started_at)}
        />
      </div>

      <section className="mt-8 space-y-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-medium text-slate-300">Architecture</h2>
          {graph ? (
            <span className="text-xs text-slate-500">
              {graph.nodes.length} {graph.nodes.length === 1 ? "node" : "nodes"} ·{" "}
              {graph.edges.length} {graph.edges.length === 1 ? "edge" : "edges"}
              {mode === "replay" ? ` · at event ${cursorLabel}` : null}
            </span>
          ) : null}
        </div>

        <Timeline
          mode={mode}
          cursor={liveCursor}
          total={total}
          timestamps={timestamps}
          connected={live.connected}
          finished={live.finished || !isRunning}
          onSetMode={(next) => {
            if (next === "replay") setCursor(total);
            setMode(next);
          }}
          onChange={(value) => {
            setMode("replay");
            setCursor(value);
          }}
        />

        {graphQuery.isLoading && mode === "live" ? (
          <div className="flex h-[600px] items-center justify-center rounded-lg border border-slate-800 text-sm text-slate-500">
            Loading graph…
          </div>
        ) : graph ? (
          <GraphCanvas graph={graph} highlightEdgeIds={highlightEdgeIds} />
        ) : (
          <div className="rounded-lg border border-rose-900/60 bg-rose-950/30 px-4 py-3 text-sm text-rose-200">
            Could not load the graph for this run.
          </div>
        )}

        <Legend />
      </section>
    </div>
  );
}
