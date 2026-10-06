import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { JobDetail } from "@/api/client";
import { formatLocation } from "@/features/feed/format";
import { feedQuery } from "@/features/feed/feed-params";
import { FeedPage } from "@/pages/FeedPage";
import { JobPage } from "@/pages/JobPage";

import { json, makeCard, makeFeed, mockFetch, renderWithApp } from "./utils";

afterEach(() => vi.unstubAllGlobals());

function feedRoutes() {
  return (
    <Routes>
      <Route path="/feed" element={<FeedPage />} />
      <Route path="/jobs/:jobId" element={<JobPage />} />
    </Routes>
  );
}

const queryOf = (request: Request) => new URL(request.url).searchParams;

it("shows cards with skill gaps, source badges and the email section first", async () => {
  mockFetch({
    "GET /api/sources/notices": () => json([]),
    "GET /api/feed": () =>
      json(makeFeed([makeCard(), makeCard({ job_id: "job-2", title: "Platform Engineer", skill_gaps: [] })])),
  });
  renderWithApp(feedRoutes(), { route: "/feed" });
  const card = (await screen.findByRole("link", { name: "Backend Engineer" })).closest("div.rounded-xl") as HTMLElement;
  expect(within(card).getByText("Missing:")).toBeInTheDocument();
  expect(within(card).getByText(/Kubernetes, Go/)).toBeInTheDocument();
  expect(within(card).getByText("Greenhouse")).toBeInTheDocument();
  expect(screen.getByText("No gaps found")).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: /With email/ })).toHaveAttribute("aria-selected", "true");
});

it("opens the apply-link section when no job has an email", async () => {
  const calls = mockFetch({
    "GET /api/sources/notices": () => json([]),
    "GET /api/feed": (request) => {
      const linkOnly = makeCard({ contact_email: null, skill_gaps: null });
      const page = makeFeed([linkOnly]);
      return json(queryOf(request).get("section") === "link" ? page : { ...page, items: [], total: 0 });
    },
  });
  renderWithApp(feedRoutes(), { route: "/feed" });
  expect(await screen.findByRole("link", { name: "Backend Engineer" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: /Apply link only/ })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("Required skills not analysed yet")).toBeInTheDocument();
  expect(calls.some((c) => queryOf(c).get("section") === "link")).toBe(true);
});

it("sends filters and search to the API", async () => {
  const calls = mockFetch({
    "GET /api/sources/notices": () => json([]),
    "GET /api/feed": () => json(makeFeed([makeCard()])),
  });
  renderWithApp(feedRoutes(), { route: "/feed" });
  await screen.findByRole("link", { name: "Backend Engineer" });
  await userEvent.selectOptions(screen.getByLabelText("Work mode"), "remote");
  await userEvent.selectOptions(screen.getByLabelText("Source"), "greenhouse");
  await userEvent.selectOptions(screen.getByLabelText("Posted within"), "7");
  await userEvent.type(screen.getByPlaceholderText("Search title or company"), "acme");
  await waitFor(() => expect(calls.some((c) => queryOf(c).get("q") === "acme")).toBe(true));
  const last = queryOf(calls.at(-1)!);
  expect(last.get("work_mode")).toBe("remote");
  expect(last.get("source")).toBe("greenhouse");
  expect(last.get("posted_within_days")).toBe("7");
});

it("says when filters hide everything and clears them", async () => {
  mockFetch({
    "GET /api/sources/notices": () => json([]),
    "GET /api/feed": (request) => json(queryOf(request).get("q") ? makeFeed([]) : makeFeed([makeCard()])),
  });
  renderWithApp(feedRoutes(), { route: "/feed?q=zzz" });
  expect(await screen.findByText("No jobs match these filters")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  expect(await screen.findByRole("link", { name: "Backend Engineer" })).toBeInTheDocument();
});

it("hides a job from the feed", async () => {
  const calls = mockFetch({
    "GET /api/sources/notices": () => json([]),
    "GET /api/feed": () => json(makeFeed([makeCard()])),
    "POST /api/feed/job-1/hide": () => new Response(null, { status: 204 }),
  });
  renderWithApp(feedRoutes(), { route: "/feed" });
  await userEvent.click(await screen.findByRole("button", { name: "Hide Backend Engineer" }));
  expect(await screen.findByText("Job hidden from your feed")).toBeInTheDocument();
  expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/api/feed/job-1/hide"))).toBe(true);
});

it("marks possible duplicates on the card", async () => {
  mockFetch({
    "GET /api/sources/notices": () => json([]),
    "GET /api/feed": () => json(makeFeed([makeCard({ possible_duplicate: true })])),
  });
  renderWithApp(feedRoutes(), { route: "/feed" });
  const marker = await screen.findByText("Possible duplicate");
  expect(marker.closest("a")).toHaveAttribute("href", "/jobs/job-1#possible-duplicates");
});

it("keeps the feed state in the URL", () => {
  const query = feedQuery(new URLSearchParams("q=go&within=3&work_mode=bogus&page=2&hidden=1"), "link");
  expect(query).toMatchObject({ section: "link", q: "go", posted_within_days: 3, hidden: true, offset: 20 });
  expect(query.work_mode).toBeUndefined();
});

it("formats locations", () => {
  expect(formatLocation({ city: "Bengaluru", country: "IN", remote: false })).toBe("Bengaluru, India");
  expect(formatLocation({ city: null, country: "IN", remote: true })).toBe("India");
  expect(formatLocation({ city: null, country: null, remote: true })).toBe("Location not given");
});

const posting = (id: string, source: string, label: string, primary = false) => ({
  id,
  source: { name: source, label },
  title: "Backend Engineer",
  locations: [{ city: "Bengaluru", country: "IN", remote: false }],
  work_mode: "hybrid",
  posted_at: new Date().toISOString(),
  first_seen_at: new Date().toISOString(),
  apply_url: `https://example.com/${id}`,
  contact_email: null,
  closed: false,
  primary,
});

function makeJob(overrides: Partial<JobDetail> = {}): JobDetail {
  return {
    job_id: "job-1",
    title: "Backend Engineer",
    company: "Acme",
    description: "Build payment APIs.",
    locations: [{ city: "Bengaluru", country: "IN", remote: false }],
    work_mode: "hybrid",
    posted_at: new Date().toISOString(),
    contact_email: "jobs@acme.com",
    apply_url: "https://example.com/p1",
    sources: [{ name: "linkedin", label: "LinkedIn (Bright Data)" }],
    required_skills: ["Python", "Kubernetes"],
    skill_gaps: ["Kubernetes"],
    hidden: false,
    expired: false,
    postings: [posting("p1", "linkedin", "LinkedIn (Bright Data)", true), posting("p2", "greenhouse", "Greenhouse")],
    possible_duplicates: [
      {
        pair_id: "pair-1",
        posting_id: "p1",
        other_job_id: "job-2",
        other_job_in_feed: true,
        other_title: "Backend Engineer II",
        other_company: "Acme",
        other_postings: [posting("p9", "jsearch", "JSearch")],
        title_similarity: 82,
        description_similarity: 0.88,
      },
    ],
    ...overrides,
  };
}

it("shows the Correspondence stack and confirms a possible duplicate", async () => {
  const calls = mockFetch({
    "GET /api/jobs/job-1": () => json(makeJob()),
    "GET /api/jobs/job-0": () => json(makeJob({ job_id: "job-0", possible_duplicates: [], title: "Merged job" })),
    "POST /api/possible-duplicates/pair-1/confirm": () => json({ job_id: "job-0" }),
  });
  renderWithApp(feedRoutes(), { route: "/jobs/job-1" });
  expect(await screen.findByRole("heading", { name: "Backend Engineer" })).toBeInTheDocument();
  expect(screen.getByText("Primary")).toBeInTheDocument();
  expect(screen.getByText("Greenhouse")).toBeInTheDocument();
  expect(screen.getByText("Possible duplicate: Backend Engineer II")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Open job advert/ })).toHaveAttribute("href", "https://example.com/p1");
  await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
  expect(await screen.findByRole("heading", { name: "Merged job" })).toBeInTheDocument();
  expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/confirm"))).toBe(true);
});

it("rejects a possible duplicate and splits a posting", async () => {
  const calls = mockFetch({
    "GET /api/jobs/job-1": () => json(makeJob()),
    "POST /api/possible-duplicates/pair-1/reject": () => new Response(null, { status: 204 }),
    "POST /api/jobs/job-1/postings/p2/split": () => json({ job_id: "job-3" }),
  });
  renderWithApp(feedRoutes(), { route: "/jobs/job-1" });
  const duplicates = await screen.findByRole("region", { name: "Possible duplicates" });
  await userEvent.click(within(duplicates).getByRole("button", { name: "Not the same Job" }));
  expect(await screen.findByText("Kept as separate jobs")).toBeInTheDocument();
  const splitButtons = screen.getAllByRole("button", { name: "Not the same Job" }).filter((b) => !duplicates.contains(b));
  await userEvent.click(splitButtons[1]!);
  expect(await screen.findByText("Moved to a separate job")).toBeInTheDocument();
  expect(calls.some((c) => c.url.endsWith("/postings/p2/split"))).toBe(true);
});

it("explains a job that is no longer in the feed", async () => {
  mockFetch({});
  renderWithApp(feedRoutes(), { route: "/jobs/gone" });
  expect(await screen.findByText("This job is not in your feed")).toBeInTheDocument();
});

it("stays on the job when it is the one that survives a merge", async () => {
  let merged = false;
  mockFetch({
    "GET /api/jobs/job-1": () => json(merged ? makeJob({ possible_duplicates: [], title: "Backend Engineer (merged)" }) : makeJob()),
    "POST /api/possible-duplicates/pair-1/confirm": () => {
      merged = true;
      return json({ job_id: "job-1" });
    },
  });
  renderWithApp(feedRoutes(), { route: "/jobs/job-1" });
  await userEvent.click(await screen.findByRole("button", { name: "Confirm" }));
  expect(await screen.findByRole("heading", { name: "Backend Engineer (merged)" })).toBeInTheDocument();
  expect(screen.queryByText("This job is not in your feed")).not.toBeInTheDocument();
});
