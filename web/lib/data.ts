"use client";
import { useEffect, useState } from "react";
import type { PlannerDoc } from "./planner";
import type { Manifest, ObsDoc, ResortDoc, ResortIndex, TrendDoc, VerificationDoc } from "./types";

export const DATA_BASE = (process.env.NEXT_PUBLIC_DATA_BASE ?? "https://tokenflyai.github.io/snow/data/v1").replace(/\/$/, "");

export interface Loaded<T> { data: T | null; error: string | null; loading: boolean }

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${DATA_BASE}/${path}`, { cache: "no-cache" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as T;
}

function useJson<T>(path: string | null): Loaded<T> {
  const [state, set] = useState<Loaded<T>>({ data: null, error: null, loading: true });
  useEffect(() => {
    if (!path) return;
    let alive = true;
    set((s) => ({ ...s, loading: true }));
    getJson<T>(path)
      .then((data) => alive && set({ data, error: null, loading: false }))
      .catch((e: Error) => alive && set({ data: null, error: e.message, loading: false }));
    return () => { alive = false; };
  }, [path]);
  return state;
}

export const useIndex = () => useJson<ResortIndex>("resorts.json");
export const useResort = (id: string) => useJson<ResortDoc>(`resort/${id}.json`);
export const useManifest = () => useJson<Manifest>("manifest.json");
export const usePlanner = () => useJson<PlannerDoc>("planner.json");
/** null: the resort has no measuring station, nothing is fetched. */
export const useObs = (id: string | null) => useJson<ObsDoc>(id ? `obs/${id}.json` : null);
export const useTrend = (id: string) => useJson<TrendDoc>(`trend/${id}.json`);

/** Change of a ski day's forecast against the newest issue at least `minHours` older than `asOf`. */
export function trendChange(trend: TrendDoc | null, day: string, asOf: string | undefined, minHours = 20): number | null {
  if (!trend || !asOf) return null;
  const vals = trend.days[day];
  if (!vals) return null;
  const at = (iso: string) => Date.parse(iso);
  const now = trend.issues.findIndex((i) => i === asOf);
  const cur = now >= 0 ? now : trend.issues.length - 1;
  let prev = -1;
  for (let i = cur - 1; i >= 0; i--) if (at(trend.issues[cur]) - at(trend.issues[i]) >= minHours * 3_600_000) { prev = i; break; }
  if (prev < 0 || vals[cur] == null || vals[prev] == null) return null;
  return (vals[cur] as number) - (vals[prev] as number);
}
export const useVerification = () => useJson<VerificationDoc>("verification.json");
