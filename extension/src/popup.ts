import type { PopupMessage } from "./background";
import type { DraftSummary, DraftVersion, PageState } from "./drafts";
import type { FillResult, ScanResult } from "./fill/session";
import type { FillReport } from "./fill/types";
import { fromNow } from "./time";

type Status = { connected: false; error?: string } | { connected: true; email: string; expiresAt: string };

const statusText = document.querySelector<HTMLParagraphElement>("#status")!;
const content = document.querySelector<HTMLDivElement>("#content")!;
const connectButton = document.querySelector<HTMLButtonElement>("#connect")!;
const disconnectButton = document.querySelector<HTMLButtonElement>("#disconnect")!;

function ask<T>(message: PopupMessage): Promise<T> {
  return chrome.runtime.sendMessage(message);
}

/** Builds elements with text only: titles and company names come from job adverts. */
function h(tag: string, attrs: Record<string, string> = {}, ...children: (Node | string | null)[]): HTMLElement {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  for (const child of children) if (child !== null) el.append(child);
  return el;
}

function button(label: string, onClick: () => void, variant = ""): HTMLButtonElement {
  const el = h("button", { type: "button", class: variant }, label) as HTMLButtonElement;
  el.addEventListener("click", onClick);
  return el;
}

/** Children for replaceChildren, without the parts a condition left out. */
const parts = (...items: (Node | string | null)[]) => items.filter((i): i is Node | string => i !== null);

const open = (path: string) => void ask({ type: "open", path });

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
        : "This page is not linked to a Draft. Choose one:";
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
  const scanButton = button("Scan this form", () => void runScan());
  section.append(body, h("div", { class: "actions" }, scanButton));
  // Reopened after checking the page: show the last fill with its Undo and downloads.
  void ask<FillResult | null>({ type: "lastFill", tabId }).then((last) => {
    if (last && !body.childElementCount) showReport(last);
  });

  async function runScan() {
    scanButton.disabled = true;
    const result = await ask<ScanResult & { error?: string }>({ type: "scan", tabId });
    scanButton.disabled = false;
    if (result.error || !result.proposals) {
      body.replaceChildren(h("p", { class: "warn-text" }, result.error ?? "This page could not be scanned."));
      return;
    }
    showPreview(result);
  }

  function showPreview(result: ScanResult) {
    const rows = result.proposals.map((p) => {
      const box = h("input", { type: "checkbox", value: p.ref, id: `f-${p.ref}` }) as HTMLInputElement;
      // A field that already holds something is overwritten only when ticked here.
      box.checked = !p.overwrite;
      return h(
        "li",
        {},
        box,
        h(
          "label",
          { for: `f-${p.ref}` },
          h("span", { class: "title" }, p.label),
          h("span", { class: "value" }, p.value),
          h("span", { class: "source" }, p.overwrite ? `${SOURCES[p.source]} - replaces what is there` : SOURCES[p.source]),
        ),
      );
    });
    const fillButton = button("Fill ticked fields", async () => {
      const refs = Array.from(body.querySelectorAll<HTMLInputElement>("input[type=checkbox]:checked"), (b) => b.value);
      fillButton.disabled = true;
      showReport(await ask<FillResult>({ type: "fill", tabId, refs }));
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
