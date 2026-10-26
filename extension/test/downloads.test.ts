import { expect, it, vi } from "vitest";
import { companyFolder, savePdfs } from "../src/downloads";
import type { Deps } from "../src/connection";

it("saves both PDFs in a safe company folder using the pinned version", async () => {
  const requests: string[] = [];
  const state = new Map<string, unknown>([
    ["connection", { token: "t", expiresAt: new Date(Date.now() + 3600000).toISOString() }],
    ["selection:5", { draftId: "d1", number: 2 }],
  ]);
  const deps = {
    origin: "https://jobweaver.example", now: () => Date.now(),
    store: { get: async (k: string) => state.get(k) },
    fetch: async (input: RequestInfo | URL) => {
      requests.push(String(input));
      return String(input).includes("/pdf?") ? new Response("%PDF") : new Response(JSON.stringify({
        draft_id: "d1", number: 2, company: "../Acme/Corp", resume_file: "Asha_Resume.pdf", cover_letter_file: "Asha_Cover_Letter.pdf",
      }));
    },
  } as unknown as Deps;
  const download = vi.fn(async (_path: string, _url: string) => 1);
  await savePdfs(deps, 5, download);
  expect(download.mock.calls.map((c) => c[0])).toEqual(["_Acme_Corp/Asha_Resume.pdf", "_Acme_Corp/Asha_Cover_Letter.pdf"]);
  expect(requests.filter((url) => url.includes("/pdf?")).every((url) => url.includes("number=2"))).toBe(true);
  expect(companyFolder("../.. ")).not.toContain("/");
  expect(companyFolder("...")).toBe("Company");
});
