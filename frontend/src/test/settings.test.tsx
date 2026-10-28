import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { ExtensionPrivacyPage } from "@/pages/ExtensionPrivacyPage";
import { SettingsPage } from "@/pages/SettingsPage";

import { expectAccessible, json, makeMe, mockFetch, renderWithApp } from "./utils";

it("saves how long to wait before a follow-up reminder", async () => {
  document.cookie = "jw_csrf=t";
  const me = makeMe();
  const calls = mockFetch({
    "GET /api/ats-boards": () => json([]),
    "GET /api/extension/connections": () => json([]),
    "GET /api/profile": () => json({ content: null, version: 0, reviewed_at: null, stale: [] }),
    "GET /api/saved-answers": () => json([]),
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

const settingsRoutes = {
  "GET /api/gmail/status": () => json({ state: "disconnected", expires_at: null }),
  "GET /api/ats-boards": () => json([]),
  "GET /api/extension/connections": () => json([]),
  "GET /api/profile": () => json({ content: null, version: 0, reviewed_at: null, stale: [] }),
  "GET /api/saved-answers": () => json([]),
};

it("links to the store listing once the extension is published, else explains the unpacked install", async () => {
  mockFetch(settingsRoutes);
  const { unmount } = renderWithApp(<SettingsPage me={{ ...makeMe(), extension_store_url: "https://chromewebstore.google.com/detail/jobweaver/abc" }} />);
  const link = await screen.findByRole("link", { name: "Get the extension" });
  expect(link).toHaveAttribute("href", "https://chromewebstore.google.com/detail/jobweaver/abc");
  expect(screen.getByRole("link", { name: "Extension privacy policy" })).toHaveAttribute("href", "/privacy/extension");
  unmount();

  renderWithApp(<SettingsPage me={makeMe()} />);
  expect(await screen.findByText(/load it unpacked/)).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Get the extension" })).toBeNull();
});

it("publishes the extension privacy policy without signing in", async () => {
  renderWithApp(<ExtensionPrivacyPage />);
  expect(screen.getByRole("heading", { name: "Browser extension privacy policy" })).toBeInTheDocument();
  expect(screen.getByText(/never submits a form/)).toBeInTheDocument();
  expect(screen.getByText(/Limited Use requirements/)).toBeInTheDocument();
  await expectAccessible();
});
