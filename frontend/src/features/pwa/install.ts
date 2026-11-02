import { useSyncExternalStore } from "react";

type InstallPrompt = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};
let pending: InstallPrompt | null = null;
let installed = false;
let registered = false;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach(listener => listener());

/** Register before React mounts: browsers can offer installation before Settings opens. */
export function registerInstallPrompt() {
  if (registered) return;
  registered = true;
  installed = window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true;
  window.addEventListener("beforeinstallprompt", event => {
    event.preventDefault();
    pending = event as InstallPrompt;
    notify();
  });
  window.addEventListener("appinstalled", () => {
    installed = true;
    pending = null;
    notify();
  });
}
const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
};
const snapshot = () => installed ? "installed" : pending ? "ready" : "manual";
export function useInstallStatus() {
  return useSyncExternalStore(subscribe, snapshot);
}
export async function installApp() {
  const prompt = pending;
  if (!prompt) return;
  try {
    await prompt.prompt();
    return (await prompt.userChoice).outcome;
  } finally {
    // Each event can be used once. A dismissed prompt may be offered again by the browser.
    pending = null;
    notify();
  }
}
