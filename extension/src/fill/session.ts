/** One scan-and-fill on one tab, run by the service worker (ADR-0017). The page never
 * sees the credential; it receives only the values the User ticked. */

import { apiFetch, type Deps } from "../connection";
import { assertConfirmed, currentSelection, version } from "../drafts";
import { propose, type Profile, type Proposal } from "./plan";
import type { FillItem, FillReport, Scan } from "./types";

export interface TabPort {
  /** Injects the content script into the tab's main frame (activeTab). */
  frames?(tabId: number): Promise<{ frameId: number; url?: string }[]>;
  inject(tabId: number, frameId?: number): Promise<void>;
  send<T>(tabId: number, message: unknown, frameId?: number): Promise<T>;
}

export type ScanResult = {
  adapter: string;
  proposals: Proposal[];
  /** Labels of fields JobWeaver will not fill: questions, sensitive or unclear fields. */
  manual: string[];
  draft: { title: string; company: string; number: number } | null;
  profileReviewed: boolean;
  unavailableFrames?: number;
};

export type FillResult = FillReport & {
  /** PDFs a site refused, for the popup to offer as downloads. */
  downloads: { name: string; base64: string }[];
  /** Field labels by ref, so a reopened popup can describe the result. */
  labels: Record<string, string>;
};

type FrameScan = { frameId: number; scanId: string; prefix?: string };
type Stored = { frames?: FrameScan[]; scan: Scan; proposals: Proposal[]; draft: { id: string; number: number; currentVersion?: number } | null };

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
  await assertConfirmed(deps, tabId);
  const frames = port.frames ? await port.frames(tabId) : [{ frameId: 0 }];
  const scans: { frameId: number; scan: Scan }[] = [];
  let unavailableFrames = 0;
  for (const frame of frames) {
    try {
      await port.inject(tabId, frame.frameId);
      const reply = await port.send<Scan>(tabId, { type: "jw.scan" }, frame.frameId);
      if (!reply || !Array.isArray(reply.fields)) throw new Error("Frame could not be scanned");
      scans.push({ frameId: frame.frameId, scan: reply });
    } catch { unavailableFrames++; }
  }
  if (!scans.length) throw new Error("This page cannot be scanned yet. Click JobWeaver in the toolbar on this tab, or allow its site, then retry.");
  const scan: Scan = { ...scans[0]!.scan, fields: scans.flatMap(({ frameId, scan }) => scan.fields.map(field => ({ ...field, ref: frames.length > 1 ? `frame${frameId}:${field.ref}` : field.ref }))) };
  const profileResponse = await apiFetch(deps, "/api/ext/profile");
  const profile = profileResponse?.ok ? ((await profileResponse.json()) as { reviewed: boolean; content: Profile | null }) : null;
  const selection = await currentSelection(deps, tabId);
  const chosen = selection ? await version(deps, selection.draftId, selection.number) : null;
  const files = chosen ? { resume: chosen.resume_file, cover_letter: chosen.cover_letter_file, background_answer: chosen.background_answer } : null;
  const proposals = propose(scan.fields, profile?.reviewed ? profile.content : null, files);
  const proposed = new Set(proposals.map((p) => p.ref));
  await deps.store.set(key(tabId), {
    frames: scans.map(f => ({ frameId: f.frameId, scanId: f.scan.scanId, prefix: frames.length > 1 ? `frame${f.frameId}:` : "" })),
    scan,
    proposals,
    draft: chosen ? { id: chosen.draft_id, number: chosen.number, currentVersion: chosen.current_version } : null,
  } satisfies Stored);
  return {
    unavailableFrames,
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
export async function fillTab(deps: Deps, port: TabPort, tabId: number, refs: string[], answers: Record<string, string> = {}): Promise<FillResult> {
  await assertConfirmed(deps, tabId);
  const stored = await deps.store.get<Stored>(key(tabId));
  if (!stored) return { filled: [], failed: [{ ref: "", reason: "Scan the form first" }], downloads: [], labels: {} };
  // An accepted replacement since the scan: the User reviews the document again first.
  if (stored.draft?.currentVersion !== undefined) {
    const latest = await version(deps, stored.draft.id, stored.draft.number);
    if (!latest || latest.current_version !== stored.draft.currentVersion) throw new Error("The resume was updated. Review the selected document and scan again before filling.");
  }
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
      const value = proposal.reviewRequired ? answers[field.ref]?.trim() : proposal.value;
      if (!value || (field.maxLength && value.length > field.maxLength)) {
        failed.push({ ref: field.ref, reason: "Review the answer and its length before filling" });
        continue;
      }
      items.push({ ref: field.ref, kind: field.kind, value });
    }
  }
  const report: FillReport = { filled: [], failed: [] };
  const frames = stored.frames ?? [{ frameId: 0, scanId: stored.scan.scanId }];
  for (const frame of frames) {
    const prefix = frame.prefix ?? `frame${frame.frameId}:`;
    const selected = items.filter(item => !item.ref.startsWith("frame") || item.ref.startsWith(prefix));
    if (!selected.length) continue;
    const localItems = selected.map(item => ({ ...item, ref: item.ref.startsWith(prefix) ? item.ref.slice(prefix.length) : item.ref }));
    try {
      const result = await port.send<FillReport>(tabId, { type: "jw.fill", scanId: frame.scanId, items: localItems }, frame.frameId);
      const globalRef = (ref: string) => selected.find(item => item.ref === ref || item.ref === prefix + ref)?.ref ?? ref;
      report.filled.push(...result.filled.map(globalRef));
      report.failed.push(...result.failed.map(f => ({ ...f, ref: globalRef(f.ref) })));
    } catch { report.failed.push(...selected.map(item => ({ ref: item.ref, reason: "This frame changed or cannot be reached. Scan again." }))); }
  }
  await deps.store.set(`undo-frames:${tabId}`, frames);
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
  const frames = await deps.store.get<FrameScan[]>(`undo-frames:${tabId}`) ?? [{ frameId: 0, scanId: "" }];
  const report: FillReport = { filled: [], failed: [] };
  for (const frame of frames) {
    try {
      const result = await port.send<FillReport>(tabId, { type: "jw.undo" }, frame.frameId);
      const ref = (value: string) => `${frame.prefix ?? (frames.length > 1 ? `frame${frame.frameId}:` : "")}${value}`;
      report.filled.push(...result.filled.map(ref));
      report.failed.push(...result.failed.map(f => ({ ...f, ref: ref(f.ref) })));
    } catch { report.failed.push({ ref: "", reason: "A frame is unavailable; check it manually." }); }
  }
  await deps.store.remove(resultKey(tabId));
  return report;
}

export async function forgetTab(deps: Deps, tabId: number): Promise<void> {
  await deps.store.remove(key(tabId));
  await deps.store.remove(resultKey(tabId));
  await deps.store.remove(`undo-frames:${tabId}`);
}

export async function lastScan(deps: Deps, tabId: number): Promise<ScanResult | null> {
  await assertConfirmed(deps, tabId);
  const stored = await deps.store.get<Stored>(key(tabId));
  if (!stored) return null;
  return { adapter: stored.scan.adapter, proposals: stored.proposals, manual: stored.scan.fields.filter(f => !stored.proposals.some(p => p.ref === f.ref)).map(f => f.label), draft: stored.draft ? { title: "Selected Job", company: "", number: stored.draft.number } : null, profileReviewed: true };
}

export async function forgetScan(deps: Deps, tabId: number): Promise<void> { await deps.store.remove(key(tabId)); }
