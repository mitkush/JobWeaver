// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const pageJob = { title: "Rails engineer", company: "Example", description: "Build Rails APIs. ".repeat(10), url: "https://example.com/jobs/42", method: "page text", truncated: false };

async function popup(read: () => unknown, options: {
  selected?: Record<string, unknown>;
  permission?: () => Promise<boolean>;
  reply?: (type: string) => unknown;
  needsConfirmation?: boolean;
  recent?: unknown[];
  saveResult?: { error?: string; ok?: boolean };
} = {}) {
  const send = vi.fn(async (message: { type: string }) => {
    const override = options.reply?.(message.type);
    if (override !== undefined) return override;
    if (message.type === "status") return { connected: true, email: "test@example.com" };
    if (message.type === "page") return { profile: { reviewed: true, needs_review: false, version: 1 }, matches: [], recent: options.recent ?? [], selected: options.selected ?? null, needsConfirmation: options.needsConfirmation ?? false };
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
  await vi.waitFor(() => expect(readButton() ?? document.querySelector('[role="alert"]')).toBeTruthy());
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

it("shows a failed Draft selection instead of silently refreshing", async () => {
  await popup(() => pageJob, { recent: [{ ...selectedDraft, current_version: 1 }], reply: type => type === "select" ? null : undefined });
  [...document.querySelectorAll("button")].find(b => b.textContent === "Use this Draft")!.click();
  await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toMatch(/could not be selected/));
});
it("shows the provider error and reenables Fill and Undo after failed replies", async () => {
  let failedFill = true;
  const report = { filled: ["r1"], failed: [], downloads: [], labels: { r1: "Name" } };
  await popup(() => pageJob, { selected: selectedDraft, reply: type => {
    if (type === "scan") return { proposals: [{ ref: "r1", label: "Name", value: "Asha", source: "profile" }], manual: [], profileReviewed: true, draft: {} };
    if (type === "fill") return failedFill ? { error: "The form changed. Scan again." } : report;
    if (type === "undo") return { error: "The page disconnected. Try again." };
  } });
  [...document.querySelectorAll("button")].find(b => b.textContent === "Scan this form")!.click();
  await vi.waitFor(() => expect([...document.querySelectorAll("button")].some(b => b.textContent === "Fill ticked fields")).toBe(true));
  const fill = [...document.querySelectorAll("button")].find(b => b.textContent === "Fill ticked fields")!;
  fill.click();
  await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toBe("The form changed. Scan again."));
  expect(fill.disabled).toBe(false);
  failedFill = false; fill.click();
  await vi.waitFor(() => expect([...document.querySelectorAll("button")].some(b => b.textContent === "Undo")).toBe(true));
  const undo = [...document.querySelectorAll("button")].find(b => b.textContent === "Undo")!;
  undo.click();
  await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toBe("The page disconnected. Try again."));
  expect(undo.disabled).toBe(false);
});
it("does not offer scanning until a retained Draft is confirmed on the new page", async () => {
  await popup(() => pageJob, { selected: selectedDraft, needsConfirmation: true });
  expect(document.body.textContent).toContain("Use this Draft on this page");
  expect(document.body.textContent).not.toContain("Scan this form");
});

it("renders a retry action for page-loading errors without presenting empty data", async () => {
  await popup(() => pageJob, { reply: type => type === "page" ? { error: "JobWeaver is unavailable. Try again." } : undefined });
  expect(document.querySelector('[role="alert"]')?.textContent).toContain("unavailable");
  expect([...document.querySelectorAll("button")].some(b => b.textContent === "Retry")).toBe(true);
  expect(document.body.textContent).not.toContain("No ready Drafts");
});
