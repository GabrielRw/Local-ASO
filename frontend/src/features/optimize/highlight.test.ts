import { describe, expect, it } from "vitest";
import {
  analysisTokens,
  classifyTokens,
  coverageConfigured,
  highlightContext,
  inferBrand,
  keywordFieldSegments,
  textSegments,
} from "./highlight";

describe("analysisTokens", () => {
  it("folds accents and case and drops stop words and single letters", () => {
    expect(analysisTokens("Le Café de Paris & the App x")).toEqual(["cafe", "paris"]);
  });

  it("handles empty input", () => {
    expect(analysisTokens("")).toEqual([]);
    expect(analysisTokens(null)).toEqual([]);
  });
});

describe("classifyTokens", () => {
  const context = highlightContext(["Astro Tarot", "Daily tarot reading", "horoscope,zodiac"], "AstroLingo Astro");

  it("marks words used in more than one place as repeated", () => {
    expect(classifyTokens(["tarot"], context)).toBe("repeated");
  });

  it("marks brand words", () => {
    expect(classifyTokens(["astro"], context)).toBe("brand");
  });

  it("marks everything else unique", () => {
    expect(classifyTokens(["zodiac"], context)).toBe("unique");
  });

  it("does not classify stop words", () => {
    expect(classifyTokens([], context)).toBeNull();
  });

  it("prefers repeated over brand", () => {
    const repeatedBrand = highlightContext(["Astro", "Astro daily"], "Astro");
    expect(classifyTokens(["astro"], repeatedBrand)).toBe("repeated");
  });
});

describe("segments", () => {
  const context = highlightContext(["Astro: Tarot", "Tarot for you", "zodiac, love match"], "Astro");

  it("keeps the original text when segments are joined", () => {
    const value = "Astro: Tarot";
    expect(
      textSegments(value, context)
        .map((segment) => segment.text)
        .join(""),
    ).toBe(value);
  });

  it("highlights each word in titles", () => {
    expect(textSegments("Astro: Tarot", context)).toEqual([
      { text: "Astro", tone: "brand" },
      { text: ": ", tone: null },
      { text: "Tarot", tone: "repeated" },
    ]);
  });

  it("leaves stop words unhighlighted", () => {
    expect(textSegments("for", context)).toEqual([{ text: "for", tone: null }]);
  });

  it("highlights keyword-field entries as whole phrases without their padding", () => {
    expect(keywordFieldSegments("zodiac, love match", context)).toEqual([
      { text: "zodiac", tone: "unique" },
      { text: ",", tone: null },
      { text: " ", tone: null },
      { text: "love match", tone: "unique" },
    ]);
  });
});

describe("inferBrand", () => {
  it("takes the last part of a separated name", () => {
    expect(inferBrand("Learn Spanish: AstroLingo")).toBe("AstroLingo");
    expect(inferBrand("Notes – Quill")).toBe("Quill");
  });

  it("returns empty when the name has no separator", () => {
    expect(inferBrand("AstroLingo")).toBe("");
  });
});

describe("coverageConfigured", () => {
  it("requires a name, a brand term, and a goal", () => {
    expect(coverageConfigured(null)).toBe(false);
    expect(
      coverageConfigured({
        name: "App",
        subtitle: "",
        keywords: "",
        channelGoal: "aso_seo_aeo",
        brandTerm: " ",
        updatedAt: null,
      }),
    ).toBe(false);
    expect(
      coverageConfigured({
        name: "App",
        subtitle: "",
        keywords: "",
        channelGoal: "ugc_ads",
        brandTerm: "Brand",
        updatedAt: null,
      }),
    ).toBe(true);
  });
});
