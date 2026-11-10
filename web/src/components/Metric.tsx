interface MetricProps {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "danger";
}

export function Metric({ label, value, hint, tone = "default" }: MetricProps) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-3">
      <div className="text-[11px] uppercase tracking-wider text-slate-500">{label}</div>
      <div
        className={`mt-1 text-xl font-semibold tabular-nums ${tone === "danger" ? "text-rose-300" : "text-slate-100"}`}
      >
        {value}
      </div>
      {hint ? <div className="mt-0.5 text-xs text-slate-500">{hint}</div> : null}
    </div>
  );
}
