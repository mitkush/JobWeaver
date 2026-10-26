/** Save explicitly requested copies under Downloads/<company>/. Attachments keep a short name. */
import { apiFetch, type Deps } from "./connection";
import { currentSelection, version } from "./drafts";

export function companyFolder(company: string): string {
  const clean = company.replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").replace(/^[.\s]+|[.\s]+$/g, "").slice(0, 80);
  return clean || "Company";
}

export async function savePdfs(deps: Deps, tabId: number, download: (path: string, url: string) => Promise<unknown>): Promise<void> {
  const selection = await currentSelection(deps, tabId);
  const chosen = selection ? await version(deps, selection.draftId, selection.number) : null;
  if (!chosen) throw new Error("Choose a ready Draft first");
  // Fetch both before starting either download, so an unavailable PDF gives a clear error.
  const files = await Promise.all((["resume", "cover_letter"] as const).map(async (kind) => {
    const response = await apiFetch(deps, `/api/ext/drafts/${encodeURIComponent(chosen.draft_id)}/pdf?number=${chosen.number}&kind=${kind}`);
    if (!response?.ok) throw new Error("JobWeaver could not make the PDF");
    const bytes = new Uint8Array(await response.arrayBuffer());
    let binary = "";
    for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return { path: `${companyFolder(chosen.company)}/${kind === "resume" ? chosen.resume_file : chosen.cover_letter_file}`, url: `data:application/pdf;base64,${btoa(binary)}` };
  }));
  for (const file of files) await download(file.path, file.url);
}
