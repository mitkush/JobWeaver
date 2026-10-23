/** Browser-to-JobWeaver capture. Reading a page does not upload it. */

import { apiFetch, type Deps } from "./connection";
import { clear } from "./drafts";
import { forgetTab, type TabPort } from "./fill/session";
import { pageUrl, type PageJob } from "./job-read";

export type Captured = { job_id: string; title: string; company: string; matched_existing: boolean; draft_id?: string; at: number };
const key = (id: number) => `captured:${id}`;
const readKey = (id: number) => `read-job:${id}`;

async function json<T>(deps: Deps, path: string, body: unknown): Promise<T> {
  const response = await apiFetch(deps, path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!response) throw new Error("Reconnect the extension to approve careers-page capture.");
  const data = await response.json() as T & { error?: { message?: string }; detail?: unknown };
  if (!response.ok) throw new Error(data.error?.message ?? "Check the title, Company and JD. The description needs at least 80 characters.");
  return data;
}

export async function readPage(deps: Deps, port: TabPort, tabId: number): Promise<PageJob> {
  await port.inject(tabId);
  const result = await port.send<PageJob & { error?: string }>(tabId, { type: "jw.read-job" });
  if (result.error) throw new Error(result.error);
  await deps.store.set(readKey(tabId), { url: result.url, at: deps.now() });
  return result;
}

export async function savePage(deps: Deps, port: TabPort, tabId: number, job: PageJob): Promise<Captured> {
  const read = await deps.store.get<{ url: string; at: number }>(readKey(tabId));
  // Read only the current URL to verify that the reviewed text still belongs to this tab.
  const current = await port.send<{ url: string }>(tabId, { type: "jw.page-url" });
  if (!read || read.url !== pageUrl(current.url) || read.url !== job.url || deps.now() - read.at > 30 * 60_000) {
    throw new Error("The page changed or the review expired. Read this job again.");
  }
  const result = await json<Captured>(deps, "/api/ext/jobs/capture", { title: job.title, company: job.company, description: job.description, url: read.url });
  const saved = { ...result, at: deps.now() };
  await deps.store.set(key(tabId), saved);
  await clear(deps, tabId); // Do not carry an unrelated Draft into this captured Job.
  await forgetTab(deps, tabId); // A prepared fill may contain that unrelated Draft's PDF.
  return saved;
}

export async function captured(deps: Deps, tabId: number): Promise<Captured | null> {
  const saved = await deps.store.get<Captured>(key(tabId));
  if (!saved || deps.now() - saved.at > 60 * 60_000) return null;
  return saved;
}

export async function createCapturedDraft(deps: Deps, tabId: number): Promise<Captured> {
  const saved = await captured(deps, tabId);
  if (!saved) throw new Error("Read and save this job first.");
  const result = await json<{ draft_id: string }>(deps, `/api/ext/jobs/${encodeURIComponent(saved.job_id)}/draft`, {});
  const updated = { ...saved, draft_id: result.draft_id };
  await deps.store.set(key(tabId), updated);
  return updated;
}

export async function carryCapture(deps: Deps, openerId: number, tabId: number): Promise<void> {
  const saved = await captured(deps, openerId);
  if (saved) await deps.store.set(key(tabId), saved);
}

export async function clearCapture(deps: Deps, tabId: number): Promise<void> {
  await deps.store.remove(key(tabId));
  await deps.store.remove(readKey(tabId));
}
