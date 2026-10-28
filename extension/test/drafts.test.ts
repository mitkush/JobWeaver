import { describe, expect, it, vi } from "vitest";

import { type Deps } from "../src/connection";
import { clear, pageState, select, requireConfirmation, assertConfirmed } from "../src/drafts";

const ORIGIN = "https://jobweaver.example";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const summary = {
  draft_id: "d1",
  job_id: "j1",
  title: "Backend Engineer",
  company: "Acme",
  apply_host: "jobs.lever.co",
  current_version: 3,
  saved_at: "2026-10-23T08:00:00Z",
  application_status: null,
};

function versionOf(number: number, current = 3) {
  return {
    ...summary,
    apply_url: "https://jobs.lever.co/acme/1",
    number,
    current_version: current,
    warnings: 0,
    template: "standard",
    resume_file: "Asha_Acme_Backend_Engineer.pdf",
    cover_letter_file: "Asha_Acme_Backend_Engineer_Cover_Letter.pdf",
  };
}

function makeDeps(routes: Record<string, (url: URL) => Response>) {
  const data = new Map<string, unknown>([
    ["connection", { token: "t", expiresAt: new Date(Date.now() + 3_600_000).toISOString(), email: "a@b.c", name: "A" }],
  ]);
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    const handler = Object.entries(routes).find(([path]) => url.pathname === path)?.[1];
    return handler ? handler(url) : json({ error: { message: "missing" } }, 404);
  });
  const deps: Deps = {
    origin: ORIGIN,
    extensionId: "npdbpfgligiimfnoblngghbokehjbafm",
    store: {
      get: async <T,>(key: string) => data.get(key) as T | undefined,
      set: async (key, value) => void data.set(key, value),
      remove: async (key) => void data.delete(key),
    },
    fetch: fetchMock as unknown as typeof fetch,
    openTab: async () => undefined,
    now: () => Date.now(),
  };
  return { deps, data, fetchMock };
}

const base = {
  "/api/ext/profile": () => json({ reviewed: true, needs_review: false, version: 2, content: {} }),
  "/api/ext/drafts": () => json([summary]),
};

describe("choosing a Draft for a tab", () => {
  it("suggests Drafts whose apply link matches, but selects nothing on its own", async () => {
    const { deps, fetchMock } = makeDeps({ ...base, "/api/ext/drafts/match": () => json({ drafts: [summary] }) });
    const state = await pageState(deps, 7, "https://jobs.lever.co/acme/1/apply");
    expect(state.matches).toEqual([summary]);
    expect(state.selected).toBeNull();
    const matchCall = fetchMock.mock.calls.map(([u]) => new URL(String(u))).find((u) => u.pathname.endsWith("/match"))!;
    expect(matchCall.searchParams.get("url")).toBe("https://jobs.lever.co/acme/1/apply");
  });

  it("never sends non-web addresses to JobWeaver", async () => {
    const { deps, fetchMock } = makeDeps(base);
    await pageState(deps, 7, "chrome://extensions");
    await pageState(deps, 7, undefined);
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes("/match"))).toBe(false);
  });

  it("pins the chosen version per tab, even after a newer save", async () => {
    let current = 3;
    const { deps, data } = makeDeps({
      ...base,
      "/api/ext/drafts/match": () => json({ drafts: [] }),
      "/api/ext/drafts/d1": (url) => json(versionOf(Number(url.searchParams.get("number") ?? current), current)),
    });
    const chosen = await select(deps, 7, "d1");
    expect(chosen?.number).toBe(3);
    expect(data.get("selection:7")).toEqual({ draftId: "d1", number: 3 });

    current = 4;
    const state = await pageState(deps, 7, "https://example.com/apply");
    expect(state.selected?.number).toBe(3);
    expect(state.selected?.current_version).toBe(4);
    expect((await pageState(deps, 8, "https://example.com/apply")).selected).toBeNull();
  });

  it("forgets a selection whose Draft is gone, and clears on request", async () => {
    const { deps, data } = makeDeps({ ...base, "/api/ext/drafts/match": () => json({ drafts: [] }) });
    data.set("selection:7", { draftId: "gone", number: 1 });
    expect((await pageState(deps, 7, "https://example.com")).selected).toBeNull();
    expect(data.has("selection:7")).toBe(false);

    data.set("selection:9", { draftId: "d1", number: 1 });
    await clear(deps, 9);
    expect(data.has("selection:9")).toBe(false);
  });
});

it("keeps a pinned selection when its server request fails temporarily", async () => {
  const { deps, data } = makeDeps({ ...base, "/api/ext/drafts/match": () => json({ drafts: [] }), "/api/ext/drafts/d1": () => json({}, 503) });
  data.set("selection:7", { draftId: "d1", number: 2 });
  await expect(pageState(deps, 7, "https://example.com")).rejects.toThrow(/unavailable/);
  expect(data.get("selection:7")).toEqual({ draftId: "d1", number: 2 });
});
it("requires confirmation after navigation and keeps the chosen version when confirmed", async () => {
  const { deps, data } = makeDeps({ ...base, "/api/ext/drafts/match": () => json({ drafts: [] }), "/api/ext/drafts/d1": (url) => json(versionOf(Number(url.searchParams.get("number") ?? 3))) });
  await select(deps, 7, "d1", 2);
  await requireConfirmation(deps, 7);
  expect((await pageState(deps, 7, "https://other.example/jobs/2")).needsConfirmation).toBe(true);
  await expect(assertConfirmed(deps, 7)).rejects.toThrow(/page changed/);
  await select(deps, 7, "d1", 2);
  await expect(assertConfirmed(deps, 7)).resolves.toBeUndefined();
  expect(data.get("selection:7")).toEqual({ draftId: "d1", number: 2 });
});
it("does not show missing profile or empty drafts when their server requests fail", async () => {
  const { deps } = makeDeps({ ...base, "/api/ext/profile": () => json({}, 500) });
  await expect(pageState(deps, 7, undefined)).rejects.toThrow(/unavailable/);
});
