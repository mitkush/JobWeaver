import { expect, it, vi } from "vitest";
import { captured, carryCapture, createCapturedDraft, readPage, savePage } from "../src/capture";
import type { Deps } from "../src/connection";
import type { TabPort } from "../src/fill/session";
import type { PageJob } from "../src/job-read";

const job: PageJob = { title: "Rails developer", company: "Example", description: "Public job description. ".repeat(6), url: "https://example.com/jobs/42", method: "page text", truncated: false };

function setup() {
  const values = new Map<string, unknown>([["connection", { token: "secret", expiresAt: "2099-01-01T00:00:00Z" }], ["selection:1", { draftId: "unrelated", number: 1 }], ["fill:1", { proposals: ["stale PDF"] }]]);
  const fetch = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify(String(input).endsWith("/draft") ? { draft_id: "d1", state: "queued" } : { job_id: "j1", title: job.title, company: job.company, matched_existing: false }), { status: 201 }));
  const deps: Deps = { origin: "https://jobweaver.example", extensionId: "id", now: () => 0, openTab: async () => {}, fetch: fetch as typeof globalThis.fetch, store: {
    get: async <T,>(key: string) => values.get(key) as T | undefined,
    set: async (key, value) => { values.set(key, value); }, remove: async (key) => { values.delete(key); },
  } };
  let currentUrl = job.url;
  const port: TabPort = { inject: vi.fn(async () => {}), send: async <T,>(_id: number, message: unknown) => ((message as { type: string }).type === "jw.read-job" ? job : { url: currentUrl }) as T };
  return { deps, port, fetch, values, changePage: () => { currentUrl = "https://example.com/jobs/other"; } };
}

it("reads locally, sends only reviewed fields on Save, then creates a Draft explicitly", async () => {
  const { deps, port, fetch, values } = setup();
  await readPage(deps, port, 1);
  expect(fetch).not.toHaveBeenCalled();
  await savePage(deps, port, 1, { ...job, company: "Reviewed Company" });
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(JSON.parse(fetch.mock.calls[0]![1]!.body as string)).toMatchObject({ company: "Reviewed Company", description: job.description });
  expect(values.has("selection:1")).toBe(false);
  expect(values.has("fill:1")).toBe(false);
  await createCapturedDraft(deps, 1);
  expect((await captured(deps, 1))?.draft_id).toBe("d1");
  await carryCapture(deps, 1, 2);
  expect((await captured(deps, 2))?.job_id).toBe("j1");
});

it("rejects a changed page before uploading reviewed text", async () => {
  const { deps, port, fetch, changePage } = setup();
  await readPage(deps, port, 1);
  changePage();
  await expect(savePage(deps, port, 1, job)).rejects.toThrow("page changed");
  expect(fetch).not.toHaveBeenCalled();
});
