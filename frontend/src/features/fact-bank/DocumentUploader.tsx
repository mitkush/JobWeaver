import { FileText, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { ApiError, type DocumentInfo, type DocumentKind, type UploadResult } from "@/api/client";
import { useRebuildFactBank, useSaveTextDocument, useUploadDocument } from "@/api/hooks";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/field";

const KIND_COPY: Record<DocumentKind, { title: string; hint: string }> = {
  resume: { title: "Resume", hint: "Required. The resume you use today (PDF or text)." },
  portfolio: {
    title: "Detailed portfolio or cover letter",
    hint: "Optional, but recommended: everything you have done, even what does not fit on one page.",
  },
  summary: { title: "Short summary", hint: "Optional. A few lines about you and what you want next." },
};

function Changes({ result }: { result: UploadResult }) {
  const { added, removed, kept_edits } = result.changes;
  return (
    <Alert tone="success" title={`${result.document.filename} processed`}>
      {added.length} Facts added{removed.length ? `, ${removed.length} removed` : ""}
      {kept_edits ? `, ${kept_edits} of your edits kept` : ""}.
    </Alert>
  );
}

function FileSlot({ kind, current }: { kind: DocumentKind; current?: DocumentInfo }) {
  const input = useRef<HTMLInputElement>(null);
  const upload = useUploadDocument();
  const rebuild = useRebuildFactBank();
  const copy = KIND_COPY[kind];
  const saved = upload.error instanceof ApiError && upload.error.code === "ai_unavailable";

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium">{copy.title}</p>
          <p className="text-xs text-slate-500 dark:text-slate-400">{copy.hint}</p>
          {current && (
            <p className="mt-1 inline-flex items-center gap-1 text-xs text-slate-600 dark:text-slate-300">
              <FileText className="size-3.5" aria-hidden />
              {current.filename}
            </p>
          )}
        </div>
        <input
          ref={input}
          type="file"
          accept=".pdf,.txt,.md,application/pdf,text/plain"
          className="sr-only"
          aria-label={`Upload ${copy.title.toLowerCase()}`}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) upload.mutate({ kind, file });
            e.target.value = "";
          }}
        />
        <Button
          variant={current ? "secondary" : kind === "resume" ? "primary" : "secondary"}
          onClick={() => input.current?.click()}
          loading={upload.isPending}
        >
          <Upload className="size-4" aria-hidden />
          {upload.isPending ? "Reading your file" : current ? "Replace" : "Upload"}
        </Button>
      </div>
      {upload.isPending && (
        <p className="text-sm text-slate-600 dark:text-slate-400" role="status">
          Reading the file and building your Fact Bank. This can take up to a minute.
        </p>
      )}
      {upload.isSuccess && <Changes result={upload.data} />}
      {upload.isError && (
        <Alert
          tone="error"
          title="That did not work"
          action={
            saved ? (
              <Button size="sm" variant="secondary" loading={rebuild.isPending} onClick={() => rebuild.mutate()}>
                Try again
              </Button>
            ) : undefined
          }
        >
          {rebuild.isSuccess ? "Your Fact Bank is ready now." : upload.error.message}
        </Alert>
      )}
    </div>
  );
}

function SummarySlot({ current }: { current?: DocumentInfo }) {
  const [text, setText] = useState("");
  const save = useSaveTextDocument();
  return (
    <div className="space-y-3 rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <div>
        <p className="text-sm font-medium">{KIND_COPY.summary.title}</p>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {current ? "Saved. Write a new one to replace it." : KIND_COPY.summary.hint}
        </p>
      </div>
      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        aria-label="Short summary"
        placeholder="Backend developer focused on Python and data-heavy products..."
      />
      <div className="flex items-center gap-3">
        <Button variant="secondary" disabled={text.trim().length < 20} loading={save.isPending} onClick={() => save.mutate({ kind: "summary", text })}>
          Save summary
        </Button>
        {text.trim().length > 0 && text.trim().length < 20 && (
          <span className="text-xs text-slate-500">At least 20 characters</span>
        )}
      </div>
      {save.isSuccess && <Changes result={save.data} />}
      {save.isError && <Alert tone="error">{save.error.message}</Alert>}
    </div>
  );
}

export function DocumentUploader({ documents }: { documents: DocumentInfo[] }) {
  const find = (kind: DocumentKind) => documents.find((d) => d.kind === kind);
  return (
    <div className="space-y-3">
      <FileSlot kind="resume" current={find("resume")} />
      <FileSlot kind="portfolio" current={find("portfolio")} />
      <SummarySlot current={find("summary")} />
    </div>
  );
}
