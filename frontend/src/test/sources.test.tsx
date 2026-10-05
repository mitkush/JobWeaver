import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import type { SourceStatus } from "@/api/client";
import { App } from "@/app/App";
import { CompanyBoards } from "@/features/sources/CompanyBoards";
import { formatQueryKey } from "@/lib/query-key";
import { AdminSourcesPage } from "@/pages/AdminSourcesPage";

import { json, makeMe, mockFetch, renderWithApp } from "./utils";

afterEach(() => vi.unstubAllGlobals());

const inDays = (days: number) => new Date(Date.now() + days * 86_400_000).toISOString();

const linkedin: SourceStatus = {
  name: "linkedin",
  label: "LinkedIn (Bright Data)",
  priority: 1,
  mode: "windowed",
  enabled: true,
  configured: true,
  state: "degraded",
  last_success_at: inDays(-2),
  last_error: "LinkedIn (Bright Data) rate limit reached",
  last_error_at: inDays(-1),
  degraded_since: inDays(-1),
  next_run_at: inDays(0.5),
  open_postings: 1234,
  boards: null,
  manual_runs_left: 4,
  budget: {
    allowance: 5000,
    unit: "credits",
    spent: 3000,
    projected: 7500,
    period_start: inDays(-12),
    renews_on: inDays(18),
    runs_out_on: inDays(8),
    top_queries: [{ query_key: "backend engineer@Bengaluru|IN|False", spent: 1800 }],
  },
};

const greenhouse: SourceStatus = {
  ...linkedin,
  name: "greenhouse",
  label: "Greenhouse",
  mode: "snapshot",
  state: "healthy",
  last_error: null,
  degraded_since: null,
  boards: 12,
  budget: null,
};

it("shows health, budget pace and the most expensive searches", async () => {
  mockFetch({
    "GET /api/admin/sources": () => json([linkedin, greenhouse]),
    "GET /api/admin/fetch-runs": () => json([]),
  });
  renderWithApp(<AdminSourcesPage />);
  expect(await screen.findByText("1 source is degraded. They are retried automatically.")).toBeInTheDocument();
  const card = screen.getByRole("heading", { name: "LinkedIn (Bright Data)" }).closest("div.rounded-xl") as HTMLElement;
  expect(within(card).getByText("Degraded")).toBeInTheDocument();
  expect(within(card).getByText("3,000 / 5,000 credits")).toBeInTheDocument();
  expect(within(card).getByText(/runs out around/)).toBeInTheDocument();
  expect(within(card).getByText("backend engineer · Bengaluru, India")).toBeInTheDocument();
  expect(screen.getByText(/Company boards · 12 tracked/)).toBeInTheDocument();
});

it("asks before a manual run and says what it costs", async () => {
  document.cookie = "jw_csrf=t";
  const calls = mockFetch({
    "GET /api/admin/sources": () => json([linkedin]),
    "GET /api/admin/fetch-runs": () => json([]),
    "POST /api/admin/sources/linkedin/run": () =>
      json({ source: "linkedin", status: "succeeded", message: "", postings_new: 7, credits_used: 7 }),
  });
  const user = userEvent.setup();
  renderWithApp(<AdminSourcesPage />);
  await user.click(await screen.findByRole("button", { name: "Run now" }));
  expect(screen.getByText(/uses credits for every result returned/)).toBeInTheDocument();
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Run now" }));
  expect(await screen.findByText("7 new postings")).toBeInTheDocument();
  expect(calls.some((c) => c.method === "POST")).toBe(true);
});

it("formats search keys for people", () => {
  expect(formatQueryKey("backend engineer@|IN|True")).toBe("backend engineer · India · remote");
  expect(formatQueryKey("all")).toBe("all recent jobs");
});

it("adds a company board from a link and explains bad links", async () => {
  document.cookie = "jw_csrf=t";
  let boards: unknown[] = [];
  mockFetch({
    "GET /api/ats-boards": () => json(boards),
    "POST /api/ats-boards": async (request) => {
      const { url } = (await request.json()) as { url: string };
      if (url.includes("linkedin")) {
        return json({ error: { code: "validation_failed", message: "Paste a link to a company's job board" } }, 422);
      }
      const board = { id: "b1", ats: "lever", slug: "netflix", company: null, discovered_from: "manual",
        enabled: true, fetched: true, last_fetched_at: null, open_postings: 0 };
      boards = [board];
      return json(board, 201);
    },
  });
  const user = userEvent.setup();
  renderWithApp(<CompanyBoards />);
  const input = await screen.findByLabelText("Company job board link");
  await user.type(input, "https://www.linkedin.com/jobs/1");
  await user.click(screen.getByRole("button", { name: "Add board" }));
  expect(await screen.findByText("Paste a link to a company's job board")).toBeInTheDocument();
  await user.clear(input);
  await user.type(input, "https://jobs.lever.co/netflix");
  await user.click(screen.getByRole("button", { name: "Add board" }));
  expect(await screen.findByText("netflix")).toBeInTheDocument();
  expect(screen.getByText("Fetched daily")).toBeInTheDocument();
});

it("shows the Sources page to the admin only", async () => {
  mockFetch({ "GET /api/me": () => json(makeMe()), "GET /api/sources/notices": () => json([]) });
  renderWithApp(<App />, { route: "/feed" });
  await screen.findByText("No jobs yet");
  expect(screen.queryByRole("link", { name: "Sources" })).not.toBeInTheDocument();

  vi.unstubAllGlobals();
  mockFetch({
    "GET /api/me": () => json({ ...makeMe(), role: "admin" }),
    "GET /api/sources/notices": () =>
      json([{ label: "LinkedIn", since: inDays(-2), message: "LinkedIn jobs are delayed; other sources are up to date." }]),
  });
  renderWithApp(<App />, { route: "/feed" });
  expect((await screen.findAllByRole("link", { name: "Sources" })).length).toBeGreaterThan(0);
  expect(await screen.findByText("LinkedIn jobs are delayed; other sources are up to date.")).toBeInTheDocument();
});
