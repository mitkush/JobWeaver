import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { SettingsPage } from "@/pages/SettingsPage";

import { expectAccessible, json, makeMe, mockFetch, renderWithApp } from "./utils";

it("saves how long to wait before a follow-up reminder", async () => {
  document.cookie = "jw_csrf=t";
  const me = makeMe();
  const calls = mockFetch({
    "GET /api/ats-boards": () => json([]),
    "PUT /api/me/follow-up-days": () => json({ ...me, follow_up_days: 10 }),
  });
  const user = userEvent.setup();
  renderWithApp(<SettingsPage me={me} />);
  const days = screen.getByLabelText("Days to wait");
  expect(days).toHaveValue(7);
  const save = screen.getByRole("button", { name: "Save" });
  expect(save).toBeDisabled();

  await user.clear(days);
  await user.type(days, "0");
  expect(days).toHaveAttribute("aria-invalid", "true");
  expect(save).toBeDisabled();

  await user.clear(days);
  await user.type(days, "10");
  await user.click(save);
  expect(await screen.findByText("Follow-up reminder saved")).toBeInTheDocument();
  const put = calls.find((c) => c.method === "PUT")!;
  expect(await put.json()).toEqual({ days: 10 });
  await expectAccessible();
});
