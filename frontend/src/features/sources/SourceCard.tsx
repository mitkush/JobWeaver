import { Play } from "lucide-react";
import { useState } from "react";

import type { SourceStatus } from "@/api/client";
import { useRunSource, useUpdateSource } from "@/api/hooks";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast-context";
import { fromNow } from "@/lib/time";

import { BudgetMeter } from "./BudgetMeter";

function stateBadge(source: SourceStatus) {
  if (!source.enabled) return <Badge>Disabled</Badge>;
  if (!source.configured) return <Badge tone="warning">Not configured</Badge>;
  if (source.state === "degraded") return <Badge tone="danger">Degraded</Badge>;
  return <Badge tone="success">Healthy</Badge>;
}

export function SourceCard({ source }: { source: SourceStatus }) {
  const [confirmRun, setConfirmRun] = useState(false);
  const update = useUpdateSource();
  const run = useRunSource();
  const toast = useToast();
  const metered = source.budget !== null;

  return (
    <Card>
      <CardBody className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="font-semibold">{source.label}</h2>
              {stateBadge(source)}
            </div>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              {source.mode === "snapshot" ? `Company boards · ${source.boards ?? 0} tracked` : "Search"} ·
              priority {source.priority} · {source.open_postings.toLocaleString()} open postings
            </p>
            {source.standby_for && (
              <p className="mt-1 text-xs text-slate-600">
                Standby for {source.standby_for}: runs only while that source is degraded or disabled.
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              size="sm"
              loading={update.isPending}
              onClick={() => update.mutate({ name: source.name, enabled: !source.enabled })}
            >
              {source.enabled ? "Disable" : "Enable"}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={!source.enabled || !source.configured || source.manual_runs_left === 0}
              onClick={() => setConfirmRun(true)}
            >
              <Play className="size-3.5" aria-hidden />
              Run now
            </Button>
          </div>
        </div>

        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs text-slate-500 dark:text-slate-400">Last success</dt>
            <dd>{fromNow(source.last_success_at)}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500 dark:text-slate-400">Next run</dt>
            <dd>{source.next_run_at ? fromNow(source.next_run_at) : "not scheduled"}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500 dark:text-slate-400">Manual runs left today</dt>
            <dd>{source.manual_runs_left}</dd>
          </div>
        </dl>

        {source.last_error && source.state === "degraded" && (
          <Alert tone="warning" title={`Degraded ${fromNow(source.degraded_since)}`}>
            {source.last_error}. It is retried automatically on the next run.
          </Alert>
        )}
        {!source.configured && source.enabled && (
          <Alert tone="info">Add this source's API key to the server settings to start fetching.</Alert>
        )}
        {!source.enabled && source.disabled_reason && (
          <Alert tone="info" title="Off by default">
            {source.disabled_reason}
          </Alert>
        )}
        {source.budget && <BudgetMeter budget={source.budget} />}
        {source.budget && source.shares_budget_with.length > 0 && (
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Shares this allowance with {source.shares_budget_with.join(", ")}.
          </p>
        )}
      </CardBody>

      <ConfirmDialog
        open={confirmRun}
        title={`Run ${source.label} now?`}
        confirmLabel="Run now"
        tone="primary"
        loading={run.isPending}
        onCancel={() => setConfirmRun(false)}
        onConfirm={async () => {
          try {
            const outcome = await run.mutateAsync(source.name);
            // The API starts the run and returns; Recent runs shows it as it progresses.
            const ok = outcome.status === "started" || outcome.status === "succeeded";
            toast(
              ok ? "success" : "error",
              outcome.status === "started"
                ? "Run started. Its progress shows under Recent runs."
                : outcome.status === "succeeded"
                  ? `${outcome.postings_new} new postings`
                  : outcome.message || "The run did not finish",
            );
          } catch (error) {
            toast("error", (error as Error).message);
          }
          setConfirmRun(false);
        }}
      >
        {metered
          ? `This searches every saved preference again and uses ${source.budget?.unit} for every result returned.`
          : "This fetches the source again now instead of waiting for the daily run."}{" "}
        {source.manual_runs_left} manual runs left today.
      </ConfirmDialog>
    </Card>
  );
}
