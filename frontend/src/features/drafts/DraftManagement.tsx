import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { api, unwrap } from "@/api/client";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast-context";
import { useCreateDraft } from "./api";

export function DraftManagement({ jobId, draftId, version, disabled = false, allowDelete = false }: {
  jobId: string; draftId: string; version?: number; disabled?: boolean; allowDelete?: boolean;
}) {
  const [action, setAction] = useState<"generate" | "delete" | null>(null);
  const [busy, setBusy] = useState(false);
  const create = useCreateDraft();
  const navigate = useNavigate();
  const client = useQueryClient();
  const toast = useToast();
  return <>
    <Button variant="secondary" disabled={disabled || busy} onClick={() => setAction("generate")}>Generate new draft</Button>
    {allowDelete && <Button variant="danger" disabled={disabled || busy} onClick={() => setAction("delete")}>Delete draft</Button>}
    <ConfirmDialog open={action !== null} title={action === "delete" ? "Delete this Draft?" : "Generate a new Draft?"}
      confirmLabel={action === "delete" ? "Delete draft" : "Generate new draft"} tone={action === "delete" ? "danger" : "primary"}
      loading={busy} onCancel={() => setAction(null)} onConfirm={() => void (async () => {
        setBusy(true);
        try {
          if (action === "delete") {
            await unwrap(api.DELETE("/api/drafts/{draft_id}", { params: { path: { draft_id: draftId }, query: { expected_version: version ?? 0 } } }));
            await client.invalidateQueries();
            navigate("/feed");
          } else {
            const draft = await create.mutateAsync(jobId);
            await client.invalidateQueries({ queryKey: ["feed"] });
            navigate(`/drafts/${draft.id}`);
          }
          setAction(null);
        } catch (error) { toast("error", (error as Error).message); }
        finally { setBusy(false); }
      })()}>
      {action === "delete"
        ? "This permanently deletes this Draft and all its saved versions and manual edits. Your Application status and history are kept."
        : "Creates a fresh package using your current Fact Bank and this Job's current description. Your older Draft and edits are kept. Save any unsaved edits first."}
    </ConfirmDialog>
  </>;
}
