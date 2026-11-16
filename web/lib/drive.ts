import meta from "./cities.generated.json";
import type { Lang } from "./i18n";
import { useEffect, useState } from "react";

/**
 * Drive times from a home city (scripts/build_drive_table.py -> data/drive.json): road distance from
 * OpenStreetMap via OSRM, converted at our own calibrated speed, with winter pass closures detoured.
 */
export interface City { id: string; name: string; name_zh: string; group: string; lat: number; lon: number }
export interface CityGroup { id: string; name: string; name_zh: string }
export interface DriveTable { minutes: Record<string, Record<string, number>>; via: Record<string, Record<string, string[]>> }

const M = meta as unknown as { groups: CityGroup[]; cities: City[]; closures: Record<string, string>; targets?: Record<string, [number, number]> };
export const CITY_GROUPS = M.groups;
export const CITIES = M.cities;
export const CLOSURES = M.closures;
/** Base-area parking for resorts whose terrain centre is a poor place to drive to (data/drive_targets.yaml). */
export const driveTarget = (id: string, lat: number, lon: number): [number, number] => M.targets?.[id] ?? [lat, lon];
export const HOURS = [2, 3, 4, 6, 8] as const;
export const DEFAULT_HOURS = 4;
/** The planner's home city, remembered on this device (set on the "Plan" page). */
export const FROM_KEY = "snow.plan.from.v1";
export function savedCity(): string {
  try { return localStorage.getItem(FROM_KEY) ?? ""; } catch { return ""; }
}

export const cityById = (id: string): City | undefined => CITIES.find((c) => c.id === id);
export const cityName = (c: City, lang: Lang) => (lang === "zh" ? c.name_zh : c.name);

let cache: Promise<DriveTable> | null = null;

/** The table, loaded on first use (it is ~100 KB; most visitors never pick a city). */
export function useDrive(from: string): DriveTable | null {
  const [table, setTable] = useState<DriveTable | null>(null);
  useEffect(() => {
    if (!from || table) return;
    let live = true;
    cache ??= import("./drive.generated.json").then((m) => (m.default ?? m) as unknown as DriveTable);
    cache.then((d) => { if (live) setTable(d); }).catch(() => { cache = null; });
    return () => { live = false; };
  }, [from, table]);
  return table;
}

/** "~45 min" / "~2.5 h", rounded so it does not look more precise than it is. */
export function fmtDrive(min: number, lang: Lang): string {
  const m = Math.max(10, Math.round(min / 5) * 5);
  if (m < 60) return lang === "zh" ? `约 ${m} 分钟` : `~${m} min`;
  const h = Math.round(min / 30) / 2;
  return lang === "zh" ? `约 ${h} 小时` : `~${h} h`;
}
