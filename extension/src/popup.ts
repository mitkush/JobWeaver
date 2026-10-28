import type { ReviewState } from "./review-state";
import type { PopupMessage } from "./background";
import type { DraftSummary, DraftVersion, PageState } from "./drafts";
import type { Answer, FillResult, Question, ScanResult } from "./fill/session";
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
    const disconnectedStatus = message.type === "status" && response && typeof response === "object" && "connected" in response && response.connected === false;
    if (!disconnectedStatus && response && typeof response === "object" && "error" in response && typeof response.error === "string") throw new Error(response.error);
    if (response === undefined) throw new Error(`The extension did not reply. ${RELOAD_HELP}`);
    if (response === null && !["lastFill", "lastScan", "capturedJob", "select", "clear", "open"].includes(message.type)) throw new Error(`The extension returned an incomplete reply. ${RELOAD_HELP}`);
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
  return h("section", { class: "panel" }, h("p", { class: "ok" }, "Profile ready for this application."));
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
  }).catch((error: unknown) => {
    if (!body.childElementCount) body.append(h("p", { class: "warn-text", role: "alert" }, error instanceof Error ? error.message : "The saved Job could not load."));
  });

  void ask<ReviewState>({ type: "reviewState", tabId }).then(review => {
    if (review?.capture && !body.childElementCount) showReview(review.capture);
  }).catch(() => undefined);

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
        await ask({ type: "reviewState", tabId, patch: { capture: null } });
        showSaved(result);
      } finally { save.disabled = false; }
    });
    const persist = () => { void ask({ type: "reviewState", tabId, patch: { capture: { ...job, title: title.value, company: company.value, description: description.value } } }).catch(() => undefined); };
    title.addEventListener("input", persist); company.addEventListener("input", persist); description.addEventListener("input", persist);
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

function selectedSection(tabId: number, d: DraftVersion, refresh: () => void, needsConfirmation = false): HTMLElement {
  const newer = d.current_version > d.number;
  const applied = Boolean(d.application_status && d.application_status !== "drafted");
  return h(
    "section",
    { class: "panel" },
    h("p", { class: "label" }, "Application documents"),
    h("p", { class: "title" }, draftLabel(d)),
    needsConfirmation ? h("div", {}, h("p", { class: "warn-text" }, "Confirm the Job and document before continuing on this page."), button("Continue with this reviewed document", async () => { await chooseDraft(tabId, d.draft_id, d.number); refresh(); })) : null,
    h("p", {}, `Saved ${fromNow(d.saved_at)}.`),
    applied ? h("p", { class: "ok" }, `Application status: ${d.application_status}`) : null,
    h("ul", { class: "files" }, h("li", {}, d.resume_file), h("li", {}, d.cover_letter_file)),
    d.warnings ? h("p", { class: "warn-text" }, `${d.warnings} ${d.warnings === 1 ? "warning" : "warnings"} to check in the Draft.`) : null,
    newer ? h("p", { class: "warn-text" }, "An updated document is available. This application still uses the copy you reviewed.") : null,
    h(
      "div",
      { class: "actions" },
      newer ? button("Use updated document", async () => {
        await chooseDraft(tabId, d.draft_id, d.current_version);
        refresh();
      }) : null,
      button("Open Draft", () => open(`/drafts/${d.draft_id}`), "ghost"),
      button("Save PDFs in company folder", async () => {
        const granted = await chrome.permissions.request({ permissions: ["downloads"] });
        if (!granted) throw new Error("Downloads permission was not granted");
        const saved = await ask<{ error?: string }>({ type: "savePdfs", tabId });
        if (saved.error) throw new Error(saved.error);
        content.append(h("p", { role: "status", class: "ok" }, "PDFs saved under Downloads in the company folder."));
      }, "ghost"),
      applied ? h("button", { type: "button", class: "ghost", disabled: "true" }, "Applied recorded") : button("Mark as applied", async () => {
        const actions = h("div", { class: "actions" }, button("Yes, I submitted this application", async () => {
          await ask({ type: "markApplied", tabId }); refresh();
        }), button("Cancel", () => actions.remove(), "ghost"));
        content.append(h("section", { class: "panel" }, h("p", {}, "Have you submitted the application yourself? Filling or downloading does not submit it."), actions));
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
  for (const d of options) select.append(h("option", { value: d.draft_id }, draftLabel(d)));
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
      await chooseDraft(tabId, select.value);
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
  const embedded = button("Find embedded forms", async () => {
    if (!await chrome.permissions.request({ permissions: ["webNavigation"] })) throw new Error("Frame discovery was not allowed. You can still scan the main page.");
    const origins = await ask<string[]>({ type: "frameSites", tabId });
    body.replaceChildren(h("p", {}, origins.length ? "Allow each embedded form site you want to scan:" : "No embedded form sites were found."), ...origins.map(origin => button(`Allow ${new URL(origin).hostname}`, async () => {
      if (!await chrome.permissions.request({ origins: [`${origin}/*`] })) throw new Error("Site access was not granted");
      await runScan();
    }, "ghost")));
  }, "ghost");
  section.append(body, h("div", { class: "actions" }, scanButton, embedded));
  // Reopened after checking the page: show the last fill with its Undo and downloads.
  void ask<FillResult | null>({ type: "lastFill", tabId }).then((last) => {
    if (last && !body.childElementCount) showReport(last);
    else if (!last && !body.childElementCount) void ask<ScanResult | null>({ type: "lastScan", tabId }).then(scan => { if (scan && !body.childElementCount) showPreview(scan); }).catch(() => undefined);
  }).catch((error: unknown) => {
    if (!body.childElementCount) body.append(h("p", { class: "warn-text", role: "alert" }, error instanceof Error ? error.message : "The previous fill could not load."));
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
    scanButton.classList.add("ghost");
    scanButton.textContent = "Scan again";
    if (result.unavailableFrames) section.append(h("p", { class: "warn-text" }, `${result.unavailableFrames} embedded frame(s) need site access. Use Find embedded forms, or open the hosted application.`));
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
      try {
        const report = await ask<FillResult>({ type: "fill", tabId, refs, answers });
        if (!report || !Array.isArray(report.filled) || !Array.isArray(report.failed) || !Array.isArray(report.downloads) || !report.labels) throw new Error("The fill report was incomplete. Scan again before retrying.");
        showReport(report);
      } finally { fillButton.disabled = false; }
    });
    void ask<ReviewState>({ type: "reviewState", tabId }).then(review => {
      for (const el of body.querySelectorAll<HTMLTextAreaElement>("textarea[data-answer-ref]")) {
        const kept = review?.answers?.[el.dataset.answerRef!];
        const origin = review?.answerOrigins?.[el.dataset.answerRef!] ?? "user";
        const suppress = result.questions?.some(q => q.noAi) && origin === "suggestion";
        if (kept && !suppress) el.value = kept;
        el.dataset.origin = suppress ? "user" : origin;
        if (!suppress && review?.answerIds?.[el.dataset.answerRef!]) el.dataset.savedAnswerId = review.answerIds[el.dataset.answerRef!];
        el.addEventListener("input", () => { const answers = Object.fromEntries(Array.from(body.querySelectorAll<HTMLTextAreaElement>("textarea[data-answer-ref]"), item => [item.dataset.answerRef!, item.value])); void ask({ type: "reviewState", tabId, patch: { answers, answerIds: Object.fromEntries(Array.from(body.querySelectorAll<HTMLTextAreaElement>("textarea[data-answer-ref]"), item => [item.dataset.answerRef!, item.dataset.savedAnswerId ?? ""]).filter(([, id]) => id)), answerOrigins: Object.fromEntries(Array.from(body.querySelectorAll<HTMLTextAreaElement>("textarea[data-answer-ref]"), item => [item.dataset.answerRef!, item.dataset.origin === "suggestion" ? "suggestion" as const : "user" as const])) } }).catch(() => undefined); });
      }
    }).catch(() => undefined);
    const questions = result.questions ?? [];
    const fillable = rows.length + questions.length;
    body.replaceChildren(...parts(
      result.draft ? null : h("p", { class: "warn-text" }, "Choose a Draft above to attach its resume and cover letter."),
      result.profileReviewed ? null : h("p", { class: "warn-text" }, "Review your profile to fill your details."),
      rows.length ? h("ul", { class: "fields" }, ...rows) : questions.length ? null : h("p", {}, "Nothing here JobWeaver can fill."),
      questions.length ? questionsBlock(tabId, questions, Boolean(result.draft)) : null,
      result.manual.length ? h("p", { class: "muted" }, `For you to fill: ${result.manual.slice(0, 8).join(", ")}${result.manual.length > 8 ? "…" : ""}`) : null,
      fillable ? h("p", { class: "muted" }, "Filling puts the ticked values into this site's form, which may save them before you submit. JobWeaver never submits.") : null,
      fillable ? h("div", { class: "actions" }, fillButton) : null,
    ));
  }

  function showReport(report: FillResult) {
    scanButton.classList.add("ghost");
    scanButton.textContent = "Scan again";
    const label = (ref: string) => report.labels[ref] ?? "A field";
    const undoButton = button("Undo", async () => {
      undoButton.disabled = true;
      try {
        const undone = await ask<FillReport>({ type: "undo", tabId });
        if (!undone || !Array.isArray(undone.filled) || !Array.isArray(undone.failed)) throw new Error("Undo did not return a report. Check the form before retrying.");
        body.replaceChildren(
          h("p", {}, `Undid ${undone.filled.length} ${undone.filled.length === 1 ? "field" : "fields"}.`),
          ...undone.failed.map((f) => h("p", { class: "muted" }, `${label(f.ref)}: ${f.reason}`)),
        );
      } finally { undoButton.disabled = false; }
    }, "ghost");
    body.replaceChildren(
      h("p", { class: report.filled.length ? "ok" : "warn-text" }, `Filled ${report.filled.length} ${report.filled.length === 1 ? "field" : "fields"}. Check them on the page, then submit yourself.`),
      ...report.failed.map((f) => h("p", { class: "warn-text" }, `${label(f.ref)}: ${f.reason}`)),
      ...report.downloads.map((d) => button(`Download ${d.name} to attach it yourself`, () => download(d.name, d.base64), "ghost")),
      h("div", { class: "actions" }, undoButton),
    );
  }

  return section;
}

const ANSWER_SOURCES: Record<Answer["kind"], string> = {
  saved: "Your saved answer",
  suggestion: "Suggestion from your Facts. Review and rework it in your own words, then tick to use.",
  fact_notes: "Notes from your Facts to write from:",
  none: "",
};

/** The form's own questions: the User writes, or reviews a Saved Answer or Suggestion,
 * and ticks it. Nothing here is filled unticked or unreviewed (ADR-0017). */
function questionsBlock(tabId: number, questions: Question[], hasDraft: boolean): HTMLElement {
  const items = new Map<string, { answer: HTMLTextAreaElement; extra: HTMLElement; box: HTMLInputElement }>();
  const list = h("ul", { class: "fields" }, ...questions.map((q) => {
    const box = h("input", { type: "checkbox", value: q.ref, id: `f-${q.ref}` }) as HTMLInputElement;
    const answer = h("textarea", {
      "data-answer-ref": q.ref,
      rows: "5",
      "aria-label": `Your answer: ${q.label}`,
      ...(q.maxLength ? { maxlength: String(q.maxLength) } : {}),
    }) as HTMLTextAreaElement;
    const extra = h("div");
    items.set(q.ref, { answer, extra, box });
    const save = button("Save this answer", async () => {
      const text = answer.value.trim();
      if (!text) throw new Error("Write or review the answer first.");
      const scope = (save.parentElement!.querySelector("select") as HTMLSelectElement).value as "company" | "country" | "general";
      const saved = await ask<{ id?: string }>({ type: "saveAnswer", tabId, ...(answer.dataset.savedAnswerId ? { answer_id: answer.dataset.savedAnswerId } : {}), question: q.label, answer: text, scope, origin: answer.dataset.origin === "suggestion" ? "suggestion" : "user" });
      if (saved?.id) { answer.dataset.savedAnswerId = saved.id; answer.dispatchEvent(new Event("input")); }
      save.textContent = "Saved";
      save.disabled = true;
    }, "ghost");
    answer.addEventListener("input", () => { save.disabled = false; save.textContent = "Save this answer"; });
    const scope = h("select", { "aria-label": `Reuse for: ${q.label}` },
      h("option", { value: "company" }, "This Company only"),
      h("option", { value: "country" }, "Jobs in this country"),
      h("option", { value: "general" }, "Any job"));
    scope.addEventListener("change", () => { save.disabled = false; save.textContent = "Save this answer"; });
    return h("li", {}, box, h("label", { for: `f-${q.ref}` }, h("span", { class: "title" }, q.label),
      q.sensitive ? h("span", { class: "source" }, "Sensitive: filled only from your saved answers or what you write.") : null),
      answer, extra, h("div", { class: "actions" }, scope, save));
  }));
  const noAi = questions.some((q) => q.noAi);
  const suggest = button(noAi ? "Show notes from my Facts" : "Suggest answers", async () => {
    suggest.disabled = true;
    try {
      const answers = await ask<Answer[]>({ type: "suggestAnswers", tabId });
      for (const a of answers) {
        const item = items.get(a.ref);
        if (!item) continue;
        if (a.saved_answer_id) item.answer.dataset.savedAnswerId = a.saved_answer_id;
        // Never replace what the User already wrote.
        if (a.text && !item.answer.value.trim()) {
          item.answer.value = a.text;
          item.answer.dataset.origin = a.origin === "suggestion" || a.kind === "suggestion" ? "suggestion" : "user";
          item.answer.dispatchEvent(new Event("input"));
        }
        item.extra.replaceChildren(...parts(
          ANSWER_SOURCES[a.kind] ? h("span", { class: "source" }, ANSWER_SOURCES[a.kind]) : null,
          a.kind === "fact_notes" && a.notes.length ? h("ul", { class: "notes" }, ...a.notes.map((n) => h("li", {}, n))) : null,
          a.warning ? h("p", { class: "warn-text" }, a.warning) : null,
        ));
      }
    } finally { suggest.disabled = false; }
  }, "ghost");
  suggest.disabled = !hasDraft;
  return h("div", { class: "questions" }, ...parts(
    h("p", { class: "label" }, `Questions on this form (${questions.length})`),
    noAi ? h("p", { class: "warn-text" }, "This form asks for answers not written by AI. JobWeaver shows your Facts as notes; write the answers yourself.") : null,
    hasDraft ? null : h("p", { class: "muted" }, "Choose a Draft above to get answers for this Job."),
    h("div", { class: "actions" }, suggest),
    list,
  ));
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
  const refresh = () => void renderSafely();
  // Offered only when this site is not yet allowed; a toolbar click also grants this tab.
  const siteAllowed = tab.url && /^https?:/.test(tab.url) && chrome.permissions?.contains
    ? await chrome.permissions.contains({ origins: [`${new URL(tab.url).origin}/*`] }).catch(() => false)
    : false;
  content.replaceChildren(...parts(
    siteAllowed ? null : tab.url && /^https?:/.test(tab.url) ? button(`Allow access to ${new URL(tab.url).hostname}`, async () => {
      const origin = new URL(tab.url!).origin;
      if (!await chrome.permissions.request({ origins: [`${origin}/*`] })) throw new Error("Site access was not granted. Use the toolbar on this tab for temporary access.");
      refresh();
    }, "ghost") : h("p", { class: "warn-text" }, "Click JobWeaver in the toolbar on the application tab to allow access to this page."),
    state.profile?.reviewed && !state.profile.needs_review ? h("p", { class: "muted" }, "Profile ready") : profileSection(state),
    !tab.url || /^https?:/.test(tab.url) ? (state.selected || state.matches.length ? h("details", {}, h("summary", {}, "Read or update the job description"), captureSection(tabId, refresh)) : captureSection(tabId, refresh)) : null,
    state.selected ? selectedSection(tabId, state.selected, refresh, state.needsConfirmation) : state.matches.length ? chooseSection(tabId, state, refresh) : h("details", {}, h("summary", {}, "Choose a saved Draft manually"), chooseSection(tabId, state, refresh)),
    // Browser pages cannot be filled; without activeTab the address is unknown, so offer it.
    (!tab.url || /^https?:/.test(tab.url)) && !state.needsConfirmation ? fillSection(tabId) : null,
  ));
}

connectButton.addEventListener("click", async () => {
  connectButton.disabled = true;
  // The panel stays open and refreshes once the connection is approved on JobWeaver.
  try { await ask({ type: "connect" }); statusText.textContent = "Approve the connection on the JobWeaver tab that opened."; }
  catch (error) { statusText.textContent = error instanceof Error ? error.message : "Connection failed. Try again."; }
  finally { connectButton.disabled = false; }
});

disconnectButton.addEventListener("click", async () => {
  disconnectButton.disabled = true;
  try { await ask({ type: "disconnect" }); await renderSafely(); }
  catch (error) { statusText.textContent = error instanceof Error ? error.message : "Disconnect failed. Try again."; }
  finally { disconnectButton.disabled = false; }
});

void renderSafely();

async function chooseDraft(tabId: number, draftId: string, number?: number) {
  const result = await ask<DraftVersion | null>({ type: "select", tabId, draftId, number });
  if (!result?.draft_id) throw new Error("This Draft could not be selected. It may have been deleted or is still preparing. Try again or choose another Draft.");
  return result;
}

async function renderSafely() {
  try { await render(); } catch (error) {
    statusText.textContent = "JobWeaver could not load.";
    content.replaceChildren(h("p", { role: "alert", class: "warn-text" }, error instanceof Error ? error.message : "Try again."), button("Retry", () => renderSafely()));
  }
}

chrome.tabs.onActivated?.addListener(() => void renderSafely());
chrome.runtime.onMessage?.addListener((message: { type?: string }) => {
  if (message.type === "panelTabChanged") void renderSafely();
});
