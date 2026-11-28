// How each computed rankings column is calculated, shown behind the (i) next to its header.
// Self-explanatory columns (Rank, Top 5) have none.
// Keep in step with services/estimates.py (Popularity estimate, Difficulty),
// services/keyword_popularity.py (Opportunity), services/analytics.py (Change)
// and lib/format.ts, components/metric.tsx (display rules).

import type { MetricExplanation } from "@/components/info-tip";
import type { SortField } from "./keyword-utils";

export const COLUMN_INFO: Partial<Record<SortField, MetricExplanation>> = {
  popularity: {
    title: "Popularity",
    summary:
      "Apple's own search popularity for this exact query in this storefront, from Apple Ads: how often people search it, on a 5–100 scale, not a number of searches. 5 is Apple's floor and reads Low. — means Apple has no value for it, or has not been asked yet.",
    formula: "~ = 100 × avg log(1 + ratings) ÷ log(1 + 3M) × min(1, rated apps ÷ 5)",
    details: [
      "Without Apple Ads connected, a local estimate marked ~ is shown instead. It measures how big the top 10 apps are (their ratings), not how often the query is searched, so it is never used once Apple Ads is connected.",
      "The estimate's average counts only apps with ratings, weighted by position: #1 counts 1.0, down to 0.46 for #10.",
    ],
  },
  difficulty: {
    title: "Difficulty",
    summary:
      "Local estimate, 0–100, of how hard it is to enter the top 10, built only from the ratings Apple returns with those apps. Not an Apple score.",
    formula: "65% × strength + 25% × density + 10% × quality",
    details: [
      "Strength: avg log(1 + ratings) ÷ log(1 + 1M), weighted by position (#1 counts 1.0, #10 counts 0.46).",
      "Density: how many of the top 10 have ratings, full at 5 apps.",
      "Quality: their average star rating ÷ 5, weighted the same way.",
      "Green below 34, orange from 34 to 66, red from 67.",
    ],
  },
  opportunity: {
    title: "Opportunity",
    summary:
      "Apple popularity still to win on this keyword, discounted by how hard its top 10 is and by what your current rank already captures. Higher is better; 0 means nothing left to win.",
    formula: "popularity × (100 − difficulty) ÷ 100 × (1 − rank^−1.2)",
    details: [
      "rank^−1.2 is the share of attention a rank already captures: #1 all of it, #2 44%, #5 14%, #10 6%. Outside Apple's results, nothing is captured yet.",
      "Needs Apple Ads popularity and a difficulty estimate; otherwise —. The ~ estimate is never used.",
      "Green from 10, orange from 4 to 9, grey below 4.",
    ],
  },
  change: {
    title: "Change",
    summary: "Rank movement between the last two checks of this keyword: +3 means three places up.",
    details: [
      "NEW: the app entered Apple's results.",
      "LOST: it dropped out of them.",
      "—: same rank, still outside the results, or a single check so far.",
    ],
  },
};
