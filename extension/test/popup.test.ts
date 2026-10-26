// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const pageJob = { title: "Rails engineer", company: "Example", description: "Build Rails APIs. ".repeat(10), url: "https://example.com/jobs/42", method: "page text", truncated: false };

async function popup(read: () => unknown, options: {
  selected?: Record<string, unknown>;
  permission?: () => Promise<boolean>;
  saveResult?: { error?: string; ok?: boolean };
} = {}) {
  const send = vi.fn(async (message: { type: string }) => {
    if (message.type === "status") return { connected: true, email: "test@example.com" };
    if (message.type === "page") return { profile: { reviewed: true, needs_review: false, version: 1 }, matches: [], recent: [], selected: options.selected ?? null };
    if (message.type === "readJob") return read();
    if (message.type === "savePdfs") return options.saveResult ?? { ok: true };
    return null;
  });
  vi.stubGlobal("chrome", {
    runtime: { sendMessage: send },
    permissions: { request: options.permission ?? (async () => true) },
    windows: { getLastFocused: async () => ({ id: 1 }) },
    tabs: { query: async () => [{ id: 42, url: pageJob.url }] },
  });
  await import("../src/popup");
  await vi.waitFor(() => expect(readButton()).toBeDefined());
  return send;
}

function readButton() {
  return [...document.querySelectorAll("button")].find((b) => b.textContent === "Read this job");
}

beforeEach(() => {
  vi.resetModules();
  document.body.innerHTML = '<p id="status"></p><div id="content"></div><button id="connect"></button><button id="disconnect"></button>';
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

it("shows the editable JD after clicking Read", async () => {
  await popup(() => pageJob);
  readButton()!.click();
  await vi.waitFor(() => expect(document.querySelector<HTMLInputElement>("#capture-title")?.value).toBe(pageJob.title));
  expect(document.querySelector<HTMLTextAreaElement>("#capture-description")?.value).toBe(pageJob.description);
});

it("explains an empty reply from an old worker instead of failing silently", async () => {
  await popup(() => undefined);
  readButton()!.click();
  await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toMatch(/reload/i));
  expect(readButton()?.disabled).toBe(false);
});

it("rejects an incomplete response instead of opening a broken review editor", async () => {
  await popup(() => ({ title: "A job" }));
  readButton()!.click();
  await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toMatch(/incomplete response/i));
  expect(document.querySelector("#capture-description")).toBeNull();
});

it("shows a transport failure and allows retry", async () => {
  let fail = true;
  await popup(() => { if (fail) throw new Error("Extension context invalidated."); return pageJob; });
  readButton()!.click();
  await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toMatch(/reload/i));
  fail = false;
  readButton()!.click();
  await vi.waitFor(() => expect(document.querySelector("#capture-description")).not.toBeNull());
});

it("shows progress then a timeout if the worker never answers", async () => {
  await popup(() => new Promise(() => {}));
  vi.useFakeTimers();
  readButton()!.click();
  await vi.advanceTimersByTimeAsync(0);
  expect(document.body.textContent).toMatch(/reading/i);
  await vi.advanceTimersByTimeAsync(16_000);
  expect(document.querySelector('[role="alert"]')?.textContent).toMatch(/timed out|reload/i);
  expect(readButton()?.disabled).toBe(false);
});

const selectedDraft = {
  draft_id: "d1", job_id: "j1", title: "Engineer", company: "Example",
  number: 1, current_version: 1, saved_at: "2026-10-26T00:00:00Z", warnings: 0,
  resume_file: "Asha_Resume.pdf", cover_letter_file: "Asha_Cover_Letter.pdf",
};

it("shows declined Downloads permission and lets the User retry", async () => {
  let granted = false;
  const send = await popup(() => pageJob, { selected: selectedDraft, permission: async () => granted });
  const save = [...document.querySelectorAll("button")].find((b) => b.textContent === "Save PDFs in company folder")!;
  save.click();
  await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toBe("Downloads permission was not granted"));
  expect(send.mock.calls.some(([m]) => m.type === "savePdfs")).toBe(false);
  granted = true;
  save.click();
  await vi.waitFor(() => expect(send.mock.calls.some(([m]) => m.type === "savePdfs")).toBe(true));
  expect(document.querySelector('[role="alert"]')).toBeNull();
});

it("shows PDF failures returned by the service worker in the popup", async () => {
  await popup(() => pageJob, { selected: selectedDraft, saveResult: { error: "JobWeaver could not make the PDF" } });
  [...document.querySelectorAll("button")].find((b) => b.textContent === "Save PDFs in company folder")!.click();
  await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toBe("JobWeaver could not make the PDF"));
});

it("shows rejected permission requests in the popup", async () => {
  await popup(() => pageJob, { selected: selectedDraft, permission: async () => { throw new Error("Permission request failed"); } });
  [...document.querySelectorAll("button")].find((b) => b.textContent === "Save PDFs in company folder")!.click();
  await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toBe("Permission request failed"));
});
