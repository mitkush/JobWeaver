import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, Route, Routes, useNavigate } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { AppShell } from "@/app/AppShell";
import type { JobDetail } from "@/api/client";
import { formatLocation } from "@/features/feed/format";
import { feedQuery } from "@/features/feed/feed-params";
import { FeedPage } from "@/pages/FeedPage";
import { JobPage } from "@/pages/JobPage";

import { json, makeCard, makeFeed, makeMe, mockFetch, renderWithApp, expectAccessible } from "./utils";

afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear(); });

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
    "GET /api/feed": () =>
      json(makeFeed([makeCard(), makeCard({ job_id: "job-2", title: "Platform Engineer", skill_gaps: [] })])),
  });
  renderWithApp(feedRoutes(), { route: "/feed" });
  const card = (await screen.findByRole("link", { name: "Backend Engineer" })).closest("[data-card]") as HTMLElement;
  expect(within(card).getByText("Not in your Fact Bank:")).toBeInTheDocument();
  expect(within(card).getByText(/Kubernetes, Go/)).toBeInTheDocument();
  expect(within(card).getByText("Greenhouse")).toBeInTheDocument();
  expect(screen.getByText("Every required skill is in your Fact Bank")).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: /With email/ })).toHaveAttribute("aria-selected", "true");
  await expectAccessible();
});

it("opens the apply-link section when no job has an email", async () => {
  const calls = mockFetch({
    "GET /api/feed": (request) => {
      const linkOnly = makeCard({ contact_email: null, skill_gaps: null });
      const page = makeFeed([linkOnly]);
      return json(queryOf(request).get("section") === "link" ? page : { ...page, items: [], total: 0 });
    },
  });
  renderWithApp(feedRoutes(), { route: "/feed" });
  expect(await screen.findByRole("link", { name: "Backend Engineer" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: /Apply link only/ })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("Skills not analysed yet")).toBeInTheDocument();
  expect(calls.some((c) => queryOf(c).get("section") === "link")).toBe(true);
});

it("sends filters and search to the API", async () => {
  const calls = mockFetch({
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

it("offers all LinkedIn providers as one source filter", async () => {
  const calls = mockFetch({
    "GET /api/feed": () => json(makeFeed([makeCard()], {
      sources: [
        { name: "linkedin", label: "LinkedIn (Bright Data)", site: "LinkedIn" },
        { name: "linkedin-apify", label: "LinkedIn (Apify)", site: "LinkedIn" },
        { name: "linkedin-piloterr", label: "LinkedIn (Piloterr)", site: "LinkedIn" },
        { name: "greenhouse", label: "Greenhouse" },
      ],
    })),
  });
  renderWithApp(feedRoutes(), { route: "/feed" });
  await screen.findByRole("link", { name: "Backend Engineer" });
  const source = screen.getByLabelText("Source");
  expect(within(source).getByRole("option", { name: "LinkedIn" })).toHaveValue("site:LinkedIn");
  expect(within(source).queryByRole("option", { name: "LinkedIn (Apify)" })).not.toBeInTheDocument();
  expect(within(source).queryByRole("option", { name: "LinkedIn (Piloterr)" })).not.toBeInTheDocument();
  await userEvent.selectOptions(source, "site:LinkedIn");
  await waitFor(() => expect(calls.some((call) => queryOf(call).get("source") === "site:LinkedIn")).toBe(true));
});

it("says when filters hide everything and clears them", async () => {
  mockFetch({
    "GET /api/feed": (request) => json(queryOf(request).get("q") ? makeFeed([]) : makeFeed([makeCard()])),
  });
  renderWithApp(feedRoutes(), { route: "/feed?q=zzz" });
  expect(await screen.findByText("No jobs match these filters")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  expect(await screen.findByRole("link", { name: "Backend Engineer" })).toBeInTheDocument();
});

it("hides a job from the feed", async () => {
  const calls = mockFetch({
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
    "GET /api/feed": () => json(makeFeed([makeCard({ possible_duplicate: true })])),
  });
  renderWithApp(feedRoutes(), { route: "/feed" });
  const marker = await screen.findByText("Possible duplicate");
  expect(marker.closest("a")).toHaveAttribute("href", "/jobs/job-1#possible-duplicates");
});

it("keeps the feed state in the URL", () => {
  const query = feedQuery(new URLSearchParams("q=go&within=3&work_mode=bogus&page=2&hidden=1"), "link");
  expect(query).toMatchObject({ section: "link", q: "go", posted_within_days: 3, view: "hidden", offset: 20 });
  expect(feedQuery(new URLSearchParams("view=saved&viewed=unviewed"), "email")).toMatchObject({ view: "saved", viewed: "unviewed" });
  expect(feedQuery(new URLSearchParams("viewed=bogus"), "email").viewed).toBeUndefined();
  expect(query.work_mode).toBeUndefined();
});

it("formats locations", () => {
  expect(formatLocation({ city: "Bengaluru", country: "IN", remote: false })).toBe("Bengaluru, India");
  expect(formatLocation({ city: null, country: "IN", remote: true })).toBe("India");
  expect(formatLocation({ city: null, country: null, remote: true })).toBe("Location not stated");
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
    company_id: "company-1",
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
  await expectAccessible();
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
  // Splitting changes the shared grouping for everyone, so it is confirmed first.
  const confirm = await screen.findByRole("dialog");
  expect(confirm).toHaveTextContent("changes the shared Job grouping for everyone");
  expect(calls.some((c) => c.url.endsWith("/postings/p2/split"))).toBe(false);
  await userEvent.click(within(confirm).getByRole("button", { name: "Separate listing" }));
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

it("switches to differently titled jobs and shows which keywords matched", async () => {
  const keywordCard = makeCard({
    job_id: "job-k",
    title: "Software Engineer - Payments",
    match: "keywords",
    matched_keywords: [
      { keyword: "Rails", where: "requirements", core: true },
      { keyword: "PostgreSQL", where: "description", core: false },
    ],
  });
  const calls = mockFetch({
    "GET /api/feed": (request) => {
      const keywords = queryOf(request).get("match") === "keywords";
      const page = makeFeed(keywords ? [keywordCard] : [makeCard()]);
      return json({ ...page, counts: { ...page.counts, title_matches: 1, keyword_matches: 1 } });
    },
  });
  renderWithApp(feedRoutes(), { route: "/feed" });
  await screen.findByRole("link", { name: "Backend Engineer" });
  await userEvent.click(screen.getByRole("button", { name: /Other titles matching your keywords/ }));
  const link = await screen.findByRole("link", { name: "Software Engineer - Payments" });
  const card = link.closest("[data-card]") as HTMLElement;
  const matched = within(card).getByRole("list", { name: "Matched keywords" });
  expect(matched).toHaveTextContent("Rails");
  expect(matched).toHaveTextContent("in requirements");
  expect(matched).toHaveTextContent("PostgreSQL");
  expect(matched).toHaveTextContent("in description");
  expect(within(card).getByLabelText("Core")).toBeInTheDocument();
  expect(calls.some((c) => queryOf(c).get("match") === "keywords")).toBe(true);
  await expectAccessible();
});

it("hides the keyword switch when no differently titled job matches", async () => {
  mockFetch({
    "GET /api/feed": () => json(makeFeed([makeCard()])),
  });
  renderWithApp(feedRoutes(), { route: "/feed" });
  await screen.findByRole("link", { name: "Backend Engineer" });
  expect(screen.queryByRole("button", { name: /Other titles matching your keywords/ })).not.toBeInTheDocument();
});

it("labels a kept job that no longer matches the preferences", async () => {
  mockFetch({
    "GET /api/feed": () => json(makeFeed([makeCard({ match: null, draft_id: "draft-1" })])),
  });
  renderWithApp(feedRoutes(), { route: "/feed" });
  await screen.findByRole("link", { name: "Backend Engineer" });
  expect(screen.getByText(/No longer matches your Preferences/)).toBeInTheDocument();
});

it("shows matched skills beside the ones not in the Fact Bank", async () => {
  mockFetch({
    "GET /api/feed": () =>
      json(
        makeFeed([
          makeCard({
            title: "Backend Developer",
            skill_matches: ["Ruby on Rails", "PostgreSQL"],
            skill_gaps: ["Elasticsearch"],
            matched_keywords: [{ keyword: "Rails", where: "description", core: true }],
          }),
        ]),
      ),
  });
  renderWithApp(feedRoutes(), { route: "/feed" });
  await screen.findByRole("link", { name: "Backend Developer" });
  expect(screen.getByText("Matched:").parentElement).toHaveTextContent("Matched: Ruby on Rails, PostgreSQL");
  expect(screen.getByText("Not in your Fact Bank:").parentElement).toHaveTextContent("Not in your Fact Bank: Elasticsearch");
  expect(screen.getByText("Your keywords:")).toBeInTheDocument();
});

it("lists jobs without a description under Needs review", async () => {
  const calls = mockFetch({
    "GET /api/feed": (request) => {
      const review = queryOf(request).get("match") === "review";
      const page = makeFeed(review ? [makeCard({ title: "Ruby on Rails Developer", match: "review" })] : [makeCard()]);
      return json({ ...page, counts: { ...page.counts, title_matches: 1, keyword_matches: 0, review_matches: 1 } });
    },
  });
  renderWithApp(feedRoutes(), { route: "/feed" });
  await screen.findByRole("link", { name: "Backend Engineer" });
  expect(screen.queryByRole("button", { name: /Other titles matching your keywords/ })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /Needs review/ }));
  await screen.findByRole("link", { name: "Ruby on Rails Developer" });
  expect(screen.getByText(/the description or skill context is not confirmed yet/)).toBeInTheDocument();
  expect(calls.some((c) => queryOf(c).get("match") === "review")).toBe(true);
});

it("keeps source health notices off the Feed and does not request them", async () => {
  const calls = mockFetch({
    "GET /api/feed": () => json(makeFeed([makeCard()])),
  });
  renderWithApp(feedRoutes(), { route: "/feed" });
  await screen.findByRole("link", { name: "Backend Engineer" });
  expect(screen.queryByText("LinkedIn searches are delayed")).not.toBeInTheDocument();
  expect(calls.some((call) => call.url.includes("/sources/notices"))).toBe(false);
});

it("puts the description first and names where it came from", async () => {
  mockFetch({
    "GET /api/jobs/job-1": () =>
      json(makeJob({
        description: "Responsibilities\n- Build billing APIs",
        description_origin: { kind: "page", url: "https://careers.acme.com/jobs/1", read_at: "2026-10-28T08:00:00Z" },
        experience_requirement: "3-5 years",
      })),
  });
  renderWithApp(feedRoutes(), { route: "/jobs/job-1" });
  expect(await screen.findByText("From your reviewed careers-page description")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Open description source" })).toHaveAttribute("href", "https://careers.acme.com/jobs/1");
  expect(screen.getByRole("heading", { name: "Responsibilities" })).toBeInTheDocument();
  expect(screen.getByText("Experience: 3-5 years")).toBeInTheDocument();
  // Listing details for everyone are collapsed below the description.
  expect(screen.getByText(/Sources and listing details/)).toBeInTheDocument();
});

it("returns to the same Feed filters from a Job", async () => {
  mockFetch({
    "GET /api/feed": () => json(makeFeed([makeCard()], { total: 60 })),
    "GET /api/jobs/job-1": () => json(makeJob()),
  });
  renderWithApp(feedRoutes(), { route: "/feed?q=rails&section=email&page=2" });
  await userEvent.click(await screen.findByRole("link", { name: "Backend Engineer" }));
  expect(await screen.findByRole("link", { name: "Back to feed" })).toHaveAttribute("href", "/feed?q=rails&section=email&page=2");
  await userEvent.click(screen.getByRole("link", { name: "Back to feed" }));
  await screen.findByRole("link", { name: "Backend Engineer" });
  expect(screen.getByLabelText("Search title or company")).toHaveValue("rails");
});

it("lists archived Drafts on the Job, so an earlier package stays reachable", async () => {
  mockFetch({
    "GET /api/jobs/job-1": () =>
      json(makeJob({ archived_drafts: [{ id: "d-old", created_at: "2026-10-01T10:00:00Z", current_version: 3 }] })),
  });
  renderWithApp(feedRoutes(), { route: "/jobs/job-1" });
  await userEvent.click(await screen.findByText("Archived Drafts (1)"));
  expect(screen.getByRole("link", { name: /version 3/ })).toHaveAttribute("href", "/drafts/d-old");
});


it("restores filters, section, match and pagination through bare Feed navigation", async () => {
  const calls = mockFetch({ "GET /api/feed": () => json(makeFeed([makeCard()], { total: 60 })) });
  const selected = "/feed?q=acme&location=India&work_mode=remote&source=greenhouse&within=7&section=link&match=keywords&page=2";
  renderWithApp(<Routes>
    <Route path="/feed" element={<><Link to="/away">Leave Feed</Link><FeedPage userId="u1" /></>} />
    <Route path="/away" element={<Link to="/feed">Main Feed</Link>} />
  </Routes>, { route: selected });
  await screen.findByRole("link", { name: "Backend Engineer" });
  await userEvent.click(screen.getByRole("link", { name: "Leave Feed" }));
  await userEvent.click(screen.getByRole("link", { name: "Main Feed" }));
  await screen.findByRole("link", { name: "Backend Engineer" });
  expect(screen.getByLabelText("Search title or company")).toHaveValue("acme");
  expect(screen.getByLabelText("Location")).toHaveValue("India");
  expect(screen.getByLabelText("Work mode")).toHaveValue("remote");
  expect(screen.getByLabelText("Source")).toHaveValue("greenhouse");
  expect(screen.getByLabelText("Posted within")).toHaveValue("7");
  expect(screen.getByRole("tab", { name: /Apply link only/ })).toHaveAttribute("aria-selected", "true");
  const request = queryOf(calls.filter(c => new URL(c.url).pathname === "/api/feed").at(-1)!);
  expect(request.get("offset")).toBe("20");
  expect(request.get("match")).toBe("keywords");
});

it("explicit Feed links override remembered filters and Clear stays cleared", async () => {
  sessionStorage.setItem("jw-feed-view:u1", "?q=old&page=3");
  mockFetch({ "GET /api/feed": () => json(makeFeed([makeCard()])) });
  renderWithApp(<FeedPage userId="u1" />, { route: "/feed?q=current" });
  await screen.findByRole("link", { name: "Backend Engineer" });
  expect(screen.getByLabelText("Search title or company")).toHaveValue("current");
  await userEvent.click(screen.getByRole("button", { name: "Clear" }));
  await waitFor(() => expect(sessionStorage.getItem("jw-feed-view:u1")).toBe(""));
  expect(screen.getByLabelText("Search title or company")).toHaveValue("");
});

it("does not restore another User's Feed view", async () => {
  sessionStorage.setItem("jw-feed-view:u1", "?q=private-search&page=3");
  const calls = mockFetch({ "GET /api/feed": () => json(makeFeed([makeCard()])) });
  renderWithApp(<FeedPage userId="u2" />, { route: "/feed" });
  await screen.findByRole("link", { name: "Backend Engineer" });
  expect(screen.getByLabelText("Search title or company")).toHaveValue("");
  expect(queryOf(calls.find(c => new URL(c.url).pathname === "/api/feed")!).get("offset")).toBe("0");
});

it("keeps search boxes in sync with browser Back without reapplying newer text", async () => {
  function Back() { const navigate = useNavigate(); return <button onClick={() => navigate(-1)}>Browser Back</button>; }
  const calls = mockFetch({ "GET /api/feed": () => json(makeFeed([makeCard()])) });
  renderWithApp(<><Back /><FeedPage /></>, { initialEntries: ["/feed?q=first&location=India", "/feed?q=second&location=London"] });
  await screen.findByRole("link", { name: "Backend Engineer" });
  await userEvent.click(screen.getByRole("button", { name: "Browser Back" }));
  expect(screen.getByLabelText("Search title or company")).toHaveValue("first");
  expect(screen.getByLabelText("Location")).toHaveValue("India");
  await new Promise(resolve => setTimeout(resolve, 400));
  expect(queryOf(calls.at(-1)!).get("q")).toBe("first");
  expect(queryOf(calls.at(-1)!).get("location")).toBe("India");
});


it("recovers a remembered page after results shrink to one page", async () => {
  sessionStorage.setItem("jw-feed-view:u1", "?q=rails&section=link&page=3");
  const calls = mockFetch({ "GET /api/feed": request => json(makeFeed(
    queryOf(request).get("offset") === "0" ? [makeCard()] : [], { total: 5 },
  )) });
  renderWithApp(<FeedPage userId="u1" />, { route: "/feed" });
  await screen.findByRole("link", { name: "Backend Engineer" });
  expect(screen.getByLabelText("Search title or company")).toHaveValue("rails");
  expect(screen.getByRole("tab", { name: /Apply link only/ })).toHaveAttribute("aria-selected", "true");
  await waitFor(() => expect(sessionStorage.getItem("jw-feed-view:u1")).toBe("?q=rails&section=link"));
  const offsets = calls.filter(c => new URL(c.url).pathname === "/api/feed").map(c => queryOf(c).get("offset"));
  expect(offsets).toEqual(["40", "0"]);
});

it("caps an out-of-range page at the last available page", async () => {
  mockFetch({ "GET /api/feed": request => json(makeFeed(
    queryOf(request).get("offset") === "20" ? [makeCard()] : [], { total: 25 },
  )) });
  renderWithApp(<FeedPage userId="u1" />, { route: "/feed?page=8&work_mode=remote" });
  await screen.findByRole("link", { name: "Backend Engineer" });
  expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
  expect(screen.getByLabelText("Work mode")).toHaveValue("remote");
});

it("keeps the current view when Feed is clicked in either navigation", async () => {
  mockFetch({ "GET /api/feed": () => json(makeFeed([makeCard()], { total: 60 })) });
  renderWithApp(<AppShell me={makeMe()}><FeedPage userId="u1" /></AppShell>, { route: "/feed?q=rails&page=2&section=link" });
  await screen.findByRole("link", { name: "Backend Engineer" });
  for (const name of ["Main", "Main mobile"]) {
    const link = within(screen.getByRole("navigation", { name })).getByRole("link", { name: "Feed" });
    expect(link).toHaveAttribute("href", "/feed?q=rails&page=2&section=link");
    await userEvent.click(link);
    expect(screen.getByLabelText("Search title or company")).toHaveValue("rails");
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();
  }
});

const feedPath = (c: Request) => new URL(c.url).pathname === "/api/feed";

it("saves a job from its card with a pressed bookmark and shows Viewed", async () => {
  document.cookie = "jw_csrf=t";
  let saved = false;
  const calls = mockFetch({
    "GET /api/feed": () => json(makeFeed([makeCard({ saved, viewed: true })], { counts: { with_email: 1, apply_link_only: 0, title_matches: 1, saved: saved ? 1 : 0 } })),
    "POST /api/feed/job-1/save": () => { saved = true; return new Response(null, { status: 204 }); },
  });
  renderWithApp(<FeedPage userId="u1" />, { route: "/feed" });
  const bookmark = await screen.findByRole("button", { name: "Save Backend Engineer" });
  expect(bookmark).toHaveAttribute("aria-pressed", "false");
  expect(screen.getAllByText("Viewed").some((el) => el.tagName === "SPAN")).toBe(true);
  await userEvent.click(bookmark);
  await waitFor(() => expect(screen.getByRole("button", { name: "Save Backend Engineer" })).toHaveAttribute("aria-pressed", "true"));
  expect(calls.some((c) => c.method === "POST" && new URL(c.url).pathname === "/api/feed/job-1/save")).toBe(true);
  expect(screen.getByRole("button", { name: "Saved (1)" })).toBeInTheDocument();
});

it("enters Saved without the Feed's filters, lists every bookmark and returns to the Feed's own view", async () => {
  const calls = mockFetch({
    "GET /api/feed": (request) => {
      const view = new URL(request.url).searchParams.get("view");
      return view === "saved"
        ? json(makeFeed([makeCard({ saved: true, hidden: true, expired: true, contact_email: null })], { total: 1, counts: { with_email: 0, apply_link_only: 0, saved: 3 } }))
        : json(makeFeed([makeCard()], { counts: { with_email: 1, apply_link_only: 0, title_matches: 1, saved: 3 } }));
    },
  });
  renderWithApp(<FeedPage userId="u1" />, { route: "/feed?q=rails&section=link" });
  await screen.findByRole("link", { name: "Backend Engineer" });
  await userEvent.click(screen.getByRole("button", { name: "Saved (3)" }));
  await screen.findByRole("heading", { name: "Saved jobs" });
  expect(screen.getByRole("button", { name: "Saved (3)" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("button", { name: "All jobs" })).toHaveAttribute("aria-pressed", "false");
  expect(screen.getByText(/Jobs you saved to come back to/)).toBeInTheDocument();
  const savedRequest = new URL(calls.filter(feedPath).at(-1)!.url).searchParams;
  expect(savedRequest.get("view")).toBe("saved");
  expect(savedRequest.get("q")).toBeNull();
  expect(screen.getByLabelText("Search title or company")).toHaveValue("");
  // No category or email/link tabs: nothing saved can look missing.
  expect(screen.queryByRole("tablist", { name: "Feed sections" })).toBeNull();
  expect(await screen.findByText("3 saved jobs, most recently saved first.")).toBeInTheDocument();
  expect(screen.getByText("Expired")).toBeInTheDocument();
  // The card says it is hidden; the view switch's Hidden button is the other match.
  expect(screen.getAllByText("Hidden").some((el) => el.tagName === "SPAN")).toBe(true);

  await userEvent.click(screen.getByRole("button", { name: "All jobs" }));
  await screen.findByRole("heading", { name: "Feed" });
  await waitFor(() => expect(screen.getByLabelText("Search title or company")).toHaveValue("rails"));
  const back = new URL(calls.filter(feedPath).at(-1)!.url).searchParams;
  expect(back.get("q")).toBe("rails");
  expect(back.get("view")).toBe("all");
});

it("counts a filtered shortlist against every bookmark", async () => {
  mockFetch({
    "GET /api/feed": () => json(makeFeed([makeCard({ saved: true })], { total: 1, counts: { with_email: 0, apply_link_only: 0, saved: 12 } })),
  });
  renderWithApp(<FeedPage userId="u1" />, { route: "/feed?view=saved&q=acme" });
  expect(await screen.findByText("Showing 1 of 12 saved jobs.")).toBeInTheDocument();
});

it("explains an empty shortlist, and a filtered one that hides bookmarks", async () => {
  mockFetch({
    "GET /api/feed": (request) =>
      json(makeFeed([], { total: 0, counts: { with_email: 0, apply_link_only: 0, saved: new URL(request.url).searchParams.get("q") ? 2 : 0 } })),
  });
  const { unmount } = renderWithApp(<FeedPage userId="u1" />, { route: "/feed?view=saved" });
  expect(await screen.findByText("No saved jobs yet")).toBeInTheDocument();
  unmount();
  renderWithApp(<FeedPage userId="u1" />, { route: "/feed?view=saved&q=zzz" });
  expect(await screen.findByText("No saved jobs match these filters")).toBeInTheDocument();
  await expectAccessible();
});

it("filters by viewing status", async () => {
  const calls = mockFetch({ "GET /api/feed": () => json(makeFeed([makeCard()])) });
  renderWithApp(<FeedPage userId="u1" />, { route: "/feed" });
  await screen.findByRole("link", { name: "Backend Engineer" });
  await userEvent.selectOptions(screen.getByLabelText("Viewing status"), "unviewed");
  await waitFor(() => expect(new URL(calls.filter(feedPath).at(-1)!.url).searchParams.get("viewed")).toBe("unviewed"));
  expect(screen.getByRole("button", { name: "Clear" })).toBeInTheDocument();
});

it("marks a Job viewed once its page has loaded, and saves it from the page", async () => {
  document.cookie = "jw_csrf=t";
  let saved = false;
  const calls = mockFetch({
    "GET /api/jobs/job-1": () => json(makeJob({ saved, viewed: false })),
    "POST /api/jobs/job-1/viewed": () => new Response(null, { status: 204 }),
    "POST /api/feed/job-1/save": () => { saved = true; return new Response(null, { status: 204 }); },
  });
  renderWithApp(feedRoutes(), { route: "/jobs/job-1" });
  const save = await screen.findByRole("button", { name: "Save" });
  await waitFor(() => expect(calls.filter((c) => c.method === "POST" && new URL(c.url).pathname === "/api/jobs/job-1/viewed")).toHaveLength(1));
  expect(save).toHaveAttribute("aria-pressed", "false");
  await userEvent.click(save);
  expect(await screen.findByRole("button", { name: "Saved" })).toHaveAttribute("aria-pressed", "true");
  expect(calls.filter((c) => c.method === "POST" && new URL(c.url).pathname === "/api/jobs/job-1/viewed")).toHaveLength(1);
});

it("does not report a Job viewed again", async () => {
  const calls = mockFetch({ "GET /api/jobs/job-1": () => json(makeJob({ viewed: true })) });
  renderWithApp(feedRoutes(), { route: "/jobs/job-1" });
  await screen.findByRole("button", { name: "Save" });
  expect(calls.some((c) => c.method === "POST")).toBe(false);
});

it("returns to the card that was opened", async () => {
  const scrollTo = vi.fn();
  vi.stubGlobal("scrollTo", scrollTo);
  mockFetch({
    "GET /api/feed": () => json(makeFeed([makeCard()])),
    "GET /api/jobs/job-1": () => json(makeJob()),
  });
  renderWithApp(feedRoutes(), { route: "/feed?q=rails" });
  Object.defineProperty(window, "scrollY", { value: 640, configurable: true });
  await userEvent.click(await screen.findByRole("link", { name: "Backend Engineer" }));
  await userEvent.click(await screen.findByRole("link", { name: "Back to feed" }));
  await screen.findByRole("link", { name: "Backend Engineer" });
  await waitFor(() => expect(scrollTo).toHaveBeenCalledWith(0, 640));
  Object.defineProperty(window, "scrollY", { value: 0, configurable: true });
});


it("shows literal keyword evidence on the Job page without interpreting markup", async () => {
  mockFetch({
    "GET /api/jobs/job-1": () => json(makeJob({
      keyword_evidence: { Rails: "Build rails APIs. <script>not executable</script>" },
    })),
  });
  renderWithApp(feedRoutes(), { route: "/jobs/job-1" });
  await screen.findByRole("heading", { name: "Backend Engineer" });
  const summary = screen.getByText("Why these keywords matched");
  expect(summary.closest("details")).not.toHaveAttribute("open");
  await userEvent.click(summary);
  expect(screen.getByText("Build rails APIs. <script>not executable</script>")).toBeVisible();
  expect(document.querySelector("script")).toBeNull();
});
