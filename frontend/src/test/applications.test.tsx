import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";

import type { Application } from "@/api/client";
import { ApplicationsPage } from "@/pages/ApplicationsPage";
import { CompanyPage } from "@/pages/CompanyPage";

import { json, mockFetch, renderWithApp, expectAccessible } from "./utils";

const now = new Date().toISOString();
const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString();

function makeApplication(overrides: Partial<Application> = {}): Application {
  return {
    id: "app-1",
    job_id: "job-1",
    draft_id: "draft-1",
    title: "Backend Engineer",
    company: "Acme",
    company_id: "company-1",
    job_expired: false,
    status: "applied",
    applied_at: daysAgo(9),
    status_changed_at: daysAgo(9),
    follow_up_due: true,
    history: [
      { status: "drafted", at: daysAgo(10) },
      { status: "applied", at: daysAgo(9) },
    ],
    ...overrides,
  };
}

const reminder = {
  application_id: "app-1",
  job_id: "job-1",
  title: "Backend Engineer",
  company: "Acme",
  applied_at: daysAgo(9),
  days_waiting: 9,
};

beforeEach(() => {
  document.cookie = "jw_csrf=t";
  vi.spyOn(window, "open").mockImplementation(() => null);
});

it("groups Applications by status and changes a status by hand", async () => {
  const offer = makeApplication({ id: "app-2", title: "Platform Engineer", status: "offer", follow_up_due: false });
  const calls = mockFetch({
    "GET /api/applications": () => json([makeApplication(), offer]),
    "GET /api/reminders": () => json([]),
    "PATCH /api/applications/app-1": () => json(makeApplication({ status: "interview", status_changed_at: now })),
  });
  const user = userEvent.setup();
  renderWithApp(<ApplicationsPage />);
  const applied = await screen.findByRole("region", { name: /Applied/ });
  expect(within(applied).getByRole("link", { name: "Backend Engineer" })).toHaveAttribute("href", "/jobs/job-1");
  expect(within(applied).getByText("Follow-up due")).toBeInTheDocument();
  expect(screen.getByRole("region", { name: /Offer/ })).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: /Rejected/ })).not.toBeInTheDocument();

  await user.selectOptions(screen.getByLabelText("Status of Backend Engineer at Acme"), "interview");
  expect(await screen.findByText("Moved to Interview")).toBeInTheDocument();
  const patch = calls.find((c) => c.method === "PATCH")!;
  expect(await patch.json()).toEqual({ status: "interview" });
  await expectAccessible();
});

it("explains what to do when there are no Applications", async () => {
  mockFetch({ "GET /api/applications": () => json([]), "GET /api/reminders": () => json([]) });
  renderWithApp(<ApplicationsPage />);
  expect(await screen.findByText("No applications yet")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Go to your Feed" })).toHaveAttribute("href", "/feed");
  await expectAccessible();
});

it("drafts a follow-up into Gmail after the User reviews it", async () => {
  const calls = mockFetch({
    "GET /api/applications": () => json([makeApplication()]),
    "GET /api/reminders": () => json([reminder]),
    "GET /api/applications/app-1/follow-up": () =>
      json({ recipient: "jobs@acme.com", subject: "Following up: Backend Engineer application", body: "Dear hiring team" }),
    "POST /api/applications/app-1/follow-up": () =>
      json({ mode: "gmail", url: "https://mail.google.com/mail/u/x/#drafts", message: "Your follow-up is in Gmail Drafts." }),
  });
  const user = userEvent.setup();
  renderWithApp(<ApplicationsPage />);
  expect(await screen.findByText(/No update from Acme for 9 days/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Draft a follow-up" }));
  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).getByText(/Nothing is sent/)).toBeInTheDocument();
  const message = await within(dialog).findByLabelText("Message");
  await user.clear(message);
  await user.type(message, "Edited by me");
  await user.click(within(dialog).getByRole("button", { name: "Open in Gmail" }));
  expect(await screen.findByText("Your follow-up is in Gmail Drafts.")).toBeInTheDocument();
  const post = calls.find((c) => c.method === "POST")!;
  expect(await post.json()).toMatchObject({ recipient: "jobs@acme.com", body: "Edited by me", confirm: true });
  expect(window.open).toHaveBeenCalledWith("https://mail.google.com/mail/u/x/#drafts", "_blank", "noopener");
});

it("asks again when the follow-up address looks wrong", async () => {
  let attempts = 0;
  const calls = mockFetch({
    "GET /api/applications": () => json([makeApplication()]),
    "GET /api/reminders": () => json([reminder]),
    "GET /api/applications/app-1/follow-up": () => json({ recipient: "jobs@acme.con", subject: "s", body: "b" }),
    "POST /api/applications/app-1/follow-up": () =>
      ++attempts === 1
        ? json({ error: { code: "precondition_failed", message: "Confirm the email warning before continuing: No MX record" } }, 409)
        : json({ mode: "fallback", url: "https://mail.google.com/compose", message: "Gmail is unavailable." }),
  });
  const user = userEvent.setup();
  renderWithApp(<ApplicationsPage />);
  await user.click(await screen.findByRole("button", { name: "Draft a follow-up" }));
  const dialog = await screen.findByRole("dialog");
  await within(dialog).findByLabelText("Message");
  await user.click(within(dialog).getByRole("button", { name: "Open in Gmail" }));
  expect(await within(dialog).findByText("No MX record")).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: "Open in Gmail" })).toBeDisabled();
  await user.click(within(dialog).getByLabelText("Use this address anyway"));
  await user.click(within(dialog).getByRole("button", { name: "Open in Gmail" }));
  expect(await screen.findByText("Gmail is unavailable.")).toBeInTheDocument();
  const posts = calls.filter((c) => c.method === "POST");
  expect(await posts[1]!.json()).toMatchObject({ confirm_email_warning: true });
});

it("asks to reconnect Gmail instead of failing", async () => {
  mockFetch({
    "GET /api/applications": () => json([makeApplication()]),
    "GET /api/reminders": () => json([reminder]),
    "GET /api/applications/app-1/follow-up": () => json({ recipient: "jobs@acme.com", subject: "s", body: "b" }),
    "POST /api/applications/app-1/follow-up": () =>
      json({ mode: "reconnect", url: "/api/gmail/connect?next=%2Fapplications", message: "Connect Gmail again." }),
  });
  const user = userEvent.setup();
  renderWithApp(<ApplicationsPage />);
  await user.click(await screen.findByRole("button", { name: "Draft a follow-up" }));
  const dialog = await screen.findByRole("dialog");
  await within(dialog).findByLabelText("Message");
  await user.click(within(dialog).getByRole("button", { name: "Open in Gmail" }));
  expect(await within(dialog).findByRole("link", { name: "Reconnect Gmail" })).toHaveAttribute(
    "href",
    "/api/gmail/connect?next=%2Fapplications",
  );
  expect(window.open).not.toHaveBeenCalled();
});

it("lets the User put a reminder off", async () => {
  const calls = mockFetch({
    "GET /api/applications": () => json([makeApplication()]),
    "GET /api/reminders": () => json([reminder]),
    "POST /api/applications/app-1/follow-up/dismiss": () => new Response(null, { status: 204 }),
  });
  const user = userEvent.setup();
  renderWithApp(<ApplicationsPage />);
  await user.click(await screen.findByRole("button", { name: "Not now" }));
  expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/follow-up/dismiss"))).toBe(true);
});

it("shows a Company's history", async () => {
  mockFetch({
    "GET /api/companies/company-1/applications": () =>
      json({ id: "company-1", name: "Acme", applications: [makeApplication({ follow_up_due: false })] }),
  });
  renderWithApp(
    <Routes>
      <Route path="/companies/:companyId" element={<CompanyPage />} />
    </Routes>,
    { route: "/companies/company-1" },
  );
  expect(await screen.findByRole("heading", { name: "Acme" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Backend Engineer" })).toBeInTheDocument();
  await userEvent.setup().click(screen.getByText("History"));
  expect(screen.getAllByText(/^(Drafted|Applied):/)).toHaveLength(2);
  await expectAccessible();
});
