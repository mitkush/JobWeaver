/** Service worker: holds the credential and is the only part that calls JobWeaver. */

import { currentConnection, disconnect, handleExternal, startConnect, status, type Deps } from "./connection";
import { savePdfs } from "./downloads";
import { currentSelection, clear, pageState, select, requireConfirmation } from "./drafts";
import { captured, carryCapture, clearCapture, createCapturedDraft, readPage, savePage } from "./capture";
import { reviewState } from "./review-state";
import { apiFetch } from "./connection";
import type { PageJob } from "./job-read";
import { fillTab, forgetTab, lastFill, scanTab, undoTab, lastScan, forgetScan, type TabPort } from "./fill/session";

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


// Toolbar activation grants activeTab for this tab; the panel itself grants nothing.
chrome.action?.onClicked.addListener(async (tab) => {
  if (tab.id === undefined) return;
  if (chrome.sidePanel?.open) {
    await chrome.sidePanel.open({ tabId: tab.id });
    void chrome.runtime.sendMessage({ type: "panelTabChanged" }).catch(() => undefined);
  } else {
    await chrome.windows.create({ url: chrome.runtime.getURL("popup.html"), type: "popup", width: 440, height: 720 });
  }
});

const port: TabPort = {
  async frames(tabId) {
    if (!await chrome.permissions.contains({ permissions: ["webNavigation"] })) return [{ frameId: 0 }];
    return (await chrome.webNavigation.getAllFrames({ tabId }) ?? []).filter(frame => frame.frameId === 0 || /^https?:/.test(frame.url));
  },
  async inject(tabId, frameId = 0) {
    // Main frame only; embedded forms on other sites come with host permissions later.
    await chrome.scripting.executeScript({ target: { tabId, frameIds: [frameId] }, files: ["content.js"] });
  },
  send: (tabId, message, frameId = 0) => chrome.tabs.sendMessage(tabId, message, { frameId }),
};

chrome.tabs.onRemoved.addListener((tabId) => {
  void clear(deps, tabId);
  void forgetTab(deps, tabId);
  void clearCapture(deps, tabId);
});
chrome.tabs.onCreated.addListener((tab) => {
  if (tab.id !== undefined && tab.openerTabId !== undefined) void carryCapture(deps, tab.openerTabId, tab.id);
});
// Cross-origin navigation can hide change.url when activeTab is revoked. Loading
// still invalidates the prepared form and requires confirming a retained Draft.
chrome.tabs.onUpdated.addListener((tabId, change) => {
  if (change.url || change.status === "loading") void (async () => {
    await requireConfirmation(deps, tabId);
    await forgetTab(deps, tabId);
  })();
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
  | { type: "lastFill" | "lastScan" | "frameSites" | "markApplied"; tabId: number }
  | { type: "reviewState"; tabId: number; patch?: { capture?: PageJob | null; answers?: Record<string, string> } }
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
    case "select": {
      const chosen = await select(deps, message.tabId, message.draftId, message.number);
      if (chosen) await forgetScan(deps, message.tabId);
      return chosen;
    }
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
    case "reviewState": {
      const tab = await chrome.tabs.get(message.tabId);
      const selection = await currentSelection(deps, message.tabId);
      return reviewState(deps, message.tabId, tab.url, selection, message.patch);
    }
    case "lastScan": return lastScan(deps, message.tabId);
    case "frameSites": {
      if (!await chrome.permissions.contains({ permissions: ["webNavigation"] })) return [];
      const frames = await chrome.webNavigation.getAllFrames({ tabId: message.tabId });
      return [...new Set((frames ?? []).filter(f => f.frameId !== 0 && /^https?:/.test(f.url)).map(f => new URL(f.url).origin))];
    }
    case "markApplied": {
      const selected = await currentSelection(deps, message.tabId);
      if (!selected) throw new Error("Choose the document you used before marking Applied");
      const response = await apiFetch(deps, `/api/ext/drafts/${encodeURIComponent(selected.draftId)}/applied`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_version: selected.number }) });
      if (!response?.ok) throw new Error("Applied could not be recorded. Reconnect or retry.");
      return { ok: true };
    }
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
