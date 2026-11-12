import { Suspense, lazy, useState } from "react";

import { RecentRuns } from "./components/RecentRuns";
import { StatusPill } from "./components/StatusPill";
import { SummaryStrip } from "./components/SummaryStrip";
import { RunDetailView } from "./views/RunDetailView";
import { TopologyView } from "./views/TopologyView";
import { useUiStore, type View } from "./store/ui";

// Recharts is heavy; the dashboard is not on the critical path, so load it on demand.
const StatsView = lazy(() =>
  import("./views/StatsView").then((module) => ({ default: module.StatsView })),
);

const navItems: { id: View; label: string; ready: boolean }[] = [
  { id: "runs", label: "Runs", ready: true },
  { id: "topology", label: "Topology", ready: true },
  { id: "stats", label: "Stats", ready: true },
];

function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  const view = useUiStore((state) => state.view);
  const setView = useUiStore((state) => state.setView);

  return (
    <nav aria-label="Main" className="flex flex-col gap-0.5 px-3">
      {navItems.map((item) => {
        const active = view === item.id;
        return (
          <button
            key={item.id}
            type="button"
            disabled={!item.ready}
            aria-current={active ? "page" : undefined}
            onClick={() => {
              setView(item.id);
              onNavigate?.();
            }}
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
  );
}

function Wordmark() {
  return (
    <div className="px-5 py-5">
      <div className="text-lg font-semibold tracking-tight text-slate-100">necto</div>
      <div className="text-[11px] text-slate-500">AI architecture, visualized</div>
    </div>
  );
}

export default function App() {
  const view = useUiStore((state) => state.view);
  const selectedRunId = useUiStore((state) => state.selectedRunId);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex h-full">
      {/* Mobile header */}
      <header className="fixed inset-x-0 top-0 z-20 flex items-center gap-3 border-b border-slate-800 bg-slate-950/95 px-4 py-3 backdrop-blur lg:hidden">
        <button
          type="button"
          onClick={() => setSidebarOpen(true)}
          aria-label="Open navigation"
          className="rounded border border-slate-700 px-2 py-1 text-slate-300"
        >
          ☰
        </button>
        <span className="text-sm font-semibold text-slate-100">necto</span>
        <span className="ml-auto">
          <StatusPill />
        </span>
      </header>

      {sidebarOpen ? (
        <button
          type="button"
          aria-label="Close navigation"
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-30 bg-black/60 lg:hidden"
        />
      ) : null}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-56 shrink-0 flex-col border-r border-slate-800 bg-slate-950 transition-transform lg:static lg:z-auto lg:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <Wordmark />
        <Navigation onNavigate={() => setSidebarOpen(false)} />
        <div className="mt-auto px-4 py-4">
          <div className="hidden lg:block">
            <StatusPill />
          </div>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto pt-12 lg:pt-0">
        {view === "stats" ? (
          <Suspense
            fallback={<div className="px-8 py-10 text-sm text-slate-500">Loading stats…</div>}
          >
            <StatsView />
          </Suspense>
        ) : view === "topology" ? (
          <TopologyView />
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
