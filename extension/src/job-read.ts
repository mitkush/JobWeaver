/** On-demand extraction of a public advert, with an editable review before upload. */

export type PageJob = {
  title: string;
  company: string;
  description: string;
  url: string;
  method: "structured data" | "selected text" | "page text";
  truncated: boolean;
};

export const MAX_DESCRIPTION = 50_000;
const JOB_PARAMS = new Set(["gh_jid", "jobid", "job_id", "reqid", "requisitionid", "jid", "id"]);

export function pageUrl(value: string): string {
  const url = new URL(value);
  if (!/^https?:$/.test(url.protocol) || url.username || url.password) throw new Error("Open a public careers-page job advert first.");
  url.hash = "";
  for (const key of [...url.searchParams.keys()]) if (!JOB_PARAMS.has(key.toLowerCase())) url.searchParams.delete(key);
  return url.toString();
}

function text(root: Element): string {
  const copy = root.cloneNode(true) as HTMLElement;
  // Exclude entered answers, account panels and navigation from the public advert.
  copy.querySelectorAll("script,style,noscript,nav,header,footer,aside,form,input,textarea,select,button,svg,[hidden],[aria-hidden='true']").forEach((n) => n.remove());
  copy.querySelectorAll("br,p,li,div,section,h1,h2,h3").forEach((n) => n.append("\n"));
  return (copy.textContent ?? "").replace(/[ \t]+/g, " ").replace(/ *\n */g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}

function plain(doc: Document, value: unknown): string {
  if (typeof value !== "string") return "";
  const parsed = new doc.defaultView!.DOMParser().parseFromString(value, "text/html");
  return text(parsed.body);
}

function structured(doc: Document): Record<string, unknown>[] {
  const found: Record<string, unknown>[] = [];
  function visit(value: unknown, depth = 0) {
    if (depth > 8 || found.length >= 20) return;
    if (Array.isArray(value)) { for (const item of value.slice(0, 100)) visit(item, depth + 1); return; }
    if (!value || typeof value !== "object") return;
    const item = value as Record<string, unknown>;
    const types = Array.isArray(item["@type"]) ? item["@type"] : [item["@type"]];
    if (types.includes("JobPosting")) found.push(item);
    if (item["@graph"]) visit(item["@graph"], depth + 1);
    if (item.mainEntity) visit(item.mainEntity, depth + 1);
    if (item.itemListElement) visit(item.itemListElement, depth + 1);
    if (item.item) visit(item.item, depth + 1);
  }
  for (const node of doc.querySelectorAll('script[type="application/ld+json"]')) {
    if ((node.textContent?.length ?? 0) > 1_000_000) continue;
    try { visit(JSON.parse(node.textContent ?? "")); } catch { /* Try visible text. */ }
  }
  return found;
}

export function readJob(doc: Document, href: string, selection = ""): PageJob {
  const url = pageUrl(href);
  const records = structured(doc);
  const exact = records.filter((r) => {
    try { return typeof r.url === "string" && pageUrl(new URL(r.url, href).href) === url; } catch { return false; }
  });
  // Never choose the first of several adverts on a search/list page.
  const record = exact.length === 1 ? exact[0] : records.length === 1 ? records[0] : undefined;
  if (records.length > 1 && !record && !selection.trim()) throw new Error("This page lists several jobs. Open one job, or select its description and read again.");
  const heading = doc.querySelector("h1")?.textContent?.trim() ?? doc.title;
  const company = record?.hiringOrganization;
  const organization = company && typeof company === "object" ? (company as { name?: unknown }).name : "";
  let description = selection.trim();
  let method: PageJob["method"] = "selected text";
  if (!description) { description = plain(doc, record?.description); method = "structured data"; }
  if (!description) {
    // Prefer the advert region; never fall back to the whole body/account/application.
    const selectors = ['[data-automation-id="jobPostingDescription"]', '[itemprop="description"]', '#job-description', '.job-description', '[data-testid="job-description"]', 'article', 'main', '[role="main"]'];
    for (const selector of selectors) {
      const root = doc.querySelector(selector);
      const candidate = root ? text(root) : "";
      if (candidate.length >= 80) { description = candidate; break; }
    }
    method = "page text";
  }
  return {
    title: (typeof record?.title === "string" ? record.title : heading).trim().slice(0, 500),
    company: typeof organization === "string" ? organization.trim().slice(0, 255) : "",
    description: description.slice(0, MAX_DESCRIPTION), url, method,
    truncated: description.length > MAX_DESCRIPTION,
  };
}
