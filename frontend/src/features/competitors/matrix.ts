// Pure helpers for the keyword x app rank matrix. Ranks are only compared when
// Apple actually returned the app inside its result window; ">limit" and
// pending cells never win, and no rank is ever inferred for them.

import { rankLabel, type Tone } from "@/lib/format";
import type { MatrixCell } from "./api";

/** The exact rank for a found, successful check; otherwise null. */
export function foundRank(cell: MatrixCell | null | undefined): number | null {
  if (!cell || cell.status !== "success" || !cell.found || cell.rank == null) return null;
  return cell.rank;
}

/** Apple app IDs holding the best (lowest) exact rank in a row; ties all win. Empty when nobody ranks. */
export function bestRankAppIds(cells: MatrixCell[]): Set<number> {
  let best: number | null = null;
  for (const cell of cells) {
    const rank = foundRank(cell);
    if (rank != null && (best == null || rank < best)) best = rank;
  }
  const winners = new Set<number>();
  if (best == null) return winners;
  for (const cell of cells) {
    if (foundRank(cell) === best) winners.add(cell.appleAppId);
  }
  return winners;
}

export interface MatrixCellView {
  label: string;
  tone: Tone;
  title: string;
}

/** Label, tone, and hover text for one matrix cell: pending, error, #N, or >limit. */
export function matrixCellView(cell: MatrixCell | undefined, appName: string): MatrixCellView {
  if (!cell || cell.status === "pending") {
    return { label: "—", tone: "neutral", title: `${appName} has not been checked for this keyword` };
  }
  if (cell.status === "error") {
    return { label: "!", tone: "bad", title: cell.error || `${appName} check failed` };
  }
  const rank = foundRank(cell);
  if (rank != null) {
    return {
      label: `#${rank}`,
      tone: rank <= 10 ? "good" : rank <= 50 ? "mid" : "low",
      title: `${appName} rank #${rank}`,
    };
  }
  const label = rankLabel({ rank: null, found: false, resultLimit: cell.resultLimit });
  return {
    label,
    tone: "neutral",
    title: `${appName} is outside Apple's retrieved top ${label.slice(1)}`,
  };
}

/** Index cells by app so a column never shifts if the server omits one. */
export function cellsByApp(cells: MatrixCell[]): Map<number, MatrixCell> {
  return new Map(cells.map((cell) => [cell.appleAppId, cell]));
}
