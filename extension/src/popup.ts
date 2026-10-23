import type { PopupMessage } from "./background";
import type { DraftSummary, DraftVersion, PageState } from "./drafts";
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

const open = (path: string) => void ask({ type: "open", path });

async function activeTab(): Promise<chrome.tabs.Tab | undefined> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
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
  content.replaceChildren(
    profileSection(state),
    state.selected ? selectedSection(tabId, state.selected, refresh) : chooseSection(tabId, state, refresh),
  );
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
