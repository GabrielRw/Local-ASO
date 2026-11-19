import { describe, expect, it } from "vitest";
import { balanceLines, fitFont, isRtl, screenshotRect, wrapText } from "./render";

const mono = (size = 10) => (text: string) => text.length * size;

describe("wrapText", () => {
  it("wraps on spaces", () => {
    expect(wrapText(mono(), "feel each other from afar", 120)).toEqual(["feel each", "other from", "afar"]);
  });

  it("wraps scripts without spaces per character", () => {
    expect(wrapText(mono(), "カップルアプリ", 30)).toEqual(["カップ", "ルアプ", "リ"]);
  });

  it("returns nothing for empty text", () => {
    expect(wrapText(mono(), "   ", 100)).toEqual([]);
  });
});

describe("fitFont", () => {
  it("shrinks until the text fits the line budget", () => {
    const result = fitFont((size) => mono(size), "dream journal together", 200, 20, 2, 5);
    expect(result.lines.length).toBeLessThanOrEqual(2);
    expect(result.size).toBeLessThan(20);
  });

  it("truncates to the line budget at the minimum size", () => {
    const result = fitFont((size) => mono(size), "a b c d e f g h", 10, 10, 2, 10);
    expect(result.lines).toHaveLength(2);
    expect(result.size).toBe(10);
  });
});

describe("screenshotRect", () => {
  it("centers the screenshot at 84% width below the caption and keeps its aspect", () => {
    const rect = screenshotRect(1320, 2868, 600, 1290, 2796);
    expect(rect.width).toBe(1109);
    expect(rect.x).toBe(106);
    expect(rect.y).toBe(600);
    expect(rect.height).toBe(Math.round((1109 * 2796) / 1290));
  });

  it("sizes a phone capture on an iPad canvas by the height left", () => {
    const rect = screenshotRect(2064, 2752, 600, 1290, 2796);
    expect(rect.width).toBe(Math.round((2152 * 1.1 * 1290) / 2796));
    expect(rect.width).toBeLessThan(2064 * 0.84);
    expect(rect.x).toBe(Math.round((2064 - rect.width) / 2));
  });
});

describe("balanceLines", () => {
  it("avoids leaving one character alone on the last line", () => {
    const measure = mono();
    const text = "讓你們的心靈感應看得見";
    const greedy = wrapText(measure, text, 100);
    expect(greedy.at(-1)).toBe("見");
    const balanced = balanceLines(measure, text, 100, greedy);
    expect(balanced).toHaveLength(2);
    expect(balanced.map((line) => line.length)).toEqual([6, 5]);
  });

  it("keeps single lines as they are", () => {
    expect(balanceLines(mono(), "short", 100, ["short"])).toEqual(["short"]);
  });
});

describe("isRtl", () => {
  it("knows the right-to-left App Store locales", () => {
    expect(isRtl("ar-SA")).toBe(true);
    expect(isRtl("he")).toBe(true);
    expect(isRtl("fr-FR")).toBe(false);
  });
});
