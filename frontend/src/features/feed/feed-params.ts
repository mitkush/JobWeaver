import type { FeedQuery } from "@/api/client";

export const PAGE_SIZE = 20;
const FILTERS = ["q", "location", "work_mode", "source", "within"] as const;
export type FilterKey = (typeof FILTERS)[number];

/** The Feed's state lives in the URL, so Back and shared links keep it. */
export function feedQuery(params: URLSearchParams, section: "email" | "link"): FeedQuery {
  const page = Math.max(1, Number(params.get("page")) || 1);
  const within = Number(params.get("within")) || undefined;
  const mode = params.get("work_mode");
  return {
    section,
    match: feedMatch(params),
    q: params.get("q") || undefined,
    location: params.get("location") || undefined,
    work_mode: mode === "onsite" || mode === "hybrid" || mode === "remote" ? mode : undefined,
    source: params.get("source") || undefined,
    posted_within_days: within,
    hidden: params.get("hidden") === "1",
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  };
}

export type FeedMatch = "title" | "keywords" | "review";

export function feedMatch(params: URLSearchParams): FeedMatch {
  const match = params.get("match");
  return match === "keywords" || match === "review" ? match : "title";
}

export function hasFilters(params: URLSearchParams): boolean {
  return FILTERS.some((key) => params.get(key));
}

export function withParam(params: URLSearchParams, key: string, value: string | null): URLSearchParams {
  const next = new URLSearchParams(params);
  if (value) next.set(key, value);
  else next.delete(key);
  if (key !== "page") next.delete("page");
  return next;
}

export function clearFilters(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const key of [...FILTERS, "page"]) next.delete(key);
  return next;
}
