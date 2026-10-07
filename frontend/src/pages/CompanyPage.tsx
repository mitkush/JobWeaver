import { Building2 } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { useCompanyHistory } from "@/api/hooks";
import { PageHeader } from "@/app/AppShell";
import { Alert } from "@/components/ui/alert";
import { buttonClasses } from "@/components/ui/button-classes";
import { EmptyState } from "@/components/ui/empty-state";
import { PageSpinner } from "@/components/ui/spinner";
import { ApplicationRow } from "@/features/applications/ApplicationRow";

/** Every Application the User made to one Company (FR-F3). */
export function CompanyPage() {
  const { companyId = "" } = useParams();
  const history = useCompanyHistory(companyId);

  if (history.isPending) return <PageSpinner />;
  if (history.isError) return <Alert tone="error">{(history.error as Error).message}</Alert>;
  const { name, applications } = history.data;
  return (
    <>
      <PageHeader title={name} description="Your Applications to this Company." />
      {applications.length === 0 ? (
        <EmptyState
          icon={Building2}
          title={`No Applications to ${name} yet`}
          action={
            <Link to="/applications" className={buttonClasses("secondary")}>
              All Applications
            </Link>
          }
        />
      ) : (
        <ul className="divide-y divide-slate-200 border-y border-slate-200 dark:divide-slate-800 dark:border-slate-800">
          {applications.map((application) => (
            <ApplicationRow key={application.id} application={application} showCompany={false} />
          ))}
        </ul>
      )}
    </>
  );
}
