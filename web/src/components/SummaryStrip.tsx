import { formatCompact, formatMoney } from "../lib/format";
import { useGlobalStats } from "../lib/queries";
import { Metric } from "./Metric";

export function SummaryStrip() {
  const { data, isLoading, isError } = useGlobalStats();

  if (isError) {
    return (
      <div className="rounded-lg border border-rose-900/60 bg-rose-950/30 px-4 py-3 text-sm text-rose-200">
        Could not load stats — is the API server running on port 8000?
      </div>
    );
  }

  const stats = data;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      <Metric label="Runs" value={isLoading ? "—" : formatCompact(stats?.run_count ?? 0)} />
      <Metric label="Events" value={isLoading ? "—" : formatCompact(stats?.event_count ?? 0)} />
      <Metric label="Cost" value={isLoading ? "—" : formatMoney(stats?.cost_usd ?? 0)} />
      <Metric label="Tokens" value={isLoading ? "—" : formatCompact(stats?.tokens ?? 0)} />
      <Metric
        label="Errors"
        value={isLoading ? "—" : formatCompact(stats?.error_count ?? 0)}
        tone={(stats?.error_count ?? 0) > 0 ? "danger" : "default"}
      />
    </div>
  );
}
