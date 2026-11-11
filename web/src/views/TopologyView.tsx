import { GraphCanvas } from "../components/graph/GraphCanvas";
import { Metric } from "../components/Metric";
import { formatCompact, formatMoney, formatNumber } from "../lib/format";
import { useTopology } from "../lib/queries";

export function TopologyView() {
  const topology = useTopology();
  const graph = topology.data;
  const stats = graph?.stats;

  const count = (kind: string) =>
    (graph?.nodes ?? []).filter((node) => node.kind === kind).length;

  return (
    <div className="px-8 py-6">
      <header>
        <h1 className="text-xl font-semibold text-slate-100">Topology</h1>
        <p className="mt-1 text-sm text-slate-500">
          Every agent, model and tool necto has observed — and how they connect across all runs.
        </p>
      </header>

      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Metric label="Runs" value={formatNumber(stats?.run_count ?? 0)} />
        <Metric label="Agents" value={formatNumber(count("agent"))} />
        <Metric label="Models" value={formatNumber(count("model"))} />
        <Metric label="Tools" value={formatNumber(count("tool"))} />
        <Metric label="Cost" value={formatMoney(stats?.cost_usd ?? 0)} />
        <Metric
          label="Errors"
          value={formatNumber(stats?.error_count ?? 0)}
          tone={(stats?.error_count ?? 0) > 0 ? "danger" : "default"}
        />
      </div>

      <section className="mt-8 space-y-3" aria-live="polite">
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-medium text-slate-300">System map</h2>
          {graph ? (
            <span className="text-xs text-slate-500">
              {graph.nodes.length} {graph.nodes.length === 1 ? "node" : "nodes"} ·{" "}
              {graph.edges.length} {graph.edges.length === 1 ? "edge" : "edges"} ·{" "}
              {formatCompact(stats?.event_count ?? 0)} events
            </span>
          ) : null}
        </div>

        {topology.isLoading ? (
          <div className="flex h-[600px] items-center justify-center rounded-lg border border-slate-800 text-sm text-slate-500">
            Loading topology…
          </div>
        ) : topology.isError || !graph ? (
          <div className="rounded-lg border border-rose-900/60 bg-rose-950/30 px-4 py-3 text-sm text-rose-200">
            Could not load the topology — is the API server running?
          </div>
        ) : (
          <GraphCanvas graph={graph} />
        )}

        <p className="text-xs text-slate-500">
          Aggregated from every run. Open a run from the Runs list to see it on its own.
        </p>
      </section>
    </div>
  );
}
