import { Check, Puzzle } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { Me } from "@/api/client";
import { useApproveExtension } from "@/api/hooks";
import { PageHeader } from "@/app/AppShell";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { sendCodeToExtension } from "@/features/extension/handoff";

const EXTENSION_ID = /^[a-p]{32}$/;
const CHALLENGE = /^[A-Za-z0-9_-]{43}$/;

/** The extension opens this page; the User approves the connection here (ADR-0017). */
export function ExtensionConnectPage({ me }: { me: Me }) {
  const [params] = useSearchParams();
  const extensionId = params.get("extension_id") ?? "";
  const challenge = params.get("challenge") ?? "";
  const valid = EXTENSION_ID.test(extensionId) && CHALLENGE.test(challenge);
  const approve = useApproveExtension();
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  async function connect() {
    setResult(null);
    try {
      const grant = await approve.mutateAsync({ extension_id: extensionId, challenge });
      const reply = await sendCodeToExtension(extensionId, grant.code);
      setResult(
        reply.ok
          ? { ok: true, message: `The extension is connected as ${reply.email}. You can close this tab.` }
          : { ok: false, message: reply.error },
      );
    } catch (error) {
      setResult({ ok: false, message: (error as Error).message });
    }
  }

  return (
    <>
      <PageHeader title="Connect extension" description="Let the JobWeaver browser extension use your account." />
      <Card className="max-w-2xl">
        <CardHeader title="JobWeaver extension" description={`Signed in as ${me.email}.`} />
        <CardBody className="space-y-4">
          {!valid ? (
            <Alert tone="error" title="This connection link is not valid">
              Open the extension and click Connect again.
            </Alert>
          ) : result?.ok ? (
            <Alert tone="success" title="Connected">
              {result.message}
            </Alert>
          ) : (
            <>
              <div className="flex items-start gap-3">
                <Puzzle className="mt-0.5 size-5 shrink-0 text-slate-500 dark:text-slate-400" aria-hidden />
                <div className="text-sm text-slate-700 dark:text-slate-300">
                  <p>The extension will be able to:</p>
                  <ul className="mt-2 space-y-1">
                    <li className="flex gap-2">
                      <Check className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden />
                      See your name and email
                    </li>
                  </ul>
                  <p className="mt-3 text-slate-600 dark:text-slate-400">
                    It never submits forms or sends anything for you. The connection lasts until it expires or you
                    revoke it in Settings. Extension ID <span className="font-mono">{extensionId}</span>.
                  </p>
                </div>
              </div>
              {result && !result.ok && <Alert tone="error">{result.message}</Alert>}
              <div className="flex flex-wrap gap-2">
                <Button loading={approve.isPending} onClick={connect}>
                  Connect extension
                </Button>
              </div>
            </>
          )}
        </CardBody>
      </Card>
    </>
  );
}
