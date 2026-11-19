import { describe, expect, it } from "vitest";
import { missingCaptions, renderCounts, renderJobs } from "./plan";
import type { ScreenshotStudioData } from "./types";

const data: ScreenshotStudioData = {
  appId: 1,
  mainLocale: "en-US",
  style: { background: "#000", backgroundTo: "#111", text: "#fff", accent: "#aaa" },
  devices: {
    iphone: { label: "iPhone", displayType: "APP_IPHONE_67", width: 1320, height: 2868 },
    ipad: { label: "iPad", displayType: "APP_IPAD_PRO_3GEN_129", width: 2064, height: 2752 },
  },
  locales: [
    { locale: "en-US", language: "English", countries: [], isMain: true },
    { locale: "fr-FR", language: "French", countries: ["fr"], isMain: false },
  ],
  sources: [
    { id: 10, position: 1, width: 1, height: 1, name: "a", url: "", captions: { "en-US": { headline: "One", subline: "", origin: "user" }, "fr-FR": { headline: "Un", subline: "", origin: "ai" } } },
    { id: 11, position: 2, width: 1, height: 1, name: "b", url: "", captions: { "en-US": { headline: "Two", subline: "", origin: "user" } } },
  ],
  renders: [],
  pushEvents: [],
};

describe("renderJobs", () => {
  it("skips screenshots without a caption in that locale", () => {
    const jobs = renderJobs(data, ["iphone", "ipad"]);
    expect(jobs).toHaveLength(6);
    expect(jobs.filter((job) => job.locale === "fr-FR").map((job) => job.position)).toEqual([1, 1]);
  });
});

describe("renderCounts", () => {
  it("counts renders per locale and device, ignoring stale positions", () => {
    const counts = renderCounts(
      [
        { id: 1, locale: "fr-FR", device: "iphone", position: 1, url: "", renderedAt: "" },
        { id: 2, locale: "fr-FR", device: "iphone", position: 3, url: "", renderedAt: "" },
        { id: 3, locale: "fr-FR", device: "ipad", position: 2, url: "", renderedAt: "" },
      ],
      2,
    );
    expect(counts.get("fr-FR")).toEqual({ iphone: 1, ipad: 1 });
  });
});

describe("missingCaptions", () => {
  it("counts screenshots without a headline", () => {
    expect(missingCaptions(data, "fr-FR")).toBe(1);
    expect(missingCaptions(data, "en-US")).toBe(0);
  });
});
