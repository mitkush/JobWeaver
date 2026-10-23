/** Injected into the tab only when the User asks to scan it (activeTab). Talks only to
 * this extension; reads and writes form fields; never submits. */

import { adapterFor, scanFields } from "./fill/fields";
import { Filler } from "./fill/apply";
import type { FillItem, Scan } from "./fill/types";
import { readJob } from "./job-read";

type Message = { type: "jw.scan" | "jw.read-job" | "jw.page-url" } | { type: "jw.fill"; scanId: string; items: FillItem[] } | { type: "jw.undo" };

declare global {
  interface Window {
    __jobweaver?: boolean;
  }
}

if (!window.__jobweaver) {
  window.__jobweaver = true;
  const filler = new Filler(document);
  let scan: { id: string; url: string } | null = null;
  let counter = 0;

  chrome.runtime.onMessage.addListener((message: Message, sender, sendResponse) => {
    if (sender.id !== chrome.runtime.id) return false;
    if (message.type === "jw.read-job") {
      try { sendResponse(readJob(document, location.href, window.getSelection()?.toString() ?? "")); }
      catch (error) { sendResponse({ error: (error as Error).message }); }
    } else if (message.type === "jw.page-url") {
      sendResponse({ url: location.href });
    } else if (message.type === "jw.scan") {
      const id = crypto.randomUUID();
      scan = { id, url: location.href };
      const adapter = adapterFor(new URL(location.href));
      const fields = scanFields(document, adapter, () => `jw-${++counter}`);
      sendResponse({ scanId: id, url: location.href, adapter: adapter.name, fields } satisfies Scan);
    } else if (message.type === "jw.fill") {
      // A fill prepared for another page, or an earlier scan, is refused: scan again.
      if (!scan || scan.id !== message.scanId || scan.url !== location.href) {
        sendResponse({ filled: [], failed: message.items.map((i) => ({ ref: i.ref, reason: "The page changed. Scan it again." })) });
      } else {
        sendResponse(filler.fill(message.items));
      }
    } else if (message.type === "jw.undo") {
      sendResponse(filler.undo());
    }
    return false;
  });
}
