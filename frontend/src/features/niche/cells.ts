// Pure helpers for the niche board. Volume and difficulty are local estimates
// from matching apps' public ratings, never Apple search volume. When Apple
// returned no rating signals there is no estimate, and the cell says so instead
// of showing a made-up 0.

import type { Tone } from "@/lib/format";
import type { NicheBoard, NicheCheck, NicheMetric } from "./api";

export type NicheCellKind = "rated" | "unrated" | "error" | "pending";
/** Overall read of a cell: good = audience and easy; mixed = audience but hard. */
export type NicheCellTone = "good" | "mixed" | "hard" | "low" | "mid";

export type NicheCellView =
  | { kind: "error" | "unrated" | "pending"; label: string; title: string }
  | {
      kind: "rated";
      volume: number;
      difficulty: number;
      volumeTone: Tone;
      difficultyTone: Tone;
      tone: NicheCellTone;
      title: string;
    };

export function nicheVolumeTone(volume: number): Tone {
  return volume >= 35 ? "good" : volume >= 15 ? "mid" : "low";
}

export function nicheDifficultyTone(difficulty: number): Tone {
  return difficulty <= 33 ? "good" : difficulty <= 66 ? "mid" : "bad";
}

export function nicheCellView(metric: NicheMetric | undefined): NicheCellView {
  if (metric?.status === "error") {
    return { kind: "error", label: "Check failed", title: metric.error || "The Apple search failed." };
  }
  if (metric?.status === "success" && (metric.volume == null || metric.difficulty == null)) {
    return {
      kind: "unrated",
      label: "No rated matches",
      title: "Apple returned matching apps, but none exposed public rating signals, so no 0–100 estimate can be calculated.",
    };
  }
  if (!metric || metric.status !== "success" || metric.volume == null || metric.difficulty == null) {
    return { kind: "pending", label: "Not checked", title: "This keyword and market have not been checked yet." };
  }
  const volumeTone = nicheVolumeTone(metric.volume);
  const difficultyTone = nicheDifficultyTone(metric.difficulty);
  const tone: NicheCellTone =
    volumeTone === "good" && difficultyTone === "good"
      ? "good"
      : volumeTone === "good" && difficultyTone === "bad"
        ? "mixed"
        : difficultyTone === "bad"
          ? "hard"
          : volumeTone === "low"
            ? "low"
            : "mid";
  const sample = metric.sampleSize ?? 0;
  return {
    kind: "rated",
    volume: metric.volume,
    difficulty: metric.difficulty,
    volumeTone,
    difficultyTone,
    tone,
    title:
      `Local estimates from ${sample} rated app match${sample === 1 ? "" : "es"}: audience ~${metric.volume}/100, ` +
      `difficulty ~${metric.difficulty}/100. Not Apple search volume.` +
      (tone === "mixed" ? " Mixed: good audience signal with strong competition." : ""),
  };
}

/** Most recent check time across the board, or null when nothing was checked. */
export function latestCheckedAt(board: NicheBoard): string | null {
  let latest: string | null = null;
  for (const keyword of board.keywords) {
    for (const metric of keyword.metrics) {
      if (metric.checkedAt && (latest == null || Date.parse(metric.checkedAt) > Date.parse(latest))) {
        latest = metric.checkedAt;
      }
    }
  }
  return latest;
}

export function checkSummary(check: NicheCheck | null | undefined): { text: string; failed: boolean } {
  const searches = check?.searches ?? 0;
  const failures = check?.failures ?? 0;
  const noun = searches === 1 ? "combination" : "combinations";
  return {
    text: failures
      ? `Checked ${searches} keyword-market ${noun}; ${failures} failed`
      : `Checked ${searches} keyword-market ${noun}`,
    failed: failures > 0,
  };
}
