import { absoluteTime, formatRelative } from "../lib/format";

/** Relative time with the exact local time on hover. */
export function TimeAgo({ iso }: { iso: string | null }) {
  if (!iso) return <span className="text-slate-500">—</span>;
  return (
    <time dateTime={iso} title={absoluteTime(iso)} className="tabular-nums">
      {formatRelative(iso)}
    </time>
  );
}
