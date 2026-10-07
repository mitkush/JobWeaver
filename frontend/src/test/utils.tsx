import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import axe from "axe-core";
import { expect, vi } from "vitest";

import type { FeedCard, FeedPage, Me } from "@/api/client";
import { ToastProvider } from "@/components/ui/toast";

type Handler = (request: Request) => Response | Promise<Response>;

/** Routes fetch calls by "METHOD /path" and records every request. */
export function mockFetch(routes: Record<string, Handler>) {
  const calls: Request[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(new URL(String(input), "http://localhost"), init);
    calls.push(request.clone());
    const key = `${request.method} ${new URL(request.url).pathname}`;
    const handler = routes[key];
    if (!handler) return json({ error: { code: "not_found", message: `No mock for ${key}` } }, 404);
    return handler(request);
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

export function renderWithApp(ui: ReactElement, { route = "/" }: { route?: string } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <ToastProvider>{ui}</ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

export function makeMe(overrides: Partial<Me["onboarding"]> = {}): Me {
  return {
    id: "u1",
    email: "asha@example.com",
    name: "Asha",
    picture_url: null,
    role: "user",
    follow_up_days: 7,
    country: "IN",
    gmail: { state: "not_connected", expires_at: null },
    onboarding: {
      ai_notice_accepted: true,
      country_set: true,
      ai_region_blocked: false,
      documents_uploaded: true,
      fact_bank_reviewed: true,
      preferences_set: true,
      gmail_connected: false,
      next_step: "done",
      ...overrides,
    },
  };
}

export function makeCard(overrides: Partial<FeedCard> = {}): FeedCard {
  return {
    job_id: "job-1",
    title: "Backend Engineer",
    company: "Acme",
    locations: [{ city: "Bengaluru", country: "IN", remote: false }],
    work_mode: "hybrid",
    posted_at: new Date(Date.now() - 2 * 3_600_000).toISOString(),
    sources: [
      { name: "linkedin", label: "LinkedIn (Bright Data)" },
      { name: "greenhouse", label: "Greenhouse" },
    ],
    contact_email: "jobs@acme.com",
    apply_url: "https://boards.greenhouse.io/acme/jobs/1",
    skill_gaps: ["Kubernetes", "Go"],
    possible_duplicate: false,
    hidden: false,
    ...overrides,
  };
}

export function makeFeed(items: FeedCard[] = [], overrides: Partial<FeedPage> = {}): FeedPage {
  const withEmail = items.filter((c) => c.contact_email).length;
  return {
    items,
    total: items.length,
    counts: { with_email: withEmail, apply_link_only: items.length - withEmail },
    last_updated_at: null,
    sources: [
      { name: "linkedin", label: "LinkedIn (Bright Data)" },
      { name: "greenhouse", label: "Greenhouse" },
    ],
    ...overrides,
  };
}

/** WCAG 2.1 AA checks with axe-core (PRD section 7). Colour contrast needs a real browser,
 * and pages here render without the app shell's landmarks, so those two rules are off. */
export async function expectAccessible(root: Element = document.body) {
  const results = await axe.run(root, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] },
    rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
  });
  const found = results.violations.map(
    (v) => `${v.id} (${v.impact}): ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`,
  );
  expect(found).toEqual([]);
}
