/** Connecting the extension to one JobWeaver server (ADR-0017).
 *
 * 1. Connect opens `<origin>/extension/connect` with a PKCE challenge.
 * 2. The User approves there; the page sends a one-time code to this extension.
 * 3. The code and the verifier are exchanged for a bearer credential, kept in session
 *    storage (cleared when the browser closes), never in the page. */

import { challengeFor, newVerifier } from "./pkce";

export const PENDING_MS = 5 * 60_000;

export type Connection = { token: string; expiresAt: string; email: string; name: string };
type Pending = { verifier: string; createdAt: number };

export interface Store {
  get<T>(key: string): Promise<T | undefined>;
  set(key: string, value: unknown): Promise<void>;
  remove(key: string): Promise<void>;
}

export interface Deps {
  origin: string;
  extensionId: string;
  store: Store;
  fetch: typeof fetch;
  openTab: (url: string) => Promise<void>;
  now: () => number;
}

export type Reply = { ok: true; email: string } | { ok: false; error: string };

export async function startConnect(deps: Deps): Promise<void> {
  const verifier = newVerifier();
  await deps.store.set("pending", { verifier, createdAt: deps.now() } satisfies Pending);
  const url = new URL("/extension/connect", deps.origin);
  url.searchParams.set("extension_id", deps.extensionId);
  url.searchParams.set("challenge", await challengeFor(verifier));
  await deps.openTab(url.toString());
}

/** A message from a web page. Only JobWeaver's connect page, with a pending request. */
export async function handleExternal(deps: Deps, message: unknown, sender: { origin?: string; url?: string }): Promise<Reply> {
  if (sender.origin !== deps.origin || !sender.url?.startsWith(`${deps.origin}/extension/connect`)) {
    return { ok: false, error: "Not a JobWeaver page" };
  }
  const code = (message as { type?: unknown; code?: unknown } | null)?.type === "jobweaver.connect" ? (message as { code?: unknown }).code : undefined;
  if (typeof code !== "string" || code.length === 0 || code.length > 128) {
    return { ok: false, error: "Not a connection code" };
  }
  const pending = await deps.store.get<Pending>("pending");
  await deps.store.remove("pending");
  if (!pending || deps.now() - pending.createdAt > PENDING_MS) {
    return { ok: false, error: "The extension was not waiting for a connection. Click Connect in the extension again." };
  }
  const response = await deps.fetch(new URL("/api/ext/token", deps.origin), {
    method: "POST",
    credentials: "omit",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, verifier: pending.verifier }),
  });
  const body = (await response.json().catch(() => null)) as
    | { token: string; expires_at: string; user: { email: string; name: string } }
    | { error?: { message?: string } }
    | null;
  if (!response.ok || !body || !("token" in body)) {
    const error = body && "error" in body ? body.error?.message : undefined;
    return { ok: false, error: error ?? "JobWeaver refused the connection. Try again." };
  }
  await deps.store.remove("notice");
  await deps.store.set("connection", {
    token: body.token,
    expiresAt: body.expires_at,
    email: body.user.email,
    name: body.user.name,
  } satisfies Connection);
  return { ok: true, email: body.user.email };
}

export async function currentConnection(deps: Deps): Promise<Connection | null> {
  const connection = await deps.store.get<Connection>("connection");
  if (!connection) return null;
  if (Date.parse(connection.expiresAt) <= deps.now()) {
    await deps.store.remove("connection");
    return null;
  }
  return connection;
}

/** Calls the /api/ext/ surface; a refused credential disconnects the extension. */
export async function apiFetch(deps: Deps, path: string, init: RequestInit = {}): Promise<Response | null> {
  const connection = await currentConnection(deps);
  if (!connection) return null;
  const response = await deps.fetch(new URL(path, deps.origin), {
    ...init,
    credentials: "omit",
    headers: { ...init.headers, Authorization: `Bearer ${connection.token}` },
  });
  if (response.status === 401 || response.status === 403) {
    // Keep JobWeaver's reason, e.g. that new access needs approving, for the popup.
    const body = (await response.clone().json().catch(() => null)) as { error?: { message?: string } } | null;
    await deps.store.set("notice", body?.error?.message ?? "JobWeaver ended the connection. Connect again.");
    await deps.store.remove("connection");
    return null;
  }
  return response;
}

/** The connection as JobWeaver sees it now, so a revoke in Settings shows at once. */
export async function status(
  deps: Deps,
): Promise<{ connected: false; error?: string } | { connected: true; email: string; expiresAt: string }> {
  const response = await apiFetch(deps, "/api/ext/me");
  const connection = await currentConnection(deps);
  if (!response?.ok || !connection) {
    const notice = await deps.store.get<string>("notice");
    return notice ? { connected: false, error: notice } : { connected: false };
  }
  const me = (await response.json()) as { email: string };
  return { connected: true, email: me.email, expiresAt: connection.expiresAt };
}

export async function disconnect(deps: Deps): Promise<void> {
  await apiFetch(deps, "/api/ext/token", { method: "DELETE" }).catch(() => null);
  await deps.store.remove("connection");
  await deps.store.remove("notice");
}
