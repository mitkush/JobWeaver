import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { PreferencesForm } from "@/features/preferences/PreferencesForm";
import { validatePreferences } from "@/features/preferences/validate";

import { json, mockFetch, renderWithApp } from "./utils";

afterEach(() => vi.unstubAllGlobals());

it("validates the three required parts", () => {
  const base = { titles: ["Engineer"], keywords: [], locations: [{ country: "IN", city: null }], work_modes: ["remote" as const] };
  expect(validatePreferences(base)).toBeNull();
  expect(validatePreferences({ ...base, titles: [] })).toMatch(/job title/);
  expect(validatePreferences({ ...base, locations: [] })).toMatch(/location/);
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
  await user.type(screen.getByLabelText("City"), "Bengaluru{Enter}");
  await user.click(screen.getByRole("button", { name: "Remote" }));
  await user.click(screen.getByRole("button", { name: "Save preferences" }));

  expect(onSaved).toHaveBeenCalled();
  const body = await calls.find((c) => c.method === "PUT")?.json();
  expect(body).toEqual({
    titles: ["Backend Engineer"],
    keywords: [],
    locations: [{ country: "IN", city: "Bengaluru" }],
    work_modes: ["remote"],
  });
});
