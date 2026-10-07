import { ClipboardList } from "lucide-react";
import { Link } from "react-router-dom";

import { useApplications } from "@/api/hooks";
import { PageHeader } from "@/app/AppShell";
import { Alert } from "@/components/ui/alert";
import { buttonClasses } from "@/components/ui/button-classes";
import { EmptyState } from "@/components/ui/empty-state";
import { PageSpinner } from "@/components/ui/spinner";
import { ApplicationRow } from "@/features/applications/ApplicationRow";
import { Reminders } from "@/features/applications/Reminders";
import { STATUSES } from "@/features/applications/status";

/** The Application tracker (FR-F1), grouped by status in tracker order. */
export function ApplicationsPage() {
  const applications = useApplications();

  return (
    <>
      <PageHeader title="Applications" description="Change a status as things happen; every change is kept in its history." />
      <Reminders />
      {applications.isPending && <PageSpinner />}
      {applications.isError && <Alert tone="error">{(applications.error as Error).message}</Alert>}
      {applications.data && applications.data.length === 0 && (
        <EmptyState
          icon={ClipboardList}
          title="No applications yet"
          action={
            <Link to="/feed" className={buttonClasses("primary")}>
              Go to your Feed
            </Link>
          }
        >
          Create a Draft for a Job and open it in Gmail or mark it as applied. It then shows here.
        </EmptyState>
      )}
      {applications.data && applications.data.length > 0 && (
        <div className="space-y-6">
          {STATUSES.map((status) => {
            const items = applications.data.filter((a) => a.status === status.id);
            if (items.length === 0) return null;
            return (
              <section key={status.id} aria-labelledby={`group-${status.id}`}>
                <h2 id={`group-${status.id}`} className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                  {status.label} <span className="font-normal text-slate-500">({items.length})</span>
                </h2>
                <ul className="divide-y divide-slate-200 border-y border-slate-200 dark:divide-slate-800 dark:border-slate-800">
                  {items.map((application) => (
                    <ApplicationRow key={application.id} application={application} />
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      )}
    </>
  );
}
