import { Mail } from "lucide-react";
import { useState } from "react";

import type { Me } from "@/api/client";
import { useDisconnectGmail } from "@/api/hooks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buttonClasses } from "@/components/ui/button-classes";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

import { formatDate, gmailConnectHref } from "./links";

const STATE_COPY = {
  not_connected: { label: "Not connected", tone: "neutral" },
  connected: { label: "Connected", tone: "success" },
  expires_soon: { label: "Expires soon", tone: "warning" },
  expired: { label: "Expired", tone: "danger" },
} as const;

/** Gmail Hand-off needs a Google grant that lasts 7 days in testing mode (ADR-0006). */
export function GmailCard({ me, next = "/settings" }: { me: Me; next?: string }) {
  const [confirm, setConfirm] = useState(false);
  const disconnect = useDisconnectGmail();
  const { state, expires_at } = me.gmail;
  const copy = STATE_COPY[state];

  return (
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex items-start gap-3">
        <Mail className="mt-0.5 size-5 text-slate-500" aria-hidden />
        <div>
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium">Gmail</p>
            <Badge tone={copy.tone}>{copy.label}</Badge>
          </div>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
            {state === "not_connected" &&
              "Connect Gmail so JobWeaver can put ready drafts with your resume attached into your Gmail. Nothing is ever sent for you."}
            {(state === "connected" || state === "expires_soon") &&
              expires_at &&
              `Google asks you to sign in again every 7 days while JobWeaver is in testing. Access ends ${formatDate(expires_at)}.`}
            {state === "connected" && !expires_at && "Connected."}
            {state === "expired" && "Google ended access after 7 days. Reconnect to keep creating Gmail drafts."}
          </p>
        </div>
      </div>
      <div className="flex gap-2">
        {state !== "not_connected" && (
          <Button variant="ghost" onClick={() => setConfirm(true)}>
            Disconnect
          </Button>
        )}
        {state !== "connected" && (
          <a className={buttonClasses(state === "not_connected" ? "primary" : "secondary")} href={gmailConnectHref(next)}>
            {state === "not_connected" ? "Connect Gmail" : "Reconnect"}
          </a>
        )}
      </div>
      <ConfirmDialog
        open={confirm}
        title="Disconnect Gmail?"
        confirmLabel="Disconnect"
        loading={disconnect.isPending}
        onCancel={() => setConfirm(false)}
        onConfirm={async () => {
          await disconnect.mutateAsync();
          setConfirm(false);
        }}
      >
        JobWeaver will stop creating drafts in your Gmail until you connect again. Drafts already in Gmail stay there.
      </ConfirmDialog>
    </div>
  );
}
