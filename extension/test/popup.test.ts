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
  siteAllowed?: boolean;
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
    permissions: { request: options.permission ?? (async () => true), contains: async () => options.siteAllowed ?? false },
    windows: { getLastFocused: async () => ({ id: 1 }) },
    tabs: { query: async () => [{ id: 42, url: pageJob.url }] },
  });
  await import("../src/popup");
  await vi.waitFor(() => expect(readButton() ?? document.querySelector('[role="alert"]') ?? document.querySelector('#connect:not([hidden])')).toBeTruthy());
  return send;
}

function readButton() {
  return [...document.querySelectorAll("button")].find((b) => b.textContent === "Read this job");
}

beforeEach(() => {
  vi.resetModules();
  document.body.innerHTML = '<p id="status"></p><div id="content"></div><button id="connect" hidden></button><button id="disconnect" hidden></button>';
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
  expect(document.body.textContent).toContain("Continue with this reviewed document");
  expect(document.body.textContent).not.toContain("Scan this form");
});

it("renders a retry action for page-loading errors without presenting empty data", async () => {
  await popup(() => pageJob, { reply: type => type === "page" ? { error: "JobWeaver is unavailable. Try again." } : undefined });
  expect(document.querySelector('[role="alert"]')?.textContent).toContain("unavailable");
  expect([...document.querySelectorAll("button")].some(b => b.textContent === "Retry")).toBe(true);
  expect(document.body.textContent).not.toContain("No ready Drafts");
});

it.each([
  "Your connection expired. Connect again.",
  "JobWeaver revoked the connection. Connect again.",
  "Connect it again to approve the new access.",
])("shows Connect and the disconnected reason: %s", async (reason) => {
  const send = await popup(() => pageJob, { reply: type => type === "status" ? { connected: false, error: reason } : undefined });
  expect(document.querySelector("#status")?.textContent).toBe(reason);
  expect(document.querySelector<HTMLButtonElement>("#connect")!.hidden).toBe(false);
  expect(document.querySelector<HTMLButtonElement>("#disconnect")!.hidden).toBe(true);
  expect(document.querySelector('[role="alert"]')).toBeNull();
  expect(send.mock.calls.some(([m]) => m.type === "page")).toBe(false);
});

const pinned = { draft_id: "d1", job_id: "j1", title: "Engineer", company: "Example", apply_url: null, number: 2, current_version: 2, saved_at: new Date().toISOString(), warnings: 0, template: "standard", resume_file: "Asha_Resume.pdf", cover_letter_file: "Asha_Cover_Letter.pdf", application_status: null };

function buttonNamed(name: string) {
  return [...document.querySelectorAll("button")].find((b) => b.textContent === name);
}

it("marks Applied only after the User confirms they submitted the form", async () => {
  const send = await popup(() => pageJob, { selected: pinned });
  await vi.waitFor(() => expect(buttonNamed("Mark as applied")).toBeTruthy());
  buttonNamed("Mark as applied")!.click();
  await vi.waitFor(() => expect(buttonNamed("Yes, I submitted this application")).toBeTruthy());
  expect(document.body.textContent).toContain("Filling or downloading does not submit it");
  expect(send.mock.calls.some(([m]) => (m as { type: string }).type === "markApplied")).toBe(false);
  buttonNamed("Yes, I submitted this application")!.click();
  await vi.waitFor(() => expect(send.mock.calls.some(([m]) => (m as { type: string }).type === "markApplied")).toBe(true));
});

it("offers site access only when this site is not allowed yet", async () => {
  await popup(() => pageJob, { siteAllowed: true });
  expect(buttonNamed("Allow access to example.com")).toBeUndefined();
  vi.resetModules();
  document.body.innerHTML = '<p id="status"></p><div id="content"></div><button id="connect" hidden></button><button id="disconnect" hidden></button>';
  await popup(() => pageJob, { siteAllowed: false });
  expect(buttonNamed("Allow access to example.com")).toBeTruthy();
});

it("puts suggestions unticked into editable answers and fills only reviewed, ticked text", async () => {
  const questions = [
    { ref: "q1", label: "Why do you want to join us?", sensitive: false, noAi: false },
    { ref: "q2", label: "What is your notice period?", sensitive: true, noAi: false },
  ];
  const send = await popup(() => pageJob, { selected: pinned, reply: type => {
    if (type === "scan") return { proposals: [], questions, manual: [], profileReviewed: true, draft: { title: "Engineer", company: "Example", number: 2 } };
    if (type === "suggestAnswers") return [
      { ref: "q1", kind: "suggestion", text: "At Acme I built the billing API.", notes: [], fact_refs: ["F4"], saved_answer_id: null, warning: "Contains stock phrasing. Rework it in your own words." },
      { ref: "q2", kind: "none", text: "", notes: [], fact_refs: [], saved_answer_id: null, warning: "Answer this yourself, or save an answer in Settings to reuse it." },
    ];
    if (type === "fill") return { filled: ["q1"], failed: [], downloads: [], labels: { q1: "Why do you want to join us?" } };
    if (type === "reviewState") return {};
  } });
  await vi.waitFor(() => expect(buttonNamed("Scan this form")).toBeTruthy());
  buttonNamed("Scan this form")!.click();
  await vi.waitFor(() => expect(buttonNamed("Suggest answers")).toBeTruthy());
  const answer = document.querySelector<HTMLTextAreaElement>('textarea[data-answer-ref="q1"]')!;
  answer.value = "";
  buttonNamed("Suggest answers")!.click();
  await vi.waitFor(() => expect(answer.value).toBe("At Acme I built the billing API."));
  expect(document.body.textContent).toContain("Rework it in your own words");
  expect(document.body.textContent).toContain("Answer this yourself");
  expect(document.querySelector<HTMLInputElement>("#f-q1")!.checked).toBe(false);

  answer.value = "My reworked answer";
  document.querySelector<HTMLInputElement>("#f-q1")!.checked = true;
  buttonNamed("Fill ticked fields")!.click();
  await vi.waitFor(() => expect(send.mock.calls.some(([m]) => (m as { type: string }).type === "fill")).toBe(true));
  const fill = send.mock.calls.map(([m]) => m as { type: string; refs?: string[]; answers?: Record<string, string> }).find(m => m.type === "fill")!;
  expect(fill.refs).toEqual(["q1"]);
  expect(fill.answers?.q1).toBe("My reworked answer");
});

it("offers notes, not suggestions, on a form that refuses AI answers", async () => {
  await popup(() => pageJob, { selected: pinned, reply: type => {
    if (type === "scan") return { proposals: [], questions: [{ ref: "q1", label: "Why us?", sensitive: false, noAi: true }], manual: [], profileReviewed: true, draft: {} };
    if (type === "reviewState") return {};
  } });
  await vi.waitFor(() => expect(buttonNamed("Scan this form")).toBeTruthy());
  buttonNamed("Scan this form")!.click();
  await vi.waitFor(() => expect(buttonNamed("Show notes from my Facts")).toBeTruthy());
  expect(buttonNamed("Suggest answers")).toBeUndefined();
  expect(document.body.textContent).toContain("answers not written by AI");
});
