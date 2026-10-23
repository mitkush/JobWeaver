import { describe, expect, it, vi } from "vitest";

import { apiFetch, disconnect, handleExternal, PENDING_MS, startConnect, status, type Deps } from "../src/connection";
import { challengeFor } from "../src/pkce";

const ORIGIN = "https://jobweaver.example";
const EXT = "npdbpfgligiimfnoblngghbokehjbafm";
const PAGE = { origin: ORIGIN, url: `${ORIGIN}/extension/connect?extension_id=${EXT}` };

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function makeDeps(fetchImpl: (url: string, init?: RequestInit) => Response | Promise<Response> = () => json({})) {
  const data = new Map<string, unknown>();
  const opened: string[] = [];
  let now = 1_000_000;
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => Promise.resolve(fetchImpl(String(input), init)));
  const deps: Deps = {
    origin: ORIGIN,
    extensionId: EXT,
    store: {
      get: async <T,>(key: string) => data.get(key) as T | undefined,
      set: async (key, value) => void data.set(key, value),
      remove: async (key) => void data.delete(key),
    },
    fetch: fetchMock as unknown as typeof fetch,
    openTab: async (url) => void opened.push(url),
    now: () => now,
  };
  return { deps, data, opened, fetchMock, advance: (ms: number) => (now += ms) };
}

const granted = {
  token: "secret-token",
  expires_at: new Date(Date.now() + 3_600_000).toISOString(),
  user: { email: "asha@example.com", name: "Asha" },
};

describe("connecting", () => {
  it("opens the connect page with a PKCE challenge for the stored verifier", async () => {
    const { deps, data, opened } = makeDeps();
    await startConnect(deps);
    const url = new URL(opened[0]!);
    expect(url.origin + url.pathname).toBe(`${ORIGIN}/extension/connect`);
    expect(url.searchParams.get("extension_id")).toBe(EXT);
    const { verifier } = data.get("pending") as { verifier: string };
    expect(verifier).toMatch(/^[A-Za-z0-9_-]{43,128}$/);
    expect(url.searchParams.get("challenge")).toBe(await challengeFor(verifier));
  });

  it("exchanges the page's code with the verifier and keeps the credential", async () => {
    const { deps, data, fetchMock } = makeDeps(() => json(granted));
    await startConnect(deps);
    const { verifier } = data.get("pending") as { verifier: string };
    const reply = await handleExternal(deps, { type: "jobweaver.connect", code: "code-1" }, PAGE);
    expect(reply).toEqual({ ok: true, email: "asha@example.com" });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe(`${ORIGIN}/api/ext/token`);
    expect(init?.credentials).toBe("omit");
    expect(JSON.parse(String(init?.body))).toEqual({ code: "code-1", verifier });
    expect(data.get("connection")).toMatchObject({ token: "secret-token", email: "asha@example.com" });
    expect(data.has("pending")).toBe(false);
  });

  it.each([
    ["another site", { origin: "https://evil.example", url: "https://evil.example/extension/connect" }],
    ["another JobWeaver page", { origin: ORIGIN, url: `${ORIGIN}/feed` }],
    ["no sender origin", { url: `${ORIGIN}/extension/connect` }],
  ])("ignores codes from %s", async (_, sender) => {
    const { deps, data, fetchMock } = makeDeps(() => json(granted));
    await startConnect(deps);
    const reply = await handleExternal(deps, { type: "jobweaver.connect", code: "c" }, sender);
    expect(reply.ok).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(data.has("pending")).toBe(true);
  });

  it("refuses a code it did not ask for, or asked for too long ago", async () => {
    const unasked = makeDeps(() => json(granted));
    expect((await handleExternal(unasked.deps, { type: "jobweaver.connect", code: "c" }, PAGE)).ok).toBe(false);

    const late = makeDeps(() => json(granted));
    await startConnect(late.deps);
    late.advance(PENDING_MS + 1);
    expect((await handleExternal(late.deps, { type: "jobweaver.connect", code: "c" }, PAGE)).ok).toBe(false);
    expect(late.fetchMock).not.toHaveBeenCalled();
  });

  it("uses a pending request once, and reports the server's refusal", async () => {
    const { deps, data } = makeDeps(() => json({ error: { message: "This connection code expired." } }, 401));
    await startConnect(deps);
    const first = await handleExternal(deps, { type: "jobweaver.connect", code: "c" }, PAGE);
    expect(first).toEqual({ ok: false, error: "This connection code expired." });
    const second = await handleExternal(deps, { type: "jobweaver.connect", code: "c" }, PAGE);
    expect(second.ok).toBe(false);
    expect(data.has("connection")).toBe(false);
  });

  it("ignores messages that are not connection codes", async () => {
    const { deps } = makeDeps(() => json(granted));
    await startConnect(deps);
    for (const message of [null, "code", { type: "other", code: "c" }, { type: "jobweaver.connect", code: 42 }]) {
      expect((await handleExternal(deps, message, PAGE)).ok).toBe(false);
    }
  });
});

describe("using the connection", () => {
  async function connected(fetchImpl: (url: string, init?: RequestInit) => Response) {
    const made = makeDeps((url, init) => (url.endsWith("/api/ext/token") && init?.method === "POST" ? json(granted) : fetchImpl(url, init)));
    await startConnect(made.deps);
    await handleExternal(made.deps, { type: "jobweaver.connect", code: "c" }, PAGE);
    return made;
  }

  it("sends the bearer credential and never cookies", async () => {
    const { deps, fetchMock } = await connected(() => json({ email: "asha@example.com", name: "Asha" }));
    expect(await status(deps)).toMatchObject({ connected: true, email: "asha@example.com" });
    const [url, init] = fetchMock.mock.calls.at(-1)!;
    expect(String(url)).toBe(`${ORIGIN}/api/ext/me`);
    expect(init?.credentials).toBe("omit");
    expect((init?.headers as Record<string, string>).Authorization).toBe("Bearer secret-token");
  });

  it("forgets a credential JobWeaver refuses, e.g. after a revoke in Settings", async () => {
    const { deps, data } = await connected(() => json({ error: { message: "Connect again" } }, 401));
    expect(await status(deps)).toEqual({ connected: false });
    expect(data.has("connection")).toBe(false);
  });

  it("forgets an expired credential without calling JobWeaver", async () => {
    const { deps, fetchMock, advance } = await connected(() => json({}));
    const calls = fetchMock.mock.calls.length;
    advance(2 * 3_600_000 + Date.now());
    expect(await apiFetch(deps, "/api/ext/me")).toBeNull();
    expect(fetchMock.mock.calls.length).toBe(calls);
  });

  it("revokes the credential on disconnect", async () => {
    const { deps, data, fetchMock } = await connected(() => new Response(null, { status: 204 }));
    await disconnect(deps);
    const [url, init] = fetchMock.mock.calls.at(-1)!;
    expect(String(url)).toBe(`${ORIGIN}/api/ext/token`);
    expect(init?.method).toBe("DELETE");
    expect(data.has("connection")).toBe(false);
  });
});
