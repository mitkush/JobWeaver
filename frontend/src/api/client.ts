import createClient, { type Middleware } from "openapi-fetch";

import type { components, paths } from "./schema.gen";

export type Schemas = components["schemas"];
export type Me = Schemas["MeOut"];
export type Fact = Schemas["FactOut"];
export type DocumentInfo = Schemas["DocumentOut"];
export type DocumentKind = DocumentInfo["kind"];
export type FactKind = Fact["kind"];
export type Preferences = Schemas["PreferencesIn"];
export type UploadResult = Schemas["UploadResult"];
export type SourceStatus = Schemas["SourceStatusOut"];
export type FetchRun = Schemas["FetchRunOut"];
export type AtsBoard = Schemas["AtsBoardOut"];
export type FeedPage = Schemas["FeedOut"];
export type FeedCard = Schemas["FeedCard"];
export type JobDetail = Schemas["JobDetailOut"];
export type PostingInfo = Schemas["PostingOut"];
export type PossibleDuplicate = Schemas["PossibleDuplicateOut"];
export type JobLocation = Schemas["LocationOut"];
export type Application = Schemas["ApplicationOut"];
export type ApplicationStatus = "drafted" | "applied" | "replied" | "interview" | "offer" | "rejected";
export type Reminder = Schemas["ReminderOut"];
export type FollowUp = Schemas["FollowUpOut"];
export type FollowUpRequest = Schemas["FollowUpIn"];
export type FollowUpResult = Schemas["FollowUpResult"];
export type CompanyHistory = Schemas["CompanyHistoryOut"];
export type FeedQuery = NonNullable<paths["/api/feed"]["get"]["parameters"]["query"]>;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
  ) {
    super(message);
  }
}

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function readCookie(name: string): string | null {
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

let csrfRequest: Promise<string> | null = null;

/** Double-submit CSRF token: read from the cookie, or ask the API to issue one. */
export async function csrfToken(): Promise<string> {
  const existing = readCookie("jw_csrf");
  if (existing) return existing;
  csrfRequest ??= fetch("/api/auth/csrf", { credentials: "same-origin" })
    .then((r) => r.json() as Promise<{ csrf_token: string }>)
    .then((body) => body.csrf_token)
    .finally(() => {
      csrfRequest = null;
    });
  return csrfRequest;
}

const csrf: Middleware = {
  async onRequest({ request }) {
    if (UNSAFE.has(request.method)) request.headers.set("X-CSRF-Token", await csrfToken());
    return request;
  },
};

export const api = createClient<paths>({
  baseUrl: typeof window === "undefined" ? "" : window.location.origin,
  credentials: "same-origin",
  // Look up fetch per call so it can be replaced (tests, instrumentation).
  fetch: (request) => globalThis.fetch(request),
});
api.use(csrf);

export function toApiError(status: number, body: unknown): ApiError {
  const payload = body as {
    error?: { code?: string; message?: string };
    detail?: { msg?: string }[] | string;
  } | null;
  if (payload?.error?.message) {
    return new ApiError(payload.error.message, status, payload.error.code ?? "error");
  }
  if (Array.isArray(payload?.detail) && payload.detail[0]?.msg) {
    const message = payload.detail[0].msg.replace(/^Value error, /, "");
    return new ApiError(message, status, "validation_failed");
  }
  if (status >= 500) return new ApiError("Something went wrong on our side. Try again.", status, "error");
  return new ApiError("The request failed. Try again.", status, "error");
}

/** Returns data or throws an ApiError with a message that is safe to show. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok) throw toApiError(response.status, error);
  return data as T;
}

/** Fetches a file with the server's own name for it. A refusal (e.g. a character the PDF
 * cannot show) is thrown as an ApiError for the page to display, instead of the browser
 * saving the error as a broken download. */
export async function fetchFile(url: string, fallbackName: string): Promise<{ blob: Blob; name: string }> {
  const response = await fetch(url, { credentials: "same-origin" });
  if (!response.ok) throw toApiError(response.status, await response.json().catch(() => null));
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1];
  return { blob: await response.blob(), name: encoded ? decodeURIComponent(encoded) : fallbackName };
}

/** Saves a fetched file through a temporary link. */
export function saveFile(blob: Blob, name: string): void {
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  // Revoked after the click has handed the file to the browser.
  setTimeout(() => URL.revokeObjectURL(href), 0);
}

export async function downloadFile(url: string, fallbackName: string): Promise<void> {
  const { blob, name } = await fetchFile(url, fallbackName);
  saveFile(blob, name);
}

export async function uploadDocument(kind: DocumentKind, file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("kind", kind);
  form.append("file", file);
  const response = await fetch("/api/documents", {
    method: "POST",
    body: form,
    credentials: "same-origin",
    headers: { "X-CSRF-Token": await csrfToken() },
  });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw toApiError(response.status, body);
  return body as UploadResult;
}
