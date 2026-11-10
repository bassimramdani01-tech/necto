import { GRAPH_LEGEND, GraphCanvas } from "../components/graph/GraphCanvas";
import { Metric } from "../components/Metric";
import { formatDuration, formatMoney, formatNumber, formatRelative } from "../lib/format";
import { useRun, useRunGraph } from "../lib/queries";
import { useUiStore } from "../store/ui";

const statusStyles: Record<string, string> = {
  running: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  ok: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  error: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  cancelled: "bg-slate-500/15 text-slate-300 ring-slate-500/30",
};

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

export function RunDetailView({ runId }: { runId: string }) {
  const selectRun = useUiStore((state) => state.selectRun);
  const run = useRun(runId);
  const graph = useRunGraph(runId);

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
          {graph.data ? (
            <span className="text-xs text-slate-500">
              {graph.data.nodes.length} nodes · {graph.data.edges.length} edges
            </span>
          ) : null}
        </div>

        {graph.isLoading ? (
          <div className="flex h-[560px] items-center justify-center rounded-lg border border-slate-800 text-sm text-slate-500">
            Loading graph…
          </div>
        ) : graph.isError || !graph.data ? (
          <div className="rounded-lg border border-rose-900/60 bg-rose-950/30 px-4 py-3 text-sm text-rose-200">
            Could not load the graph for this run.
          </div>
        ) : (
          <GraphCanvas graph={graph.data} />
        )}

        <Legend />
      </section>
    </div>
  );
}
