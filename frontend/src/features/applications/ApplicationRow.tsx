import { Link } from "react-router-dom";

import type { Application, ApplicationStatus } from "@/api/client";
import { useSetApplicationStatus } from "@/api/hooks";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast-context";
import { fromNow, shortDate } from "@/lib/time";

import { STATUSES, statusLabel } from "./status";

/** One Application: what, where, its status (changed by hand) and when each change happened. */
export function ApplicationRow({ application, showCompany = true }: { application: Application; showCompany?: boolean }) {
  const setStatus = useSetApplicationStatus();
  const toast = useToast();
  const selectId = `status-${application.id}`;

  async function change(status: ApplicationStatus) {
    try {
      await setStatus.mutateAsync({ id: application.id, status });
      toast("success", `Moved to ${statusLabel(status)}`);
    } catch (error) {
      toast("error", (error as Error).message);
    }
  }

  return (
    <li className="flex flex-wrap items-start justify-between gap-3 py-4">
      <div className="min-w-0 flex-1">
        <Link to={`/jobs/${application.job_id}`} className="font-medium hover:underline">
          {application.title}
        </Link>
        {showCompany && (
          <p className="text-sm text-slate-600 dark:text-slate-400">
            <Link to={`/companies/${application.company_id}`} className="hover:underline">
              {application.company}
            </Link>
          </p>
        )}
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
          <span>Updated {fromNow(application.status_changed_at)}</span>
          {application.applied_at && <span>Applied {shortDate(application.applied_at)}</span>}
          {application.follow_up_due && <Badge tone="warning">Follow-up due</Badge>}
          {application.job_expired && <Badge>No longer listed</Badge>}
        </div>
        <details className="mt-2 text-xs text-slate-600 dark:text-slate-400">
          <summary className="cursor-pointer select-none rounded focus-visible:outline-2 focus-visible:outline-brand-500">
            History
          </summary>
          <ol className="mt-1 space-y-0.5 pl-4">
            {application.history.map((event) => (
              <li key={`${event.status}-${event.at}`}>
                {statusLabel(event.status)}: <time dateTime={event.at}>{new Date(event.at).toLocaleString()}</time>
              </li>
            ))}
          </ol>
        </details>
      </div>
      <div className="w-40">
        <label htmlFor={selectId} className="sr-only">
          Status of {application.title} at {application.company}
        </label>
        <Select
          id={selectId}
          value={application.status}
          disabled={setStatus.isPending}
          onChange={(e) => void change(e.target.value as ApplicationStatus)}
        >
          {STATUSES.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </Select>
      </div>
    </li>
  );
}
