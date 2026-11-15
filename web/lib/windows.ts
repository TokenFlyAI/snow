import type { IndexResort, Level, WindowKey } from "./types";

export const WINDOWS: { key: WindowKey; label: "d3" | "d7" | "d16" }[] = [
  { key: "3d", label: "d3" }, { key: "7d", label: "d7" }, { key: "16d", label: "d16" },
];

export interface WindowValue { cm: number; low: number | null; high: number | null }

/** Ski-day total of a resort for the 3 / 7 / 16 day window, with the ensemble 10-90 % range when there is one. */
export function windowValue(r: IndexResort, w: WindowKey, level: Level): WindowValue {
  const tot = r.summary.totals?.[w];
  if (!tot) return { cm: 0, low: null, high: null };
  return { cm: tot.cm[level] ?? 0, low: tot.low_cm ? tot.low_cm[level] : null, high: tot.high_cm ? tot.high_cm[level] : null };
}
