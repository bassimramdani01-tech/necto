import { useHealth } from "../lib/queries";

export function StatusPill() {
  const { data, isError, isLoading } = useHealth();

  const state = isLoading ? "connecting" : isError ? "offline" : "online";
  const styles: Record<string, string> = {
    connecting: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
    online: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
    offline: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  };
  const dot: Record<string, string> = {
    connecting: "bg-amber-400 animate-pulse",
    online: "bg-emerald-400",
    offline: "bg-rose-400",
  };

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ${styles[state]}`}
      title={data ? `database ${data.database} · v${data.version}` : "no connection to the necto API"}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${dot[state]}`} />
      {state === "online" ? `API v${data?.version ?? ""}` : state === "offline" ? "API offline" : "connecting"}
    </span>
  );
}
