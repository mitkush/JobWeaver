import { describe, expect, it, vi } from "vitest";

import { requireConfirmation } from "../src/drafts";
import type { Deps } from "../src/connection";
import { fillTab, forgetTab, lastFill, scanTab, undoTab, type TabPort } from "../src/fill/session";
import type { FillItem, Scan } from "../src/fill/types";

const ORIGIN = "https://jobweaver.example";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const scan: Scan = {
  scanId: "s1",
  url: "https://jobs.example/apply",
  adapter: "generic",
  fields: [
    { ref: "r1", kind: "text", label: "First name", key: "first_name", required: true, hasValue: false },
    { ref: "r2", kind: "text", label: "City", key: "city", required: false, hasValue: true },
    { ref: "r3", kind: "file", label: "Resume", key: "resume", required: true, hasValue: false },
    { ref: "r4", kind: "textarea", label: "Why us?", key: null, required: false, hasValue: false },
  ],
};

function setup(reply: (items: FillItem[]) => { filled: string[]; failed: { ref: string; reason: string }[] }) {
  const data = new Map<string, unknown>([
    ["connection", { token: "t", expiresAt: new Date(Date.now() + 3_600_000).toISOString(), email: "a@b.c", name: "A" }],
    ["selection:5", { draftId: "d1", number: 2 }],
  ]);
  const requested: string[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    requested.push(url.pathname + url.search);
    if (url.pathname === "/api/ext/profile") {
      return json({ reviewed: true, needs_review: false, version: 1, content: { first_name: "Asha", city: "Bengaluru" } });
    }
    if (url.pathname === "/api/ext/drafts/d1/pdf") return new Response(new Uint8Array([37, 80, 68, 70]), { status: 200 });
    if (url.pathname === "/api/ext/drafts/d1") {
      return json({ draft_id: "d1", job_id: "j1", title: "Backend Engineer", company: "Acme", apply_url: null, number: 2, current_version: 3, saved_at: "2026-10-23T08:00:00Z", warnings: 0, template: "standard", resume_file: "Asha_Acme.pdf", cover_letter_file: "Asha_Acme_Cover_Letter.pdf", application_status: null });
    }
    return json({}, 404);
  });
  const deps: Deps = {
    origin: ORIGIN,
    extensionId: "npdbpfgligiimfnoblngghbokehjbafm",
    store: {
      get: async <T,>(k: string) => data.get(k) as T | undefined,
      set: async (k, v) => void data.set(k, v),
      remove: async (k) => void data.delete(k),
    },
    fetch: fetchMock as unknown as typeof fetch,
    openTab: async () => undefined,
    now: () => Date.now(),
  };
  const sent: unknown[] = [];
  const port: TabPort = {
    inject: vi.fn(async () => undefined),
    send: async <T,>(_tab: number, message: unknown) => {
      sent.push(message);
      const m = message as { type: string; items?: FillItem[] };
      return (m.type === "jw.scan" ? scan : reply(m.items ?? [])) as T;
    },
  };
  return { deps, port, sent, requested };
}

describe("scan and fill", () => {
  it("proposes profile values and the pinned version's PDF, leaving questions to the User", async () => {
    const { deps, port } = setup(() => ({ filled: [], failed: [] }));
    const result = await scanTab(deps, port, 5);
    expect(result.proposals.map((p) => [p.ref, p.value, p.overwrite])).toEqual([
      ["r1", "Asha", false],
      ["r2", "Bengaluru", true],
      ["r3", "Asha_Acme.pdf", false],
    ]);
    expect(result.manual).toEqual(["Why us?"]);
    expect(result.draft).toEqual({ title: "Backend Engineer", company: "Acme", number: 2 });
  });

  it("sends only ticked fields, with the PDF of the exact version", async () => {
    const { deps, port, sent, requested } = setup((items) => ({ filled: items.map((i) => i.ref), failed: [] }));
    await scanTab(deps, port, 5);
    const result = await fillTab(deps, port, 5, ["r1", "r3"]);
    expect(result.filled).toEqual(["r1", "r3"]);
    const fill = sent.at(-1) as { scanId: string; items: FillItem[] };
    expect(fill.scanId).toBe("s1");
    expect(fill.items.map((i) => i.ref)).toEqual(["r1", "r3"]);
    expect(requested).toContain("/api/ext/drafts/d1/pdf?number=2&kind=resume");
    const file = fill.items[1] as Extract<FillItem, { kind: "file" }>;
    expect(atob(file.file.base64)).toBe("%PDF");
  });

  it("offers a PDF the site refused as a download", async () => {
    const { deps, port } = setup((items) => ({
      filled: items.filter((i) => i.kind !== "file").map((i) => i.ref),
      failed: items.filter((i) => i.kind === "file").map((i) => ({ ref: i.ref, reason: "The site did not accept the file" })),
    }));
    await scanTab(deps, port, 5);
    const result = await fillTab(deps, port, 5, ["r1", "r3"]);
    expect(result.downloads).toEqual([{ name: "Asha_Acme.pdf", base64: btoa("%PDF") }]);
  });

  it("keeps the result for a reopened popup until Undo or a new page", async () => {
    const { deps, port } = setup((items) => ({ filled: items.map((i) => i.ref), failed: [] }));
    await scanTab(deps, port, 5);
    await fillTab(deps, port, 5, ["r1", "r3"]);
    // The popup closed when the User clicked the page; reopening finds the result.
    expect(await lastFill(deps, 5)).toMatchObject({ filled: ["r1", "r3"], labels: { r1: "First name", r3: "Resume" } });
    expect(await lastFill(deps, 6)).toBeNull();
    await undoTab(deps, port, 5);
    expect(await lastFill(deps, 5)).toBeNull();

    await scanTab(deps, port, 5);
    await fillTab(deps, port, 5, ["r1"]);
    await forgetTab(deps, 5); // the tab moved to another page
    expect(await lastFill(deps, 5)).toBeNull();
  });

  it("fills nothing without a scan of this tab", async () => {
    const { deps, port, sent } = setup(() => ({ filled: [], failed: [] }));
    const result = await fillTab(deps, port, 9, ["r1"]);
    expect(result.filled).toEqual([]);
    expect(sent).toEqual([]);
  });
});

it("requires an explicitly reviewed answer and fills the edited text", async () => {
  const { deps, port, sent } = setup((items) => ({ filled: items.map((i) => i.ref), failed: [] }));
  await deps.store.set("fill:5", {
    scan: { ...scan, fields: [{ ref: "q", kind: "textarea", key: "background_answer", maxLength: 40 }] },
    proposals: [{ ref: "q", key: "background_answer", value: "Old letter text", reviewRequired: true }],
    draft: { id: "d1", number: 2 },
  });
  expect((await fillTab(deps, port, 5, ["q"])).filled).toEqual([]);
  expect((await fillTab(deps, port, 5, ["q"], { q: "My reviewed answer" })).filled).toEqual(["q"]);
  expect((sent.at(-1) as { items: FillItem[] }).items).toEqual([{ ref: "q", kind: "textarea", value: "My reviewed answer" }]);
  expect((await fillTab(deps, port, 5, ["q"], { q: "x".repeat(41) })).failed).toHaveLength(1);
});

it("refuses scan and prepared fill after navigation until the Draft is reconfirmed", async () => {
  const { deps, port } = setup((items) => ({ filled: items.map(i => i.ref), failed: [] }));
  await scanTab(deps, port, 5);
  await requireConfirmation(deps, 5);
  await expect(scanTab(deps, port, 5)).rejects.toThrow(/Confirm/);
  await expect(fillTab(deps, port, 5, ["r3"])).rejects.toThrow(/Confirm/);
});
