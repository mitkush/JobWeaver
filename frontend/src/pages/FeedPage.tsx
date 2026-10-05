import { Inbox } from "lucide-react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/app/AppShell";
import { buttonClasses } from "@/components/ui/button-classes";
import { EmptyState } from "@/components/ui/empty-state";

export function FeedPage() {
  return (
    <>
      <PageHeader title="Feed" description="New jobs that match your preferences, one card per real opening." />
      <EmptyState
        icon={Inbox}
        title="No jobs yet"
        action={
          <Link to="/preferences" className={buttonClasses("secondary")}>
            Review your preferences
          </Link>
        }
      >
        Your profile is ready. Job sources are being connected next; once they run, new jobs that
        match your preferences appear here every day.
      </EmptyState>
    </>
  );
}
