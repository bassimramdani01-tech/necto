// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";

async function loadStore() {
  const module = await import("./ui");
  return module.useUiStore;
}

beforeEach(() => {
  // The store reads the URL at module load, so every test gets a fresh module.
  vi.resetModules();
  window.history.replaceState({}, "", "/");
});

describe("ui store URL sync", () => {
  it("reads the initial view, filter and run from the URL", async () => {
    window.history.replaceState({}, "", "/?view=stats&status=error&run=abc");
    const store = await loadStore();

    expect(store.getState().view).toBe("stats");
    expect(store.getState().statusFilter).toBe("error");
    expect(store.getState().selectedRunId).toBe("abc");
  });

  it("defaults to the runs view for unknown values", async () => {
    window.history.replaceState({}, "", "/?view=bogus&status=all");
    const store = await loadStore();

    expect(store.getState().view).toBe("runs");
    expect(store.getState().statusFilter).toBeNull();
  });

  it("writes the view into the URL and removes it for runs", async () => {
    const store = await loadStore();

    store.getState().setView("topology");
    expect(window.location.search).toContain("view=topology");

    store.getState().setView("runs");
    expect(window.location.search).not.toContain("view=");
  });

  it("clears replay and inspector state when the run changes", async () => {
    window.history.replaceState({}, "", "/?run=old&at=3&node=agent:a&edge=x");
    const store = await loadStore();

    store.getState().selectRun("new");

    const search = window.location.search;
    expect(search).toContain("run=new");
    expect(search).not.toContain("at=");
    expect(search).not.toContain("node=");
    expect(search).not.toContain("edge=");
  });

  it("removes the run parameter when deselected", async () => {
    window.history.replaceState({}, "", "/?run=old");
    const store = await loadStore();

    store.getState().selectRun(null);
    expect(window.location.search).not.toContain("run=");
  });

  it("keeps the status filter in the URL", async () => {
    const store = await loadStore();

    store.getState().setStatusFilter("error");
    expect(window.location.search).toContain("status=error");

    store.getState().setStatusFilter(null);
    expect(window.location.search).not.toContain("status=");
  });
});
