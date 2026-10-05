import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import type { Me } from "@/api/client";
import { useDeleteAccount, useSetCountry } from "@/api/hooks";
import { PageHeader } from "@/app/AppShell";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Field, Select } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast-context";
import { GmailCard } from "@/features/gmail/GmailCard";
import { COUNTRIES } from "@/lib/countries";

export function SettingsPage({ me }: { me: Me }) {
  const [params] = useSearchParams();
  const [country, setCountry] = useState(me.country ?? "IN");
  const [confirm, setConfirm] = useState(false);
  const saveCountry = useSetCountry();
  const deleteAccount = useDeleteAccount();
  const navigate = useNavigate();
  const toast = useToast();

  return (
    <>
      <PageHeader title="Settings" />
      <div className="space-y-6">
        {params.get("gmail") === "connected" && <Alert tone="success">Gmail is connected.</Alert>}
        {params.get("google_error") && (
          <Alert tone="warning">Google did not finish connecting Gmail. Please try again.</Alert>
        )}
        <Card>
          <CardHeader title="Gmail" description="Used only to create drafts in your Gmail. JobWeaver never sends email." />
          <CardBody>
            <GmailCard me={me} />
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

        <Card className="border-red-200 dark:border-red-900/60">
          <CardHeader
            title="Delete account"
            description="Removes your documents, Fact Bank, preferences and Gmail connection. This cannot be undone."
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
