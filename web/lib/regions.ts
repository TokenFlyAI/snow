import type { Lang } from "./i18n";

/**
 * Larger areas made of the regions in data/resorts.yaml, for the rank and map filters.
 * A filter value is "all", a group id prefixed with "g:", or a single region id.
 */
export interface RegionGroup { id: string; name: string; name_zh: string; regions: string[] }

const US_WEST = ["tahoe", "sierra-south", "socal", "utah", "colorado", "southwest", "northern-rockies", "pnw", "alaska"];
const US_EAST = ["northeast", "mid-atlantic", "midwest"];
const CANADA = ["canada-west", "canada-east"];
const ALPS = ["alps-fr", "alps-ch", "alps-at", "alps-it", "dolomites"];

export const REGION_GROUPS: RegionGroup[] = [
  { id: "na", name: "US + Canada", name_zh: "美国 + 加拿大", regions: [...US_WEST, ...US_EAST, ...CANADA] },
  { id: "us", name: "United States", name_zh: "美国", regions: [...US_WEST, ...US_EAST] },
  { id: "us-west", name: "US West", name_zh: "美国西部", regions: US_WEST },
  { id: "us-east", name: "US East + Midwest", name_zh: "美国东部 + 中西部", regions: US_EAST },
  { id: "canada", name: "Canada", name_zh: "加拿大", regions: CANADA },
  { id: "west-na", name: "Western US + Canada", name_zh: "北美西部（美加）", regions: [...US_WEST, "canada-west"] },
  { id: "europe", name: "Europe", name_zh: "欧洲", regions: [...ALPS, "pyrenees"] },
  { id: "alps", name: "Alps", name_zh: "阿尔卑斯", regions: ALPS },
  { id: "asia", name: "Japan + East Asia", name_zh: "日本 + 东亚", regions: ["japan", "east-asia"] },
  { id: "south", name: "Southern Hemisphere", name_zh: "南半球", regions: ["australia", "new-zealand", "south-america"] },
];

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
