/** Service worker: holds the credential and is the only part that calls JobWeaver. */

import { currentConnection, disconnect, handleExternal, startConnect, status, type Deps } from "./connection";
import { clear, pageState, select } from "./drafts";

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

chrome.tabs.onRemoved.addListener((tabId) => void clear(deps, tabId));

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
  | { type: "open"; path: string };

async function handle(message: PopupMessage): Promise<unknown> {
  switch (message.type) {
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
    .catch(() => sendResponse({ connected: false, error: "JobWeaver could not be reached." }));
  return true;
});
