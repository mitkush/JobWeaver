/** Service worker: holds the credential and is the only part that calls JobWeaver. */

import { currentConnection, disconnect, handleExternal, startConnect, status, type Deps } from "./connection";
import { savePdfs } from "./downloads";
import { clear, pageState, select } from "./drafts";
import { captured, carryCapture, clearCapture, createCapturedDraft, readPage, savePage } from "./capture";
import type { PageJob } from "./job-read";
import { fillTab, forgetTab, lastFill, scanTab, undoTab, type TabPort } from "./fill/session";

declare const __JOBWEAVER_ORIGIN__: string;

const deps: Deps = {
  origin: __JOBWEAVER_ORIGIN__,
  extensionId: chrome.runtime.id,
  store: {
    async get<T>(key: string) {
      return (await chrome.storage.session.get(key))[key] as T | undefined;
    },
    set: (key, value) => chrome.storage.session.set({ [key]: value }),
    remove: (key) => chrome.storage.session.remove(key),
  },
  fetch: (input, init) => fetch(input, init),
  openTab: async (url) => {
    await chrome.tabs.create({ url });
  },
  now: () => Date.now(),
};

// Session storage stays private to the extension's own pages and service worker.
void chrome.storage.session.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" });

const port: TabPort = {
  async inject(tabId) {
    // Main frame only; embedded forms on other sites come with host permissions later.
    await chrome.scripting.executeScript({ target: { tabId, frameIds: [0] }, files: ["content.js"] });
  },
  send: (tabId, message) => chrome.tabs.sendMessage(tabId, message, { frameId: 0 }),
};

chrome.tabs.onRemoved.addListener((tabId) => {
  void clear(deps, tabId);
  void forgetTab(deps, tabId);
  void clearCapture(deps, tabId);
});
chrome.tabs.onCreated.addListener((tab) => {
  if (tab.id !== undefined && tab.openerTabId !== undefined) void carryCapture(deps, tab.openerTabId, tab.id);
});
// A new page in the tab means a new form: the last scan no longer applies.
chrome.tabs.onUpdated.addListener((tabId, change) => {
  if (change.url) void forgetTab(deps, tabId);
});

chrome.runtime.onMessageExternal.addListener((message, sender, sendResponse) => {
  handleExternal(deps, message, sender)
    .then(sendResponse)
    .catch(() => sendResponse({ ok: false, error: "The extension could not reach JobWeaver." }));
  return true;
});

export type PopupMessage =
  | { type: "status" | "connect" | "disconnect" }
  | { type: "page"; tabId: number; url?: string }
  | { type: "select"; tabId: number; draftId: string; number?: number }
  | { type: "clear"; tabId: number }
  | { type: "readJob" | "capturedJob" | "createCapturedDraft"; tabId: number }
  | { type: "saveJob"; tabId: number; job: PageJob }
  | { type: "savePdfs"; tabId: number }
  | { type: "scan"; tabId: number }
  | { type: "fill"; tabId: number; refs: string[]; answers?: Record<string, string> }
  | { type: "undo"; tabId: number }
  | { type: "lastFill"; tabId: number }
  | { type: "open"; path: string };

async function handle(message: PopupMessage): Promise<unknown> {
  switch (message.type) {
    case "readJob": return readPage(deps, port, message.tabId);
    case "saveJob": return savePage(deps, port, message.tabId, message.job);
    case "capturedJob": return captured(deps, message.tabId);
    case "createCapturedDraft": return createCapturedDraft(deps, message.tabId);
    case "connect":
      await startConnect(deps);
      return { connected: Boolean(await currentConnection(deps)) };
    case "disconnect":
      await disconnect(deps);
      return { connected: false };
    case "status":
      return status(deps);
    case "page":
      return pageState(deps, message.tabId, message.url);
    case "select":
      return select(deps, message.tabId, message.draftId, message.number);
    case "clear":
      await clear(deps, message.tabId);
      return null;
    case "savePdfs":
      if (!await chrome.permissions.contains({ permissions: ["downloads"] })) throw new Error("Allow downloads to save PDFs in a company folder");
      await savePdfs(deps, message.tabId, (filename, url) => chrome.downloads.download({ filename, url, conflictAction: "uniquify", saveAs: false }));
      return { ok: true };
    case "scan":
      return scanTab(deps, port, message.tabId);
    case "fill":
      return fillTab(deps, port, message.tabId, message.refs, message.answers);
    case "undo":
      return undoTab(deps, port, message.tabId);
    case "lastFill":
      return lastFill(deps, message.tabId);
    case "open":
      // Only JobWeaver's own pages; the path never comes from the visited site.
      if (!message.path.startsWith("/") || message.path.startsWith("//")) return null;
      await deps.openTab(new URL(message.path, deps.origin).toString());
      return null;
  }
}

chrome.runtime.onMessage.addListener((message: PopupMessage, sender, sendResponse) => {
  // Only the extension's own popup talks to the service worker this way.
  if (sender.id !== chrome.runtime.id || !sender.url?.startsWith(`chrome-extension://${chrome.runtime.id}/`)) {
    return false;
  }
  handle(message)
    .then(sendResponse)
    .catch((error: unknown) =>
      sendResponse({ connected: false, error: error instanceof Error && /Cannot access|cannot be scripted/i.test(error.message) ? "This page cannot be read or filled (a browser or store page)." : error instanceof Error ? error.message : "JobWeaver could not be reached." }),
    );
  return true;
});
