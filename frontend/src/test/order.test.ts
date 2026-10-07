import { describe, expect, it } from "vitest";

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
