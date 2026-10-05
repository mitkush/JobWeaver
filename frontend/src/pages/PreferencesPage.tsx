import { usePreferences } from "@/api/hooks";
import { PageHeader } from "@/app/AppShell";
import { Alert } from "@/components/ui/alert";
import { Card, CardBody } from "@/components/ui/card";
import { PageSpinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast-context";
import { PreferencesForm } from "@/features/preferences/PreferencesForm";

export function PreferencesPage() {
  const preferences = usePreferences();
  const toast = useToast();
  if (preferences.isPending) return <PageSpinner />;
  if (preferences.isError) return <Alert tone="error">{preferences.error.message}</Alert>;
  return (
    <>
      <PageHeader title="Preferences" description="The Feed and the job searches follow these." />
      <Card>
        <CardBody>
          <PreferencesForm initial={preferences.data} onSaved={() => toast("success", "Preferences saved")} />
        </CardBody>
      </Card>
    </>
  );
}
