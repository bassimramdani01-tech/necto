import { useEffect, useState } from "react";
import { formatMoney, shortId } from "../lib/format";
import { useFrameworks, useRuns } from "../lib/queries";
import { useUiStore } from "../store/ui";
import { TimeAgo } from "./TimeAgo";

const statusStyles: Record<string, string> = {
  running: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  ok: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  error: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  cancelled: "bg-slate-500/15 text-slate-300 ring-slate-500/30",
};

const FILTERS: { id: string | null; label: string }[] = [
  { id: null, label: "All" },
  { id: "running", label: "Running" },
  { id: "ok", label: "OK" },
  { id: "error", label: "Error" },
];

const SORTS: { id: string; label: string }[] = [
  { id: "recent", label: "Newest" },
  { id: "oldest", label: "Oldest" },
  { id: "cost", label: "Cost" },
  { id: "events", label: "Events" },
  { id: "name", label: "Name" },
];

const selectClass =
  "rounded-md border border-slate-800 bg-slate-900 px-2.5 py-1.5 text-xs text-slate-200 focus:border-slate-600";

export function RecentRuns() {
  const statusFilter = useUiStore((state) => state.statusFilter);
  const setStatusFilter = useUiStore((state) => state.setStatusFilter);
  const selectRun = useUiStore((state) => state.selectRun);

  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [framework, setFramework] = useState("");
  const [sort, setSort] = useState("recent");

  // Debounce typing so the server isn't hit on every keystroke.
  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const frameworks = useFrameworks();
  const runsQuery = useRuns({
    status: statusFilter ?? undefined,
    q: query || undefined,
    framework: framework || undefined,
    sort,
  });

  const runs = (runsQuery.data?.pages ?? []).flatMap((page) => page.runs);
  const total = runsQuery.data?.pages[0]?.total ?? 0;
  const hasFilters = Boolean(statusFilter || query || framework);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search runs by name…"
          aria-label="Search runs by name"
          className="min-w-[12rem] flex-1 rounded-md border border-slate-800 bg-slate-900 px-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-500 focus:border-slate-600"
        />

        <select
          value={framework}
          onChange={(event) => setFramework(event.target.value)}
          aria-label="Filter by framework"
          className={selectClass}
        >
          <option value="">All frameworks</option>
          {(frameworks.data ?? []).map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>

        <select
          value={sort}
          onChange={(event) => setSort(event.target.value)}
          aria-label="Sort runs"
          className={selectClass}
        >
          {SORTS.map((option) => (
            <option key={option.id} value={option.id}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {FILTERS.map((filter) => {
          const active = statusFilter === filter.id;
          return (
            <button
              key={filter.id ?? "all"}
              type="button"
              aria-pressed={active}
              onClick={() => setStatusFilter(filter.id)}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                active
                  ? "border-slate-600 bg-slate-800 text-slate-100"
                  : "border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
              }`}
            >
              {filter.label}
            </button>
          );
        })}
        <span className="ml-auto text-[11px] text-slate-500">
          {runsQuery.isPending ? "" : `${runs.length} of ${total} runs`}
        </span>
      </div>

      {runsQuery.isPending ? (
        <div className="text-sm text-slate-500">Loading runs…</div>
      ) : runsQuery.isError ? (
        <div className="rounded-lg border border-rose-900/60 bg-rose-950/30 px-4 py-3 text-sm text-rose-200">
          {runsQuery.error instanceof Error ? runsQuery.error.message : "Failed to load runs"}
        </div>
      ) : runs.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-800 bg-slate-900/30 px-6 py-12 text-center">
          <p className="text-sm font-medium text-slate-300">No matching runs</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
            {hasFilters
              ? "Try clearing the search, framework or status filter."
              : "Point the necto SDK at this server, or POST events to /v1/runs, and they will appear here."}
          </p>
          {hasFilters ? (
            <button
              type="button"
              onClick={() => {
                setSearch("");
                setQuery("");
                setFramework("");
                setStatusFilter(null);
              }}
              className="mt-3 rounded border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
            >
              Clear filters
            </button>
          ) : null}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-800">
          <table className="w-full min-w-[40rem] text-left text-sm">
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
              {runs.map((run) => (
                <tr
                  key={run.id}
                  onClick={() => selectRun(run.id)}
                  className="cursor-pointer transition-colors hover:bg-slate-900/60"
                >
                  <td className="px-4 py-2.5">
                    <button
                      type="button"
                      onClick={() => selectRun(run.id)}
                      className="block max-w-[18rem] truncate text-left font-medium text-slate-200 hover:text-sky-300"
                    >
                      {run.name ?? "untitled run"}
                    </button>
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
                  <td className="px-4 py-2.5 text-right text-slate-500">
                    <TimeAgo iso={run.started_at} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {runsQuery.hasNextPage ? (
        <div className="flex justify-center">
          <button
            type="button"
            onClick={() => void runsQuery.fetchNextPage()}
            disabled={runsQuery.isFetchingNextPage}
            className="rounded-md border border-slate-700 px-4 py-1.5 text-xs text-slate-300 transition-colors hover:border-slate-600 hover:bg-slate-900 disabled:opacity-50"
          >
            {runsQuery.isFetchingNextPage ? "Loading…" : `Load more (${total - runs.length} left)`}
          </button>
        </div>
      ) : null}
    </div>
  );
}
