import { useState } from "react";

import { useClearWritingStyle, useRebuildWritingStyle, useSaveWritingStyle, useWritingStyle } from "@/api/hooks";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Field, Textarea } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast-context";

const lines = (text: string) =>
  text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

/** How the User writes, used only for the tone of suggested answers (ADR-0017). It never
 * carries a claim: excerpts are redacted on the server, including after an edit. */
export function WritingStyleCard() {
  const style = useWritingStyle();
  const rebuild = useRebuildWritingStyle();
  const save = useSaveWritingStyle();
  const clear = useClearWritingStyle();
  const toast = useToast();
  const [editing, setEditing] = useState<{ traits: string; excerpts: string } | null>(null);
  const [clearing, setClearing] = useState(false);
  const empty = !style.data || (style.data.traits.length === 0 && style.data.excerpts.length === 0);
  const error = rebuild.error ?? save.error ?? clear.error;

  return (
    <Card>
      <CardHeader
        title="Writing style"
        description="Learned from your summary and the answers you saved in your own words. Suggested answers follow its tone; their content still comes only from your Facts."
      />
      <CardBody className="space-y-4">
        {style.isPending ? null : style.isError ? (
          <Alert tone="error">{style.error.message}</Alert>
        ) : editing ? (
          <>
            <Field label="Traits" htmlFor="ws-traits" hint="One per line, for example: Short, direct sentences.">
              <Textarea id="ws-traits" value={editing.traits} onChange={(e) => setEditing({ ...editing, traits: e.target.value })} />
            </Field>
            <Field
              label="Tone examples"
              htmlFor="ws-excerpts"
              hint="One per line. Names, numbers, dates and tools are replaced with placeholders when you save."
            >
              <Textarea
                id="ws-excerpts"
                value={editing.excerpts}
                onChange={(e) => setEditing({ ...editing, excerpts: e.target.value })}
              />
            </Field>
            <div className="flex flex-wrap gap-2">
              <Button
                loading={save.isPending}
                onClick={async () => {
                  try {
                    await save.mutateAsync({ traits: lines(editing.traits), excerpts: lines(editing.excerpts) });
                    setEditing(null);
                    toast("success", "Writing style saved");
                  } catch {
                    // Shown below; the edit stays open.
                  }
                }}
              >
                Save style
              </Button>
              <Button variant="ghost" onClick={() => setEditing(null)}>
                Cancel
              </Button>
            </div>
          </>
        ) : (
          <>
            {empty ? (
              <p className="text-sm text-slate-600 dark:text-slate-400">
                No writing style yet. Suggested answers use a plain, neutral tone until you build one.
              </p>
            ) : (
              <>
                <div>
                  <p className="text-sm font-medium">Traits</p>
                  <ul className="mt-1 list-disc pl-5 text-sm text-slate-700 dark:text-slate-300">
                    {style.data.traits.map((trait) => (
                      <li key={trait}>{trait}</li>
                    ))}
                  </ul>
                </div>
                {style.data.excerpts.length > 0 && (
                  <div>
                    <p className="text-sm font-medium">Tone examples</p>
                    <ul className="mt-1 space-y-1 text-sm text-slate-700 italic dark:text-slate-300">
                      {style.data.excerpts.map((excerpt) => (
                        <li key={excerpt}>{excerpt}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
            <div className="flex flex-wrap gap-2">
              <Button
                variant={empty ? "primary" : "secondary"}
                loading={rebuild.isPending}
                onClick={async () => {
                  try {
                    await rebuild.mutateAsync();
                    toast("success", "Writing style updated");
                  } catch {
                    // Shown below.
                  }
                }}
              >
                {empty ? "Learn my writing style" : "Learn again"}
              </Button>
              {!empty && (
                <>
                  <Button
                    variant="ghost"
                    onClick={() =>
                      setEditing({ traits: style.data.traits.join("\n"), excerpts: style.data.excerpts.join("\n") })
                    }
                  >
                    Edit
                  </Button>
                  <Button variant="ghost" onClick={() => setClearing(true)}>
                    Clear
                  </Button>
                </>
              )}
            </div>
          </>
        )}
        {error && <Alert tone="error">{error.message}</Alert>}
      </CardBody>
      <ConfirmDialog
        open={clearing}
        title="Clear your writing style?"
        confirmLabel="Clear"
        loading={clear.isPending}
        onCancel={() => setClearing(false)}
        onConfirm={async () => {
          await clear.mutateAsync();
          setClearing(false);
          toast("success", "Writing style cleared");
        }}
      >
        Suggested answers go back to a plain, neutral tone. You can learn it again at any time.
      </ConfirmDialog>
    </Card>
  );
}
