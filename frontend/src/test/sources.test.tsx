import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import type { SourceStatus } from "@/api/client";
import { App } from "@/app/App";
import { CompanyBoards } from "@/features/sources/CompanyBoards";
import { formatQueryKey } from "@/lib/query-key";
import { AdminSourcesPage } from "@/pages/AdminSourcesPage";

import { json, makeFeed, makeMe, mockFetch, renderWithApp, expectAccessible } from "./utils";

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
  standby_for: null,
  shares_budget_with: [],
  disabled_reason: null,
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
  await expectAccessible();
});

it("explains standbys, shared allowances and sources that are off by default", async () => {
  const apify: SourceStatus = {
    ...linkedin,
    name: "linkedin-apify",
    label: "LinkedIn (Apify)",
    state: "healthy",
    last_error: null,
    degraded_since: null,
    standby_for: "LinkedIn (Bright Data)",
    shares_budget_with: ["Naukri (Apify)"],
    budget: { ...linkedin.budget!, unit: "US cents", allowance: 500, spent: 120, top_queries: [] },
  };
  const workday: SourceStatus = {
    ...greenhouse,
    name: "workday",
    label: "Workday",
    enabled: false,
    state: "disabled",
    disabled_reason: "Not a published API.",
  };
  mockFetch({
    "GET /api/admin/sources": () => json([apify, workday]),
    "GET /api/admin/fetch-runs": () => json([]),
  });
  renderWithApp(<AdminSourcesPage />);
  expect(
    await screen.findByText(/Standby for LinkedIn \(Bright Data\): runs only while that source is degraded/),
  ).toBeInTheDocument();
  expect(screen.getByText("Shares this allowance with Naukri (Apify).")).toBeInTheDocument();
  expect(screen.getByText("Off by default")).toBeInTheDocument();
  expect(screen.getByText("Not a published API.")).toBeInTheDocument();
});

it("asks before a manual run and says what it costs", async () => {
  document.cookie = "jw_csrf=t";
  const calls = mockFetch({
    "GET /api/admin/sources": () => json([linkedin]),
    "GET /api/admin/fetch-runs": () => json([]),
    "POST /api/admin/sources/linkedin/run": () =>
      json({ source: "linkedin", status: "started", message: "", postings_new: 0, credits_used: 0 }),
  });
  const user = userEvent.setup();
  renderWithApp(<AdminSourcesPage />);
  await user.click(await screen.findByRole("button", { name: "Run now" }));
  expect(screen.getByText(/uses credits for every result returned/)).toBeInTheDocument();
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Run now" }));
  expect(await screen.findByText("Run started. Its progress shows under Recent runs.")).toBeInTheDocument();
  expect(calls.some((c) => c.method === "POST")).toBe(true);
});

it("refreshes recent runs while a run is in progress", async () => {
  let runs = [{ id: "r1", source: "greenhouse", status: "running", created_at: new Date().toISOString(), board: "acme", query_key: null, postings_found: 0, postings_new: 0, postings_closed: 0, credits_used: 0, error: null, trigger: "manual", window_since: null, window_until: null, finished_at: null }];
  const calls = mockFetch({
    "GET /api/admin/sources": () => json([linkedin]),
    "GET /api/admin/fetch-runs": () => json(runs),
  });
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    renderWithApp(<AdminSourcesPage />);
    expect(await screen.findByText("running")).toBeInTheDocument();
    runs = [{ ...runs[0]!, status: "succeeded" }];
    await vi.advanceTimersByTimeAsync(5100);
    expect(await screen.findByText("succeeded")).toBeInTheDocument();
    // Once nothing runs any more, the Sources are refreshed too.
    await vi.waitFor(() =>
      expect(calls.filter((c) => c.url.endsWith("/api/admin/sources")).length).toBeGreaterThan(1),
    );
  } finally {
    vi.useRealTimers();
  }
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
  mockFetch({
    "GET /api/me": () => json(makeMe()),
    "GET /api/sources/notices": () => json([]),
    "GET /api/feed": () => json(makeFeed()),
  });
  renderWithApp(<App />, { route: "/feed" });
  await screen.findByText("No jobs yet");
  expect(screen.queryByRole("link", { name: "Sources" })).not.toBeInTheDocument();

  vi.unstubAllGlobals();
  mockFetch({
    "GET /api/me": () => json({ ...makeMe(), role: "admin" }),
    "GET /api/feed": () => json(makeFeed()),
    "GET /api/sources/notices": () =>
      json([{ label: "LinkedIn", since: inDays(-2), message: "LinkedIn jobs are delayed; other sources are up to date." }]),
  });
  renderWithApp(<App />, { route: "/feed" });
  expect((await screen.findAllByRole("link", { name: "Sources" })).length).toBeGreaterThan(0);
  expect(await screen.findByText("LinkedIn jobs are delayed; other sources are up to date.")).toBeInTheDocument();
});

it("shows AI calls against each free daily quota", async () => {
  mockFetch({
    "GET /api/admin/sources": () => json([linkedin]),
    "GET /api/admin/fetch-runs": () => json([]),
    "GET /api/admin/ai-usage": () =>
      json({
        day_started_at: new Date().toISOString(),
        models: [
          { provider: "gemini", model: "gemini-flash-latest", calls_today: 16, errors_today: 1, daily_quota: 18 },
          { provider: "groq", model: "openai/gpt-oss-120b", calls_today: 3, errors_today: 0, daily_quota: 900 },
        ],
        tasks_last_7_days: [{ task: "tailor_draft", calls: 40, errors: 2, input_tokens: 120000, output_tokens: 30000 }],
      }),
  });
  renderWithApp(<AdminSourcesPage />);
  const table = await screen.findByRole("table", { name: "AI calls today by provider and model" });
  const flash = within(table).getByRole("row", { name: /gemini-flash-latest/ });
  // Within 20% of the quota is highlighted.
  expect(within(flash).getByText("16")).toHaveClass("font-semibold");
  expect(within(table).getByRole("row", { name: /gpt-oss-120b/ })).toHaveTextContent("900");
  expect(screen.getByRole("table", { name: "Last 7 days by task" })).toHaveTextContent("120,000 / 30,000");
  await expectAccessible();
});

it("shows the account's Apify usage instead of the local estimate", async () => {
  const apify: SourceStatus = {
    ...linkedin,
    label: "LinkedIn (Apify)",
    budget: {
      ...linkedin.budget!,
      unit: "US cents", allowance: 500, spent: 281,
      account: {
        status: "live", allowance: 500, spent: 500, remaining: 0, unit: "US cents",
        checked_at: inDays(0), period_start: inDays(-5), renews_on: inDays(25),
        message: "Account-wide usage, including activity outside JobWeaver.",
      },
    },
  };
  mockFetch({
    "GET /api/admin/sources": () => json([apify]),
    "GET /api/admin/fetch-runs": () => json([]),
  });
  renderWithApp(<AdminSourcesPage />);
  expect(await screen.findByText("500 / 500 US cents")).toBeInTheDocument();
  expect(screen.getByText(/0 US cents available/)).toBeInTheDocument();
  expect(screen.getByText(/JobWeaver tracked usage: 281/)).toBeInTheDocument();
  expect(screen.queryByText(/On this pace/)).not.toBeInTheDocument();
  await expectAccessible();
});

it.each(["unsupported", "unavailable"] as const)("labels %s balances as unknown and local usage as an estimate", async (status) => {
  mockFetch({
    "GET /api/admin/sources": () => json([{
      ...linkedin,
      budget: { ...linkedin.budget!, account: { status, unit: "credits", message: "Actual account credits could not be verified." } },
    }]),
    "GET /api/admin/fetch-runs": () => json([]),
  });
  renderWithApp(<AdminSourcesPage />);
  expect(await screen.findByText("JobWeaver tracked usage (estimate)")).toBeInTheDocument();
  expect(screen.getByText("Actual account credits could not be verified.")).toBeInTheDocument();
  expect(screen.queryByText(/On this pace/)).not.toBeInTheDocument();
  expect(screen.queryByText(/available for searches/)).not.toBeInTheDocument();
});

it("shows backup account credits and each account's remaining allowance", async () => {
  mockFetch({
    "GET /api/admin/sources": () => json([{
      ...linkedin,
      budget: {
        ...linkedin.budget!, tracked_account: "Backup account 1",
        account: {
          status: "live", account_label: "Backup account 1", allowance: 500, spent: 0,
          remaining: 500, unit: "US cents", checked_at: inDays(0), renews_on: inDays(25),
          message: "Account-wide usage",
          accounts: [
            { label: "Primary account", status: "live", remaining: 0, renews_on: inDays(5) },
            { label: "Backup account 1", status: "live", remaining: 500, renews_on: inDays(25) },
          ],
        },
      },
    }]),
    "GET /api/admin/fetch-runs": () => json([]),
  });
  renderWithApp(<AdminSourcesPage />);
  expect(await screen.findByText("Apify credits — Backup account 1")).toBeInTheDocument();
  expect(screen.getByText(/Primary account: 0 US cents available/)).toBeInTheDocument();
  expect(screen.getByText(/Backup account 1: 500 US cents available/)).toBeInTheDocument();
  await expectAccessible();
});
