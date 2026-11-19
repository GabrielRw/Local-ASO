import { describe, expect, it } from "vitest";
import type { NicheBoard, NicheMetric } from "./api";
import { checkSummary, latestCheckedAt, nicheCellView } from "./cells";

function metric(patch: Partial<NicheMetric> = {}): NicheMetric {
  return { volume: null, difficulty: null, sampleSize: null, status: "pending", checkedAt: null, error: null, ...patch };
}

describe("nicheCellView", () => {
  it("never shows a made-up 0 when Apple returned no rating signals", () => {
    const view = nicheCellView(metric({ status: "success", sampleSize: 0 }));
    expect(view.kind).toBe("unrated");
    if (view.kind !== "rated") expect(view.label).toBe("No rated matches");
  });

  it("separates pending and failed checks", () => {
    expect(nicheCellView(undefined).kind).toBe("pending");
    expect(nicheCellView(metric({ status: "error", error: "timeout" }))).toMatchObject({ kind: "error", title: "timeout" });
  });

  it("classifies rated estimates", () => {
    const good = nicheCellView(metric({ status: "success", volume: 50, difficulty: 20, sampleSize: 8 }));
    expect(good).toMatchObject({ kind: "rated", tone: "good", volumeTone: "good", difficultyTone: "good" });
    expect(nicheCellView(metric({ status: "success", volume: 60, difficulty: 80 }))).toMatchObject({ tone: "mixed" });
    expect(nicheCellView(metric({ status: "success", volume: 20, difficulty: 90 }))).toMatchObject({ tone: "hard" });
    expect(nicheCellView(metric({ status: "success", volume: 5, difficulty: 40 }))).toMatchObject({ tone: "low" });
  });

  it("labels rated values as local estimates", () => {
    const view = nicheCellView(metric({ status: "success", volume: 40, difficulty: 30, sampleSize: 1 }));
    expect(view.title).toContain("Not Apple search volume");
  });
});

describe("latestCheckedAt", () => {
  it("finds the most recent check", () => {
    const board = {
      keywords: [
        { id: 1, keyword: "a", metrics: [metric({ checkedAt: "2026-01-02T00:00:00+00:00" }), metric()] },
        { id: 2, keyword: "b", metrics: [metric({ checkedAt: "2026-03-01T00:00:00+00:00" })] },
      ],
    } as NicheBoard;
    expect(latestCheckedAt(board)).toBe("2026-03-01T00:00:00+00:00");
    expect(latestCheckedAt({ keywords: [] } as unknown as NicheBoard)).toBeNull();
  });
});

describe("checkSummary", () => {
  it("reports failures", () => {
    expect(checkSummary({ searches: 1, failures: 0 })).toEqual({ text: "Checked 1 keyword-market combination", failed: false });
    expect(checkSummary({ searches: 6, failures: 2 }).failed).toBe(true);
  });
});
