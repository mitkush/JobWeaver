import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import type { Me } from "@/api/client";
import { useDeleteAccount, useSetCountry, useSetFollowUpDays } from "@/api/hooks";
import { PageHeader } from "@/app/AppShell";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Field, Input, Select } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast-context";
import { GmailCard } from "@/features/gmail/GmailCard";
import { CompanyBoards } from "@/features/sources/CompanyBoards";
import { COUNTRIES } from "@/lib/countries";
import { googleErrorMessage } from "@/lib/google-errors";

export function SettingsPage({ me }: { me: Me }) {
  const [params] = useSearchParams();
  const [country, setCountry] = useState(me.country ?? "IN");
  const [confirm, setConfirm] = useState(false);
  const saveCountry = useSetCountry();
  const [followUpDays, setFollowUpDays] = useState(String(me.follow_up_days));
  const saveFollowUpDays = useSetFollowUpDays();
  const days = Number(followUpDays);
  const daysValid = Number.isInteger(days) && days >= 1 && days <= 60;
  const deleteAccount = useDeleteAccount();
  const navigate = useNavigate();
  const toast = useToast();

  return (
    <>
      <PageHeader title="Settings" />
      <div className="space-y-6">
        {params.get("gmail") === "connected" && <Alert tone="success">Gmail is connected.</Alert>}
        {params.get("google_error") && <Alert tone="warning">{googleErrorMessage(params.get("google_error"))}</Alert>}
        <Card>
          <CardHeader title="Gmail" description="Used only to create drafts in your Gmail. JobWeaver never sends email." />
          <CardBody>
            <GmailCard me={me} />
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Company job boards"
            description="JobWeaver checks these company boards every day, so jobs are seen first-hand and closed jobs disappear."
          />
          <CardBody>
            <CompanyBoards />
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Account" description={`Signed in with Google as ${me.email}.`} />
          <CardBody className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <Field label="Country" htmlFor="settings-country">
              <Select id="settings-country" value={country} onChange={(e) => setCountry(e.target.value)} className="sm:w-72">
                {COUNTRIES.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Button
              variant="secondary"
              disabled={country === me.country}
              loading={saveCountry.isPending}
              onClick={async () => {
                await saveCountry.mutateAsync(country);
                toast("success", "Country saved");
              }}
            >
              Save country
            </Button>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Follow-up reminders"
            description="When an Application stays Applied this long, JobWeaver suggests a follow-up email."
          />
          <CardBody className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <Field label="Days to wait" htmlFor="settings-follow-up" hint="Between 1 and 60. Applies to Applications marked Applied from now on.">
              <Input
                id="settings-follow-up"
                type="number"
                min={1}
                max={60}
                inputMode="numeric"
                value={followUpDays}
                onChange={(e) => setFollowUpDays(e.target.value)}
                aria-invalid={!daysValid}
                className="sm:w-32"
              />
            </Field>
            <Button
              variant="secondary"
              disabled={!daysValid || days === me.follow_up_days}
              loading={saveFollowUpDays.isPending}
              onClick={async () => {
                try {
                  await saveFollowUpDays.mutateAsync(days);
                  toast("success", "Follow-up reminder saved");
                } catch (error) {
                  toast("error", (error as Error).message);
                }
              }}
            >
              Save
            </Button>
          </CardBody>
        </Card>

        <Card className="border-red-200 dark:border-red-900/60">
          <CardHeader
            title="Delete account"
            description="Removes your documents, Fact Bank, preferences, Drafts, Applications and Gmail connection. This cannot be undone."
            action={
              <Button variant="danger" onClick={() => setConfirm(true)}>
                Delete account
              </Button>
            }
          />
        </Card>
      </div>
      <ConfirmDialog
        open={confirm}
        title="Delete your JobWeaver account?"
        confirmLabel="Delete my account"
        loading={deleteAccount.isPending}
        onCancel={() => setConfirm(false)}
        onConfirm={async () => {
          await deleteAccount.mutateAsync();
          navigate("/sign-in");
        }}
      >
        Everything you added to JobWeaver is deleted and Gmail access is revoked. Drafts already in your
        Gmail stay there.
      </ConfirmDialog>
    </>
  );
}
