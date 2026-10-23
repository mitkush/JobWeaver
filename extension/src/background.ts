/** Service worker: holds the credential and is the only part that calls JobWeaver. */

import { currentConnection, disconnect, handleExternal, startConnect, status, type Deps } from "./connection";

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

chrome.runtime.onMessageExternal.addListener((message, sender, sendResponse) => {
  handleExternal(deps, message, sender)
    .then(sendResponse)
    .catch(() => sendResponse({ ok: false, error: "The extension could not reach JobWeaver." }));
  return true;
});

type PopupMessage = { type: "status" | "connect" | "disconnect" };

chrome.runtime.onMessage.addListener((message: PopupMessage, sender, sendResponse) => {
  // Only the extension's own popup talks to the service worker this way.
  if (sender.id !== chrome.runtime.id || !sender.url?.startsWith(`chrome-extension://${chrome.runtime.id}/`)) {
    return false;
  }
  const run = async () => {
    if (message.type === "connect") await startConnect(deps);
    if (message.type === "disconnect") await disconnect(deps);
    return message.type === "status" ? status(deps) : { connected: Boolean(await currentConnection(deps)) };
  };
  run()
    .then(sendResponse)
    .catch(() => sendResponse({ connected: false, error: "JobWeaver could not be reached." }));
  return true;
});
