/** Unfinished review stays private to this browser session and exact user/page/document. */
import { currentConnection, type Deps } from "./connection";
import type { PageJob } from "./job-read";
export type ReviewState = { capture?: PageJob | null; answers?: Record<string, string>; answerOrigins?: Record<string, "user" | "suggestion">; answerIds?: Record<string, string> };
export async function reviewState(deps: Deps, tabId: number, url: string | undefined,
  selection: { draftId: string; number: number } | null, patch?: ReviewState): Promise<ReviewState> {
  const connection = await currentConnection(deps);
  if (!connection || !url || !/^https?:/.test(url)) return {};
  const key = `review:${tabId}`;
  const identity = JSON.stringify([connection.email, url, selection?.draftId, selection?.number]);
  const stored = await deps.store.get<{ identity: string; at: number; data: ReviewState }>(key);
  const data = stored?.identity === identity && deps.now() - stored.at < 30 * 60_000 ? stored.data : {};
  if (patch) {
    if (JSON.stringify(patch).length > 100_000) throw new Error("Review text is too long");
    const updated = { ...data, ...patch };
    await deps.store.set(key, { identity, at: deps.now(), data: updated });
    return updated;
  }
  return data;
}
