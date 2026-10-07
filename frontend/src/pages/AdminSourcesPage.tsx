import { useFetchRuns, useSources } from "@/api/hooks";
import { PageHeader } from "@/app/AppShell";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { PageSpinner } from "@/components/ui/spinner";
import { AiUsage } from "@/features/sources/AiUsage";
import { SourceCard } from "@/features/sources/SourceCard";
import { formatQueryKey } from "@/lib/query-key";
import { fromNow } from "@/lib/time";

const STATUS_TONE = { succeeded: "success", failed: "danger", running: "brand", skipped: "neutral" } as const;

function RecentRuns() {
  const runs = useFetchRuns();
  if (!runs.data?.length) return null;
  return (
    <Card>
      <CardHeader title="Recent runs" description="Each search or company board fetched, newest first." />
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-500">
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
            {runs.data.map((run) => (
              <tr key={run.id}>
                <td className="px-6 py-2 whitespace-nowrap">{fromNow(run.created_at)}</td>
                <td className="px-3 py-2">{run.source}</td>
                <td className="max-w-64 truncate px-3 py-2" title={run.error ?? undefined}>
                  {run.board ?? formatQueryKey(run.query_key)}
                </td>
                <td className="px-3 py-2">
                  <Badge tone={STATUS_TONE[run.status]}>{run.status}</Badge>
                </td>
                <td className="px-3 py-2 text-right">{run.postings_new}</td>
                <td className="px-6 py-2 text-right">{run.credits_used || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
