import { describe, expect, it } from "vitest";
import type { MatrixCell } from "./api";
import { bestRankAppIds, matrixCellView } from "./matrix";

function cell(appleAppId: number, patch: Partial<MatrixCell> = {}): MatrixCell {
  return {
    appleAppId,
    rank: null,
    found: false,
    resultLimit: 200,
    status: "success",
    checkedAt: null,
    error: null,
    ...patch,
  };
}

describe("bestRankAppIds", () => {
  it("picks the lowest exact rank", () => {
    const best = bestRankAppIds([cell(1, { rank: 12, found: true }), cell(2, { rank: 3, found: true }), cell(3)]);
    expect([...best]).toEqual([2]);
  });

  it("keeps ties", () => {
    const best = bestRankAppIds([cell(1, { rank: 4, found: true }), cell(2, { rank: 4, found: true })]);
    expect([...best].sort()).toEqual([1, 2]);
  });

  it("never lets >limit, pending, or failed cells win", () => {
    const best = bestRankAppIds([
      cell(1),
      cell(2, { status: "pending", resultLimit: null }),
      cell(3, { status: "error", rank: 1, found: true }),
    ]);
    expect(best.size).toBe(0);
  });
});

describe("matrixCellView", () => {
  it("shows exact ranks with a tone", () => {
    expect(matrixCellView(cell(1, { rank: 7, found: true }), "A")).toMatchObject({ label: "#7", tone: "good" });
    expect(matrixCellView(cell(1, { rank: 70, found: true }), "A").tone).toBe("low");
  });

  it("shows apps outside Apple's window as >limit", () => {
    expect(matrixCellView(cell(1, { resultLimit: 50 }), "A").label).toBe(">50");
  });

  it("marks pending and failed checks", () => {
    expect(matrixCellView(cell(1, { status: "pending" }), "A").label).toBe("—");
    expect(matrixCellView(cell(1, { status: "error", error: "timeout" }), "A")).toMatchObject({
      label: "!",
      title: "timeout",
    });
  });
});
