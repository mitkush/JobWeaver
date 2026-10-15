import { useState } from "react";

import { useFetchRuns, useSources } from "@/api/hooks";
import { PageHeader } from "@/app/AppShell";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { PageSpinner } from "@/components/ui/spinner";
import { AiUsage } from "@/features/sources/AiUsage";
import { SourceCard } from "@/features/sources/SourceCard";
import { formatQueryKey } from "@/lib/query-key";
import { fromNow } from "@/lib/time";

const STATUS_TONE = { succeeded: "success", failed: "danger", running: "brand", skipped: "neutral" } as const;
const RUNS_PAGE_SIZE = 20;

function RecentRuns() {
  const [page, setPage] = useState(0);
  const runs = useFetchRuns(page, RUNS_PAGE_SIZE);
  const items = runs.data?.slice(0, RUNS_PAGE_SIZE) ?? [];
  const hasNext = (runs.data?.length ?? 0) > RUNS_PAGE_SIZE;
  return (
    <Card>
      <CardHeader title="Recent runs" description="Each search or company board fetched, newest first." />
      {runs.isPending && <PageSpinner />}
      {runs.isError && <Alert tone="error">{runs.error.message}</Alert>}
      <div key={page} className="max-h-96 overflow-auto" role="region" aria-label="Recent fetch runs" tabIndex={0}>
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 bg-white text-xs text-slate-500 dark:bg-slate-900">
            <tr>
              <th className="px-6 py-2 font-medium">When</th>
              <th className="px-3 py-2 font-medium">Source</th>
              <th className="px-3 py-2 font-medium">Search or board</th>
              <th className="px-3 py-2 font-medium">Result</th>
              <th className="px-3 py-2 text-right font-medium">New</th>
              <th className="px-6 py-2 text-right font-medium">Cost</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {items.map((run) => (
              <tr key={run.id}>
                <td className="px-6 py-2 whitespace-nowrap">{fromNow(run.created_at)}</td>
                <td className="px-3 py-2">{run.source}</td>
                <td className="max-w-64 px-3 py-2">
                  <span className="block truncate" title={run.board ?? formatQueryKey(run.query_key)}>
                    {run.board ?? formatQueryKey(run.query_key)}
                  </span>
                  {run.error && (
                    <span className={`mt-0.5 block text-xs ${run.status === "failed" ? "text-red-600 dark:text-red-400" : "text-amber-700 dark:text-amber-300"}`}>
                      {run.error}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2">
                  {/* A succeeded run with a message reached the provider's record cap. */}
                  {run.status === "succeeded" && run.error
                    ? <Badge tone="warning">incomplete</Badge>
                    : <Badge tone={STATUS_TONE[run.status]}>{run.status}</Badge>}
                </td>
                <td className="px-3 py-2 text-right">{run.postings_new}</td>
                <td className="px-6 py-2 text-right">{run.credits_used || "-"}</td>
              </tr>
            ))}
            {!runs.isPending && !runs.isError && items.length === 0 && (
              <tr><td colSpan={6} className="px-6 py-4 text-slate-500">No fetch runs found.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <nav aria-label="Recent runs pagination" className="flex items-center justify-between gap-3 border-t border-slate-200 px-6 py-4 dark:border-slate-800">
        <Button variant="secondary" size="sm" disabled={page === 0 || runs.isFetching} onClick={() => setPage(page - 1)}>Previous</Button>
        <span className="text-sm text-slate-500" aria-live="polite">Page {page + 1}</span>
        <Button variant="secondary" size="sm" disabled={!hasNext || runs.isFetching} onClick={() => setPage(page + 1)}>Next</Button>
      </nav>
    </Card>
  );
}

export function AdminSourcesPage() {
  const sources = useSources();
  if (sources.isPending) return <PageSpinner />;
  if (sources.isError) return <Alert tone="error">{sources.error.message}</Alert>;
  const degraded = sources.data.filter((s) => s.enabled && s.state === "degraded").length;
  return (
    <>
      <PageHeader
        title="Sources"
        description="Where jobs come from, their health and their free allowances. Runs daily; a failing source never stops the others."
      />
      {degraded > 0 && (
        <Alert tone="warning" className="mb-6">
          {degraded} source{degraded > 1 ? "s are" : " is"} degraded. They are retried automatically.
        </Alert>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        {sources.data.map((source) => (
          <SourceCard key={source.name} source={source} />
        ))}
      </div>
      <div className="mt-8 space-y-8">
        <RecentRuns />
        <AiUsage />
      </div>
    </>
  );
}
