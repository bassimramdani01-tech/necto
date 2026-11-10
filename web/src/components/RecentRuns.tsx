import { formatMoney, formatRelative, shortId } from "../lib/format";
import { useRuns } from "../lib/queries";
import { useUiStore } from "../store/ui";

const statusStyles: Record<string, string> = {
  running: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  ok: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  error: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  cancelled: "bg-slate-500/15 text-slate-300 ring-slate-500/30",
};

export function RecentRuns() {
  const { data, isLoading, isError, error } = useRuns();
  const selectRun = useUiStore((state) => state.selectRun);

  if (isLoading) {
    return <div className="text-sm text-slate-500">Loading runs…</div>;
  }
  if (isError) {
    return (
      <div className="rounded-lg border border-rose-900/60 bg-rose-950/30 px-4 py-3 text-sm text-rose-200">
        {error instanceof Error ? error.message : "Failed to load runs"}
      </div>
    );
  }
  if (!data || data.runs.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-slate-800 bg-slate-900/30 px-6 py-12 text-center">
        <p className="text-sm font-medium text-slate-300">No runs yet</p>
        <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
          Point the necto SDK at this server, or POST some events to <code className="text-slate-400">/v1/runs</code>, and
          they will appear here.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-slate-800">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-900/70 text-[11px] uppercase tracking-wider text-slate-500">
          <tr>
            <th className="px-4 py-2 font-medium">Run</th>
            <th className="px-4 py-2 font-medium">Status</th>
            <th className="px-4 py-2 font-medium">Framework</th>
            <th className="px-4 py-2 text-right font-medium">Events</th>
            <th className="px-4 py-2 text-right font-medium">Cost</th>
            <th className="px-4 py-2 text-right font-medium">Started</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/70">
          {data.runs.map((run) => (
            <tr
              key={run.id}
              onClick={() => selectRun(run.id)}
              className="cursor-pointer transition-colors hover:bg-slate-900/60"
            >
              <td className="px-4 py-2.5">
                <div className="font-medium text-slate-200">{run.name ?? "untitled run"}</div>
                <div className="font-mono text-[11px] text-slate-500">{shortId(run.id)}</div>
              </td>
              <td className="px-4 py-2.5">
                <span
                  className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ${
                    statusStyles[run.status] ?? statusStyles.cancelled
                  }`}
                >
                  {run.status}
                </span>
              </td>
              <td className="px-4 py-2.5 text-slate-400">{run.framework ?? "—"}</td>
              <td className="px-4 py-2.5 text-right tabular-nums text-slate-300">{run.event_count}</td>
              <td className="px-4 py-2.5 text-right tabular-nums text-slate-300">{formatMoney(run.cost_usd)}</td>
              <td className="px-4 py-2.5 text-right text-slate-500">{formatRelative(run.started_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="border-t border-slate-800 bg-slate-900/40 px-4 py-2 text-[11px] text-slate-500">
        {data.runs.length} of {data.total} runs
      </div>
    </div>
  );
}
