import { Download, ExternalLink, X } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";

import { saveFile } from "@/api/client";
import { Button } from "@/components/ui/button";

export type PdfFile = { kind: "resume" | "cover_letter"; template: string; blob: Blob; name: string };

/** The exact PDF a download would save, shown in the page before it is sent anywhere. */
export function PdfPreview({ file, onClose }: { file: PdfFile; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const url = useMemo(() => URL.createObjectURL(file.blob), [file.blob]);
  useEffect(() => () => URL.revokeObjectURL(url), [url]);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog || dialog.open) return;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }, []);
  const title = `${file.kind === "resume" ? "Resume" : "Cover Letter"} preview · ${file.template === "compact" ? "Compact" : "Standard"}`;

  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      aria-labelledby="pdf-preview-title"
      className="fixed inset-0 m-auto flex h-[min(56rem,calc(100%-2rem))] w-[min(60rem,calc(100%-2rem))] flex-col rounded-xl border border-slate-200 bg-white p-0 text-slate-900 shadow-xl backdrop:bg-slate-950/50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <h2 id="pdf-preview-title" className="text-base font-semibold">
          {title}
        </h2>
        <div className="flex flex-wrap gap-2">
          {/* Phones often cannot show a PDF inside a page; a new tab always can. */}
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <ExternalLink className="size-4" aria-hidden />
            Open in new tab
          </a>
          <Button variant="secondary" size="sm" onClick={() => saveFile(file.blob, file.name)}>
            <Download className="size-4" aria-hidden />
            Download
          </Button>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close preview">
            <X className="size-4" aria-hidden />
          </Button>
        </div>
      </div>
      <iframe title={title} src={url} className="min-h-0 w-full flex-1 bg-slate-100 dark:bg-slate-950" />
    </dialog>
  );
}
