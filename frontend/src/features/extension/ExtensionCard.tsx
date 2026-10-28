import { ExternalLink, Puzzle } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { ExtensionConnection } from "@/api/client";
import { useExtensionConnections, useRevokeExtensionConnection } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { buttonClasses } from "@/components/ui/button-classes";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast-context";
import { fromNow } from "@/lib/time";

/** Browser extension connections, each revocable at once (ADR-0017). */
export function ExtensionCard({ storeUrl = null }: { storeUrl?: string | null }) {
  const connections = useExtensionConnections();
  const revoke = useRevokeExtensionConnection();
  const [pending, setPending] = useState<ExtensionConnection | null>(null);
  const toast = useToast();

  if (connections.isPending) return <Spinner />;
  if (connections.isError) return <p className="text-sm text-red-700 dark:text-red-400">{connections.error.message}</p>;

  return (
    <div className="space-y-3">
      {connections.data.length === 0 ? (
        <div className="flex items-start gap-3">
          <Puzzle className="mt-0.5 size-5 text-slate-500 dark:text-slate-400" aria-hidden />
          <div className="space-y-3">
            <p className="text-sm text-slate-600 dark:text-slate-400">
              No extension is connected. Install the JobWeaver extension in Chrome or Brave, then click Connect in it.
              {!storeUrl && " Until it is in the Chrome Web Store, load it unpacked as the README describes."}
            </p>
            {storeUrl && (
              <a href={storeUrl} target="_blank" rel="noreferrer" className={buttonClasses("secondary")}>
                Get the extension
                <ExternalLink className="size-4" aria-hidden />
              </a>
            )}
          </div>
        </div>
      ) : (
        <ul className="divide-y divide-slate-200 dark:divide-slate-800">
          {connections.data.map((connection) => (
            <li key={connection.id} className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
              <div className="text-sm">
                <p className="font-medium">Connected {fromNow(connection.created_at)}</p>
                <p className="text-slate-600 dark:text-slate-400">
                  Last used {fromNow(connection.last_used_at)}. Expires {fromNow(connection.expires_at)}.
                </p>
              </div>
              <Button variant="ghost" onClick={() => setPending(connection)}>
                Revoke
              </Button>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-slate-500 dark:text-slate-400">
        <Link to="/privacy/extension" className="underline">
          Extension privacy policy
        </Link>
      </p>
      <ConfirmDialog
        open={pending !== null}
        title="Revoke this extension connection?"
        confirmLabel="Revoke"
        loading={revoke.isPending}
        onCancel={() => setPending(null)}
        onConfirm={async () => {
          if (!pending) return;
          try {
            await revoke.mutateAsync(pending.id);
            toast("success", "Extension connection revoked");
          } catch (error) {
            toast("error", (error as Error).message);
          }
          setPending(null);
        }}
      >
        The extension stops working with your account at once. Connect it again from the extension at any time.
      </ConfirmDialog>
    </div>
  );
}
