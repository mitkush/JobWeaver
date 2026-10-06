import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, toApiError, unwrap } from "@/api/client";

import { json, mockFetch } from "./utils";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "jw_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("toApiError", () => {
  it("uses the API's own message", () => {
    const error = toApiError(409, { error: { code: "precondition_failed", message: "Upload your resume first" } });
    expect(error).toMatchObject({ message: "Upload your resume first", status: 409, code: "precondition_failed" });
  });

  it("turns validation details into a readable message", () => {
    const error = toApiError(422, { detail: [{ msg: "Value error, Add at least one job title" }] });
    expect(error.message).toBe("Add at least one job title");
  });

  it("never shows raw server errors", () => {
    expect(toApiError(500, "<html>Traceback</html>").message).toMatch(/Something went wrong/);
  });
});

describe("CSRF", () => {
  it("sends the cookie token on state-changing requests", async () => {
    document.cookie = "jw_csrf=token-123";
    const calls = mockFetch({ "POST /api/me/ai-notice": () => json({}) });
    await unwrap(api.POST("/api/me/ai-notice"));
    expect(calls[0]?.headers.get("X-CSRF-Token")).toBe("token-123");
  });

  it("asks the API for a token when there is no cookie", async () => {
    const calls = mockFetch({
      "GET /api/auth/csrf": () => json({ csrf_token: "fresh" }),
      "POST /api/auth/logout": () => new Response(null, { status: 204 }),
    });
    await unwrap(api.POST("/api/auth/logout"));
    expect(calls.map((c) => new URL(c.url).pathname)).toEqual(["/api/auth/csrf", "/api/auth/logout"]);
    expect(calls[1]?.headers.get("X-CSRF-Token")).toBe("fresh");
  });

  it("does not add the header to reads", async () => {
    const calls = mockFetch({ "GET /api/facts": () => json([]) });
    await unwrap(api.GET("/api/facts"));
    expect(calls[0]?.headers.get("X-CSRF-Token")).toBeNull();
  });
});

it("unwrap throws an ApiError for failed responses", async () => {
  mockFetch({ "GET /api/me": () => json({ error: { code: "unauthenticated", message: "Please sign in" } }, 401) });
  await expect(unwrap(api.GET("/api/me"))).rejects.toBeInstanceOf(ApiError);
});
