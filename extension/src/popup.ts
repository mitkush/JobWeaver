import type { PopupMessage } from "./background";
import type { DraftSummary, DraftVersion, PageState } from "./drafts";
import type { FillResult, ScanResult } from "./fill/session";
import type { FillReport } from "./fill/types";
import { fromNow } from "./time";
import type { Captured } from "./capture";
import { isPageJob, type PageJob } from "./job-read";

type Status = { connected: false; error?: string } | { connected: true; email: string; expiresAt: string };

const statusText = document.querySelector<HTMLParagraphElement>("#status")!;
const content = document.querySelector<HTMLDivElement>("#content")!;
const connectButton = document.querySelector<HTMLButtonElement>("#connect")!;
const disconnectButton = document.querySelector<HTMLButtonElement>("#disconnect")!;

const RELOAD_HELP = "Reload JobWeaver in brave://extensions (or chrome://extensions), refresh this careers page, then try again.";

async function ask<T>(message: PopupMessage, timeoutMs?: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const pending = chrome.runtime.sendMessage(message);
    const response = timeoutMs ? await Promise.race([
      pending,
      new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error(`Reading the page timed out. ${RELOAD_HELP}`)), timeoutMs); }),
    ]) : await pending;
    if (response === undefined) throw new Error(`The extension did not reply. ${RELOAD_HELP}`);
    return response as T;
  } catch (error) {
    if (error instanceof Error && /context invalidated|receiving end|message port|establish connection/i.test(error.message)) {
      throw new Error(`The extension needs to reconnect to this page. ${RELOAD_HELP}`);
    }
    throw error;
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}

/** Builds elements with text only: titles and company names come from job adverts. */
function h(tag: string, attrs: Record<string, string> = {}, ...children: (Node | string | null)[]): HTMLElement {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  for (const child of children) if (child !== null) el.append(child);
  return el;
}

function button(label: string, onClick: () => unknown, variant = ""): HTMLButtonElement {
  const el = h("button", { type: "button", class: variant }, label) as HTMLButtonElement;
  el.addEventListener("click", () => {
    const section = el.closest("section") ?? content;
    section.querySelector("[data-action-error]")?.remove();
    void Promise.resolve().then(onClick).catch((error: unknown) => {
      section.append(h("p", { class: "warn-text", role: "alert", "data-action-error": "true" }, error instanceof Error ? error.message : "The action failed. Try again."));
    });
  });
  return el;
}

/** Children for replaceChildren, without the parts a condition left out. */
const parts = (...items: (Node | string | null)[]) => items.filter((i): i is Node | string => i !== null);

const open = (path: string) => ask({ type: "open", path });

/** The tab the User is looking at: the active tab of the last focused browser window,
 * which is the one the toolbar button belongs to. */
async function activeTab(): Promise<chrome.tabs.Tab | undefined> {
  const window = await chrome.windows.getLastFocused({ windowTypes: ["normal"] });
  const [tab] = await chrome.tabs.query({ active: true, windowId: window.id });
  return tab;
}

function draftLabel(d: Pick<DraftSummary, "company" | "title">): string {
  return `${d.company} - ${d.title}`;
}

function profileSection(state: PageState): HTMLElement {
  const profile = state.profile;
  if (!profile?.reviewed) {
    return h("section", { class: "panel warn" }, h("p", {}, "Review your application profile so forms can be filled."), button("Review profile", () => open("/settings/profile")));
  }
  if (profile.needs_review) {
    return h("section", { class: "panel warn" }, h("p", {}, "Some profile entries cite Facts you changed. They are left out until you check them."), button("Check profile", () => open("/settings/profile"), "ghost"));
  }
  return h("section", { class: "panel" }, h("p", { class: "ok" }, `Profile reviewed (version ${profile.version}).`));
}

/** Read before any Draft exists, then review before storing public advert text. */
function captureSection(tabId: number, refresh: () => void): HTMLElement {
  const section = h("section", { class: "panel" }, h("p", { class: "label" }, "Careers-page job"));
  const body = h("div");
  const read = button("Read this job", async () => {
    read.disabled = true;
    read.textContent = "Reading…";
    body.replaceChildren(h("p", { role: "status" }, "Reading the job description on this page…"));
    try {
      const result = await ask<unknown>({ type: "readJob", tabId }, 15_000);
      if (result && typeof result === "object" && "error" in result && typeof result.error === "string") throw new Error(result.error);
      if (!isPageJob(result)) throw new Error(`The page reader returned an incomplete response. ${RELOAD_HELP}`);
      showReview(result);
    } catch (error) {
      body.replaceChildren(h("p", { class: "warn-text", role: "alert" }, error instanceof Error ? error.message : "The page could not be read. Try again."));
    } finally { read.disabled = false; read.textContent = "Read this job"; }
  });
  section.append(h("p", { class: "muted" }, "Start here even if this Job is not in JobWeaver. Read its JD, review it, then create a Draft from your Fact Bank."), body, h("div", { class: "actions" }, read));
  void ask<(Captured & { error?: string }) | null>({ type: "capturedJob", tabId }).then((saved) => {
    if (saved && !saved.error && !body.childElementCount) showSaved(saved);
  });

  function showReview(job: PageJob) {
    const title = h("input", { type: "text", value: job.title, maxlength: "500", id: "capture-title" }) as HTMLInputElement;
    const company = h("input", { type: "text", value: job.company, maxlength: "255", id: "capture-company" }) as HTMLInputElement;
    const description = h("textarea", { id: "capture-description", rows: "12", maxlength: "50000" }, job.description) as HTMLTextAreaElement;
    const error = h("p", { class: "warn-text", role: "status" });
    const save = button("Save reviewed job", async () => {
      save.disabled = true;
      error.textContent = "";
      try {
        const result = await ask<Captured & { error?: string }>({ type: "saveJob", tabId, job: { ...job, title: title.value, company: company.value, description: description.value } });
        if (result.error) { error.textContent = result.error; return; }
        showSaved(result);
      } finally { save.disabled = false; }
    });
    body.replaceChildren(
      h("p", { class: "muted" }, `Read from ${job.method}. The JD has not been sent yet.`),
      h("p", { class: "muted" }, job.url),
      h("label", { for: "capture-title" }, "Job title"), title,
      h("label", { for: "capture-company" }, "Company"), company,
      h("label", { for: "capture-description" }, "Public job description"), description,
      job.truncated ? h("p", { class: "warn-text" }, "The JD was limited to 50,000 characters. Review the extracted text.") : h("span"),
      h("p", { class: "muted" }, "Review and edit this public advert only. Remove any personal, account or application information. Saving sends these fields to JobWeaver; it does not call AI."),
      error, h("div", { class: "actions" }, save),
    );
  }

  function showSaved(saved: Captured) {
    const error = h("p", { class: "warn-text", role: "status" });
    const create = button("Create Draft from this JD", async () => {
      create.disabled = true;
      try {
        const result = await ask<Captured & { error?: string }>({ type: "createCapturedDraft", tabId });
        if (result.error) { error.textContent = result.error; return; }
        showSaved(result);
        if (result.draft_id) await open(`/drafts/${result.draft_id}`);
      } finally { create.disabled = false; }
    });
    const use = button("Use this Draft", async () => {
      const chosen = await ask<(DraftVersion & { error?: string }) | null>({ type: "select", tabId, draftId: saved.draft_id! });
      if (!chosen || chosen.error) { error.textContent = chosen?.error ?? "The Draft is still preparing. Open it to check progress, then try again."; return; }
      refresh();
    });
    body.replaceChildren(
      h("p", { class: "title" }, `${saved.company} - ${saved.title}`),
      h("p", { class: "muted" }, saved.matched_existing ? "Linked to the existing Job. Your reviewed page JD will be used for a new Draft." : "Captured and saved to your Feed. Your Fact Bank supplies the resume content."),
      error,
      saved.draft_id ? h("div", { class: "actions" }, button("Open Draft", () => open(`/drafts/${saved.draft_id}`), "ghost"), use) : h("div", { class: "actions" }, create),
    );
  }
  return section;
}

function selectedSection(tabId: number, d: DraftVersion, refresh: () => void): HTMLElement {
  const newer = d.current_version > d.number;
  return h(
    "section",
    { class: "panel" },
    h("p", { class: "label" }, "Draft for this page"),
    h("p", { class: "title" }, draftLabel(d)),
    h("p", {}, `Version ${d.number}, saved ${fromNow(d.saved_at)}.`),
    h("ul", { class: "files" }, h("li", {}, d.resume_file), h("li", {}, d.cover_letter_file)),
    d.warnings ? h("p", { class: "warn-text" }, `${d.warnings} ${d.warnings === 1 ? "warning" : "warnings"} to check in the Draft.`) : null,
    newer ? h("p", { class: "warn-text" }, `A newer version (${d.current_version}) was saved. This page still uses version ${d.number}.`) : null,
    h(
      "div",
      { class: "actions" },
      newer ? button(`Use version ${d.current_version}`, async () => {
        await ask({ type: "select", tabId, draftId: d.draft_id, number: d.current_version });
        refresh();
      }) : null,
      button("Open Draft", () => open(`/drafts/${d.draft_id}`), "ghost"),
      button("Save PDFs in company folder", async () => {
        const granted = await chrome.permissions.request({ permissions: ["downloads"] });
        if (!granted) throw new Error("Downloads permission was not granted");
        const saved = await ask<{ error?: string }>({ type: "savePdfs", tabId });
        if (saved.error) throw new Error(saved.error);
      }, "ghost"),
      button("Change", async () => {
        await ask({ type: "clear", tabId });
        refresh();
      }, "ghost"),
    ),
  );
}

function chooseSection(tabId: number, state: PageState, refresh: () => void): HTMLElement {
  const suggested = state.matches;
  const options = suggested.length ? suggested : state.recent;
  if (!options.length) {
    return h("section", { class: "panel" }, h("p", {}, "No ready Drafts yet. Create one from a Job in JobWeaver."), button("Open Feed", () => open("/feed"), "ghost"));
  }
  const select = h("select", { id: "draft", "aria-label": "Draft to use" }) as HTMLSelectElement;
  for (const d of options) select.append(h("option", { value: d.draft_id }, `${draftLabel(d)} (version ${d.current_version})`));
  const intro =
    suggested.length === 1
      ? "This page looks like the apply link of:"
      : suggested.length > 1
        ? `This page matches ${suggested.length} Drafts. Choose one:`
        : "No matching Draft. Read this job above, or choose a saved Draft manually:";
  return h(
    "section",
    { class: "panel" },
    h("p", { class: "label" }, intro),
    select,
    h("div", { class: "actions" }, button("Use this Draft", async () => {
      await ask({ type: "select", tabId, draftId: select.value });
      refresh();
    })),
  );
}

function download(name: string, base64: string) {
  const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
  const a = h("a", { href: url, download: name }) as HTMLAnchorElement;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

const SOURCES = { profile: "Profile", draft: "Draft PDF" } as const;

/** Scan, preview with a tick per field, fill only what is ticked, undo. */
function fillSection(tabId: number): HTMLElement {
  const section = h("section", { class: "panel" }, h("p", { class: "label" }, "Fill this form"));
  const body = h("div");
  const scanButton = button("Scan this form", () => runScan());
  section.append(body, h("div", { class: "actions" }, scanButton));
  // Reopened after checking the page: show the last fill with its Undo and downloads.
  void ask<FillResult | null>({ type: "lastFill", tabId }).then((last) => {
    if (last && !body.childElementCount) showReport(last);
  });

  async function runScan() {
    scanButton.disabled = true;
    try {
      const result = await ask<ScanResult & { error?: string }>({ type: "scan", tabId });
      if (result.error || !result.proposals) {
        body.replaceChildren(h("p", { class: "warn-text" }, result.error ?? "This page could not be scanned."));
        return;
      }
      showPreview(result);
    } finally { scanButton.disabled = false; }
  }

  function showPreview(result: ScanResult) {
    const rows = result.proposals.map((p) => {
      const box = h("input", { type: "checkbox", value: p.ref, id: `f-${p.ref}` }) as HTMLInputElement;
      // A field that already holds something is overwritten only when ticked here.
      box.checked = !p.overwrite && !p.reviewRequired;
      return h(
        "li",
        {},
        box,
        h(
          "label",
          { for: `f-${p.ref}` },
          h("span", { class: "title" }, p.label),
          p.reviewRequired
            ? h("textarea", { "data-answer-ref": p.ref, rows: "8", "aria-label": `Review answer: ${p.label}`, ...(p.maxLength ? { maxlength: String(p.maxLength) } : {}) }, p.value)
            : h("span", { class: "value" }, p.value),
          p.reviewRequired ? h("span", { class: "source" }, "From this Draft's cover letter. Review or edit, then tick to use.") : null,
          h("span", { class: "source" }, p.overwrite ? `${SOURCES[p.source]} - replaces what is there` : SOURCES[p.source]),
        ),
      );
    });
    const fillButton = button("Fill ticked fields", async () => {
      const refs = Array.from(body.querySelectorAll<HTMLInputElement>("input[type=checkbox]:checked"), (b) => b.value);
      fillButton.disabled = true;
      const answers = Object.fromEntries(Array.from(body.querySelectorAll<HTMLTextAreaElement>("textarea[data-answer-ref]"), (el) => [el.dataset.answerRef!, el.value]));
      showReport(await ask<FillResult>({ type: "fill", tabId, refs, answers }));
    });
    body.replaceChildren(...parts(
      result.draft ? null : h("p", { class: "warn-text" }, "Choose a Draft above to attach its resume and cover letter."),
      result.profileReviewed ? null : h("p", { class: "warn-text" }, "Review your profile to fill your details."),
      rows.length ? h("ul", { class: "fields" }, ...rows) : h("p", {}, "Nothing here JobWeaver can fill."),
      result.manual.length ? h("p", { class: "muted" }, `For you to fill: ${result.manual.slice(0, 8).join(", ")}${result.manual.length > 8 ? "…" : ""}`) : null,
      rows.length ? h("p", { class: "muted" }, "Filling puts the ticked values into this site's form, which may save them before you submit. JobWeaver never submits.") : null,
      rows.length ? h("div", { class: "actions" }, fillButton) : null,
    ));
  }

  function showReport(report: FillResult) {
    const label = (ref: string) => report.labels[ref] ?? "A field";
    const undoButton = button("Undo", async () => {
      undoButton.disabled = true;
      const undone = await ask<FillReport>({ type: "undo", tabId });
      body.replaceChildren(
        h("p", {}, `Undid ${undone.filled.length} ${undone.filled.length === 1 ? "field" : "fields"}.`),
        ...undone.failed.map((f) => h("p", { class: "muted" }, `${label(f.ref)}: ${f.reason}`)),
      );
    }, "ghost");
    body.replaceChildren(
      h("p", { class: "ok" }, `Filled ${report.filled.length} ${report.filled.length === 1 ? "field" : "fields"}. Check them on the page, then submit yourself.`),
      ...report.failed.map((f) => h("p", { class: "warn-text" }, `${label(f.ref)}: ${f.reason}`)),
      ...report.downloads.map((d) => button(`Download ${d.name} to attach it yourself`, () => download(d.name, d.base64), "ghost")),
      h("div", { class: "actions" }, undoButton),
    );
  }

  return section;
}

async function render() {
  const status = await ask<Status>({ type: "status" });
  connectButton.hidden = status.connected;
  disconnectButton.hidden = !status.connected;
  content.replaceChildren();
  if (!status.connected) {
    statusText.textContent = status.error ?? "Not connected. Connect to use your JobWeaver Drafts here.";
    return;
  }
  statusText.textContent = `Connected as ${status.email}.`;
  const tab = await activeTab();
  if (tab?.id === undefined) return;
  const tabId = tab.id;
  const state = await ask<PageState>({ type: "page", tabId, url: tab.url });
  const refresh = () => void render();
  content.replaceChildren(...parts(
    profileSection(state),
    !tab.url || /^https?:/.test(tab.url) ? captureSection(tabId, refresh) : null,
    state.selected ? selectedSection(tabId, state.selected, refresh) : chooseSection(tabId, state, refresh),
    // Browser pages cannot be filled; without activeTab the address is unknown, so offer it.
    !tab.url || /^https?:/.test(tab.url) ? fillSection(tabId) : null,
  ));
}

connectButton.addEventListener("click", async () => {
  connectButton.disabled = true;
  await ask({ type: "connect" });
  window.close();
});

disconnectButton.addEventListener("click", async () => {
  disconnectButton.disabled = true;
  await ask({ type: "disconnect" });
  disconnectButton.disabled = false;
  void render();
});

void render();
