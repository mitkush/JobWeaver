/** Choosing the Draft, and its exact version, the extension will use on a page (ADR-0017).
 * A page may suggest a Draft by its apply link, but nothing is chosen without the User. */

import { apiFetch, type Deps } from "./connection";

export type DraftSummary = {
  draft_id: string;
  job_id: string;
  title: string;
  company: string;
  apply_host: string | null;
  current_version: number;
  saved_at: string;
  application_status: string | null;
};

export type DraftVersion = {
  draft_id: string;
  job_id: string;
  title: string;
  company: string;
  apply_url: string | null;
  number: number;
  current_version: number;
  saved_at: string;
  warnings: number;
  template: "standard" | "compact";
  resume_file: string;
  cover_letter_file: string;
  application_status: string | null;
};

export type ProfileState = { reviewed: boolean; needs_review: boolean; version: number };

export type PageState = {
  profile: ProfileState | null;
  matches: DraftSummary[];
  recent: DraftSummary[];
  selected: DraftVersion | null;
};

type Selection = { draftId: string; number: number };

const selectionKey = (tabId: number) => `selection:${tabId}`;

async function getJson<T>(deps: Deps, path: string): Promise<T | null> {
  const response = await apiFetch(deps, path);
  if (!response?.ok) return null;
  return (await response.json()) as T;
}

export async function version(deps: Deps, draftId: string, number?: number): Promise<DraftVersion | null> {
  const query = number ? `?number=${number}` : "";
  return getJson<DraftVersion>(deps, `/api/ext/drafts/${encodeURIComponent(draftId)}${query}`);
}

/** Everything the popup shows for one tab. Matching only reads the page's address. */
export async function pageState(deps: Deps, tabId: number, url: string | undefined): Promise<PageState> {
  const httpPage = url && /^https?:\/\//.test(url) ? url : null;
  const [profile, matched, recent] = await Promise.all([
    getJson<ProfileState>(deps, "/api/ext/profile"),
    httpPage ? getJson<{ drafts: DraftSummary[] }>(deps, `/api/ext/drafts/match?url=${encodeURIComponent(httpPage)}`) : null,
    getJson<DraftSummary[]>(deps, "/api/ext/drafts"),
  ]);
  const chosen = await deps.store.get<Selection>(selectionKey(tabId));
  const selected = chosen ? await version(deps, chosen.draftId, chosen.number) : null;
  if (chosen && !selected) await deps.store.remove(selectionKey(tabId));
  return { profile, matches: matched?.drafts ?? [], recent: recent ?? [], selected };
}

/** Pins a version: a newer save of the Draft never replaces it silently. */
export async function select(deps: Deps, tabId: number, draftId: string, number?: number): Promise<DraftVersion | null> {
  const chosen = await version(deps, draftId, number);
  if (!chosen) return null;
  await deps.store.set(selectionKey(tabId), { draftId: chosen.draft_id, number: chosen.number } satisfies Selection);
  return chosen;
}

export async function currentSelection(deps: Deps, tabId: number): Promise<Selection | null> {
  return (await deps.store.get<Selection>(selectionKey(tabId))) ?? null;
}

export async function clear(deps: Deps, tabId: number): Promise<void> {
  await deps.store.remove(selectionKey(tabId));
}
