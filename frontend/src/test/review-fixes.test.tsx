import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { Fact } from "@/api/client";
import { ToastProvider } from "@/components/ui/toast";
import { DocumentUploader } from "@/features/fact-bank/DocumentUploader";
import { FactBankEditor } from "@/features/fact-bank/FactBankEditor";
import { SignInPage } from "@/pages/SignInPage";

import { json, mockFetch, renderWithApp } from "./utils";

afterEach(() => vi.unstubAllGlobals());

const fact = (id: string, text: string): Fact => ({
  id, kind: "skill", group: "", text, source_kind: "resume", in_base_resume: true, origin: "ai", edited: false,
});

it("never sends a deleted Fact's id when merging", async () => {
  document.cookie = "jw_csrf=t";
  const calls = mockFetch({
    "POST /api/facts/merge": () => json(fact("9", "merged")),
    "GET /api/facts": () => json([]),
    "GET /api/documents": () => json([]),
    "GET /api/me": () => json({}),
  });
  const client = new QueryClient();
  const wrap = (facts: Fact[]) => (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ToastProvider>
          <FactBankEditor facts={facts} />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
  const user = userEvent.setup();
  const view = render(wrap([fact("1", "Python"), fact("2", "Kafka"), fact("3", "Go")]));
  for (const name of ["Python", "Kafka", "Go"]) await user.click(screen.getByLabelText(`Select "${name}" to merge`));
  // "Kafka" is deleted elsewhere; the list re-renders without it.
  view.rerender(wrap([fact("1", "Python"), fact("3", "Go")]));
  expect(screen.getByText("2 Facts selected")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Merge into one" }));
  await user.click(screen.getByRole("button", { name: "Merge" }));
  const merge = calls.find((c) => c.url.endsWith("/api/facts/merge"));
  expect(merge).toBeDefined();
  expect((await merge!.json()).fact_ids).toEqual(["1", "3"]);
});

it("shows the retry's own error when trying again fails", async () => {
  document.cookie = "jw_csrf=t";
  mockFetch({
    "POST /api/documents": () =>
      json({ error: { code: "ai_unavailable", message: "Your document is saved, but building failed." } }, 503),
    "POST /api/fact-bank/rebuild": () =>
      json({ error: { code: "ai_unavailable", message: "All AI providers are busy." } }, 503),
    "GET /api/facts": () => json([]),
    "GET /api/documents": () => json([]),
    "GET /api/me": () => json({}),
  });
  const user = userEvent.setup();
  renderWithApp(<DocumentUploader documents={[]} />);
  await user.upload(screen.getByLabelText("Upload resume"), new File(["resume text here"], "r.txt", { type: "text/plain" }));
  expect(await screen.findByText("Your document is saved, but building failed.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("All AI providers are busy.")).toBeInTheDocument();
  expect(screen.getByText("Trying again did not work")).toBeInTheDocument();
});

it("explains a sign-in link opened in another browser", () => {
  renderWithApp(<SignInPage />, { route: "/sign-in?google_error=state" });
  expect(screen.getByText(/not started in this browser/)).toBeInTheDocument();
});
