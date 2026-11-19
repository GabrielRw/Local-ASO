import { describe, expect, it } from "vitest";
import { changeLabel, changeable, defaultSelection, parsePercent } from "./plan";
import type { PriceRow } from "./types";

const row = (territory: string, current: string, suggested: string | null, change: number | null): PriceRow => ({
  territory,
  currency: "EUR",
  currentPrice: 9.99,
  currentPointId: current,
  manual: false,
  equalizedPrice: 9.99,
  pppRatio: 0.7,
  ratio: 0.7,
  suggestedPrice: suggested ? 6.99 : null,
  suggestedPointId: suggested,
  changePercent: change,
});

describe("pricing plan", () => {
  it("selects only rows with a different real price point", () => {
    const rows = [row("FRA", "a", "b", -30), row("DEU", "a", "a", 0), row("XXX", "a", null, null)];
    expect(rows.map(changeable)).toEqual([true, false, false]);
    expect([...defaultSelection(rows)]).toEqual(["FRA"]);
  });

  it("formats changes with a sign", () => {
    expect(changeLabel(-30.04)).toBe("−30.0%");
    expect(changeLabel(12.5)).toBe("+12.5%");
    expect(changeLabel(null)).toBe("—");
  });

  it("parses percentage bounds", () => {
    expect(parsePercent("35")).toBe(0.35);
    expect(parsePercent("0")).toBeNull();
    expect(parsePercent("150")).toBeNull();
    expect(parsePercent("abc")).toBeNull();
  });
});
