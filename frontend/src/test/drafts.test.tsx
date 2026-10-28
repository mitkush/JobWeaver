import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Route, Routes, useNavigate } from "react-router-dom";
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

/** The workspace opens on a readable preview; editing a section opens its editor. */
async function editSection(user: ReturnType<typeof userEvent.setup>, section = "Skills") {
  await user.click(await screen.findByRole("button", { name: `Edit ${section}` }));
  return screen.findByLabelText("Draft line 1");
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
    "GET /api/drafts/draft-1/proposals": () => json([]),
    "GET /api/drafts/draft-1/email-check": () => json({ recipient: "jobs@acme.com", valid: true, warnings: [] }),
    "POST /api/drafts/draft-1/handoff": () => json({ mode: "gmail", url: "https://mail.google.com/mail/u/asha@example.com/#drafts", attachment_name: draft.attachment_name, message: "Your Gmail draft includes the resume PDF.", application_id: "a1" }),
    "POST /api/drafts/draft-1/applied": () => {
      draft = { ...draft, application_status: "applied" };
      return new Response(null, { status: 204 });
    },
    ...extra,
  });
  renderWithApp(<Routes><Route path="/drafts/:draftId" element={<DraftPage />} /><Route path="/jobs/:jobId" element={<h1>Job destination</h1>} /></Routes>, { route: "/drafts/draft-1" });
  return calls;
}

it("shows generation progress without exposing editor actions", async () => {
  setup({ ...makeDraft(), state: "generating", version: null, current_version: 0, progress: "Choosing your experience" });
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Choosing your experience"));
  expect(screen.queryByRole("button", { name: "Save now" })).not.toBeInTheDocument();
});

it("saves edits locally without triggering Gmail and protects unsaved edits", async () => {
  const calls = setup();
  const user = userEvent.setup();
  const line = await editSection(user);
  await user.clear(line);
  await user.type(line, "PYTHON");
  expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  // Editing a section scopes the replacement to that section; unsaved edits block it.
  expect(screen.getByRole("button", { name: "Prepare Skills changes" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Save now" }));
  expect(await screen.findByText("Saved")).toBeInTheDocument();
  const save = calls.find((r) => r.method === "PUT");
  expect(await save?.json()).toMatchObject({ expected_version: 1, content: { resume: [{ text: "PYTHON" }] } });
  expect(calls.some((r) => r.url.includes("/handoff"))).toBe(false);
});

it("offers a confirmed Fact Bank recheck and updates the warning", async () => {
  const draft = makeDraft();
  draft.version!.warnings = ['Your edit in the resume: "senior" is not stated in the Facts it cites'];
  const calls = setup(draft, {
    "POST /api/drafts/draft-1/recheck": () => {
      draft.current_version = 2;
      draft.version = { ...draft.version!, number: 2, source: "recheck", warnings: [] };
      return json(draft);
    },
  });
  const user = userEvent.setup();
  await screen.findByText(/"senior" is not stated/);
  expect(screen.getByRole("link", { name: "Open Fact Bank" })).toHaveAttribute("href", "/fact-bank");
  await user.click(screen.getByRole("button", { name: "Recheck latest Facts" }));
  expect(screen.getByRole("dialog")).toHaveTextContent("AI-written lines that no longer have supporting Facts may be removed");
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Recheck draft" }));
  await waitFor(() => expect(screen.queryByText(/"senior" is not stated/)).not.toBeInTheDocument());
  const request = calls.find((call) => call.url.endsWith("/recheck"));
  expect(await request?.json()).toEqual({ expected_version: 1 });
});

it("lets a user cite another Fact for an edited line", async () => {
  const draft = makeDraft();
  draft.version!.warnings = ['Your edit in the resume: "senior" is not stated in the Facts it cites'];
  const calls = setup(draft);
  const user = userEvent.setup();
  await editSection(user);
  await user.click(screen.getByText("Tailoring Trace (1 Facts)"));
  await user.click(screen.getByRole("button", { name: "Cite Fact" }));
  expect(screen.getByRole("button", { name: "Recheck latest Facts" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Save now" }));
  const request = calls.find((call) => call.method === "PUT");
  expect(await request?.json()).toMatchObject({ content: { resume: [{ fact_refs: ["F1", "F2"] }] } });
});

it("shows the source Fact and the Base Resume diff", async () => {
  setup();
  const user = userEvent.setup();
  await editSection(user);
  await user.click(screen.getByText("Tailoring Trace (1 Facts)"));
  expect(screen.getByText(/F1 · skill/)).toBeInTheDocument();
  await user.click(screen.getByText("Compare with your Base Resume"));
  expect(await screen.findByText("Added from portfolio")).toBeInTheDocument();
  await expectAccessible();
});

it("adds a Fact from the Fact Bank with its trace", async () => {
  const calls = setup();
  const user = userEvent.setup();
  await editSection(user);
  await user.selectOptions(screen.getByLabelText("Fact to add"), "F2");
  await user.click(screen.getByRole("button", { name: "Add Fact" }));
  expect(screen.getByLabelText("Draft line 2")).toHaveValue("PostgreSQL");
  await user.click(screen.getByRole("button", { name: "Save now" }));
  await screen.findByText("Saved");
  const body = await calls.find((r) => r.method === "PUT")?.json();
  expect(body.content.resume[1]).toMatchObject({ text: "PostgreSQL", fact_refs: ["F2"], manual: true });
});

it("marks an Experience line as a role title line", async () => {
  const calls = setup();
  const user = userEvent.setup();
  await editSection(user);
  expect(screen.getByLabelText("Title line")).not.toBeChecked();
  await user.selectOptions(screen.getByLabelText("Section for line 1"), "Experience");
  // The line moves to its new section, which is edited separately.
  await user.click(screen.getByRole("button", { name: "Done editing" }));
  await editSection(user, "Experience");
  await user.click(screen.getByLabelText("Title line"));
  await user.click(screen.getByRole("button", { name: "Save now" }));
  await screen.findByText("Saved");
  const body = await calls.find((r) => r.method === "PUT")?.json();
  expect(body.content.resume[0]).toMatchObject({ section: "Experience", heading: true });
});

it("marks a Skills line as a title line", async () => {
  const calls = setup();
  const user = userEvent.setup();
  await editSection(user);
  await user.click(screen.getByLabelText("Title line"));
  await user.click(screen.getByRole("button", { name: "Save now" }));
  await screen.findByText("Saved");
  const body = await calls.find((r) => r.method === "PUT")?.json();
  expect(body.content.resume[0]).toMatchObject({ section: "Skills", heading: true });
});

it("edits the email greeting name with the subject", async () => {
  const calls = setup();
  const user = userEvent.setup();
  await user.click(await screen.findByRole("tab", { name: "Application Email" }));
  await user.type(screen.getByLabelText("Greeting name (blank: Hiring Team)"), "Sapna");
  await user.click(screen.getByRole("button", { name: "Save now" }));
  await screen.findByText("Saved");
  const body = await calls.find((r) => r.method === "PUT")?.json();
  expect(body.content).toMatchObject({ email_greeting: "Sapna", email_subject: "Application for Backend Engineer" });
});

it("prepares a replacement in the background and changes nothing until it is accepted", async () => {
  const draft = makeDraft();
  let proposals: unknown[] = [];
  const proposal = {
    id: "p1", base_version: 1, part: "resume", section: null, state: "ready", progress: "Review this replacement", error: null, warnings: [],
    content: { ...draft.version!.content, resume: [{ id: "r1", text: "Python and PostgreSQL", fact_refs: ["F1", "F2"], section: "Skills" }] },
  };
  const calls = setup(draft, {
    "GET /api/drafts/draft-1/proposals": () => json(proposals),
    "POST /api/drafts/draft-1/proposals": () => { proposals = [proposal]; return json(proposal, 202); },
    "POST /api/drafts/draft-1/proposals/p1/accept": () => {
      proposals = [];
      return json({ ...draft, current_version: 2, version: { ...draft.version!, number: 2, source: "replacement", content: proposal.content } });
    },
  });
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Instructions for replacement"), "Lead with PostgreSQL");
  await user.click(screen.getByRole("button", { name: "Prepare replacement resume" }));
  expect(await screen.findByText("Review this replacement")).toBeInTheDocument();
  expect(await calls.find((r) => r.method === "POST" && r.url.endsWith("/proposals"))?.json()).toMatchObject({ expected_version: 1, part: "resume", instruction: "Lead with PostgreSQL" });
  // The accepted document is unchanged while the replacement waits for review.
  expect(screen.getByRole("article", { name: "Readable document preview" })).toHaveTextContent(/^SkillsEdit SkillsPython$/);
  await user.click(screen.getByRole("button", { name: "Use this replacement" }));
  await waitFor(() => expect(screen.getByRole("article", { name: "Readable document preview" })).toHaveTextContent("Python and PostgreSQL"));
  expect(await calls.find((r) => r.url.endsWith("/accept"))?.json()).toEqual({ expected_version: 1 });
  expect(screen.getByRole("button", { name: "Undo replacement" })).toBeInTheDocument();
});

it("keeps the current document when the User declines a replacement", async () => {
  const draft = makeDraft();
  let proposals: unknown[] = [{ id: "p1", base_version: 1, part: "resume", section: null, state: "ready", progress: "Review this replacement", error: null, warnings: [], content: draft.version!.content }];
  const calls = setup(draft, {
    "GET /api/drafts/draft-1/proposals": () => json(proposals),
    "DELETE /api/drafts/draft-1/proposals/p1": () => { proposals = []; return new Response(null, { status: 204 }); },
  });
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Keep current" }));
  await waitFor(() => expect(calls.some((r) => r.method === "DELETE")).toBe(true));
  expect(await screen.findByLabelText("Instructions for replacement")).toBeInTheDocument();
  expect(calls.some((r) => r.url.endsWith("/accept"))).toBe(false);
});

it("shows a failed replacement without touching the current document", async () => {
  setup(makeDraft(), {
    "GET /api/drafts/draft-1/proposals": () => json([{ id: "p1", base_version: 1, part: "resume", section: null, state: "failed", progress: "Generation stopped", error: "The replacement could not be prepared. Your current document is unchanged.", warnings: [], content: null }]),
  });
  expect(await screen.findByText(/current document is unchanged/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Use this replacement" })).not.toBeInTheDocument();
  expect(screen.getByRole("article", { name: "Readable document preview" })).toHaveTextContent("Python");
});

it("saves edits automatically after a pause", async () => {
  const calls = setup();
  const user = userEvent.setup();
  await user.type(await editSection(user), " and SQL");
  expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  await waitFor(() => expect(calls.some((r) => r.method === "PUT")).toBe(true), { timeout: 3000 });
  expect((await calls.find((r) => r.method === "PUT")!.json()).content.resume[0].text).toBe("Python and SQL");
  expect(await screen.findByText("Saved")).toBeInTheDocument();
});

it("names recipient and attachment and requires a separate email-warning confirmation", async () => {
  const tab = { opener: undefined, location: { href: "" }, close: vi.fn() };
  vi.stubGlobal("open", vi.fn(() => tab));
  const open = vi.spyOn(window, "open").mockImplementation(() => tab as unknown as Window);
  const calls = setup(makeDraft(), { "GET /api/drafts/draft-1/email-check": () => json({ recipient: "jobs@acme.com", valid: false, warnings: ["No MX record"] }) });
  const user = userEvent.setup();
  await editSection(user);
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
  await user.type(await editSection(user), " edit");
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
  await editSection(user);
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
  await editSection(user);
  await user.click(screen.getByRole("button", { name: "Download Resume PDF" }));
  expect(await screen.findByText(/The PDF cannot show "🚀"/)).toBeInTheDocument();
  expect(screen.getByText("The PDF could not be made")).toBeInTheDocument();
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
  await editSection(user);
  await user.click(screen.getByRole("button", { name: "Download Cover Letter PDF" }));
  await waitFor(() => expect(clicked).toEqual(["Asha_Acme_Backend_Engineer_Cover_Letter.pdf"]));
  expect(calls.some((c) => new URL(c.url).searchParams.get("kind") === "cover_letter")).toBe(true);
  expect(screen.queryByText("The PDF could not be made")).not.toBeInTheDocument();
  click.mockRestore();
});

it("previews the exact PDF in the page and downloads it from the preview", async () => {
  const calls = setup(makeDraft(), {
    "GET /api/drafts/draft-1/pdf": () =>
      new Response("%PDF-1.7", {
        headers: { "Content-Type": "application/pdf", "Content-Disposition": "attachment; filename*=UTF-8''Asha_Acme_Backend_Engineer.pdf" },
      }),
  });
  stubObjectUrls(() => "blob:resume-preview");
  const clicked: string[] = [];
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    clicked.push(this.download);
  });
  const user = userEvent.setup();
  await editSection(user);
  await user.selectOptions(screen.getByLabelText("PDF layout"), "compact");
  await user.click(screen.getByRole("button", { name: "Preview Resume" }));
  const dialog = await screen.findByRole("dialog", { name: "Resume preview · Compact" });
  expect(within(dialog).getByTitle("Resume preview · Compact")).toHaveAttribute("src", "blob:resume-preview");
  expect(within(dialog).getByRole("link", { name: "Open in new tab" })).toHaveAttribute("href", "blob:resume-preview");
  const pdfCall = calls.find((c) => new URL(c.url).pathname.endsWith("/pdf"))!;
  expect(new URL(pdfCall.url).searchParams.get("template")).toBe("compact");
  // Downloading from the preview saves the same file without asking the server again.
  await user.click(within(dialog).getByRole("button", { name: "Download" }));
  expect(clicked).toEqual(["Asha_Acme_Backend_Engineer.pdf"]);
  expect(calls.filter((c) => new URL(c.url).pathname.endsWith("/pdf"))).toHaveLength(1);
  await user.click(within(dialog).getByRole("button", { name: "Close preview" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  click.mockRestore();
});

it("archives the package after confirmation and keeps it for the application history", async () => {
  const calls = setup(makeDraft(), { "DELETE /api/drafts/draft-1": () => new Response(null, { status: 204 }) });
  const user = userEvent.setup();
  await user.click(await screen.findByText("More actions"));
  await user.click(screen.getByRole("button", { name: "Archive Draft" }));
  expect(screen.getByRole("dialog")).toHaveTextContent("application history and document snapshots are kept");
  expect(calls.some((r) => r.method === "DELETE")).toBe(false);
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Archive Draft" }));
  await waitFor(() => expect(calls.some((r) => r.method === "DELETE" && new URL(r.url).searchParams.get("expected_version") === "1")).toBe(true));
});

it("shows an archived package read-only", async () => {
  setup({ ...makeDraft(), active: false });
  expect(await screen.findByText(/archived package is kept for your application history/)).toBeInTheDocument();
  expect(screen.queryByText("More actions")).not.toBeInTheDocument();
});

it("protects manual edits on internal navigation and supports discard or keep editing", async () => {
  setup();
  const user = userEvent.setup();
  const line = await editSection(user);
  await user.type(line, " and SQL");
  await user.click(screen.getByRole("link", { name: /Back to Job/ }));
  expect(await screen.findByRole("dialog")).toHaveTextContent("Save your edits before leaving?");
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.getByLabelText("Draft line 1")).toHaveValue("Python and SQL");
  await user.click(screen.getByRole("link", { name: /Back to Job/ }));
  await user.click(screen.getByRole("button", { name: "Discard and leave" }));
  expect(await screen.findByRole("heading", { name: "Job destination" })).toBeInTheDocument();
});
it("saves successfully before following a blocked navigation", async () => {
  const calls = setup();
  const user = userEvent.setup();
  await user.type(await editSection(user), " and SQL");
  await user.click(screen.getByRole("link", { name: /Back to Job/ }));
  await user.click(screen.getByRole("button", { name: "Save and leave" }));
  expect(await screen.findByRole("heading", { name: "Job destination" })).toBeInTheDocument();
  const save = calls.find(r => r.method === "PUT")!;
  expect((await save.json()).content.resume[0].text).toBe("Python and SQL");
});
it("retains edits and stays on the Draft when Save and leave fails", async () => {
  setup(makeDraft(), { "PUT /api/drafts/draft-1": () => json({ error: { message: "Save unavailable", code: "unavailable" } }, 503) });
  const user = userEvent.setup();
  await user.type(await editSection(user), " and SQL");
  await user.click(screen.getByRole("link", { name: /Back to Job/ }));
  await user.click(screen.getByRole("button", { name: "Save and leave" }));
  await waitFor(() => expect(screen.getByRole("dialog")).toHaveTextContent("Save unavailable"));
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.getByLabelText("Draft line 1")).toHaveValue("Python and SQL");
});

it("blocks browser history navigation while keeping the pending destination", async () => {
  const draft = makeDraft();
  mockFetch({ "GET /api/drafts/draft-1/versions": () => json([draft.version]) });
  function WorkspaceWithBack() {
    const navigate = useNavigate();
    return <><button onClick={() => navigate(-1)}>History back</button><DraftWorkspace draft={draft} /></>;
  }
  renderWithApp(<Routes><Route path="/jobs/:jobId" element={<h1>Previous Job</h1>} /><Route path="/drafts/:draftId" element={<WorkspaceWithBack />} /></Routes>, { initialEntries: ["/jobs/job-1", "/drafts/draft-1"] });
  const user = userEvent.setup();
  await user.type(await editSection(user), " and SQL");
  await user.click(screen.getByRole("button", { name: "History back" }));
  expect(await screen.findByRole("dialog")).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Previous Job" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Discard and leave" }));
  expect(await screen.findByRole("heading", { name: "Previous Job" })).toBeInTheDocument();
});

it("makes saving the primary footer action and discarding a secondary action", async () => {
  setup();
  const user = userEvent.setup();
  await user.type(await editSection(user), " and SQL");
  await user.click(screen.getByRole("link", { name: /Back to Job/ }));
  const dialog = screen.getByRole("dialog");
  const save = within(dialog).getByRole("button", { name: "Save and leave" });
  const discard = within(dialog).getByRole("button", { name: "Discard and leave" });
  expect(dialog.lastElementChild).toContainElement(save);
  expect(dialog.lastElementChild).toContainElement(discard);
  expect(save).toHaveClass("bg-brand-600");
  expect(discard).not.toHaveClass("bg-brand-600");
});
