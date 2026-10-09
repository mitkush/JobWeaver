import { Plus } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";

import type { Fact, FactKind } from "@/api/client";
import { useCreateFact, useMergeFacts } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input, Textarea } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast-context";

import { FactRow } from "./FactRow";
import { KIND_LABELS, KIND_ORDER } from "./labels";

function AddFact({ kind }: { kind: FactKind }) {
  const [text, setText] = useState("");
  const [group, setGroup] = useState("");
  const create = useCreateFact();
  const toast = useToast();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!text.trim() || (["experience", "project", "education"].includes(kind) && !group.trim())) return;
    try {
      await create.mutateAsync({ kind, text: text.trim(), group: group.trim() });
      setText("");
    } catch (error) {
      toast("error", (error as Error).message);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap gap-2 px-4 py-3">
      {["experience", "project", "education", "achievement", "link"].includes(kind) && (
        <Input
          value={group}
          onChange={(e) => setGroup(e.target.value)}
          placeholder={kind === "experience" ? "Employer" : kind === "project" ? "Project name" : "Group (optional)"}
          aria-label={`Group for ${KIND_LABELS[kind]}`}
          required={["experience", "project", "education"].includes(kind)}
        />
      )}
      <Input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={`Add to ${KIND_LABELS[kind].toLowerCase()}`}
        aria-label={`Add to ${KIND_LABELS[kind]}`}
      />
      <Button type="submit" variant="secondary" loading={create.isPending} disabled={!text.trim() || (["experience", "project", "education"].includes(kind) && !group.trim())}>
        <Plus className="size-4" aria-hidden />
        Add
      </Button>
    </form>
  );
}

/** The Fact Bank: the only content tailored resumes may use (ADR-0005). */
export function FactBankEditor({ facts }: { facts: Fact[] }) {
  const [picked, setPicked] = useState<string[]>([]);
  // Facts can disappear (deleted, merged, rebuilt); never keep or send a stale id.
  const selected = useMemo(() => picked.filter((id) => facts.some((f) => f.id === id)), [picked, facts]);
  const [mergeText, setMergeText] = useState<string | null>(null);
  const merge = useMergeFacts();
  const toast = useToast();

  const byKind = useMemo(() => {
    const groups = new Map<FactKind, Fact[]>();
    for (const fact of facts) groups.set(fact.kind, [...(groups.get(fact.kind) ?? []), fact]);
    return groups;
  }, [facts]);

  const visibleKinds = KIND_ORDER.filter((kind) => byKind.has(kind) || ["skill", "experience", "project"].includes(kind));

  function toggle(id: string) {
    setPicked((current) => (current.includes(id) ? current.filter((x) => x !== id) : [...current, id]));
  }

  const selectedFacts = facts.filter((f) => selected.includes(f.id));
  const firstSelected = selectedFacts[0];
  const sameGroup = !firstSelected || selectedFacts.every(
    (fact) => fact.kind === firstSelected.kind && fact.group.trim().toLowerCase() === firstSelected.group.trim().toLowerCase(),
  );

  return (
    <div className="space-y-6">
      {selected.length >= 2 && (
        <div className="sticky top-16 z-10 flex items-center justify-between gap-3 rounded-lg border border-brand-100 bg-brand-50 px-4 py-3 text-sm dark:border-brand-600/40 dark:bg-slate-900">
          <span>{selected.length} Facts selected</span>
          <div className="flex gap-2">
            <Button size="sm" variant="ghost" onClick={() => setPicked([])}>
              Clear
            </Button>
              <Button size="sm" disabled={!sameGroup} onClick={() => setMergeText(selectedFacts.map((f) => f.text).join("; "))}>
              Merge into one
            </Button>
          </div>
          {!sameGroup && <span className="text-xs text-amber-800">Select Facts from the same section and employer or project to merge.</span>}
        </div>
      )}

      {visibleKinds.map((kind) => {
        const items = byKind.get(kind) ?? [];
        return (
          <section key={kind} aria-labelledby={`kind-${kind}`}>
            <h3 id={`kind-${kind}`} className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-300">
              {KIND_LABELS[kind]} <span className="font-normal text-slate-500">({items.length})</span>
            </h3>
            <Card>
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {items.map((fact) => (
                  <FactRow key={fact.id} fact={fact} selected={selected.includes(fact.id)} onToggle={() => toggle(fact.id)} />
                ))}
              </ul>
              <div className="border-t border-slate-100 dark:border-slate-800">
                <AddFact kind={kind} />
              </div>
            </Card>
          </section>
        );
      })}

      <ConfirmDialog
        open={mergeText !== null}
        title={`Merge ${selected.length} Facts`}
        confirmLabel="Merge"
        tone="primary"
        loading={merge.isPending}
        onCancel={() => setMergeText(null)}
        onConfirm={async () => {
          try {
            await merge.mutateAsync({ fact_ids: selected, text: mergeText ?? "" });
            setPicked([]);
            setMergeText(null);
          } catch (error) {
            toast("error", (error as Error).message);
          }
        }}
      >
        <p className="mb-2">The selected Facts are replaced by one Fact with this text:</p>
        <Textarea value={mergeText ?? ""} onChange={(e) => setMergeText(e.target.value)} aria-label="Merged Fact text" />
      </ConfirmDialog>
    </div>
  );
}
