import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { COLUMN_INFO } from "@/features/keywords/column-info";
import { InfoTip } from "./info-tip";

describe("InfoTip", () => {
  it("opens the explanation of a metric with its formula", () => {
    const info = COLUMN_INFO.difficulty!;
    render(<InfoTip info={info} />);

    expect(screen.queryByText(info.formula!)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "How Difficulty is calculated" }));

    expect(screen.getByText(info.formula!)).toBeInTheDocument();
    expect(screen.getByText(/Green below 34/)).toBeInTheDocument();
  });

  it("explains every computed rankings column", () => {
    for (const field of ["popularity", "difficulty", "opportunity", "change"] as const) {
      expect(COLUMN_INFO[field]?.summary).toBeTruthy();
    }
    expect(COLUMN_INFO.rank).toBeUndefined();
    expect(COLUMN_INFO.top5).toBeUndefined();
  });
});
