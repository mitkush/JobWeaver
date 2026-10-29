import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams, useBlocker } from "react-router-dom";

import { api, downloadFile, fetchFile, unwrap, type Schemas } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buttonClasses } from "@/components/ui/button-classes";
import { Card } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Field, Input, Select } from "@/components/ui/field";
import { PageSpinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast-context";
import { pdfHref, useDraft, useDraftActions, useDraftDiff, type Content, type Draft, type Part, type Version } from "@/features/drafts/api";
import { DocumentReview } from "@/features/drafts/DocumentReview";
import { ReplacementPanel } from "@/features/drafts/ReplacementPanel";
import { DraftManagement } from "@/features/drafts/DraftManagement";
import { PdfPreview, type PdfFile } from "@/features/drafts/PdfPreview";
import { statusLabel } from "@/features/applications/status";

const DIFF_LABELS = { unchanged: "Unchanged", rewritten: "Rewritten", added_from_portfolio: "Added from portfolio", reordered: "Reordered", removed: "Removed" };

const PARTS: { value: Part; label: string }[] = [
  { value: "resume", label: "Tailored Resume" },
  { value: "cover_letter", label: "Cover Letter" },
  { value: "email_body", label: "Application Email" },
];

export function DraftPage() {
  const { draftId = "" } = useParams();
  const draft = useDraft(draftId);
  const actions = useDraftActions(draftId);
  if (draft.isPending) return <PageSpinner />;
  if (draft.isError) return <Alert tone="error" title="Draft could not load">{draft.error.message}</Alert>;
  if (draft.data.state === "failed") return <Card className="space-y-4 p-6"><h1 className="text-xl font-semibold">Draft generation stopped</h1><Alert tone="warning">{draft.data.error}</Alert><DraftManagement jobId={draft.data.job_id} draftId={draft.data.id} version={draft.data.current_version} allowDelete /><Button loading={actions.retry.isPending} onClick={() => void actions.retry.mutate()}>Retry generation</Button>{actions.retry.isError && <Alert tone="error">{actions.retry.error.message}</Alert>}</Card>;
  if (!draft.data.version) return <Card className="space-y-4 p-6"><h1 className="text-xl font-semibold">Preparing your Draft</h1><p role="status" aria-live="polite">{draft.data.progress}</p><p className="text-sm text-slate-500 dark:text-slate-400">Reading the job → Choosing your experience → Writing → Checking Facts and Trace</p></Card>;
  return <DraftWorkspace draft={draft.data} key={draftId} />;
}

export function DraftWorkspace({ draft }: { draft: Draft }) {
  const [search] = useSearchParams();
  const [current, setCurrent] = useState<Version>(draft.version!);
  const [content, setContent] = useState<Content>(draft.version!.content);
  const [part, setPart] = useState<Part>("resume");
  const [section, setSection] = useState<Content["resume"][number]["section"]>();
  const [compareOpen, setCompareOpen] = useState(false);
  const [failedSnapshot, setFailedSnapshot] = useState<string>();
  const [recipient, setRecipient] = useState(() =>
    search.has("resume_handoff") ? (sessionStorage.getItem(`draft-recipient-${draft.id}`) ?? String(draft.job.contact_email ?? "")) : String(draft.job.contact_email ?? ""),
  );
  const [emailCheck, setEmailCheck] = useState<Schemas["EmailCheck"] | null>(null);
  const [confirmWarning, setConfirmWarning] = useState(false);
  const [handoffConfirm, setHandoffConfirm] = useState(false);
  const [handoff, setHandoff] = useState<Schemas["HandoffOut"] | null>(null);
  // Until the User picks one, use the layout this version fits on two pages in.
  const [chosenTemplate, setTemplate] = useState<"standard" | "compact" | null>(null);
  const template = chosenTemplate ?? draft.template ?? "standard";
  const [error, setError] = useState<string | null>(null);
  // Shown beside the PDF buttons, where the User clicked, not at the top of the page.
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [preview, setPreview] = useState<PdfFile | null>(null);
  const [outwardBusy, setOutwardBusy] = useState(false);
  const [loadLatestConfirm, setLoadLatestConfirm] = useState(false);
  const [recheckConfirm, setRecheckConfirm] = useState(false);
  const [resumePrompt, setResumePrompt] = useState(search.has("resume_handoff"));
  const actions = useDraftActions(draft.id);
  const toast = useToast();
  const dirty = JSON.stringify(content) !== JSON.stringify(current.content);
  // Fetched only when the comparison is opened.
  const diff = useDraftDiff(draft.id, current.number, compareOpen);
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && (currentLocation.pathname !== nextLocation.pathname || currentLocation.search !== nextLocation.search));
  const busy = actions.save.isPending || actions.recheck.isPending || actions.chat.isPending || actions.restore.isPending || outwardBusy;
  const hasEmail = Boolean(draft.job.contact_email);
  // Applied or any later status: Mark as applied has nothing left to do.
  const applied = Boolean(draft.application_status && draft.application_status !== "drafted");
  const stale = current.number !== draft.current_version;
  const snapshot = JSON.stringify(content);
  const blocked = actions.recheck.isPending || actions.restore.isPending || outwardBusy || draft.active === false;
  const { mutateAsync: saveDraft, isPending: saving } = actions.save;

  useEffect(() => {
    if (!dirty || stale || busy || failedSnapshot === snapshot) return;
    const timer = setTimeout(() => {
      void saveDraft({ expected_version: current.number, content: JSON.parse(snapshot) as Content }).then(updated => {
        if (updated.version) {
          setCurrent(updated.version);
          setContent(local => JSON.stringify(local) === snapshot ? updated.version!.content : local);
        }
        setError(null); setFailedSnapshot(undefined);
      }).catch((failure: Error) => { setError(failure.message); setFailedSnapshot(snapshot); });
    }, 1200);
    return () => clearTimeout(timer);
  }, [dirty, stale, busy, failedSnapshot, snapshot, current.number, saveDraft]);

  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [dirty]);

  function accept(updated: Draft) {
    if (updated.version) {
      setCurrent(updated.version);
      setContent(updated.version.content);
    }
    setError(null);
  }
  async function save() {
    try {
      const updated = await actions.save.mutateAsync({ expected_version: current.number, content });
      if (updated.version) { setCurrent(updated.version); setContent(local => JSON.stringify(local) === snapshot ? updated.version!.content : local); }
      setError(null); setFailedSnapshot(undefined);
      return updated;
    } catch (failure) { setError((failure as Error).message); setFailedSnapshot(snapshot); return null; }
  }
  async function recheck() {
    setRecheckConfirm(false);
    try {
      accept(await actions.recheck.mutateAsync(current.number));
      toast("success", "Draft checked against your latest Fact Bank");
    } catch (failure) { setError((failure as Error).message); }
  }
  async function restore(number: number) {
    try {
      accept(await actions.restore.mutateAsync({ expected_version: current.number, number }));
    } catch (failure) { setError((failure as Error).message); }
  }
  async function prepareHandoff() {
    setError(null);
    setOutwardBusy(true);
    try {
      const result = await unwrap(api.GET("/api/drafts/{draft_id}/email-check", { params: { path: { draft_id: draft.id }, query: { recipient } } }));
      setEmailCheck(result);
      setConfirmWarning(false);
      setHandoffConfirm(true);
      setResumePrompt(false);
    } catch (failure) { setError((failure as Error).message); }
    finally { setOutwardBusy(false); }
  }
  async function pdfFile(kind: "resume" | "cover_letter", action: "preview" | "download") {
    if (!current) return;
    setDownloadError(null);
    setDownloading(`${action}-${kind}`);
    const fallback = kind === "cover_letter" ? draft.attachment_name.replace(/\.pdf$/, "_Cover_Letter.pdf") : draft.attachment_name;
    try {
      const saved = dirty ? await save() : null;
      if (dirty && !saved) throw new Error("Save failed. Your edits are still here; retry saving before previewing.");
      const url = pdfHref(draft.id, kind, saved?.version?.number ?? current.number, template);
      if (action === "download") await downloadFile(url, fallback);
      else setPreview({ kind, template, ...(await fetchFile(url, fallback)) });
    } catch (failure) {
      setDownloadError((failure as Error).message);
    } finally {
      setDownloading(null);
    }
  }

  async function openGmail() {
    setOutwardBusy(true);
    setHandoffConfirm(false);
    // Open synchronously from the click so browsers do not block the new tab.
    const tab = window.open("about:blank", "_blank");
    if (tab) tab.opener = null;
    try {
      const result = await unwrap(api.POST("/api/drafts/{draft_id}/handoff", {
        params: { path: { draft_id: draft.id } },
        body: { expected_version: current.number, recipient, template, confirm: true, confirm_email_warning: confirmWarning },
      }));
      setHandoff(result);
      if (result.mode === "reconnect") {
        tab?.close();
        sessionStorage.setItem(`draft-recipient-${draft.id}`, recipient);
        window.location.assign(result.url);
        return;
      }
      if (tab) tab.location.href = result.url;
      if (result.mode === "fallback") {
        await downloadFile(pdfHref(draft.id, "resume", current.number, template), draft.attachment_name);
      }
      await actions.refresh();
    } catch (failure) { tab?.close(); setError((failure as Error).message); }
    finally { setOutwardBusy(false); }
  }

  return (
    <div className="space-y-5">
      <ConfirmDialog open={blocker.state === "blocked"} title="Save your edits before leaving?" confirmLabel="Save and leave" tone="primary" loading={actions.save.isPending} confirmDisabled={busy || stale} onCancel={() => blocker.state === "blocked" && blocker.reset()} onConfirm={() => void (async () => { if (await save()) { if (blocker.state === "blocked") blocker.proceed(); } })()}
        secondaryAction={<Button variant="secondary" disabled={busy} onClick={() => blocker.state === "blocked" && blocker.proceed()}>Discard and leave</Button>}>
        <p>Your unsaved changes will be lost if you leave without saving. Cancel keeps you here.</p>
        {error && <Alert tone="error">{error}</Alert>}
      </ConfirmDialog>
      <Link to={`/jobs/${draft.job_id}`} className="text-sm text-brand-700 dark:text-brand-200">← Back to Job</Link>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h1 className="text-2xl font-semibold">Draft · {String(draft.job.company ?? "")}</h1><p className="mt-1 text-slate-600 dark:text-slate-400">{String(draft.job.title ?? "")}</p></div>
        <div className="flex items-center gap-2"><Badge>{saving ? "Saving…" : dirty ? failedSnapshot === snapshot ? "Couldn’t save" : "Unsaved changes" : "Saved"}</Badge>{draft.application_status && <Badge>{statusLabel(draft.application_status)}</Badge>}</div>
      </div>
      {draft.active === false && <Alert tone="info">This archived package is kept for your application history and is read-only. Open the current Draft from the Job page.</Alert>}
      {error && <Alert tone="error">{error}</Alert>}
      {stale && <Alert tone="warning">A newer version is available. Your edits are still here. <Button variant="ghost" size="sm" onClick={() => dirty ? setLoadLatestConfirm(true) : accept(draft)}>Load latest version</Button></Alert>}
      {current.warnings.length > 0 && <Alert tone="warning" title="Checked against your Fact Bank"><ul className="list-disc pl-5">{current.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul><p className="mt-2">Edit the line or cite a supporting Fact in its Tailoring Trace. If the Fact is missing, add it to your Fact Bank and recheck.</p><div className="mt-2 flex flex-wrap items-center gap-3"><a href="#draft-editor" className="text-sm font-medium underline" onClick={() => { setPart("resume"); setSection(undefined); }}>Review resume lines</a><Link to="/fact-bank" className="text-sm font-medium underline">Open Fact Bank</Link><Button variant="secondary" size="sm" disabled={busy || dirty || stale} onClick={() => setRecheckConfirm(true)}>Recheck latest Facts</Button></div>{dirty && <p className="mt-2 text-xs">Save your edits before rechecking.</p>}</Alert>}
      {resumePrompt && <Alert tone="info">Gmail connection returned. Review the recipient and confirm to resume the hand-off.<Button variant="ghost" onClick={() => { setRecipient(sessionStorage.getItem(`draft-recipient-${draft.id}`) ?? recipient); }}>Restore recipient</Button></Alert>}
      {handoff && <Alert tone={handoff.mode === "fallback" ? "warning" : "info"}>{handoff.message} <a className="font-medium underline" href={handoff.url} target="_blank" rel="noreferrer">{handoff.mode === "fallback" ? "Open Gmail compose" : "Open Gmail Drafts"}</a>{handoff.mode === "fallback" && <> · <button type="button" className="underline" onClick={() => void pdfFile("resume", "download")}>Download resume PDF</button></>}</Alert>}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Card id="draft-editor" className="min-w-0 space-y-5 p-4 sm:p-6">
          <div className="flex flex-wrap gap-2" role="tablist" aria-label="Draft documents">
            {PARTS.filter((entry) => entry.value !== "email_body" || hasEmail).map((entry) => <Button key={entry.value} id={`draft-tab-${entry.value}`} role="tab" aria-controls="draft-document-panel" tabIndex={part === entry.value ? 0 : -1} aria-selected={part === entry.value} variant={part === entry.value ? "primary" : "secondary"} onClick={() => { setPart(entry.value); setSection(undefined); }} onKeyDown={event => {
              const entries = PARTS.filter(item => item.value !== "email_body" || hasEmail);
              const index = entries.findIndex(item => item.value === entry.value);
              const next = event.key === "ArrowRight" ? (index + 1) % entries.length : event.key === "ArrowLeft" ? (index - 1 + entries.length) % entries.length : event.key === "Home" ? 0 : event.key === "End" ? entries.length - 1 : -1;
              if (next < 0) return;
              event.preventDefault(); setPart(entries[next]!.value); setSection(undefined);
              document.getElementById(`draft-tab-${entries[next]!.value}`)?.focus();
            }}>{entry.label}</Button>)}
          </div>
          {part === "email_body" && <div className="grid gap-3 sm:grid-cols-[2fr_1fr]">
            <Field label="Email subject" htmlFor="email-subject"><Input id="email-subject" value={content.email_subject ?? ""} maxLength={200} onChange={(event) => setContent({ ...content, email_subject: event.target.value })} disabled={busy} /></Field>
            <Field label="Greeting name (blank: Hiring Team)" htmlFor="email-greeting"><Input id="email-greeting" value={content.email_greeting ?? ""} maxLength={100} onChange={(event) => setContent({ ...content, email_greeting: event.target.value })} disabled={busy} /></Field>
          </div>}
          <div id="draft-document-panel" role="tabpanel" aria-labelledby={`draft-tab-${part}`}><DocumentReview key={part} content={content} part={part} facts={current.facts} onChange={setContent} disabled={blocked} onSection={setSection} /></div>
          <div className="sticky bottom-2 z-10 flex flex-wrap items-center gap-3 rounded border bg-white p-3 shadow dark:border-slate-700 dark:bg-slate-900"><Button variant="primary" loading={actions.save.isPending} disabled={busy || !dirty || stale} onClick={() => void save()}>Save now</Button><span className="text-xs text-slate-500 dark:text-slate-400">{dirty ? "Your edits save automatically. Saving never sends anything." : "Saved in JobWeaver. Nothing has been sent."}</span></div>
          <details onToggle={(event) => setCompareOpen((event.target as HTMLDetailsElement).open)}><summary className="cursor-pointer text-sm font-medium">Compare with your Base Resume</summary>
            <div className="mt-3 space-y-2" aria-label="Changes from your Base Resume">
              {diff.isPending && compareOpen && <p className="text-sm text-slate-500 dark:text-slate-400">Loading the comparison…</p>}
              {diff.isError && <Alert tone="error">{diff.error.message}</Alert>}
              {diff.data?.map((line, i) => <div key={i} className="rounded border border-slate-200 p-3 text-sm dark:border-slate-700"><Badge>{DIFF_LABELS[line.kind]}</Badge><p className="mt-2">{line.text}</p>{line.kind === "rewritten" && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Before: {line.before?.join(" · ")}</p>}<p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Trace: {line.fact_refs.join(", ")}</p></div>)}
            </div>
          </details>
          <details><summary className="cursor-pointer text-sm font-medium">Base Resume</summary><pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-600 dark:text-slate-400">{draft.base_resume || "No Base Resume text is available."}</pre></details>

        </Card>
        <div className="min-w-0 space-y-4">
          {part !== "email_body" && <ReplacementPanel draftId={draft.id} currentVersion={current.number} currentContent={content} part={part} section={section} dirty={dirty || stale || busy} onAccept={updated => { accept(updated); void actions.refresh(updated); }} />}
          {current.source === "replacement" && current.number > 1 && <Button variant="secondary" disabled={dirty || stale || busy} onClick={() => void restore(current.number - 1)}>Undo replacement</Button>}
          <Card className="space-y-4 p-4">
            <h2 className="text-base font-semibold">Review and apply</h2>
            <div className="flex flex-wrap gap-2"><DraftManagement jobId={draft.job_id} draftId={draft.id} version={current.number} disabled={dirty || stale || busy} allowDelete={draft.active !== false} /></div>
            <Field label="PDF layout" htmlFor="pdf-template" hint={draft.template === "compact" ? "This resume fits two pages only in Compact." : undefined}><Select id="pdf-template" value={template} onChange={(event) => setTemplate(event.target.value === "compact" ? "compact" : "standard")}><option value="standard">Standard · single column</option><option value="compact">Compact · single column</option></Select></Field>
            {!stale ? <div className="flex flex-wrap gap-2">{(["resume", "cover_letter"] as const).map((kind) => { const label = kind === "resume" ? "Resume" : "Cover Letter"; return <span key={kind} className="flex flex-wrap gap-1"><Button variant="secondary" size="sm" loading={downloading === `preview-${kind}`} disabled={downloading !== null || saving} onClick={() => void pdfFile(kind, "preview")}>Preview {label}</Button><Button variant="secondary" size="sm" loading={downloading === `download-${kind}`} disabled={downloading !== null || saving} onClick={() => void pdfFile(kind, "download")} aria-label={`Download ${label} PDF`}>{label} PDF</Button></span>; })}</div> : <p className="text-xs text-slate-500 dark:text-slate-400">Load the latest saved Draft before previewing.</p>}
            {downloadError && <Alert tone="error" title="The PDF could not be made">{downloadError}</Alert>}
            {preview && <PdfPreview file={preview} onClose={() => setPreview(null)} />}
            {hasEmail ? <>
              <Field label="Recipient" htmlFor="draft-recipient"><Input id="draft-recipient" type="email" value={recipient} onChange={(event) => setRecipient(event.target.value)} /></Field>
              <Button className="w-full" disabled={dirty || stale || busy || !recipient.trim()} loading={outwardBusy} onClick={() => void prepareHandoff()}>Open in Gmail</Button>
            </> : draft.job.apply_url ? <a className={buttonClasses("primary") + " w-full"} href={String(draft.job.apply_url)} target="_blank" rel="noreferrer noopener">Open apply link</a> : <p className="text-sm text-slate-500 dark:text-slate-400">This Job has no apply link.</p>}
            <Button className="w-full" variant={hasEmail ? "secondary" : "primary"} disabled={busy || dirty || stale || applied} loading={actions.applied.isPending} onClick={async () => {
              try { await actions.applied.mutateAsync(current.number); toast("success", "Marked as applied"); }
              catch (failure) { setError((failure as Error).message); }
            }}>{applied ? statusLabel(draft.application_status!) : "Mark as applied"}</Button>
            <p className="text-xs text-slate-500 dark:text-slate-400">{hasEmail ? "You review and send from Gmail. JobWeaver only creates a draft." : "Download your PDFs, apply on the company site, then mark this Job as applied."}</p>
          </Card>
        </div>
      </div>
      <ConfirmDialog open={handoffConfirm} title="Create a Gmail draft?" confirmLabel="Create draft and open Gmail" tone="primary" loading={outwardBusy} confirmDisabled={Boolean(emailCheck && !emailCheck.valid && !confirmWarning)} onCancel={() => setHandoffConfirm(false)} onConfirm={() => void openGmail()}>
        <p>Recipient: <strong className="break-all">{recipient}</strong></p><p className="mt-2">Attachment: <strong className="break-all">{draft.attachment_name}</strong></p>
        {emailCheck && !emailCheck.valid && <div className="mt-3"><Alert tone="warning">{emailCheck.warnings.join(". ")}</Alert><label className="mt-3 flex gap-2"><input type="checkbox" checked={confirmWarning} onChange={(event) => setConfirmWarning(event.target.checked)} />I understand the email warning and want to continue.</label></div>}
        <p className="mt-2 text-xs">You will send from Gmail after reviewing.</p>
      </ConfirmDialog>
      <ConfirmDialog open={loadLatestConfirm} title="Replace unsaved edits?" confirmLabel="Load latest version" tone="primary" onCancel={() => setLoadLatestConfirm(false)} onConfirm={() => { accept(draft); setLoadLatestConfirm(false); }}>Your unsaved edits will be replaced with the latest saved version.</ConfirmDialog>
      <ConfirmDialog open={recheckConfirm} title="Recheck against your latest Fact Bank?" confirmLabel="Recheck draft" tone="primary" loading={actions.recheck.isPending} onCancel={() => setRecheckConfirm(false)} onConfirm={() => void recheck()}>This creates a new version. Your edited lines stay and are flagged if unsupported. AI-written lines that no longer have supporting Facts may be removed; you can restore an earlier version.</ConfirmDialog>
    </div>
  );
}
