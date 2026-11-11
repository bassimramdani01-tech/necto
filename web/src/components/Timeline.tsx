interface TimelineProps {
  mode: "live" | "replay";
  cursor: number;
  total: number;
  timestamps: string[];
  connected: boolean;
  finished: boolean;
  onSetMode: (mode: "live" | "replay") => void;
  onChange: (value: number) => void;
}

function LiveIndicator({ connected, finished }: { connected: boolean; finished: boolean }) {
  if (finished) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-800/80 px-2 py-0.5 text-[11px] font-medium text-slate-400">
        <span className="h-1.5 w-1.5 rounded-full bg-slate-500" />
        finished
      </span>
    );
  }
  if (connected) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-300">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
        live
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] font-medium text-amber-300">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-400" />
      reconnecting…
    </span>
  );
}

export function Timeline({
  mode,
  cursor,
  total,
  timestamps,
  connected,
  finished,
  onSetMode,
  onChange,
}: TimelineProps) {
  const clamped = Math.max(0, Math.min(cursor, total));
  const stamp = clamped > 0 ? timestamps[clamped - 1] : timestamps[0];
  const timeLabel = stamp ? new Date(stamp).toLocaleTimeString([], { hour12: false }) : "—";

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-3 rounded-lg border border-slate-800 bg-slate-900/40 px-4 py-3">
      <div className="flex overflow-hidden rounded-md border border-slate-700 text-xs">
        <button
          type="button"
          aria-pressed={mode === "live"}
          onClick={() => onSetMode("live")}
          className={`px-3 py-1.5 transition-colors ${
            mode === "live" ? "bg-slate-700 text-slate-100" : "text-slate-400 hover:bg-slate-800"
          }`}
        >
          Live
        </button>
        <button
          type="button"
          aria-pressed={mode === "replay"}
          onClick={() => onSetMode("replay")}
          className={`px-3 py-1.5 transition-colors ${
            mode === "replay" ? "bg-slate-700 text-slate-100" : "text-slate-400 hover:bg-slate-800"
          }`}
        >
          Replay
        </button>
      </div>

      <input
        type="range"
        min={0}
        max={Math.max(total, 1)}
        value={clamped}
        disabled={total === 0}
        onChange={(event) => onChange(Number(event.target.value))}
        aria-label="replay position"
        className="h-1 min-w-40 flex-1 cursor-pointer accent-sky-500 disabled:cursor-not-allowed disabled:opacity-40"
      />

      <span className="tabular-nums text-xs text-slate-400">
        {clamped} / {total} events
      </span>
      <span className="tabular-nums text-xs text-slate-500">{timeLabel}</span>

      {mode === "replay" ? (
        <button
          type="button"
          onClick={() => onSetMode("live")}
          className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 transition-colors hover:bg-slate-800"
        >
          Jump to live
        </button>
      ) : (
        <LiveIndicator connected={connected} finished={finished} />
      )}
    </div>
  );
}
