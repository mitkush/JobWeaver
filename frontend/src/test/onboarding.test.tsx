import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "@/app/App";
import { furthestStep } from "@/pages/onboarding-steps";
import { OnboardingPage } from "@/pages/OnboardingPage";

import { json, makeMe, mockFetch, renderWithApp } from "./utils";

afterEach(() => vi.unstubAllGlobals());

describe("furthestStep", () => {
  it.each([
    ["ai_notice", "notice"],
    ["region_blocked", "country"],
    ["review", "review"],
    ["done", "gmail"],
  ] as const)("maps %s to %s", (next, step) => {
    expect(furthestStep(makeMe({ next_step: next }))).toBe(step);
  });
});

function renderOnboarding(route: string, next: string) {
  const me = makeMe({ next_step: next });
  return renderWithApp(
    <Routes>
      <Route path="/onboarding/:step?" element={<OnboardingPage me={me} />} />
    </Routes>,
    { route },
  );
}

describe("OnboardingPage", () => {
  it("starts new users at the AI notice", async () => {
    renderOnboarding("/onboarding", "ai_notice");
    expect(await screen.findByText("How your documents are used")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "I understand, continue" })).toBeInTheDocument();
  });

  it("does not let users skip ahead of their progress", async () => {
    mockFetch({ "GET /api/documents": () => json([]) });
    renderOnboarding("/onboarding/preferences", "documents");
    expect(await screen.findByText("Add your documents")).toBeInTheDocument();
  });

  it("explains the region block on the country step", async () => {
    const me = makeMe({ next_step: "region_blocked", ai_region_blocked: true });
    renderWithApp(
      <Routes>
        <Route path="/onboarding/:step?" element={<OnboardingPage me={me} />} />
      </Routes>,
      { route: "/onboarding/country" },
    );
    expect(await screen.findByText("Not available in your region yet")).toBeInTheDocument();
  });
});

describe("App routing", () => {
  it("sends signed-out visitors to sign-in", async () => {
    mockFetch({ "GET /api/me": () => json({ error: { code: "unauthenticated", message: "Please sign in" } }, 401) });
    renderWithApp(<App />, { route: "/feed" });
    expect(await screen.findByRole("link", { name: "Sign in with Google" })).toBeInTheDocument();
  });

  it("sends users who have not finished setup to onboarding", async () => {
    mockFetch({ "GET /api/me": () => json(makeMe({ next_step: "ai_notice", ai_notice_accepted: false })) });
    renderWithApp(<App />, { route: "/feed" });
    expect(await screen.findByText("Set up JobWeaver")).toBeInTheDocument();
  });

  it("shows the Feed with a helpful empty state once setup is done", async () => {
    mockFetch({ "GET /api/me": () => json(makeMe()) });
    renderWithApp(<App />, { route: "/feed" });
    expect(await screen.findByText("No jobs yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review your preferences" })).toBeInTheDocument();
  });

  it("warns when Gmail access has expired", async () => {
    const me = { ...makeMe(), gmail: { state: "expired" as const, expires_at: "2026-10-01T00:00:00Z" } };
    mockFetch({ "GET /api/me": () => json(me) });
    renderWithApp(<App />, { route: "/feed" });
    expect(await screen.findByText(/Gmail access ended/)).toBeInTheDocument();
  });
});
