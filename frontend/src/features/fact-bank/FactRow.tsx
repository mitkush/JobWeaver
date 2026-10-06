import { Pencil, Trash2 } from "lucide-react";
import { useState } from "react";

import type { Fact } from "@/api/client";
import { useDeleteFact, useUpdateFact } from "@/api/hooks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Textarea } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast-context";

export function FactRow({
  fact,
  selected,
  onToggle,
}: {
  fact: Fact;
  selected: boolean;
  onToggle: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(fact.text);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const update = useUpdateFact();
  const remove = useDeleteFact();
  const toast = useToast();

  async function save() {
    try {
      await update.mutateAsync({ id: fact.id, text });
      setEditing(false);
    } catch (error) {
      toast("error", (error as Error).message);
    }
  }

  return (
    <li className="group flex items-start gap-3 px-4 py-3">
      <input
        type="checkbox"
        checked={selected}
        onChange={onToggle}
        aria-label={`Select "${fact.text}" to merge`}
        className="mt-1 size-4 rounded border-slate-300 accent-brand-600"
      />
      <div className="min-w-0 flex-1">
        {editing ? (
          <div className="space-y-2">
            <Textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              aria-label="Fact text"
              className="min-h-16"
              autoFocus
            />
            <div className="flex gap-2">
              <Button size="sm" onClick={save} loading={update.isPending} disabled={!text.trim()}>
                Save
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setText(fact.text);
                  setEditing(false);
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <>
            <p className="text-sm leading-relaxed">{fact.text}</p>
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              {fact.group && <span className="text-xs text-slate-500">{fact.group}</span>}
              {!fact.in_base_resume && <Badge tone="brand">Not in your resume</Badge>}
              {fact.origin === "user" && <Badge>Added by you</Badge>}
              {fact.edited && fact.origin === "ai" && <Badge>Edited</Badge>}
            </div>
          </>
        )}
      </div>
      {!editing && (
        <div className="flex shrink-0 gap-1 opacity-100 sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100">
          <Button size="sm" variant="ghost" onClick={() => setEditing(true)} aria-label={`Edit "${fact.text}"`}>
            <Pencil className="size-4" aria-hidden />
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(true)} aria-label={`Delete "${fact.text}"`}>
            <Trash2 className="size-4" aria-hidden />
          </Button>
        </div>
      )}
      <ConfirmDialog
        open={confirmDelete}
        title="Delete this Fact?"
        confirmLabel="Delete Fact"
        loading={remove.isPending}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={async () => {
          try {
            await remove.mutateAsync(fact.id);
          } catch (error) {
            toast("error", (error as Error).message);
          }
          setConfirmDelete(false);
        }}
      >
        Tailored resumes will no longer be able to use: “{fact.text}”.
      </ConfirmDialog>
    </li>
  );
}
