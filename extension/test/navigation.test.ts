import { afterEach, expect, it, vi } from "vitest";

afterEach(() => { vi.unstubAllGlobals(); vi.resetModules(); });

it("invalidates a retained Draft and prepared fill even when navigation hides the URL", async () => {
  const data: Record<string, unknown> = { "selection:7": { draftId: "d1", number: 2 }, "fill:7": {}, "filled:7": {} };
  let updated: ((tabId: number, change: { status?: string; url?: string }) => void) | undefined;
  vi.stubGlobal("__JOBWEAVER_ORIGIN__", "https://jobweaver.example");
  vi.stubGlobal("chrome", {
    storage: { session: {
      setAccessLevel: async () => undefined,
      get: async (key: string) => ({ [key]: data[key] }),
      set: async (items: Record<string, unknown>) => Object.assign(data, items),
      remove: async (key: string) => { delete data[key]; },
    } },
    runtime: { id: "test", onMessage: { addListener: vi.fn() }, onMessageExternal: { addListener: vi.fn() } },
    tabs: {
      onRemoved: { addListener: vi.fn() }, onCreated: { addListener: vi.fn() },
      onUpdated: { addListener: (callback: typeof updated) => { updated = callback; } },
    },
  });
  await import("../src/background");
  updated!(7, { status: "loading" });
  await vi.waitFor(() => {
    expect(data["confirm-job:7"]).toBe(true);
    expect(data["fill:7"]).toBeUndefined();
    expect(data["filled:7"]).toBeUndefined();
  });
  expect(data["selection:7"]).toEqual({ draftId: "d1", number: 2 });
});
