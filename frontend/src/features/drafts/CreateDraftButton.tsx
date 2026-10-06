import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast-context";

import { useCreateDraft } from "./api";

export function CreateDraftButton({ jobId, draftId, disabled = false }: { jobId: string; draftId?: string | null; disabled?: boolean }) {
  const create = useCreateDraft();
  const navigate = useNavigate();
  const toast = useToast();
  return (
    <Button disabled={disabled} loading={create.isPending} onClick={async () => {
      if (draftId) {
        navigate(`/drafts/${draftId}`);
        return;
      }
      try {
        const draft = await create.mutateAsync(jobId);
        navigate(`/drafts/${draft.id}`);
      } catch (error) {
        toast("error", (error as Error).message);
      }
    }}>
      {draftId ? "Open draft" : "Create draft"}
    </Button>
  );
}

