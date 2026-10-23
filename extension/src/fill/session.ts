/** One scan-and-fill on one tab, run by the service worker (ADR-0017). The page never
 * sees the credential; it receives only the values the User ticked. */

import { apiFetch, type Deps } from "../connection";
import { currentSelection, version } from "../drafts";
import { propose, type Profile, type Proposal } from "./plan";
import type { FillItem, FillReport, Scan } from "./types";

export interface TabPort {
  /** Injects the content script into the tab's main frame (activeTab). */
  inject(tabId: number): Promise<void>;
  send<T>(tabId: number, message: unknown): Promise<T>;
}

export type ScanResult = {
  adapter: string;
  proposals: Proposal[];
  /** Labels of fields JobWeaver will not fill: questions, sensitive or unclear fields. */
  manual: string[];
  draft: { title: string; company: string; number: number } | null;
  profileReviewed: boolean;
};

export type FillResult = FillReport & {
  /** PDFs a site refused, for the popup to offer as downloads. */
  downloads: { name: string; base64: string }[];
  /** Field labels by ref, so a reopened popup can describe the result. */
  labels: Record<string, string>;
};

type Stored = { scan: Scan; proposals: Proposal[]; draft: { id: string; number: number } | null };

const key = (tabId: number) => `fill:${tabId}`;
// Kept until Undo or a new page: the popup closes whenever the User clicks the page.
const resultKey = (tabId: number) => `filled:${tabId}`;

function toBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

export async function scanTab(deps: Deps, port: TabPort, tabId: number): Promise<ScanResult> {
  await port.inject(tabId);
  const scan = await port.send<Scan>(tabId, { type: "jw.scan" });
  const profileResponse = await apiFetch(deps, "/api/ext/profile");
  const profile = profileResponse?.ok ? ((await profileResponse.json()) as { reviewed: boolean; content: Profile | null }) : null;
  const selection = await currentSelection(deps, tabId);
  const chosen = selection ? await version(deps, selection.draftId, selection.number) : null;
  const files = chosen ? { resume: chosen.resume_file, cover_letter: chosen.cover_letter_file } : null;
  const proposals = propose(scan.fields, profile?.reviewed ? profile.content : null, files);
  const proposed = new Set(proposals.map((p) => p.ref));
  await deps.store.set(key(tabId), {
    scan,
    proposals,
    draft: chosen ? { id: chosen.draft_id, number: chosen.number } : null,
  } satisfies Stored);
  return {
    adapter: scan.adapter,
    proposals,
    manual: scan.fields.filter((f) => !proposed.has(f.ref)).map((f) => f.label),
    draft: chosen ? { title: chosen.title, company: chosen.company, number: chosen.number } : null,
    profileReviewed: Boolean(profile?.reviewed),
  };
}

async function pdf(deps: Deps, draft: { id: string; number: number }, kind: "resume" | "cover_letter") {
  const response = await apiFetch(deps, `/api/ext/drafts/${encodeURIComponent(draft.id)}/pdf?number=${draft.number}&kind=${kind}`);
  if (!response?.ok) throw new Error("JobWeaver could not make the PDF");
  return toBase64(await response.arrayBuffer());
}

/** Fills only the ticked proposals from the last scan of this tab. */
export async function fillTab(deps: Deps, port: TabPort, tabId: number, refs: string[]): Promise<FillResult> {
  const stored = await deps.store.get<Stored>(key(tabId));
  if (!stored) return { filled: [], failed: [{ ref: "", reason: "Scan the form first" }], downloads: [], labels: {} };
  const wanted = new Set(refs);
  const items: FillItem[] = [];
  const pdfs = new Map<string, string>();
  const downloads: FillResult["downloads"] = [];
  const failed: FillReport["failed"] = [];
  for (const proposal of stored.proposals.filter((p) => wanted.has(p.ref))) {
    const field = stored.scan.fields.find((f) => f.ref === proposal.ref);
    if (!field) continue;
    if (field.kind === "file") {
      const kind = proposal.key === "cover_letter" ? "cover_letter" : "resume";
      if (!stored.draft) continue;
      try {
        const base64 = pdfs.get(kind) ?? (await pdf(deps, stored.draft, kind));
        pdfs.set(kind, base64);
        items.push({ ref: field.ref, kind: "file", file: { name: proposal.value, type: "application/pdf", base64 } });
      } catch (error) {
        failed.push({ ref: field.ref, reason: (error as Error).message });
      }
    } else {
      items.push({ ref: field.ref, kind: field.kind, value: proposal.value });
    }
  }
  const report = await port.send<FillReport>(tabId, { type: "jw.fill", scanId: stored.scan.scanId, items });
  for (const failure of report.failed) {
    const item = items.find((i) => i.ref === failure.ref);
    if (item?.kind === "file") downloads.push({ name: item.file.name, base64: item.file.base64 });
  }
  const labels = Object.fromEntries(stored.proposals.map((p) => [p.ref, p.label]));
  const result: FillResult = { filled: report.filled, failed: [...failed, ...report.failed], downloads, labels };
  if (result.filled.length || result.downloads.length) await deps.store.set(resultKey(tabId), result);
  return result;
}

/** The last fill on this tab, for a popup reopened after checking the page. */
export async function lastFill(deps: Deps, tabId: number): Promise<FillResult | null> {
  return (await deps.store.get<FillResult>(resultKey(tabId))) ?? null;
}

export async function undoTab(deps: Deps, port: TabPort, tabId: number): Promise<FillReport> {
  const report = await port.send<FillReport>(tabId, { type: "jw.undo" });
  await deps.store.remove(resultKey(tabId));
  return report;
}

export async function forgetTab(deps: Deps, tabId: number): Promise<void> {
  await deps.store.remove(key(tabId));
  await deps.store.remove(resultKey(tabId));
}
