import { createHash } from "node:crypto";

import { expect, it } from "vitest";

import { buildManifest, matchPattern, PUBLIC_KEY } from "../manifest";

it("derives the fixed extension ID the server allows", () => {
  const der = Buffer.from(PUBLIC_KEY, "base64");
  const hex = createHash("sha256").update(der).digest("hex").slice(0, 32);
  const id = [...hex].map((c) => String.fromCharCode(97 + parseInt(c, 16))).join("");
  expect(id).toBe("npdbpfgligiimfnoblngghbokehjbafm");
});

it("asks only for storage and the one JobWeaver origin", () => {
  const manifest = buildManifest("https://jobweaver.duckdns.org", "0.1.0");
  expect(manifest.permissions).toEqual(["storage"]);
  expect(manifest.host_permissions).toEqual(["https://jobweaver.duckdns.org/*"]);
  expect(manifest.externally_connectable.matches).toEqual(["https://jobweaver.duckdns.org/*"]);
  expect(JSON.stringify(manifest)).not.toContain("<all_urls>");
});

it("matches a local origin on its host, since match patterns cannot name a port", () => {
  expect(matchPattern("http://localhost:5173")).toBe("http://localhost/*");
});
