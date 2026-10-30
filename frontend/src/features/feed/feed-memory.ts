/** Per browser tab, per account: the last Feed URL, each view's own filters, and where the
 * User was on the page when they opened a Job. Storage can be unavailable (private
 * windows, blocked site data); then the URL alone still works. */

import type { FeedView } from "./feed-params";

const SCROLL_KEY = "jw-feed-scroll";

export function lastFeedKey(userId: string): string {
  return `jw-feed-view:${userId}`;
}

export function viewKey(userId: string, view: FeedView): string {
  return `jw-feed-view:${userId}:${view}`;
}

export function read(key: string): string | null {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

export function write(key: string, value: string): void {
  try {
    sessionStorage.setItem(key, value);
  } catch {
    // The URL still carries the view.
  }
}

/** Called when a Job is opened from the Feed. */
export function rememberScroll(search: string): void {
  write(SCROLL_KEY, JSON.stringify({ search, y: window.scrollY }));
}

/** The position to go back to on this exact Feed URL, used once. */
export function takeScroll(search: string): number | null {
  const raw = read(SCROLL_KEY);
  if (!raw) return null;
  try {
    const saved = JSON.parse(raw) as { search?: unknown; y?: unknown };
    if (saved.search !== search || typeof saved.y !== "number") return null;
    sessionStorage.removeItem(SCROLL_KEY);
    return saved.y;
  } catch {
    return null;
  }
}
