import { expect, it } from "vitest";

import type { Deps } from "../src/connection";
import { reviewState } from "../src/review-state";

function makeDeps(email = "asha@example.com") {
  const data = new Map<string, unknown>([["connection", { token: "t", expiresAt: new Date(Date.now() + 3_600_000).toISOString(), email, name: "A" }]]);
  let now = 1_000_000;
  const deps = {
    origin: "https://jobweaver.example",
    extensionId: "x",
    store: {
      get: async <T,>(k: string) => data.get(k) as T | undefined,
      set: async (k: string, v: unknown) => void data.set(k, v),
      remove: async (k: string) => void data.delete(k),
    },
    fetch: fetch,
    openTab: async () => undefined,
    now: () => now,
  } as unknown as Deps;
  return { deps, data, advance: (ms: number) => (now += ms) };
}

const page = "https://careers.example.com/jobs/1";
const job = { title: "Engineer", company: "Example", description: "Edited text", url: page, method: "page text" as const, truncated: false };

it("restores unfinished review text for the same user, page and document only", async () => {
  const { deps, data } = makeDeps();
  await reviewState(deps, 4, page, { draftId: "d1", number: 2 }, { capture: job, answers: { q: "My answer" } });
  expect(await reviewState(deps, 4, page, { draftId: "d1", number: 2 })).toEqual({ capture: job, answers: { q: "My answer" } });
  expect(await reviewState(deps, 4, "https://careers.example.com/jobs/2", { draftId: "d1", number: 2 })).toEqual({});
  expect(await reviewState(deps, 4, page, { draftId: "d1", number: 3 })).toEqual({});
  data.set("connection", { token: "t", expiresAt: new Date(Date.now() + 3_600_000).toISOString(), email: "other@example.com", name: "B" });
  expect(await reviewState(deps, 4, page, { draftId: "d1", number: 2 })).toEqual({});
});

it("forgets review text after half an hour and refuses oversized text", async () => {
  const { deps, advance } = makeDeps();
  await reviewState(deps, 4, page, null, { answers: { q: "A" } });
  advance(31 * 60_000);
  expect(await reviewState(deps, 4, page, null)).toEqual({});
  await expect(reviewState(deps, 4, page, null, { answers: { q: "x".repeat(100_001) } })).rejects.toThrow("too long");
});

it("keeps nothing without a connection or on browser pages", async () => {
  const { deps, data } = makeDeps();
  expect(await reviewState(deps, 4, "chrome://extensions", null, { answers: { q: "A" } })).toEqual({});
  data.delete("connection");
  expect(await reviewState(deps, 4, page, null, { answers: { q: "A" } })).toEqual({});
});
