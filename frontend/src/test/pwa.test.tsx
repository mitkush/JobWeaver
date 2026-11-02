import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { InstallCard } from "@/features/pwa/InstallCard";
import { registerInstallPrompt } from "@/features/pwa/install";

beforeEach(() => {
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
  registerInstallPrompt();
});
afterEach(() => vi.unstubAllGlobals());

function offer(outcome: "accepted" | "dismissed" = "dismissed", fails = false) {
  const event = new Event("beforeinstallprompt", { cancelable: true });
  const prompt = fails ? vi.fn().mockRejectedValue(new Error("blocked")) : vi.fn().mockResolvedValue(undefined);
  Object.assign(event, { prompt, userChoice: Promise.resolve({ outcome }) });
  act(() => { window.dispatchEvent(event); });
  expect(event.defaultPrevented).toBe(true);
  return prompt;
}
it("retains an install offer before Settings opens and permits retry after dismissal", async () => {
  const prompt = offer();
  render(<InstallCard />);
  await userEvent.click(screen.getByRole("button", { name: "Install app" }));
  expect(prompt).toHaveBeenCalledOnce();
  expect(await screen.findByRole("status")).toHaveTextContent("install later");
  expect(screen.queryByRole("button", { name: "Install app" })).not.toBeInTheDocument();
  offer();
  expect(screen.getByRole("button", { name: "Install app" })).toBeEnabled();
});
it("shows a recoverable prompt error", async () => {
  offer("dismissed", true);
  render(<InstallCard />);
  await userEvent.click(screen.getByRole("button", { name: "Install app" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Installation could not open");
});
it("does not call an accepted prompt installed until the browser confirms it", async () => {
  offer("accepted");
  render(<InstallCard />);
  await userEvent.click(screen.getByRole("button", { name: "Install app" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Installation accepted");
  act(() => { window.dispatchEvent(new Event("appinstalled")); });
  expect(screen.getByText("JobWeaver is installed on this device.")).toBeInTheDocument();
});
