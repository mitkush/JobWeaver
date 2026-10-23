import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { ApplicationProfilePage } from "@/pages/ApplicationProfilePage";
import { SavedAnswersPage } from "@/pages/SavedAnswersPage";

import { expectAccessible, json, mockFetch, renderWithApp } from "./utils";

const suggestion = {
  first_name: "Asha",
  last_name: "Rao",
  email: "asha@example.com",
  phone: "+91 98765 43210",
  phone_fact_id: "f-phone",
  city: "",
  country: "IN",
  links: [{ label: "linkedin", url: "https://linkedin.com/in/asha", fact_id: "f-link" }],
  employment: [
    { employer: "Acme Corp", title: "Senior Developer", location: "", start: "2023-03", end: null, current: true, fact_ids: ["f-role"] },
  ],
  education: [],
};

it("starts from the Fact Bank and saves the reviewed profile", async () => {
  document.cookie = "jw_csrf=t";
  const calls = mockFetch({
    "GET /api/profile": () => json({ content: null, version: 0, reviewed_at: null, stale: [] }),
    "GET /api/profile/suggestion": () => json(suggestion),
    "PUT /api/profile": async (request) => {
      const body = (await request.clone().json()) as { content: unknown };
      return json({ content: body.content, version: 1, reviewed_at: "2026-10-23T10:00:00Z", stale: [] });
    },
  });
  const user = userEvent.setup();
  renderWithApp(<ApplicationProfilePage />);

  expect(await screen.findByText("Not reviewed yet")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Fill from Fact Bank" }));
  expect(await screen.findByDisplayValue("Acme Corp")).toBeInTheDocument();
  expect(screen.getByLabelText("Phone")).toHaveValue("+91 98765 43210");

  await user.type(screen.getByLabelText("City"), "Bengaluru");
  await user.click(screen.getByRole("button", { name: "Save and mark reviewed" }));
  expect(await screen.findByText(/Profile saved/)).toBeInTheDocument();

  const put = calls.find((c) => c.method === "PUT")!;
  const body = (await put.json()) as { content: typeof suggestion; expected_version: number };
  expect(body.expected_version).toBe(0);
  expect(body.content.city).toBe("Bengaluru");
  expect(body.content.employment[0]!.fact_ids).toEqual(["f-role"]);
  await expectAccessible();
});

it("highlights entries whose Facts changed and blocks invalid dates", async () => {
  mockFetch({
    "GET /api/profile": () =>
      json({ content: suggestion, version: 3, reviewed_at: "2026-10-01T10:00:00Z", stale: ["employment.0"] }),
  });
  const user = userEvent.setup();
  renderWithApp(<ApplicationProfilePage />);

  expect(await screen.findByText("Your Fact Bank changed")).toBeInTheDocument();
  expect(screen.getByText("The Fact behind this changed. Check it.")).toBeInTheDocument();

  const start = screen.getByLabelText("Start");
  await user.clear(start);
  await user.type(start, "March 2023");
  expect(start).toHaveAttribute("aria-invalid", "true");
  expect(screen.getByRole("button", { name: "Save and mark reviewed" })).toBeDisabled();
});

it("says so when the profile changed in another tab", async () => {
  document.cookie = "jw_csrf=t";
  mockFetch({
    "GET /api/profile": () => json({ content: suggestion, version: 2, reviewed_at: "2026-10-01T10:00:00Z", stale: [] }),
    "PUT /api/profile": () => json({ error: { code: "conflict", message: "changed" } }, 409),
  });
  const user = userEvent.setup();
  renderWithApp(<ApplicationProfilePage />);
  await user.click(await screen.findByRole("button", { name: "Save and mark reviewed" }));
  expect(await screen.findByText(/changed in another tab/)).toBeInTheDocument();
});

it("saves a salary answer for one country and keeps the form when the server refuses", async () => {
  document.cookie = "jw_csrf=t";
  let posts = 0;
  const calls = mockFetch({
    "GET /api/saved-answers": () => json([]),
    "POST /api/saved-answers": () =>
      ++posts === 1
        ? json({ error: { code: "conflict", message: "You already saved an answer to this question for the same scope" } }, 409)
        : json({}, 201),
  });
  const user = userEvent.setup();
  renderWithApp(<SavedAnswersPage />);

  await user.click(await screen.findByRole("button", { name: "Add answer" }));
  await user.type(screen.getByLabelText("Question"), "Expected salary?");
  await user.type(screen.getByLabelText("Your answer"), "30 LPA");
  await user.selectOptions(screen.getByLabelText("Use it for"), "country");
  await user.type(screen.getByLabelText("Salary currency"), "inr");
  const save = screen.getByRole("button", { name: "Save answer" });
  expect(save).toBeDisabled(); // a currency needs a period
  await user.selectOptions(screen.getByLabelText("Salary period"), "year");
  await user.click(screen.getByRole("checkbox"));

  await user.click(save);
  expect(await screen.findByText(/already saved an answer/)).toBeInTheDocument();
  expect(screen.getByLabelText("Question")).toHaveValue("Expected salary?");

  await user.click(screen.getByRole("button", { name: "Save answer" }));
  expect(await screen.findByText("Answer saved")).toBeInTheDocument();
  const body = (await calls.filter((c) => c.method === "POST").at(-1)!.json()) as Record<string, unknown>;
  expect(body).toMatchObject({ scope: "country", country: "IN", currency: "INR", period: "year", sensitive: true });
});

it("lists answers with where they apply", async () => {
  mockFetch({
    "GET /api/saved-answers": () =>
      json([
        {
          id: "a1",
          question: "Why us?",
          answer: "Billing at scale",
          scope: "company",
          country: null,
          currency: null,
          period: null,
          company_id: "c1",
          company_name: "Acme",
          sensitive: false,
          origin: "user",
          job_id: null,
          updated_at: "2026-10-23T10:00:00Z",
        },
      ]),
  });
  renderWithApp(<SavedAnswersPage />);
  expect(await screen.findByText("Only for Acme")).toBeInTheDocument();
  await expectAccessible();
});
