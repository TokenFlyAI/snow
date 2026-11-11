// Turns ../data/resorts.yaml into lib/resorts.generated.json so the picker and
// the static resort routes work even when the forecast data is unreachable.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";

const here = dirname(fileURLToPath(import.meta.url));
const db = parse(readFileSync(resolve(here, "../../data/resorts.yaml"), "utf8"));
const resorts = db.resorts.map((r) => ({
  id: r.id, name: r.name, name_zh: r.name_zh ?? null, destination: r.destination ?? null,
  passes: r.passes ?? {}, country: r.country, state: r.state ?? null, region: r.region,
  lat: r.lat, lon: r.lon, elevation_m: r.elevation_m, timezone: r.timezone,
  needs_review: !!r.needs_review,
}));
writeFileSync(resolve(here, "../lib/resorts.generated.json"),
  JSON.stringify({ regions: db.regions, resorts }, null, 1));
console.log(`gen-resorts: ${resorts.length} resorts, ${db.regions.length} regions`);
