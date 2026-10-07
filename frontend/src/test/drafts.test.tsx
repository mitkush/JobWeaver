import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Route, Routes } from "react-router-dom";
import { afterEach, expect, it, onTestFinished, vi } from "vitest";

import { DraftPage, DraftWorkspace } from "@/pages/DraftPage";
import type { Draft, Version } from "@/features/drafts/api";

import { json, mockFetch, renderWithApp, expectAccessible } from "./utils";

afterEach(() => vi.unstubAllGlobals());

function makeDraft(): Draft {
  const version: Version = {
    number: 1, source: "generation", warnings: [], message: "", created_at: "2026-10-06T00:00:00Z",
    content: {
      resume: [{ id: "r1", text: "Python", fact_refs: ["F1"], section: "Skills" }],
      cover_letter: [{ id: "c1", text: "Python", fact_refs: ["F1"] }],
      email_subject: "Application for Backend Engineer",
      email_body: [{ id: "e1", text: "Python", fact_refs: ["F1"] }],
    },
    facts: [{ ref: "F1", id: "f1", kind: "skill", group: "", text: "Python", in_base_resume: true },
            { ref: "F2", id: "f2", kind: "skill", group: "", text: "PostgreSQL", in_base_resume: false }],
  };
  return {
    id: "draft-1", job_id: "job-1", state: "ready", progress: "Ready to review", error: null,
    current_version: 1, base_resume: "Python engineer", version,
    job: { title: "Backend Engineer", company: "Acme", name: "Asha", email: "asha@example.com",
           contact_email: "jobs@acme.com", apply_url: "https://example.com/apply" },
    application_status: null, attachment_name: "Asha_Acme_Backend_Engineer.pdf",
  };
}

function setup(initial = makeDraft(), extra: Record<string, (r: Request) => Response | Promise<Response>> = {}) {
  document.cookie = "jw_csrf=t";
  let draft = initial;
  const calls = mockFetch({
    "GET /api/drafts/draft-1": () => json(draft),
    "GET /api/drafts/draft-1/versions": () => json(draft.version ? [draft.version] : []),
    "GET /api/drafts/draft-1/diff": () => json([{ text: "PostgreSQL", kind: "added_from_portfolio", fact_refs: ["F2"], before: ["PostgreSQL"] }]),
    "PUT /api/drafts/draft-1": async (r) => {
      const body = await r.json();
      draft = { ...draft, current_version: 2, version: { ...draft.version!, number: 2, source: "manual", content: body.content } };
      return json(draft);
    },
    "POST /api/drafts/draft-1/chat": () => {
      draft = { ...draft, current_version: 2, version: { ...draft.version!, number: 2, source: "chat", message: "You: Shorten it\n\nDraft Chat: Shortened" } };
      return json(draft);
    },
    "GET /api/drafts/draft-1/email-check": () => json({ recipient: "jobs@acme.com", valid: true, warnings: [] }),
    "POST /api/drafts/draft-1/handoff": () => json({ mode: "gmail", url: "https://mail.google.com/mail/u/asha@example.com/#drafts", attachment_name: draft.attachment_name, message: "Your Gmail draft includes the resume PDF.", application_id: "a1" }),
    "POST /api/drafts/draft-1/applied": () => {
      draft = { ...draft, application_status: "applied" };
      return new Response(null, { status: 204 });
    },
    ...extra,
  });
  renderWithApp(<Routes><Route path="/drafts/:draftId" element={<DraftPage />} /></Routes>, { route: "/drafts/draft-1" });
  return calls;
}

it("shows generation progress without exposing editor actions", async () => {
  setup({ ...makeDraft(), state: "generating", version: null, current_version: 0, progress: "Choosing your experience" });
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Choosing your experience"));
  expect(screen.queryByRole("button", { name: "Save draft" })).not.toBeInTheDocument();
});

it("saves edits locally without triggering Gmail and protects unsaved edits", async () => {
  const calls = setup();
  const user = userEvent.setup();
  const line = await screen.findByLabelText("Draft line 1");
  await user.clear(line);
  await user.type(line, "PYTHON");
  expect(screen.queryByRole("link", { name: "Resume PDF" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Apply chat change" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Save draft" }));
  expect(await screen.findByText("Version 2")).toBeInTheDocument();
  const save = calls.find((r) => r.method === "PUT");
  expect(await save?.json()).toMatchObject({ expected_version: 1, content: { resume: [{ text: "PYTHON" }] } });
  expect(calls.some((r) => r.url.includes("/handoff"))).toBe(false);
});

it("shows the source Fact and the Base Resume diff", async () => {
  setup();
  const user = userEvent.setup();
  await screen.findByLabelText("Draft line 1");
  await user.click(screen.getByText("Tailoring Trace (1 Facts)"));
  expect(screen.getByText(/F1 · skill/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Show diff and versions" }));
  expect(await screen.findByText("Added from portfolio")).toBeInTheDocument();
  await expectAccessible();
});

it("adds a Fact from the Fact Bank with its trace", async () => {
  const calls = setup();
  const user = userEvent.setup();
  await screen.findByLabelText("Draft line 1");
  await user.selectOptions(screen.getByLabelText("Fact to add"), "F2");
  await user.click(screen.getByRole("button", { name: "Add Fact" }));
  expect(screen.getByLabelText("Draft line 2")).toHaveValue("PostgreSQL");
  await user.click(screen.getByRole("button", { name: "Save draft" }));
  await screen.findByText("Version 2");
  const body = await calls.find((r) => r.method === "PUT")?.json();
  expect(body.content.resume[1]).toMatchObject({ text: "PostgreSQL", fact_refs: ["F2"], manual: true });
});

it("creates a chat version and requires confirmation before changing manual edits", async () => {
  const calls = setup();
  const user = userEvent.setup();
  await screen.findByLabelText("Draft Chat message");
  await user.type(screen.getByLabelText("Draft Chat message"), "Shorten it");
  await user.click(screen.getByRole("checkbox", { name: "Allow chat to change my saved manual edits" }));
  await user.click(screen.getByRole("button", { name: "Apply chat change" }));
  const dialog = screen.getByRole("dialog");
  expect(calls.filter((r) => r.url.endsWith("/chat"))).toHaveLength(0);
  await user.click(within(dialog).getByRole("button", { name: "Apply chat change" }));
  await screen.findByText("Version 2");
  expect(await calls.find((r) => r.url.endsWith("/chat"))?.json()).toMatchObject({ expected_version: 1, overwrite_manual: true });
  expect(screen.getByLabelText("Draft Chat message")).toHaveValue("");
});

it("retains the chat request on a refusal", async () => {
  setup(makeDraft(), { "POST /api/drafts/draft-1/chat": () => json({ error: { code: "validation_failed", message: "Add Kubernetes to your Fact Bank first." } }, 422) });
  const user = userEvent.setup();
  await screen.findByLabelText("Draft Chat message");
  await user.type(screen.getByLabelText("Draft Chat message"), "Add Kubernetes");
  await user.click(screen.getByRole("button", { name: "Apply chat change" }));
  expect(await screen.findByText("Add Kubernetes to your Fact Bank first.")).toBeInTheDocument();
  expect(screen.getByLabelText("Draft Chat message")).toHaveValue("Add Kubernetes");
});

it("names recipient and attachment and requires a separate email-warning confirmation", async () => {
  const tab = { opener: undefined, location: { href: "" }, close: vi.fn() };
  vi.stubGlobal("open", vi.fn(() => tab));
  const open = vi.spyOn(window, "open").mockImplementation(() => tab as unknown as Window);
  const calls = setup(makeDraft(), { "GET /api/drafts/draft-1/email-check": () => json({ recipient: "jobs@acme.com", valid: false, warnings: ["No MX record"] }) });
  const user = userEvent.setup();
  await screen.findByLabelText("Draft line 1");
  await user.click(screen.getByRole("button", { name: "Open in Gmail" }));
  const dialog = await screen.findByRole("dialog");
  expect(dialog).toHaveTextContent("jobs@acme.com");
  expect(dialog).toHaveTextContent("Asha_Acme_Backend_Engineer.pdf");
  const confirm = within(dialog).getByRole("button", { name: "Create draft and open Gmail" });
  expect(confirm).toBeDisabled();
  expect(calls.some((r) => r.url.endsWith("/handoff"))).toBe(false);
  await user.click(within(dialog).getByRole("checkbox"));
  await user.click(confirm);
  await waitFor(() => expect(calls.some((r) => r.url.endsWith("/handoff"))).toBe(true));
  expect(await calls.find((r) => r.url.endsWith("/handoff"))?.json()).toMatchObject({ confirm: true, confirm_email_warning: true, recipient: "jobs@acme.com" });
  expect(open).toHaveBeenCalled();
  open.mockRestore();
  await expectAccessible();
});

it("keeps local edits when a newer server version appears", async () => {
  mockFetch({ "GET /api/drafts/draft-1/versions": () => json([makeDraft().version]) });
  function OtherTabUpdate() {
    const [draft, setDraft] = useState(makeDraft());
    return <><DraftWorkspace draft={draft} /><button onClick={() => setDraft({ ...draft, current_version: 2, version: { ...draft.version!, number: 2 } })}>Simulate other tab</button></>;
  }
  renderWithApp(<OtherTabUpdate />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Draft line 1"), " edit");
  await user.click(screen.getByRole("button", { name: "Simulate other tab" }));
  expect(screen.getByLabelText("Draft line 1")).toHaveValue("Python edit");
  await user.click(screen.getByRole("button", { name: "Load latest version" }));
  expect(screen.getByRole("dialog")).toHaveTextContent("Your unsaved edits will be replaced");
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.getByLabelText("Draft line 1")).toHaveValue("Python edit");
});

it("shows apply-link downloads and records Applied after the user's action", async () => {
  setup({ ...makeDraft(), job: { ...makeDraft().job, contact_email: null } });
  const user = userEvent.setup();
  await screen.findByLabelText("Draft line 1");
  expect(screen.getByRole("link", { name: "Open apply link" })).toHaveAttribute("href", "https://example.com/apply");
  expect(screen.queryByRole("button", { name: "Open in Gmail" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Mark as applied" }));
  expect(await screen.findByRole("button", { name: "Applied" })).toBeDisabled();
});

// jsdom has no object URLs; the real ones are restored after each test.
function stubObjectUrls(create: () => string) {
  const original = { create: URL.createObjectURL, revoke: URL.revokeObjectURL };
  URL.createObjectURL = create;
  URL.revokeObjectURL = vi.fn();
  onTestFinished(() => {
    URL.createObjectURL = original.create;
    URL.revokeObjectURL = original.revoke;
  });
}

it("shows why a PDF cannot be made instead of starting a broken download", async () => {
  const message = 'The PDF cannot show "🚀" (U+1F680) in the resume line "Shipped 🚀". Remove or replace that character.';
  setup(makeDraft(), {
    "GET /api/drafts/draft-1/pdf": () => json({ error: { code: "validation_failed", message } }, 422),
  });
  const createObjectURL = vi.fn(() => "blob:pdf");
  stubObjectUrls(createObjectURL);
  const user = userEvent.setup();
  await screen.findByLabelText("Draft line 1");
  await user.click(screen.getByRole("button", { name: "Resume PDF" }));
  expect(await screen.findByText(/The PDF cannot show "🚀"/)).toBeInTheDocument();
  expect(screen.getByText("The PDF was not downloaded")).toBeInTheDocument();
  expect(createObjectURL).not.toHaveBeenCalled();
});

it("saves a PDF under the server's file name", async () => {
  const calls = setup(makeDraft(), {
    "GET /api/drafts/draft-1/pdf": () =>
      new Response("%PDF-1.7", {
        headers: { "Content-Type": "application/pdf", "Content-Disposition": "attachment; filename*=UTF-8''Asha_Acme_Backend_Engineer_Cover_Letter.pdf" },
      }),
  });
  const createObjectURL = vi.fn(() => "blob:pdf");
  stubObjectUrls(createObjectURL);
  const clicked: string[] = [];
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    clicked.push(this.download);
  });
  const user = userEvent.setup();
  await screen.findByLabelText("Draft line 1");
  await user.click(screen.getByRole("button", { name: "Cover Letter PDF" }));
  await waitFor(() => expect(clicked).toEqual(["Asha_Acme_Backend_Engineer_Cover_Letter.pdf"]));
  expect(calls.some((c) => new URL(c.url).searchParams.get("kind") === "cover_letter")).toBe(true);
  expect(screen.queryByText("The PDF was not downloaded")).not.toBeInTheDocument();
  click.mockRestore();
});
