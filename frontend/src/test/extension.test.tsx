import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { ExtensionCard } from "@/features/extension/ExtensionCard";
import { ExtensionConnectPage } from "@/pages/ExtensionConnectPage";

import { expectAccessible, json, makeMe, mockFetch, renderWithApp } from "./utils";

const EXT = "abcdefghijklmnopabcdefghijklmnop";
const CHALLENGE = "A".repeat(43);
const route = `/extension/connect?extension_id=${EXT}&challenge=${CHALLENGE}`;

function stubExtension(reply: unknown) {
  const sendMessage = vi.fn((_id: string, _message: unknown, callback: (reply: unknown) => void) => callback(reply));
  vi.stubGlobal("chrome", { runtime: { sendMessage } });
  return sendMessage;
}

afterEach(() => vi.unstubAllGlobals());

it("approves the connection and hands the one-time code to that extension only", async () => {
  document.cookie = "jw_csrf=t";
  const calls = mockFetch({
    "POST /api/extension/approve": () => json({ code: "one-time-code", expires_at: "2026-10-24T10:00:00Z" }),
  });
  const sendMessage = stubExtension({ ok: true, email: "asha@example.com" });
  const user = userEvent.setup();
  renderWithApp(<ExtensionConnectPage me={makeMe()} />, { route });

  expect(screen.getByText("See your name and email")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Connect extension" }));

  expect(await screen.findByText(/connected as asha@example.com/)).toBeInTheDocument();
  expect(await calls[0]!.json()).toEqual({ extension_id: EXT, challenge: CHALLENGE });
  expect(sendMessage).toHaveBeenCalledWith(EXT, { type: "jobweaver.connect", code: "one-time-code" }, expect.any(Function));
  await expectAccessible();
});

it("explains when the extension is missing instead of claiming success", async () => {
  document.cookie = "jw_csrf=t";
  mockFetch({ "POST /api/extension/approve": () => json({ code: "c", expires_at: "2026-10-24T10:00:00Z" }) });
  const user = userEvent.setup();
  renderWithApp(<ExtensionConnectPage me={makeMe()} />, { route });
  await user.click(screen.getByRole("button", { name: "Connect extension" }));
  expect(await screen.findByText(/Open this page from the JobWeaver extension/)).toBeInTheDocument();
  expect(screen.queryByText("Connected")).not.toBeInTheDocument();
});

it("refuses a malformed connection link without calling the API", () => {
  const calls = mockFetch({});
  renderWithApp(<ExtensionConnectPage me={makeMe()} />, { route: "/extension/connect?extension_id=evil" });
  expect(screen.getByText("This connection link is not valid")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Connect extension" })).not.toBeInTheDocument();
  expect(calls).toHaveLength(0);
});

it("lists connections in Settings and revokes one after confirmation", async () => {
  document.cookie = "jw_csrf=t";
  const now = new Date().toISOString();
  let connections = [
    { id: "c1", extension_id: EXT, created_at: now, last_used_at: now, expires_at: new Date(Date.now() + 3_600_000).toISOString() },
  ];
  const calls = mockFetch({
    "GET /api/extension/connections": () => json(connections),
    "DELETE /api/extension/connections/c1": () => {
      connections = [];
      return new Response(null, { status: 204 });
    },
  });
  const user = userEvent.setup();
  renderWithApp(<ExtensionCard />);

  await user.click(await screen.findByRole("button", { name: "Revoke" }));
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Revoke" }));
  expect(await screen.findByText(/No extension is connected/)).toBeInTheDocument();
  expect(calls.some((c) => c.method === "DELETE")).toBe(true);
});

