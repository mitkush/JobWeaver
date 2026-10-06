import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import type { Me } from "@/api/client";
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
