// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";

afterEach(() => { vi.unstubAllGlobals(); delete window.__jobweaver; });

it("registers the capture reader even when the old form helper marked the page", async () => {
  vi.resetModules();
  window.__jobweaver = true;
  const addListener = vi.fn();
  vi.stubGlobal("chrome", { runtime: { id: "extension-id", onMessage: { addListener, removeListener: vi.fn() } } });
  await import("../src/content");
  expect(addListener).toHaveBeenCalledTimes(1);
});

it("keeps one listener when the current helper is injected repeatedly", async () => {
  vi.resetModules();
  const addListener = vi.fn();
  vi.stubGlobal("chrome", { runtime: { id: "extension-id", onMessage: { addListener, removeListener: vi.fn() } } });
  await import("../src/content");
  vi.resetModules();
  await import("../src/content");
  expect(addListener).toHaveBeenCalledTimes(1);
});
