/**
 * Powder Planner: decode planner.json (pipeline/publish/planner.py) and the go / wait rules.
 *
 * The powder score is computed in the pipeline; here we only filter, rank and phrase the advice.
 * Rules follow the planner backtest (docs/phase3-planner-validation.md):
 *  - rank single mountains only up to 4 days ahead; from day 5 only "which day, which region";
 *  - "go" needs a high probability of 6 in+ and a short lead; further out the advice is to wait
 *    until the day is 2 days away, when choosing the mountain starts to pay off.
 */
import type { PassTier, Quality, Region } from "./types";

export interface PlannerDay {
  date: string; lead: number; score: number; fresh: number; night: number;
  cm: number | null; low: number | null; high: number | null; p2_5: number | null; p15: number | null;
  quality: Quality | null; gust: number | null; rain: number | null; rain_mid: number; conf: string | null;
}
export interface PlannerProbDay { date: string; lead: number; p2_5: number | null; p15: number | null; p50: number | null }

interface RawResort {
  name: string; name_zh: string | null; destination: string | null; region: string; country: string;
  state: string | null; lat: number; lon: number; timezone: string; tier: string;
  passes: Partial<Record<"ikon" | "epic", PassTier>>; mid_m: number | null; generated_at: string;
  days: unknown[][]; prob_days: unknown[][];
}
export interface PlannerDoc {
  schema_version: number; planner_version: number; generated_at: string;
  fields: string[]; prob_fields: string[]; regions: Region[]; resorts: Record<string, RawResort>;
}

export interface PlannerResort extends Omit<RawResort, "days" | "prob_days"> {
  id: string; days: PlannerDay[]; probDays: PlannerProbDay[];
}

function rows<T>(fields: string[], data: unknown[][]): T[] {
  return data.map((r) => Object.fromEntries(fields.map((f, i) => [f, r[i]])) as T);
}

export function decodePlanner(doc: PlannerDoc): PlannerResort[] {
  return Object.entries(doc.resorts).map(([id, r]) => {
    const { days, prob_days, ...meta } = r;
    return { id, ...meta, days: rows<PlannerDay>(doc.fields, days), probDays: rows<PlannerProbDay>(doc.prob_fields, prob_days) };
  });
}

/** Today's date and hour at the resort ("2026-11-15", 9). */
export function resortNow(tz: string, now = new Date()): { date: string; hour: number } {
  try {
    const parts = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", hourCycle: "h23" })
      .formatToParts(now);
    const g = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
    return { date: `${g("year")}-${g("month")}-${g("day")}`, hour: Number(g("hour")) };
  } catch {
    return { date: now.toISOString().slice(0, 10), hour: now.getUTCHours() };
  }
}

const dayNum = (iso: string) => { const [y, m, d] = iso.split("-").map(Number); return Date.UTC(y, m - 1, d) / 86_400_000; };
export const daysBetween = (from: string, to: string) => Math.round(dayNum(to) - dayNum(from));
export const addDays = (iso: string, n: number) => new Date((dayNum(iso) + n) * 86_400_000).toISOString().slice(0, 10);
export const weekday = (iso: string) => new Date(dayNum(iso) * 86_400_000).getUTCDay();
export const isWeekend = (iso: string) => { const w = weekday(iso); return w === 0 || w === 6; };

/** Lifts close at 16:00: after that today's ski day is over. */
export const LIFTS_CLOSE_H = 16;
/** Single mountains are ranked only this many days ahead (backtest: from 5 days on, switching mountains no longer helps). */
export const RANK_MAX_AHEAD = 4;
/** A row needs at least this score (~5 cm / 2 in of fresh snow) to be listed. */
export const MIN_SCORE = 20;

export type Advice = { kind: "go" | "likely" | "wait"; decideOn?: string } | null;

/**
 * Go / wait from the probability of 6 in+ (15 cm) and the days ahead. The probabilities are the
 * ensemble's own and not yet calibrated against observations (design doc A7).
 */
export function advice(day: { date: string; p15: number | null; rain_mid?: number }, ahead: number): Advice {
  const p = day.p15 ?? 0;
  if (ahead <= 2) {
    if (p >= 0.7 && !day.rain_mid) return { kind: "go" };   // rain at mid-mountain: at most "probably"
    if (p >= 0.4) return { kind: "likely" };
    return null;
  }
  if (p >= 0.4) return { kind: "wait", decideOn: addDays(day.date, -2) };
  return null;
}
