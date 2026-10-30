import { Inbox, Mail, SearchX } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, Navigate, useLocation, useSearchParams } from "react-router-dom";

import { useFeed } from "@/api/hooks";
import { PageHeader } from "@/app/AppShell";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { buttonClasses } from "@/components/ui/button-classes";
import { EmptyState } from "@/components/ui/empty-state";
import { PageSpinner } from "@/components/ui/spinner";
import { FeedFilters } from "@/features/feed/FeedFilters";
import { clearFilters, feedMatch, feedQuery, hasFilters, PAGE_SIZE, withParam, type FeedMatch } from "@/features/feed/feed-params";
import { Reminders } from "@/features/applications/Reminders";
import { JobCard } from "@/features/feed/JobCard";
import { cn } from "@/lib/cn";
import { fromNow } from "@/lib/time";

type Section = "email" | "link";

function SectionTabs({
  section,
  counts,
  onSelect,
}: {
  section: Section;
  counts: { with_email: number; apply_link_only: number } | undefined;
  onSelect: (section: Section) => void;
}) {
  const tabs: { id: Section; label: string; count?: number }[] = [
    { id: "email", label: "With email", count: counts?.with_email },
    { id: "link", label: "Apply link only", count: counts?.apply_link_only },
  ];
  return (
    <div role="tablist" aria-label="Feed sections" className="mb-4 flex gap-1 border-b border-slate-200 dark:border-slate-800">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          role="tab"
          type="button"
          aria-selected={section === tab.id}
          onClick={() => onSelect(tab.id)}
          className={cn(
            "-mb-px flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium",
            section === tab.id
              ? "border-brand-600 text-slate-900 dark:text-white"
              : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200",
          )}
        >
          {tab.id === "email" && <Mail className="size-4" aria-hidden />}
          {tab.label}
          {tab.count !== undefined && (
            <span className="rounded-full bg-slate-100 px-2 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              {tab.count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}

type Match = FeedMatch;

/** Title matches, differently titled Jobs that match the User's core keywords, and title
 * matches whose advert has no description to confirm a Core keyword. */
function MatchSwitch({
  match,
  counts,
  onSelect,
}: {
  match: Match;
  counts: { title_matches?: number; keyword_matches?: number; review_matches?: number } | undefined;
  onSelect: (match: Match) => void;
}) {
  if (match === "title" && !counts?.keyword_matches && !counts?.review_matches) return null;
  const options: { id: Match; label: string; count?: number }[] = [
    { id: "title", label: "Your titles", count: counts?.title_matches },
    { id: "keywords", label: "Other titles matching your keywords", count: counts?.keyword_matches },
    { id: "review", label: "Needs review", count: counts?.review_matches },
  ];
  return (
    <div className="mb-3 flex flex-wrap gap-2" role="group" aria-label="Which jobs">
      {options
        .filter((option) => option.id === "title" || option.id === match || option.count)
        .map((option) => (
          <Button
            key={option.id}
            size="sm"
            variant={match === option.id ? "primary" : "secondary"}
            aria-pressed={match === option.id}
            onClick={() => onSelect(option.id)}
          >
            {option.label}
            {option.count !== undefined && <span className="ml-1 opacity-80">({option.count})</span>}
          </Button>
        ))}
    </div>
  );
}

/** Bare Feed navigation restores this User's view in this browser tab. An explicit
 * query always wins; replacing the bare entry also keeps browser Back predictable. */
export function FeedPage({ userId }: { userId?: string }) {
  const location = useLocation();
  const storageKey = userId ? `jw-feed-view:${userId}` : null;
  const [initial] = useState(() => {
    try {
      return { key: location.key, search: !location.search && storageKey ? sessionStorage.getItem(storageKey) ?? "" : "" };
    } catch {
      return { key: location.key, search: "" };
    }
  });
  if (location.key === initial.key && initial.search && !location.search) {
    return <Navigate to={{ pathname: "/feed", search: initial.search }} replace />;
  }
  return <FeedView storageKey={storageKey} />;
}

function FeedView({ storageKey }: { storageKey: string | null }) {
  // Clearing from the empty state also resets the filter boxes, whose typed text would
  // otherwise be applied again after the typing pause.
  const [filtersKey, setFiltersKey] = useState(0);
  const [params, setParams] = useSearchParams();
  const search = params.toString();
  useEffect(() => {
    if (!storageKey) return;
    try {
      sessionStorage.setItem(storageKey, search ? `?${search}` : "");
    } catch {
      // URL-based Back still works when browser storage is unavailable.
    }
  }, [storageKey, search]);
  const explicit = params.get("section");
  const requested: Section = explicit === "link" ? "link" : "email";
  const feed = useFeed(feedQuery(params, requested));
  const counts = feed.data?.counts;
  // With no choice made, open the section that has jobs.
  const section: Section =
    !explicit && counts && counts.with_email === 0 && counts.apply_link_only > 0 ? "link" : requested;
  const shown = useFeed(feedQuery(params, section));
  const data = section === requested ? feed.data : shown.data;
  const hidden = params.get("hidden") === "1";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const currentResult = section === requested ? feed : shown;
  useEffect(() => {
    // Previous-query placeholder data cannot tell us how many pages this view has.
    if (!data || currentResult.isPlaceholderData || currentResult.isFetching || currentResult.isError || page <= pages) return;
    setParams(withParam(params, "page", pages > 1 ? String(pages) : null), { replace: true });
  }, [data, currentResult.isPlaceholderData, currentResult.isFetching, currentResult.isError, page, pages, params, setParams]);
  const match = feedMatch(params);
  const nothingAtAll =
    counts && (counts.title_matches ?? 0) + (counts.keyword_matches ?? 0) + (counts.review_matches ?? 0) === 0;

  return (
    <>
      <PageHeader
        title={hidden ? "Hidden jobs" : "Feed"}
        description={
          data?.last_updated_at
            ? `Jobs that match your preferences, one card per real opening. Updated ${fromNow(data.last_updated_at)}.`
            : "Jobs that match your preferences, one card per real opening."
        }
        action={
          <Button variant="secondary" size="sm" onClick={() => setParams(withParam(params, "hidden", hidden ? null : "1"))}>
            {hidden ? "Back to feed" : "Hidden jobs"}
          </Button>
        }
      />
      <Reminders />
      {feed.isError && (
        <Alert tone="error" className="mb-4" title="The feed could not load">
          {feed.error.message}
        </Alert>
      )}
      <FeedFilters key={filtersKey} params={params} onChange={setParams} sources={data?.sources ?? []} />
      <MatchSwitch
        match={match}
        counts={counts}
        onSelect={(next) => setParams(withParam(params, "match", next === "title" ? null : next))}
      />
      <SectionTabs section={section} counts={counts} onSelect={(next) => setParams(withParam(params, "section", next))} />

      {feed.isPending ? (
        <PageSpinner label="Loading your feed" />
      ) : nothingAtAll && hasFilters(params) ? (
        <EmptyState
          icon={SearchX}
          title="No jobs match these filters"
          action={
            <Button
              variant="secondary"
              onClick={() => {
                setParams(clearFilters(params));
                setFiltersKey((k) => k + 1);
              }}
            >
              Clear filters
            </Button>
          }
        >
          Try a wider date range or another location.
        </EmptyState>
      ) : nothingAtAll ? (
        hidden ? (
          <EmptyState
            icon={Inbox}
            title="No hidden jobs"
            action={
              <Button variant="secondary" onClick={() => setParams(withParam(params, "hidden", null))}>
                Back to feed
              </Button>
            }
          >
            Jobs you hide from your feed are kept here, so you can bring them back.
          </EmptyState>
        ) : (
          <EmptyState
            icon={Inbox}
            title="No jobs yet"
            action={
              <Link to="/preferences" className={buttonClasses("secondary")}>
                Review your preferences
              </Link>
            }
          >
            Jobs are collected every morning from LinkedIn, company job boards and other sources. Matching jobs appear
            here after the next collection.
          </EmptyState>
        )
      ) : data && data.items.length === 0 ? (
        <p className="py-10 text-center text-sm text-slate-500 dark:text-slate-400">
          {match === "review"
            ? "No jobs waiting for review here."
            : match === "keywords"
            ? section === "email"
              ? "No differently titled jobs with a contact email here."
              : "No differently titled apply-link-only jobs here."
            : section === "email"
              ? "No jobs with a contact email here."
              : "No apply-link-only jobs here."}
        </p>
      ) : (
        <div className="grid items-start gap-4 xl:grid-cols-2" aria-busy={shown.isFetching || undefined}>
          {data?.items.map((job) => <JobCard key={job.job_id} job={job} />)}
        </div>
      )}

      {data && pages > 1 && (
        <nav aria-label="Pages" className="mt-6 flex items-center justify-between text-sm">
          <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setParams(withParam(params, "page", String(page - 1)))}>
            Previous
          </Button>
          <span className="text-slate-600 dark:text-slate-400">
            Page {page} of {pages}
          </span>
          <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => setParams(withParam(params, "page", String(page + 1)))}>
            Next
          </Button>
        </nav>
      )}
    </>
  );
}
