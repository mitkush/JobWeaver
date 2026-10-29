import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/field";
import type { Content, Draft } from "./api";

type Proposal = Schemas["ProposalOut"];
export function ReplacementPanel({ draftId, currentVersion, part, section, dirty, currentContent, onAccept }: {
  draftId: string; currentVersion: number; part: "resume" | "cover_letter"; section?: Content["resume"][number]["section"];
  dirty: boolean; currentContent: Content; onAccept: (draft: Draft) => void;
}) {
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const query = useQuery({ queryKey: ["draft", draftId, "proposals"],
    queryFn: () => unwrap(api.GET("/api/drafts/{draft_id}/proposals", { params: { path: { draft_id: draftId } } })),
    refetchInterval: q => q.state.data?.some(p => ["queued", "generating"].includes(p.state)) ? 1500 : false,
  });
  const proposal = query.data?.[0];
  async function action(run: () => Promise<unknown>) {
    setBusy(true); setError(undefined);
    try { await run(); await query.refetch(); } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function discard(p: Proposal) {
    await unwrap(api.DELETE("/api/drafts/{draft_id}/proposals/{proposal_id}", { params: { path: { draft_id: draftId, proposal_id: p.id } } }));
  }
  return <section aria-label="AI replacement review" className="space-y-3 rounded border border-slate-200 p-4 dark:border-slate-700">
    <h2 className="font-semibold">Improve {section ?? part.replaceAll("_", " ")}</h2>
    <p className="text-sm text-slate-500">AI prepares a replacement from your Fact Bank. Your current document stays until you accept.</p>
    {(error || query.isError) && <Alert tone="error">{error ?? query.error?.message}</Alert>}
    {proposal ? <>
      <p role="status">{proposal.progress}</p>
      {proposal.error && <Alert tone="warning">{proposal.error}</Alert>}
      {proposal.base_version !== currentVersion && <Alert tone="warning">Your Draft changed. Keep your edits and generate a fresh proposal.</Alert>}
      {proposal.content && <details open><summary className="cursor-pointer">Review proposed {proposal.part.replaceAll("_", " ")}</summary>
        <div className="mt-3 grid gap-4 xl:grid-cols-2">{(["Current", "Proposed"] as const).map(label => <div key={label}><h3 className="font-semibold">{label}</h3>{(label === "Current" ? currentContent : proposal.content)![proposal.part as "resume" | "cover_letter"].filter(line => !proposal.section || line.section === proposal.section).map(line => <p key={line.id} className="mt-2 text-sm leading-6">{line.text}</p>)}</div>)}</div>
      </details>}
      {!!proposal.warnings.length && <Alert tone="warning">{proposal.warnings.join(" · ")}</Alert>}
      <div className="flex flex-wrap gap-2">
        {proposal.state === "ready" && <Button disabled={busy || dirty || currentVersion !== proposal.base_version} onClick={() => void action(async () => onAccept(await unwrap(api.POST("/api/drafts/{draft_id}/proposals/{proposal_id}/accept", { params: { path: { draft_id: draftId, proposal_id: proposal.id } }, body: { expected_version: currentVersion } }))))}>Use this replacement</Button>}
        <Button variant="secondary" disabled={busy} onClick={() => void action(() => discard(proposal))}>Keep current</Button>
      </div>
    </> : <>
      <Textarea aria-label="Instructions for replacement" value={instruction} onChange={e => setInstruction(e.target.value)} maxLength={1800} placeholder="Emphasize my Rails work and shorten the summary" />
      <Button variant="secondary" disabled={busy || dirty || query.isPending} onClick={() => void action(() => unwrap(api.POST("/api/drafts/{draft_id}/proposals", { params: { path: { draft_id: draftId } }, body: { expected_version: currentVersion, part, section, instruction } })))}>Prepare {section ? `${section} changes` : part === "resume" ? "replacement resume" : "replacement cover letter"}</Button>
    </>}
  </section>;
}
