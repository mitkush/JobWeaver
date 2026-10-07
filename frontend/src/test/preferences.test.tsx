import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { PreferencesForm } from "@/features/preferences/PreferencesForm";
import { validatePreferences } from "@/features/preferences/validate";

import { json, mockFetch, renderWithApp, expectAccessible } from "./utils";

afterEach(() => vi.unstubAllGlobals());

it("requires titles and work modes and accepts global locations", () => {
  const base = { titles: ["Engineer"], keywords: [], locations: [{ country: "IN", city: null }], work_modes: ["remote" as const] };
  expect(validatePreferences(base)).toBeNull();
  expect(validatePreferences({ ...base, titles: [] })).toMatch(/job title/);
  expect(validatePreferences({ ...base, locations: [] })).toBeNull();
  expect(validatePreferences({ ...base, work_modes: [] })).toMatch(/work mode/);
});

it("saves titles, locations and work modes", async () => {
  document.cookie = "jw_csrf=t";
  const calls = mockFetch({
    "PUT /api/preferences": async (r) => json(await r.json()),
    "GET /api/me": () => json({}),
  });
  const onSaved = vi.fn();
  const user = userEvent.setup();
  renderWithApp(<PreferencesForm onSaved={onSaved} />);

  await user.click(screen.getByRole("button", { name: "Save preferences" }));
  expect(screen.getByRole("alert")).toHaveTextContent("Add at least one job title.");

  await user.type(screen.getByLabelText("Job titles"), "Backend Engineer{Enter}");
  await user.click(screen.getByRole("button", { name: "India" }));
  await user.type(screen.getByLabelText("City"), "Bengaluru{Enter}");
  await user.click(screen.getByRole("button", { name: "Remote (WFH)" }));
  await user.click(screen.getByRole("button", { name: "Save preferences" }));

  expect(onSaved).toHaveBeenCalled();
  const body = await calls.find((c) => c.method === "PUT")?.json();
  expect(body).toEqual({
    titles: ["Backend Engineer"],
    keywords: [],
    locations: [{ country: "IN", city: "Bengaluru" }],
    work_modes: ["remote"],
  });
  await expectAccessible();
});

it("saves global WFH preferences without choosing a country", async () => {
  document.cookie = "jw_csrf=t";
  const calls = mockFetch({
    "PUT /api/preferences": async (r) => json(await r.json()),
    "GET /api/me": () => json({}),
  });
  const user = userEvent.setup();
  const onSaved = vi.fn();
  renderWithApp(<PreferencesForm onSaved={onSaved} initial={{ titles: ["Engineer"], keywords: [], locations: [{ country: "IN", city: "Indore" }], work_modes: ["remote"] }} />);
  await user.click(screen.getByRole("button", { name: "Global (any country)" }));
  expect(screen.queryByLabelText("Country")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("City")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Save preferences" }));
  expect(onSaved).toHaveBeenCalled();
  expect(await calls.find((c) => c.method === "PUT")?.json()).toMatchObject({ locations: [], work_modes: ["remote"] });
});

it("saves India as a whole country without requiring Add location", async () => {
  document.cookie = "jw_csrf=t";
  const calls = mockFetch({
    "PUT /api/preferences": async (r) => json(await r.json()),
    "GET /api/me": () => json({}),
  });
  const user = userEvent.setup();
  renderWithApp(<PreferencesForm initial={{ titles: ["Engineer"], keywords: [], locations: [], work_modes: ["onsite"] }} />);
  await user.click(screen.getByRole("button", { name: "India" }));
  await user.click(screen.getByRole("button", { name: "Save preferences" }));
  expect(await calls.find((c) => c.method === "PUT")?.json()).toMatchObject({ locations: [{ country: "IN", city: null }] });
});

it("adds a specific overseas country alongside an Indian city", async () => {
  document.cookie = "jw_csrf=t";
  const calls = mockFetch({
    "PUT /api/preferences": async (r) => json(await r.json()),
    "GET /api/me": () => json({}),
  });
  const user = userEvent.setup();
  renderWithApp(<PreferencesForm initial={{ titles: ["Engineer"], keywords: [], locations: [{ country: "IN", city: "Indore" }], work_modes: ["remote"] }} />);
  await user.click(screen.getByRole("button", { name: "Other country" }));
  await user.selectOptions(screen.getByLabelText("Country"), "DE");
  await user.click(screen.getByRole("button", { name: "Add location" }));
  await user.click(screen.getByRole("button", { name: "Save preferences" }));
  expect(await calls.find((c) => c.method === "PUT")?.json()).toMatchObject({ locations: [{ country: "IN", city: "Indore" }, { country: "DE", city: null }] });
});

it("adds a city under India to India even when another country was saved first", async () => {
  document.cookie = "jw_csrf=t";
  const calls = mockFetch({
    "PUT /api/preferences": async (r) => json(await r.json()),
    "GET /api/me": () => json({}),
  });
  const user = userEvent.setup();
  renderWithApp(
    <PreferencesForm
      initial={{ titles: ["Engineer"], keywords: [], locations: [{ country: "DE", city: null }, { country: "IN", city: "Pune" }], work_modes: ["onsite"] }}
    />,
  );
  expect(screen.getByRole("button", { name: "India" })).toHaveAttribute("aria-pressed", "true");
  await user.type(screen.getByLabelText("City"), "Mumbai{Enter}");
  await user.click(screen.getByRole("button", { name: "Save preferences" }));
  expect(await calls.find((c) => c.method === "PUT")?.json()).toMatchObject({
    locations: [{ country: "DE", city: null }, { country: "IN", city: "Pune" }, { country: "IN", city: "Mumbai" }],
  });
});

it("keeps the places when switching to Global and back", async () => {
  const user = userEvent.setup();
  renderWithApp(
    <PreferencesForm initial={{ titles: ["Engineer"], keywords: [], locations: [{ country: "IN", city: "Indore" }], work_modes: ["remote"] }} />,
  );
  await user.click(screen.getByRole("button", { name: "Global (any country)" }));
  expect(screen.getByText(/kept if you switch back/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "India" }));
  expect(screen.getByRole("button", { name: "Remove Indore, India" })).toBeInTheDocument();
});
