/** Hands a one-time connection code to the JobWeaver extension (ADR-0017). Chrome only
 * exposes `chrome.runtime.sendMessage` to pages listed in the extension's
 * `externally_connectable`, so this fails cleanly anywhere else. */

type ExtensionReply = { ok: true; email: string } | { ok: false; error: string };

type ChromeRuntime = {
  sendMessage: (extensionId: string, message: unknown, callback: (reply: unknown) => void) => void;
  lastError?: { message?: string };
};

function runtime(): ChromeRuntime | undefined {
  return (globalThis as { chrome?: { runtime?: ChromeRuntime } }).chrome?.runtime;
}

export function extensionReachable(): boolean {
  return typeof runtime()?.sendMessage === "function";
}

export function sendCodeToExtension(extensionId: string, code: string, timeoutMs = 15_000): Promise<ExtensionReply> {
  const chromeRuntime = runtime();
  if (!chromeRuntime?.sendMessage) {
    return Promise.resolve({ ok: false, error: "Open this page from the JobWeaver extension in Chrome or Brave." });
  }
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve({ ok: false, error: "The extension did not answer. Try again." }), timeoutMs);
    chromeRuntime.sendMessage(extensionId, { type: "jobweaver.connect", code }, (reply) => {
      clearTimeout(timer);
      if (chromeRuntime.lastError || !reply || typeof reply !== "object") {
        resolve({ ok: false, error: "The JobWeaver extension is not installed or not enabled." });
        return;
      }
      const value = reply as Partial<{ ok: boolean; email: string; error: string }>;
      resolve(
        value.ok && typeof value.email === "string"
          ? { ok: true, email: value.email }
          : { ok: false, error: value.error ?? "The extension could not connect. Try again." },
      );
    });
  });
}
