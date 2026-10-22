import { describe, expect, it } from "vitest";

import { accentFor } from "@/lib/accent";
import { movedIndexes } from "@/lib/order";

describe("movedIndexes", () => {
  it("marks nothing when the order is kept", () => {
    expect(movedIndexes([0, 1, 2, 3])).toEqual(new Set());
  });

  it("marks only the line that moved", () => {
    expect(movedIndexes([0, 3, 1, 2])).toEqual(new Set([1]));
  });

  it("treats equal values as in order", () => {
    expect(movedIndexes([1, 1, 2])).toEqual(new Set());
  });

  it("handles an empty list", () => {
    expect(movedIndexes([])).toEqual(new Set());
  });
});


it("gives each area of the app its own accent", () => {
  expect(accentFor("/feed")).toBe("pink");
  expect(accentFor("/jobs/abc")).toBe("pink");
  expect(accentFor("/drafts/abc")).toBe("purple");
  expect(accentFor("/fact-bank")).toBe("purple");
  expect(accentFor("/preferences")).toBe("lime");
  expect(accentFor("/applications")).toBe("amber");
  expect(accentFor("/admin/sources")).toBe("cyan");
  expect(accentFor("/somewhere-else")).toBe("pink");
});
