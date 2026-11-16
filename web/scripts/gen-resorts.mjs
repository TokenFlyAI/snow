// Turns ../data/resorts.yaml into lib/resorts.generated.json so the picker and
// the static resort routes work even when the forecast data is unreachable.
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";

const here = dirname(fileURLToPath(import.meta.url));
const db = parse(readFileSync(resolve(here, "../../data/resorts.yaml"), "utf8"));
// resorts with a matched measuring station (scripts/match_stations.py) get obs/{id}.json
const stationsFile = resolve(here, "../../data/stations.yaml");
const withObs = new Set(Object.keys((existsSync(stationsFile) && parse(readFileSync(stationsFile, "utf8"))?.resorts) || {}));
const resorts = db.resorts.map((r) => ({
  id: r.id, name: r.name, name_zh: r.name_zh ?? null, destination: r.destination ?? null,
  passes: r.passes ?? {}, country: r.country, state: r.state ?? null, region: r.region,
  lat: r.lat, lon: r.lon, elevation_m: r.elevation_m, timezone: r.timezone,
  needs_review: !!r.needs_review, has_obs: withObs.has(r.id),
}));
const groups = parse(readFileSync(resolve(here, "../../data/region_groups.yaml"), "utf8")).groups;
// Lower-tier pass products (data/pass_products.yaml; same rules as pipeline/passes.py)
const iso = (d) => (d instanceof Date ? d.toISOString().slice(0, 10) : String(d));
const merge = (rs) => rs.slice().sort((x, y) => (x[0] < y[0] ? -1 : 1)).reduce((out, [a, b]) => {
  const last = out[out.length - 1];
  if (last && a <= last[1]) last[1] = b > last[1] ? b : last[1]; else out.push([a, b]);
  return out;
}, []);
const productDefs = parse(readFileSync(resolve(here, "../../data/pass_products.yaml"), "utf8"), { version: "1.1" }).products;
const products = productDefs.map((p) => ({ id: p.id, pass: p.pass, name: p.name }));
const productAccess = Object.fromEntries(productDefs.map((p) => {
  const base = (p.blackout ?? []).map(([a, b]) => [iso(a), iso(b)]);
  const acc = {};
  for (const e of p.access) {
    const ranges = merge([...(e.blackout ? base : []), ...(e.extra ?? []).map(([a, b]) => [iso(a), iso(b)])]);
    for (const r of e.resorts) acc[r] = { days: e.days, shared: !!e.shared, blackout: ranges, consecutive: !!e.consecutive };
  }
  return [p.id, acc];
}));
writeFileSync(resolve(here, "../lib/resorts.generated.json"),
  JSON.stringify({ regions: db.regions, groups, resorts, products, product_access: productAccess }, null, 1));
console.log(`gen-resorts: ${resorts.length} resorts, ${db.regions.length} regions, ${withObs.size} with observations`);

// Drive times for the planner (scripts/build_drive_table.py): the city list is small and goes into
// the page; the table is loaded only once a city is picked.
const cities = parse(readFileSync(resolve(here, "../../data/cities.yaml"), "utf8"));
const driveFile = resolve(here, "../../data/drive.json");
const drive = existsSync(driveFile) ? JSON.parse(readFileSync(driveFile, "utf8")) : { minutes: {}, via: {}, closures: {} };
const known = new Set(resorts.map((r) => r.id));
const minutes = Object.fromEntries(Object.entries(drive.minutes).map(([c, m]) => [c, Object.fromEntries(Object.entries(m).filter(([r]) => known.has(r)))]));
writeFileSync(resolve(here, "../lib/cities.generated.json"), JSON.stringify({
  groups: cities.groups,
  cities: cities.cities.filter((c) => minutes[c.id] && Object.keys(minutes[c.id]).length),
  closures: drive.closures ?? {},
  targets: drive.targets ?? {},
}));
writeFileSync(resolve(here, "../lib/drive.generated.json"), JSON.stringify({ minutes, via: drive.via ?? {} }));
console.log(`gen-resorts: drive times from ${Object.keys(minutes).length} cities`);
