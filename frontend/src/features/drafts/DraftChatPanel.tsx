import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Textarea } from "@/components/ui/field";

import type { Version } from "./api";

export function DraftChatPanel({ versions, busy, dirty, onChat, onUndo, error }: {
  versions: Version[]; busy: boolean; dirty: boolean;
  onChat: (message: string, overwriteManual: boolean) => Promise<boolean>;
  onUndo: (number: number) => void; error?: string;
}) {
  const [message, setMessage] = useState("");
  const [overwrite, setOverwrite] = useState(false);
  const [confirm, setConfirm] = useState(false);
  async function submit() {
    setConfirm(false);
    if (await onChat(message, overwrite)) setMessage("");
  }
  return (
    <aside className="min-w-0 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <details open>
        <summary className="cursor-pointer text-base font-semibold">Draft Chat</summary>
        <p className="mt-2 text-xs text-slate-500">Ask for changes using your Fact Bank. Each change creates a version you can undo.</p>
        <div className="my-4 max-h-80 space-y-3 overflow-auto" aria-label="Draft Chat history">
          {versions.filter((version) => version.source === "chat").slice().reverse().map((version) => <div key={version.number} className="rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-950"><p className="whitespace-pre-wrap">{version.message}</p><Button size="sm" variant="ghost" disabled={busy || dirty} onClick={() => onUndo(version.number - 1)}>Undo version {version.number}</Button></div>)}
        </div>
        {error && <Alert tone="error">{error}</Alert>}
        {dirty && <p className="mb-2 text-xs text-amber-700 dark:text-amber-300">Save your edits before using Draft Chat.</p>}
        <Textarea aria-label="Draft Chat message" placeholder="Lead with the Rails work and shorten the summary" value={message} onChange={(event) => setMessage(event.target.value)} disabled={busy} rows={4} maxLength={2000} />
        <label className="mt-3 flex items-start gap-2 text-xs"><input type="checkbox" checked={overwrite} onChange={(event) => setOverwrite(event.target.checked)} />Allow chat to change my saved manual edits</label>
        <Button className="mt-3 w-full" variant="secondary" loading={busy} disabled={dirty || !message.trim()} onClick={() => overwrite ? setConfirm(true) : void submit()}>Apply chat change</Button>
      </details>
      <ConfirmDialog open={confirm} title="Allow changes to your manual edits?" confirmLabel="Apply chat change" tone="primary" onCancel={() => setConfirm(false)} onConfirm={() => void submit()}>
        Draft Chat may replace your saved manual edits. Your previous version will remain available to restore.
      </ConfirmDialog>
    </aside>
  );
}
