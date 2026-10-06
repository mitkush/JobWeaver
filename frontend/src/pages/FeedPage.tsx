import { Inbox } from "lucide-react";
import { Link } from "react-router-dom";

import { useNotices } from "@/api/hooks";
import { PageHeader } from "@/app/AppShell";
import { Alert } from "@/components/ui/alert";
import { buttonClasses } from "@/components/ui/button-classes";
import { EmptyState } from "@/components/ui/empty-state";

export function FeedPage() {
  const notices = useNotices();
  return (
    <>
      <PageHeader title="Feed" description="New jobs that match your preferences, one card per real opening." />
      {notices.data?.map((notice) => (
        <Alert key={notice.label} tone="info" className="mb-4">
          {notice.message}
        </Alert>
      ))}
      <EmptyState
        icon={Inbox}
        title="No jobs yet"
        action={
          <Link to="/preferences" className={buttonClasses("secondary")}>
            Review your preferences
          </Link>
        }
      >
        Your profile is ready. Jobs are collected every morning from LinkedIn, company job boards and
        other sources; matching jobs start appearing here in the next release.
      </EmptyState>
    </>
  );
}
