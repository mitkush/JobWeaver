import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api, unwrap } from "@/api/client";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast-context";

export function DraftManagement({ draftId, version, disabled = false, allowDelete = false }: {
  jobId: string; draftId: string; version?: number; disabled?: boolean; allowDelete?: boolean;
}) {
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const client = useQueryClient();
  const toast = useToast();
  if (!allowDelete) return null;
  return <details><summary className="cursor-pointer text-sm">More actions</summary>
    <Button className="mt-2" variant="secondary" disabled={disabled || busy} onClick={() => setConfirm(true)}>Archive Draft</Button>
    <ConfirmDialog open={confirm} title="Archive this Draft?" confirmLabel="Archive Draft" loading={busy} onCancel={() => setConfirm(false)} onConfirm={() => void (async () => {
      setBusy(true);
      try {
        await unwrap(api.DELETE("/api/drafts/{draft_id}", { params: { path: { draft_id: draftId }, query: { expected_version: version ?? 0 } } }));
        await client.invalidateQueries(); navigate("/feed");
      } catch (e) { toast("error", (e as Error).message); }
      finally { setBusy(false); }
    })()}>Your application history and document snapshots are kept. This package is removed from the active workflow.</ConfirmDialog>
  </details>;
}
