export type Units = "imperial" | "metric";

const dash = "–";
const isNum = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v);

/** Snow depth: inches or cm. Below one unit keep a decimal so a dusting is not shown as 0. */
export function snowValue(cm: number | null | undefined, u: Units): number | null {
  return isNum(cm) ? (u === "imperial" ? cm / 2.54 : cm) : null;
}
export function fmtSnow(cm: number | null | undefined, u: Units, withUnit = true): string {
  const v = snowValue(cm, u);
  if (v === null) return dash;
  const unit = withUnit ? (u === "imperial" ? "″" : " cm") : "";
  if (v < 0.05) return `0${unit}`;
  return `${v < 1 ? v.toFixed(1) : Math.round(v)}${unit}`;
}
export const snowUnit = (u: Units) => (u === "imperial" ? "in" : "cm");

export function tempValue(c: number | null | undefined, u: Units): number | null {
  return isNum(c) ? (u === "imperial" ? c * 9 / 5 + 32 : c) : null;
}
export function fmtTemp(c: number | null | undefined, u: Units): string {
  const v = tempValue(c, u);
  return v === null ? dash : `${Math.round(v)}°`;
}
export const tempUnit = (u: Units) => (u === "imperial" ? "°F" : "°C");

export function heightValue(m: number | null | undefined, u: Units): number | null {
  return isNum(m) ? (u === "imperial" ? m * 3.28084 : m) : null;
}
/** `exact` is for fixed resort elevations; forecast heights are rounded to 100 ft / 50 m. */
export function fmtHeight(m: number | null | undefined, u: Units, exact = false): string {
  const v = heightValue(m, u);
  if (v === null) return dash;
  const r = exact ? (u === "imperial" ? Math.round(v / 10) * 10 : Math.round(v))
    : u === "imperial" ? Math.round(v / 100) * 100 : Math.round(v / 50) * 50;
  return `${r.toLocaleString("en-US")} ${u === "imperial" ? "ft" : "m"}`;
}
export const heightUnit = (u: Units) => (u === "imperial" ? "ft" : "m");

export function windValue(kmh: number | null | undefined, u: Units): number | null {
  return isNum(kmh) ? (u === "imperial" ? kmh / 1.609344 : kmh) : null;
}
export function fmtWind(kmh: number | null | undefined, u: Units): string {
  const v = windValue(kmh, u);
  return v === null ? dash : `${Math.round(v)} ${windUnit(u)}`;
}
export const windUnit = (u: Units) => (u === "imperial" ? "mph" : "km/h");

export function precipValue(mm: number | null | undefined, u: Units): number | null {
  return isNum(mm) ? (u === "imperial" ? mm / 25.4 : mm) : null;
}
export function fmtPrecip(mm: number | null | undefined, u: Units): string {
  const v = precipValue(mm, u);
  if (v === null) return dash;
  return u === "imperial" ? `${v.toFixed(2)}″` : `${v < 10 ? v.toFixed(1) : Math.round(v)} mm`;
}
