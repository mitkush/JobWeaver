import { createHash } from "node:crypto";

import { expect, it } from "vitest";

import { buildManifest, matchPattern, PUBLIC_KEY } from "../manifest";

it("derives the fixed extension ID the server allows", () => {
  const der = Buffer.from(PUBLIC_KEY, "base64");
  const hex = createHash("sha256").update(der).digest("hex").slice(0, 32);
  const id = [...hex].map((c) => String.fromCharCode(97 + parseInt(c, 16))).join("");
  expect(id).toBe("npdbpfgligiimfnoblngghbokehjbafm");
});

it("holds only the JobWeaver origin; other sites are asked for one at a time", () => {
  const manifest = buildManifest("https://jobweaver.duckdns.org", "0.1.0");
  expect(manifest.permissions).toEqual(["storage", "activeTab", "scripting", "sidePanel"]);
  expect(manifest.host_permissions).toEqual(["https://jobweaver.duckdns.org/*"]);
  expect(manifest.externally_connectable.matches).toEqual(["https://jobweaver.duckdns.org/*"]);
  // Granted per site at the User's click (chrome.permissions.request), never at install.
  expect(manifest.optional_host_permissions).toEqual(["https://*/*", "http://*/*"]);
  expect(manifest.optional_permissions).toEqual(["downloads", "webNavigation"]);
  expect(JSON.stringify(manifest)).not.toContain("<all_urls>");
  expect(manifest.side_panel.default_path).toBe("popup.html");
});

it("matches a local origin on its host, since match patterns cannot name a port", () => {
  expect(matchPattern("http://localhost:5173")).toBe("http://localhost/*");
});

it("leaves the pinned key out of the store build and ships icons that exist", async () => {
  const { existsSync } = await import("node:fs");
  const { join } = await import("node:path");
  const unpacked = buildManifest("https://jobweaver.duckdns.org", "0.2.0");
  const store = buildManifest("https://jobweaver.duckdns.org", "0.2.0", { store: true });
  expect(unpacked.key).toBe(PUBLIC_KEY);
  expect("key" in store).toBe(false);
  expect(store.permissions).toEqual(unpacked.permissions);
  for (const path of Object.values(store.icons)) {
    expect(existsSync(join(import.meta.dirname, "..", "public", path))).toBe(true);
  }
});
