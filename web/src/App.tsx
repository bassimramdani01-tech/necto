import { RecentRuns } from "./components/RecentRuns";
import { StatusPill } from "./components/StatusPill";
import { SummaryStrip } from "./components/SummaryStrip";
import { RunDetailView } from "./views/RunDetailView";
import { StatsView } from "./views/StatsView";
import { useUiStore, type View } from "./store/ui";

const navItems: { id: View; label: string; ready: boolean }[] = [
  { id: "runs", label: "Runs", ready: true },
  { id: "topology", label: "Topology", ready: false },
  { id: "stats", label: "Stats", ready: true },
];

export default function App() {
  const view = useUiStore((state) => state.view);
  const setView = useUiStore((state) => state.setView);
  const selectedRunId = useUiStore((state) => state.selectedRunId);

  return (
    <div className="flex h-full">
      <aside className="flex w-56 shrink-0 flex-col border-r border-slate-800 bg-slate-950/80">
        <div className="px-5 py-5">
          <div className="text-lg font-semibold tracking-tight text-slate-100">necto</div>
          <div className="text-[11px] text-slate-500">AI architecture, visualized</div>
        </div>

        <nav className="flex flex-col gap-0.5 px-3">
          {navItems.map((item) => {
            const active = view === item.id;
            return (
              <button
                key={item.id}
                type="button"
                disabled={!item.ready}
                onClick={() => setView(item.id)}
                className={`flex items-center justify-between rounded-md px-3 py-2 text-left text-sm transition-colors ${
                  active
                    ? "bg-slate-800/80 font-medium text-slate-100"
                    : item.ready
                      ? "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
                      : "cursor-not-allowed text-slate-600"
                }`}
              >
                {item.label}
                {!item.ready ? (
                  <span className="rounded bg-slate-800/80 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-slate-500">
                    soon
                  </span>
                ) : null}
              </button>
            );
          })}
        </nav>

        <div className="mt-auto px-4 py-4">
          <StatusPill />
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        {view === "stats" ? (
          <StatsView />
        ) : selectedRunId ? (
          <RunDetailView runId={selectedRunId} />
        ) : (
          <>
            <header className="border-b border-slate-800 px-8 py-6">
              <h1 className="text-xl font-semibold text-slate-100">Runs</h1>
              <p className="mt-1 text-sm text-slate-500">
                Every observed agent run. Click a run to explore its graph.
              </p>
            </header>

            <section className="space-y-6 px-8 py-6">
              <SummaryStrip />
              <RecentRuns />
            </section>
          </>
        )}
      </main>
    </div>
  );
}
