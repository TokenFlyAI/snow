import generated from "./resorts.generated.json";
import type { Lang } from "./i18n";

/**
 * Larger areas made of the regions in data/resorts.yaml, for the rank, map and planner filters
 * (data/region_groups.yaml; the calendar feeds use the same file).
 * A filter value is "all", a group id prefixed with "g:", or a single region id.
 */
export interface RegionGroup { id: string; name: string; name_zh: string; regions: string[] }

export const REGION_GROUPS = (generated as unknown as { groups: RegionGroup[] }).groups;
const REGION_IDS = new Set((generated as unknown as { regions: { id: string }[] }).regions.map((r) => r.id));

/** A filter value from a URL: unknown values become "all" (so the list and the dropdown agree);
 * "g-xxx" (the calendar feeds' spelling) is read as "g:xxx". */
export function normalizeArea(v: string | null | undefined): string {
  if (!v) return "all";
  const s = v.startsWith("g-") ? `g:${v.slice(2)}` : v;
  if (s.startsWith("g:")) return REGION_GROUPS.some((g) => g.id === s.slice(2)) ? s : "all";
  return REGION_IDS.has(s) ? s : "all";
}

/** Does a resort in `region` pass the filter `value`? */
export function inRegion(value: string, region: string): boolean {
  if (value === "all") return true;
  if (value.startsWith("g:")) return REGION_GROUPS.find((g) => g.id === value.slice(2))?.regions.includes(region) ?? false;
  return value === region;
}

/** Display name of a filter value. */
export function regionLabel(value: string, lang: Lang, regions: { id: string; name: string; name_zh: string }[]): string {
  const g = value.startsWith("g:") ? REGION_GROUPS.find((x) => x.id === value.slice(2)) : regions.find((x) => x.id === value);
  return g ? (lang === "zh" ? g.name_zh : g.name) : value;
}
