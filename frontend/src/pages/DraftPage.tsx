import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { api, unwrap, type Schemas } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buttonClasses } from "@/components/ui/button-classes";
import { Card } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Field, Input, Select } from "@/components/ui/field";
import { PageSpinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast-context";
import { pdfHref, useDraft, useDraftActions, useDraftDiff, useVersions, type Content, type Draft, type Part, type Version } from "@/features/drafts/api";
import { DraftChatPanel } from "@/features/drafts/DraftChatPanel";
import { DraftEditor } from "@/features/drafts/DraftEditor";
import { statusLabel } from "@/features/applications/status";
import { movedIndexes } from "@/lib/order";

const PARTS: { value: Part; label: string }[] = [
  { value: "resume", label: "Tailored Resume" },
  { value: "cover_letter", label: "Cover Letter" },
  { value: "email_body", label: "Application Email" },
];
const DIFF_LABELS = { unchanged: "Unchanged", rewritten: "Rewritten", added_from_portfolio: "Added from portfolio", reordered: "Reordered", removed: "Removed" };

export function DraftPage() {
  const { draftId = "" } = useParams();
  const draft = useDraft(draftId);
  const actions = useDraftActions(draftId);
  if (draft.isPending) return <PageSpinner />;
  if (draft.isError) return <Alert tone="error" title="Draft could not load">{draft.error.message}</Alert>;
  if (draft.data.state === "failed") return <Card className="space-y-4 p-6"><h1 className="text-xl font-semibold">Draft generation stopped</h1><Alert tone="warning">{draft.data.error}</Alert><Button loading={actions.retry.isPending} onClick={() => void actions.retry.mutate()}>Retry generation</Button>{actions.retry.isError && <Alert tone="error">{actions.retry.error.message}</Alert>}</Card>;
  if (!draft.data.version) return <Card className="space-y-4 p-6"><h1 className="text-xl font-semibold">Preparing your Draft</h1><p role="status" aria-live="polite">{draft.data.progress}</p><p className="text-sm text-slate-500">Reading the job → Choosing your experience → Writing → Checking Facts and Trace</p></Card>;
  return <DraftWorkspace draft={draft.data} key={draftId} />;
}

export function DraftWorkspace({ draft }: { draft: Draft }) {
  const [search] = useSearchParams();
  const [current, setCurrent] = useState<Version>(draft.version!);
  const [content, setContent] = useState<Content>(draft.version!.content);
  const [part, setPart] = useState<Part>("resume");
  const [showDiff, setShowDiff] = useState(false);
  const [compare, setCompare] = useState("base");
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
  const [chatError, setChatError] = useState<string | undefined>();
  const [outwardBusy, setOutwardBusy] = useState(false);
  const [loadLatestConfirm, setLoadLatestConfirm] = useState(false);
  const [resumePrompt, setResumePrompt] = useState(search.has("resume_handoff"));
  const versions = useVersions(draft.id);
  const diff = useDraftDiff(draft.id, current.number, showDiff && compare === "base");
  const actions = useDraftActions(draft.id);
  const toast = useToast();
  const dirty = JSON.stringify(content) !== JSON.stringify(current.content);
  const busy = actions.save.isPending || actions.chat.isPending || actions.restore.isPending || outwardBusy;
  const hasEmail = Boolean(draft.job.contact_email);
  // Applied or any later status: Mark as applied has nothing left to do.
  const applied = Boolean(draft.application_status && draft.application_status !== "drafted");
  const stale = current.number !== draft.current_version;

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
      accept(await actions.save.mutateAsync({ expected_version: current.number, content }));
      toast("success", "Draft saved");
    } catch (failure) { setError((failure as Error).message); }
  }
  async function chat(message: string, overwrite: boolean) {
    setChatError(undefined);
    try {
      accept(await actions.chat.mutateAsync({ expected_version: current.number, message, overwrite_manual: overwrite }));
      return true;
    } catch (failure) { setChatError((failure as Error).message); return false; }
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
        const link = document.createElement("a");
        link.href = pdfHref(draft.id, "resume", current.number, template);
        link.download = draft.attachment_name;
        link.click();
      }
      await actions.refresh();
    } catch (failure) { tab?.close(); setError((failure as Error).message); }
    finally { setOutwardBusy(false); }
  }

  const selected = versions.data?.find((version) => String(version.number) === compare);
  const oldLines = selected?.content[part] ?? [];
  const prior = new Map(oldLines.map((line) => [line.id, line.text]));
  const oldIndex = new Map(oldLines.map((line, i) => [line.id, i]));
  const keptLines = (content[part] ?? []).map((line, i) => [i, oldIndex.get(line.id)] as const).filter((entry): entry is readonly [number, number] => entry[1] !== undefined);
  const movedLines = new Set([...movedIndexes(keptLines.map(([, old]) => old))].map((j) => keptLines[j]![0]));
  return (
    <div className="space-y-5">
      <Link to={`/jobs/${draft.job_id}`} className="text-sm text-brand-700 dark:text-brand-200">← Back to Job</Link>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h1 className="text-2xl font-semibold">Draft · {String(draft.job.company ?? "")}</h1><p className="mt-1 text-slate-600 dark:text-slate-400">{String(draft.job.title ?? "")}</p></div>
        <div className="flex items-center gap-2"><Badge>Version {current.number}</Badge>{draft.application_status && <Badge>{statusLabel(draft.application_status)}</Badge>}</div>
      </div>
      {error && <Alert tone="error">{error}</Alert>}
      {stale && <Alert tone="warning">A newer version is available. Your edits are still here. <Button variant="ghost" size="sm" onClick={() => dirty ? setLoadLatestConfirm(true) : accept(draft)}>Load latest version</Button></Alert>}
      {current.warnings.length > 0 && <Alert tone="warning" title="Checked against your Fact Bank"><ul className="list-disc pl-5">{current.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul></Alert>}
      {resumePrompt && <Alert tone="info">Gmail connection returned. Review the recipient and confirm to resume the hand-off.<Button variant="ghost" onClick={() => { setRecipient(sessionStorage.getItem(`draft-recipient-${draft.id}`) ?? recipient); }}>Restore recipient</Button></Alert>}
      {handoff && <Alert tone={handoff.mode === "fallback" ? "warning" : "info"}>{handoff.message} <a className="font-medium underline" href={handoff.url} target="_blank" rel="noreferrer">{handoff.mode === "fallback" ? "Open Gmail compose" : "Open Gmail Drafts"}</a>{handoff.mode === "fallback" && <> · <a className="underline" href={pdfHref(draft.id, "resume", current.number, template)} download>Download resume PDF</a></>}</Alert>}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Card className="min-w-0 space-y-5 p-4 sm:p-6">
          <div className="flex flex-wrap gap-2" role="tablist" aria-label="Draft documents">
            {PARTS.filter((entry) => entry.value !== "email_body" || hasEmail).map((entry) => <Button key={entry.value} role="tab" aria-selected={part === entry.value} variant={part === entry.value ? "primary" : "secondary"} onClick={() => setPart(entry.value)}>{entry.label}</Button>)}
          </div>
          {part === "email_body" && <Field label="Email subject" htmlFor="email-subject"><Input id="email-subject" value={content.email_subject ?? ""} maxLength={200} onChange={(event) => setContent({ ...content, email_subject: event.target.value })} disabled={busy} /></Field>}
          <DraftEditor content={content} part={part} facts={current.facts} onChange={setContent} disabled={busy} />
          <div className="flex flex-wrap items-center gap-3"><Button variant="secondary" loading={actions.save.isPending} disabled={busy || !dirty || stale} onClick={() => void save()}>Save draft</Button><span className="text-xs text-slate-500">{dirty ? "Unsaved edits. Save before downloading or opening Gmail." : "Saved in JobWeaver. Nothing has been sent."}</span></div>
          <details><summary className="cursor-pointer text-sm font-medium">Base Resume</summary><pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-600 dark:text-slate-400">{draft.base_resume || "No Base Resume text is available."}</pre></details>
          <Button variant="ghost" onClick={() => setShowDiff(!showDiff)}>{showDiff ? "Hide diff and versions" : "Show diff and versions"}</Button>
          {showDiff && <section className="space-y-3" aria-label="Diff and versions">
            <Field label="Compare against" htmlFor="compare-version"><Select id="compare-version" value={compare} onChange={(event) => setCompare(event.target.value)}><option value="base">Base Resume</option>{versions.data?.map((version) => <option key={version.number} value={version.number}>Version {version.number} · {version.source}</option>)}</Select></Field>
            {compare === "base" ? <>
              {diff.isError && <Alert tone="error">{diff.error.message}</Alert>}
              {diff.data?.map((line, i) => <div key={i} className="rounded border border-slate-200 p-3 text-sm dark:border-slate-700"><Badge>{DIFF_LABELS[line.kind]}</Badge><p className="mt-2">{line.text}</p>{line.kind === "rewritten" && <p className="mt-1 text-xs text-slate-500">Before: {line.before?.join(" · ")}</p>}<p className="mt-1 text-xs text-slate-500">Trace: {line.fact_refs.join(", ")}</p></div>)}
            </> : selected && <>
              {(content[part] ?? []).map((line, index) => <div key={line.id ?? index} className="rounded border border-slate-200 p-3 text-sm dark:border-slate-700"><Badge>{!prior.has(line.id) ? "Added" : prior.get(line.id) !== line.text ? "Rewritten" : movedLines.has(index) ? "Reordered" : "Unchanged"}</Badge><p className="mt-1">{line.text}</p>{prior.get(line.id) !== line.text && prior.has(line.id) && <p className="text-xs text-slate-500">Before: {prior.get(line.id)}</p>}</div>)}
              {oldLines.filter((line) => !(content[part] ?? []).some((entry) => entry.id === line.id)).map((line, index) => <p key={line.id ?? index} className="text-sm"><Badge>Removed</Badge> {line.text}</p>)}
              <Button variant="secondary" disabled={busy || dirty || stale} onClick={() => void restore(selected.number)}>Restore version {selected.number}</Button>
            </>}
          </section>}
        </Card>
        <div className="min-w-0 space-y-4">
          <DraftChatPanel versions={versions.data ?? []} currentVersion={draft.current_version} busy={busy} dirty={dirty || stale} onChat={chat} onUndo={(number) => void restore(number)} error={chatError} />
          <Card className="space-y-4 p-4">
            <h2 className="text-base font-semibold">Review and apply</h2>
            <Field label="PDF layout" htmlFor="pdf-template" hint={draft.template === "compact" ? "This resume fits two pages only in Compact." : undefined}><Select id="pdf-template" value={template} onChange={(event) => setTemplate(event.target.value === "compact" ? "compact" : "standard")}><option value="standard">Standard · single column</option><option value="compact">Compact · single column</option></Select></Field>
            {!dirty && !stale ? <div className="flex flex-wrap gap-2"><a className={buttonClasses("secondary", "sm")} href={pdfHref(draft.id, "resume", current.number, template)} download>Resume PDF</a><a className={buttonClasses("secondary", "sm")} href={pdfHref(draft.id, "cover_letter", current.number, template)} download>Cover Letter PDF</a></div> : <p className="text-xs text-slate-500">Save your edits to download PDFs.</p>}
            {hasEmail ? <>
              <Field label="Recipient" htmlFor="draft-recipient"><Input id="draft-recipient" type="email" value={recipient} onChange={(event) => setRecipient(event.target.value)} /></Field>
              <Button className="w-full" disabled={dirty || stale || busy || !recipient.trim()} loading={outwardBusy} onClick={() => void prepareHandoff()}>Open in Gmail</Button>
            </> : draft.job.apply_url ? <a className={buttonClasses("primary") + " w-full"} href={String(draft.job.apply_url)} target="_blank" rel="noreferrer noopener">Open apply link</a> : <p className="text-sm text-slate-500">This Job has no apply link.</p>}
            <Button className="w-full" variant={hasEmail ? "secondary" : "primary"} disabled={busy || dirty || stale || applied} loading={actions.applied.isPending} onClick={async () => {
              try { await actions.applied.mutateAsync(current.number); toast("success", "Marked as applied"); }
              catch (failure) { setError((failure as Error).message); }
            }}>{applied ? statusLabel(draft.application_status!) : "Mark as applied"}</Button>
            <p className="text-xs text-slate-500">{hasEmail ? "You review and send from Gmail. JobWeaver only creates a draft." : "Download your PDFs, apply on the company site, then mark this Job as applied."}</p>
          </Card>
        </div>
      </div>
      <ConfirmDialog open={handoffConfirm} title="Create a Gmail draft?" confirmLabel="Create draft and open Gmail" tone="primary" loading={outwardBusy} confirmDisabled={Boolean(emailCheck && !emailCheck.valid && !confirmWarning)} onCancel={() => setHandoffConfirm(false)} onConfirm={() => void openGmail()}>
        <p>Recipient: <strong className="break-all">{recipient}</strong></p><p className="mt-2">Attachment: <strong className="break-all">{draft.attachment_name}</strong></p>
        {emailCheck && !emailCheck.valid && <div className="mt-3"><Alert tone="warning">{emailCheck.warnings.join(". ")}</Alert><label className="mt-3 flex gap-2"><input type="checkbox" checked={confirmWarning} onChange={(event) => setConfirmWarning(event.target.checked)} />I understand the email warning and want to continue.</label></div>}
        <p className="mt-2 text-xs">You will send from Gmail after reviewing.</p>
      </ConfirmDialog>
      <ConfirmDialog open={loadLatestConfirm} title="Replace unsaved edits?" confirmLabel="Load latest version" tone="primary" onCancel={() => setLoadLatestConfirm(false)} onConfirm={() => { accept(draft); setLoadLatestConfirm(false); }}>Your unsaved edits will be replaced with the latest saved version.</ConfirmDialog>
    </div>
  );
}
