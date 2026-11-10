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

export const useUiStore = create<UiState>((set) => ({
  view: "runs",
  selectedRunId: null,
  statusFilter: null,
  setView: (view) => set({ view }),
  selectRun: (selectedRunId) => set({ selectedRunId }),
  setStatusFilter: (statusFilter) => set({ statusFilter }),
}));
