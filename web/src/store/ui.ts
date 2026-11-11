import { create } from "zustand";

export type View = "runs" | "topology" | "stats";

interface UiState {
  view: View;
  selectedRunId: string | null;
  statusFilter: string | null;
  setView: (view: View) => void;
  selectRun: (runId: string | null) => void;
  setStatusFilter: (status: string | null) => void;
}

// Keep the selected run in the URL so a run view can be linked to and reloaded.
function readRunFromUrl(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("run");
}

function writeRunToUrl(runId: string | null): void {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  // Changing run clears per-run view state (replay point / inspector selection).
  url.searchParams.delete("at");
  url.searchParams.delete("node");
  url.searchParams.delete("edge");
  if (runId) {
    url.searchParams.set("run", runId);
  } else {
    url.searchParams.delete("run");
  }
  window.history.replaceState({}, "", url);
}

export const useUiStore = create<UiState>((set) => ({
  view: "runs",
  selectedRunId: readRunFromUrl(),
  statusFilter: null,
  setView: (view) => set({ view }),
  selectRun: (runId) => {
    writeRunToUrl(runId);
    set({ selectedRunId: runId });
  },
  setStatusFilter: (statusFilter) => set({ statusFilter }),
}));
