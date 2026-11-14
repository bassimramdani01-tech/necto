import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Metric } from "../components/Metric";
import { formatCompact, formatMoney, formatNumber } from "../lib/format";
import { useRuns, useRunGraph, useStats } from "../lib/queries";
import { useTopology } from "../lib/queries";

const AXIS_STROKE = "#334155";
const AXIS_TICK = { fill: "#94a3b8", fontSize: 11 };
const GRID = "#1e293b";
const TOOLTIP_STYLE = {
  background: "#0f172a",
  border: "1px solid #1e293b",
  borderRadius: 8,
  fontSize: 12,
  color: "#e2e8f0",
};
// Recharts defaults the hover cursor to a light grey rectangle and repaints the active
// bar; on a dark theme that reads as an unnatural colour flash. Disable the cursor
// rectangle (tooltips still work) and pin each bar's hover colour to its own fill.
const activeBar = (fill: string) => ({ fill, stroke: "none" });

const PIE_COLORS = [
  "#38bdf8",
  "#a78bfa",
  "#fbbf24",
  "#34d399",
  "#fb7185",
  "#94a3b8",
  "#f472b6",
  "#22d3ee",
  "#facc15",
  "#4ade80",
  "#c084fc",
  "#fda4af",
];

function shortLabel(ref: string): string {
  const parts = ref.split(":");
  return parts.length > 1 ? (parts[parts.length - 1] as string) : ref;
}

function Panel({
  title,
  subtitle,
  children,
  className = "",
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-lg border border-slate-800 bg-slate-900/40 p-4 ${className}`}>
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-medium text-slate-200">{title}</h3>
        {subtitle ? <span className="text-[11px] text-slate-500">{subtitle}</span> : null}
      </div>
      {children}
    </section>
  );
}

function Empty() {
  return (
    <div className="flex h-[200px] items-center justify-center text-xs text-slate-500">
      No data yet — send a run to see this chart.
    </div>
  );
}

function readRunParam(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("run");
}

export function StatsView() {
  const [scope, setScope] = useState<string | null>(readRunParam);
  const runs = useRuns();
  const stats = useStats(scope);
  const topology = useTopology();
  const scopedGraph = useRunGraph(scope);
  const edges = scope ? (scopedGraph.data?.edges ?? []) : (topology.data?.edges ?? []);

  const data = stats.data;
  const hasData = Boolean(data && data.event_count > 0);

  const modelData = (data?.by_model ?? []).map((item) => ({
    name: shortLabel(item.model),
    cost_usd: Number(item.cost_usd.toFixed(4)),
    calls: item.calls,
    tokens: item.tokens,
    avg_latency_ms: item.avg_latency_ms ?? 0,
  }));

  const agentData = (data?.by_agent ?? []).map((item) => ({
    name: shortLabel(item.agent),
    calls: item.calls,
    tokens: item.tokens,
    cost_usd: Number(item.cost_usd.toFixed(4)),
  }));

  const typeData = Object.entries(data?.by_type ?? {})
    .map(([type, count]) => ({ type, count }))
    .sort((a, b) => b.count - a.count);

  const riskyEdges = [...edges]
    .filter((edge) => edge.error_count > 0)
    .sort((a, b) => b.error_rate - a.error_rate)
    .slice(0, 8);

  const busiestEdges = [...edges]
    .sort((a, b) => b.count - a.count)
    .slice(0, 8);

  return (
    <div className="px-8 py-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Stats</h1>
          <p className="mt-1 text-sm text-slate-500">
            Cost, tokens, latency and failures across {scope ? "this run" : "all runs"}.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={scope ?? ""}
            onChange={(event) => {
              const next = event.target.value || null;
              setScope(next);
              const url = new URL(window.location.href);
              if (next) {
                url.searchParams.set("run", next);
              } else {
                url.searchParams.delete("run");
              }
              window.history.replaceState({}, "", url);
            }}
            className="rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-200"
          >
            <option value="">All runs</option>
            {(runs.data?.pages[0]?.runs ?? []).map((run) => (
              <option key={run.id} value={run.id}>
                {run.name ?? "untitled"} · {run.id.slice(0, 8)}
              </option>
            ))}
          </select>
          {scope ? (
            <button
              type="button"
              onClick={() => {
                setScope(null);
                const url = new URL(window.location.href);
                url.searchParams.delete("run");
                window.history.replaceState({}, "", url);
              }}
              className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-900"
            >
              All runs
            </button>
          ) : null}
        </div>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Metric label="Runs" value={formatNumber(data?.run_count ?? 0)} />
        <Metric label="Events" value={formatNumber(data?.event_count ?? 0)} />
        <Metric label="Cost" value={formatMoney(data?.cost_usd ?? 0)} />
        <Metric label="Tokens" value={formatCompact(data?.tokens ?? 0)} />
        <Metric
          label="Errors"
          value={formatNumber(data?.error_count ?? 0)}
          tone={(data?.error_count ?? 0) > 0 ? "danger" : "default"}
        />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Panel title="Spend by model" subtitle="total cost per model">
          {modelData.length === 0 ? (
            <Empty />
          ) : (
            <ResponsiveContainer width="100%" height={230}>
              <BarChart data={modelData} margin={{ top: 4, right: 8, bottom: 4, left: -18 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="name" stroke={AXIS_STROKE} tick={AXIS_TICK} interval={0} height={44} angle={-15} textAnchor="end" />
                <YAxis stroke={AXIS_STROKE} tick={AXIS_TICK} />
                <Tooltip
                  cursor={false}
                  contentStyle={TOOLTIP_STYLE}
                  formatter={(value) => [`$${Number(value).toFixed(4)}`, "cost"]}
                />
                <Bar dataKey="cost_usd" fill="#a78bfa" radius={[4, 4, 0, 0]} isAnimationActive={false}  activeBar={activeBar("#a78bfa")} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Panel>

        <Panel title="Model calls" subtitle="calls per model (tokens on hover)">
          {modelData.length === 0 ? (
            <Empty />
          ) : (
            <ResponsiveContainer width="100%" height={230}>
              <BarChart data={modelData} margin={{ top: 4, right: 8, bottom: 4, left: -18 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="name" stroke={AXIS_STROKE} tick={AXIS_TICK} interval={0} height={44} angle={-15} textAnchor="end" />
                <YAxis stroke={AXIS_STROKE} tick={AXIS_TICK} />
                <Tooltip
                  cursor={false}
                  contentStyle={TOOLTIP_STYLE}
                  formatter={(value, name, item) => {
                    if (name === "calls") {
                      const tokens = (item?.payload as { tokens?: number } | undefined)?.tokens ?? 0;
                      return [`${Number(value)} calls · ${formatCompact(tokens)} tokens`, "calls"];
                    }
                    return [String(value), String(name)];
                  }}
                />
                <Bar dataKey="calls" name="calls" fill="#38bdf8" radius={[4, 4, 0, 0]} isAnimationActive={false}  activeBar={activeBar("#38bdf8")} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Panel>

        <Panel title="Calls by agent" subtitle="how much work each agent did">
          {agentData.length === 0 ? (
            <Empty />
          ) : (
            <ResponsiveContainer width="100%" height={230}>
              <BarChart data={agentData} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 28 }}>
                <CartesianGrid stroke={GRID} horizontal={false} />
                <XAxis type="number" stroke={AXIS_STROKE} tick={AXIS_TICK} />
                <YAxis type="category" dataKey="name" stroke={AXIS_STROKE} tick={AXIS_TICK} width={90} />
                <Tooltip cursor={false} contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="calls" fill="#38bdf8" radius={[0, 4, 4, 0]} isAnimationActive={false}  activeBar={activeBar("#38bdf8")} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Panel>

        <Panel title="Average LLM latency" subtitle="ms per model">
          {modelData.length === 0 ? (
            <Empty />
          ) : (
            <ResponsiveContainer width="100%" height={230}>
              <BarChart data={modelData} margin={{ top: 4, right: 8, bottom: 4, left: -18 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="name" stroke={AXIS_STROKE} tick={AXIS_TICK} interval={0} height={44} angle={-15} textAnchor="end" />
                <YAxis stroke={AXIS_STROKE} tick={AXIS_TICK} />
                <Tooltip
                  cursor={false}
                  contentStyle={TOOLTIP_STYLE}
                  formatter={(value) => [`${Number(value)} ms`, "avg latency"]}
                />
                <Bar dataKey="avg_latency_ms" fill="#fbbf24" radius={[4, 4, 0, 0]} isAnimationActive={false}  activeBar={activeBar("#fbbf24")} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Panel>

        <Panel title="Events by type" subtitle="what the run is made of">
          {typeData.length === 0 ? (
            <Empty />
          ) : (
            <ResponsiveContainer width="100%" height={230}>
              <PieChart>
                <Pie data={typeData} dataKey="count" nameKey="type" innerRadius={45} outerRadius={80} paddingAngle={2} isAnimationActive={false}>
                  {typeData.map((entry, index) => (
                    <Cell key={entry.type} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip cursor={false} contentStyle={TOOLTIP_STYLE} />
                <Legend wrapperStyle={{ fontSize: 11, color: "#94a3b8" }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Panel>

        <Panel title="Edge failure rate" subtitle="edges with errors">
          {riskyEdges.length === 0 ? (
            <div className="flex h-[200px] items-center justify-center text-xs text-slate-500">
              No failing edges. 🎉
            </div>
          ) : (
            <div className="space-y-2">
              {riskyEdges.map((edge) => (
                <div key={edge.id} className="text-xs">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-slate-300">
                      {shortLabel(edge.source)} → {shortLabel(edge.target)}
                      <span className="ml-1 text-slate-500">({edge.kind})</span>
                    </span>
                    <span className="tabular-nums text-rose-300">
                      {(edge.error_rate * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded bg-slate-800">
                    <div
                      className="h-full rounded bg-rose-400"
                      style={{ width: `${Math.min(edge.error_rate * 100, 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <Panel
        title="Busiest connections"
        subtitle={scope ? "this run" : "topology across all runs"}
        className="mt-4"
      >
        {busiestEdges.length === 0 ? (
          <Empty />
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="text-[10px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="py-1.5 font-medium">Connection</th>
                <th className="py-1.5 font-medium">Kind</th>
                <th className="py-1.5 text-right font-medium">Calls</th>
                <th className="py-1.5 text-right font-medium">Cost</th>
                <th className="py-1.5 text-right font-medium">Tokens</th>
                <th className="py-1.5 text-right font-medium">Errors</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {busiestEdges.map((edge) => (
                <tr key={edge.id}>
                  <td className="py-1.5 text-slate-300">
                    {shortLabel(edge.source)} → {shortLabel(edge.target)}
                  </td>
                  <td className="py-1.5 text-slate-400">{edge.kind}</td>
                  <td className="py-1.5 text-right tabular-nums text-slate-300">{formatNumber(edge.count)}</td>
                  <td className="py-1.5 text-right tabular-nums text-slate-300">{formatMoney(edge.cost_usd)}</td>
                  <td className="py-1.5 text-right tabular-nums text-slate-300">{formatCompact(edge.tokens)}</td>
                  <td className="py-1.5 text-right tabular-nums">
                    <span className={edge.error_count > 0 ? "text-rose-300" : "text-slate-500"}>
                      {edge.error_count}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      {stats.isError ? (
        <p className="mt-4 text-xs text-rose-300">
          Could not load stats — is the API server running?
        </p>
      ) : null}
      {!hasData && !stats.isLoading ? (
        <p className="mt-4 text-xs text-slate-500">
          No runs recorded yet. Instrument an app with the SDK, then come back.
        </p>
      ) : null}
    </div>
  );
}