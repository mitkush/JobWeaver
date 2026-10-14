import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import type { Fact } from "@/api/client";
import { FactBankEditor } from "@/features/fact-bank/FactBankEditor";

import { json, mockFetch, renderWithApp, expectAccessible } from "./utils";

afterEach(() => vi.unstubAllGlobals());

const fact = (id: string, text: string, extra: Partial<Fact> = {}): Fact => ({
  id,
  kind: "skill",
  group: "",
  text,
  source_kind: "resume",
  in_base_resume: true,
  origin: "ai",
  edited: false,
  ...extra,
});

const FACTS = [
  fact("1", "Python"),
  fact("2", "Kafka", { in_base_resume: false, source_kind: "portfolio" }),
  fact("3", "Built the billing API", { kind: "experience", group: "Acme" }),
];

it("groups Facts by kind and marks portfolio-only Facts", async () => {
  renderWithApp(<FactBankEditor facts={FACTS} />);
  const skills = screen.getByRole("region", { name: /Skills/ });
  expect(within(skills).getByText("Kafka")).toBeInTheDocument();
  expect(within(skills).getByText("Not in your resume")).toBeInTheDocument();
  expect(screen.getByRole("region", { name: /Experience/ })).toHaveTextContent("Acme");
  await expectAccessible();
});

it("merges selected Facts after confirmation", async () => {
  document.cookie = "jw_csrf=t";
  const calls = mockFetch({
    "POST /api/facts/merge": () => json(fact("9", "Python; Kafka", { origin: "user" })),
    "GET /api/facts": () => json([]),
    "GET /api/documents": () => json([]),
    "GET /api/me": () => json({}),
  });
  const user = userEvent.setup();
  renderWithApp(<FactBankEditor facts={FACTS} />);

  await user.click(screen.getByLabelText('Select "Python" to merge'));
  await user.click(screen.getByLabelText('Select "Kafka" to merge'));
  await user.click(screen.getByRole("button", { name: "Merge into one" }));
  expect(screen.getByLabelText("Merged Fact text")).toHaveValue("Python; Kafka");
  await user.click(screen.getByRole("button", { name: "Merge" }));

  const merge = calls.find((c) => c.url.endsWith("/api/facts/merge"));
  expect(await merge?.json()).toEqual({ fact_ids: ["1", "2"], text: "Python; Kafka" });
});

it("keeps project Facts grouped and prevents merging different projects", async () => {
  const user = userEvent.setup();
  const facts = [
    fact("p1", "Built payroll", { kind: "project", group: "Payroll" }),
    fact("p2", "Built commerce", { kind: "project", group: "Commerce" }),
  ];
  renderWithApp(<FactBankEditor facts={facts} />);
  await user.click(screen.getByLabelText('Select "Built payroll" to merge'));
  await user.click(screen.getByLabelText('Select "Built commerce" to merge'));
  expect(screen.getByRole("button", { name: "Merge into one" })).toBeDisabled();
  expect(screen.getByText(/same section and employer or project/)).toBeInTheDocument();
});

it("sends a project name when adding a project Fact", async () => {
  document.cookie = "jw_csrf=t";
  const calls = mockFetch({
    "POST /api/facts": () => json(fact("p3", "Built a dashboard", { kind: "project", group: "Payroll" }), 201),
    "GET /api/facts": () => json([]),
    "GET /api/documents": () => json([]),
    "GET /api/me": () => json({}),
  });
  const user = userEvent.setup();
  renderWithApp(<FactBankEditor facts={FACTS} />);
  const projects = screen.getByRole("region", { name: /Projects/ });
  await user.type(within(projects).getByLabelText("Group for Projects"), "Payroll");
  await user.type(within(projects).getByLabelText("Add to Projects"), "Built a dashboard");
  await user.click(within(projects).getByRole("button", { name: "Add" }));
  const request = calls.find((call) => call.url.endsWith("/api/facts") && call.method === "POST");
  expect(await request?.json()).toEqual({ kind: "project", group: "Payroll", text: "Built a dashboard" });
});

it("asks before deleting a Fact", async () => {
  const calls = mockFetch({});
  const user = userEvent.setup();
  renderWithApp(<FactBankEditor facts={FACTS} />);
  await user.click(screen.getByRole("button", { name: 'Delete "Python"' }));
  expect(screen.getByText("Delete this Fact?")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(calls).toHaveLength(0);
});
