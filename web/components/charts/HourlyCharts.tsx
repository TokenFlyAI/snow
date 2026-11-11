"use client";
import { useMemo } from "react";
import type { Hourly, Level, ResortMeta } from "@/lib/types";
import { fmtHeight, fmtSnow, fmtTemp, fmtWind, heightUnit, heightValue, snowUnit, snowValue, tempUnit, tempValue, windUnit, windValue } from "@/lib/units";
import { useUser } from "../Providers";
import { axisStyle, baseOption, EChart, type Palette } from "./EChart";

const GROUP = "hourly";
const PTYPE = ["snow", "mix", "rain"] as const;

/** Four small charts on one shared time axis (never two y-scales in one chart). */
export function HourlyCharts({ hourly, resort, level }: { hourly: Hourly; resort: ResortMeta; level: Level }) {
  const { t, lang, units } = useUser();

  const axis = useMemo(() => {
    const fmtH = new Intl.DateTimeFormat("en-US", { timeZone: resort.timezone, hour: "numeric", hourCycle: "h23" });
    const fmtD = new Intl.DateTimeFormat(lang === "zh" ? "zh-CN" : "en-US", { timeZone: resort.timezone, weekday: "short", month: "numeric", day: "numeric" });
    const fmtFull = new Intl.DateTimeFormat(lang === "zh" ? "zh-CN" : "en-US", { timeZone: resort.timezone, weekday: "short", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
    const hours = hourly.time.map((s) => Number(fmtH.format(new Date(s))) % 24);
    const dayLabel = hourly.time.map((s, i) => (hours[i] === 0 ? fmtD.format(new Date(s)) : ""));
    const full = hourly.time.map((s) => fmtFull.format(new Date(s)));
    return { hours, dayLabel, full };
  }, [hourly.time, resort.timezone, lang]);

  const x = (p: Palette, showLabels: boolean) => ({
    type: "category", data: hourly.time, boundaryGap: true, ...axisStyle(p),
    axisLabel: { show: showLabels, color: p.muted, fontSize: 11, interval: (i: number) => axis.hours[i] === 0, formatter: (_: string, i: number) => axis.dayLabel[i] },
    splitLine: { show: true, interval: (i: number) => axis.hours[i] === 0, lineStyle: { color: p.grid } },
  });
  const y = (p: Palette, name: string, extra: object = {}) => ({
    type: "value", name, nameTextStyle: { color: p.muted, fontSize: 11, align: "right" }, splitNumber: 3, ...axisStyle(p), axisLine: { show: false }, ...extra,
  });
  const tip = (p: Palette, rows: (i: number) => [string, string][]) => ({
    ...(baseOption(p).tooltip as object), axisPointer: { type: "line", lineStyle: { color: p.muted, width: 1 } },
    formatter: (params: { dataIndex: number }[]) => {
      const i = params[0].dataIndex;
      return `<b>${axis.full[i]}</b>` + rows(i).map(([k, v]) => `<div style="display:flex;justify-content:space-between;gap:16px"><span>${k}</span><b>${v}</b></div>`).join("");
    },
  });
  const conv = (a: (number | null)[], f: (v: number | null, u: typeof units) => number | null, nd = 1) =>
    a.map((v) => { const r = f(v, units); return r === null ? null : +r.toFixed(nd); });
  const deps = [hourly, level, units, lang];
  const grid = { left: 4, right: 8, top: 46, bottom: 8, containLabel: true };

  const snow = (p: Palette) => ({
    ...baseOption(p), grid: { ...grid, top: 26 }, legend: { show: false },
    tooltip: tip(p, (i) => [
      [t("snow"), fmtSnow(hourly.snow_cm[level][i], units)],
      [t("ptype"), (hourly.precip_mm[i] ?? 0) > 0.05 && hourly.ptype[level][i] >= 0 ? t(PTYPE[hourly.ptype[level][i]]) : "–"],
      [t("precip"), `${(hourly.precip_mm[i] ?? 0).toFixed(1)} mm`],
    ]),
    xAxis: x(p, false),
    yAxis: y(p, `${snowUnit(units)}/h`, { min: 0, max: (v: { max: number }) => { const step = units === "imperial" ? 0.5 : 1; return Math.max(Math.ceil(v.max / step) * step, step); } }),
    series: [{ type: "bar", name: t("snow"), color: p.series[0], barCategoryGap: "10%", itemStyle: { borderRadius: [2, 2, 0, 0] }, data: conv(hourly.snow_cm[level], snowValue, 2) }],
  });

  const temp = (p: Palette) => ({
    ...baseOption(p), grid,
    legend: { ...(baseOption(p).legend as object), data: [t("summit"), t("base")] },
    tooltip: tip(p, (i) => [
      [t("summit"), fmtTemp(hourly.temp_c.summit[i], units)], [t("base"), fmtTemp(hourly.temp_c.base[i], units)],
      [`${t("feelsLike")} (${t("summit")})`, fmtTemp(hourly.feels_summit_c[i], units)],
    ]),
    xAxis: x(p, false),
    yAxis: y(p, tempUnit(units), { scale: true, min: (v: { min: number }) => Math.floor((v.min - 1) / 10) * 10, max: (v: { max: number }) => Math.ceil((v.max + 1) / 10) * 10 }),
    series: [
      { type: "line", name: t("summit"), color: p.series[0], symbol: "none", lineStyle: { width: 2 }, data: conv(hourly.temp_c.summit, tempValue),
        markLine: { silent: true, symbol: "none", lineStyle: { color: p.muted, type: "solid", width: 1 },
          label: { color: p.muted, fontSize: 10, formatter: units === "imperial" ? "32°F" : "0°C", position: "insideEndTop" },
          data: [{ yAxis: units === "imperial" ? 32 : 0 }] } },
      { type: "line", name: t("base"), color: p.series[1], symbol: "none", lineStyle: { width: 2 }, data: conv(hourly.temp_c.base, tempValue) },
    ],
  });

  const snowLevel = (p: Palette) => ({
    ...baseOption(p), grid,
    legend: { ...(baseOption(p).legend as object), data: [t("snowLevel"), t("freezingLevel")] },
    tooltip: tip(p, (i) => [[t("snowLevel"), fmtHeight(hourly.snow_level_m[i], units)], [t("freezingLevel"), fmtHeight(hourly.freezing_level_m[i], units)]]),
    xAxis: x(p, false),
    yAxis: y(p, heightUnit(units), { scale: true, min: (v: { min: number }) => { const step = units === "imperial" ? 1000 : 500; return Math.max(0, Math.floor((Math.min(v.min, heightValue(resort.elevation_m.base, units)!) - step / 4) / step) * step); } }),
    series: [
      { type: "line", name: t("snowLevel"), color: p.series[0], symbol: "none", lineStyle: { width: 2 }, data: conv(hourly.snow_level_m, heightValue, 0),
        markLine: { silent: true, symbol: "none", lineStyle: { color: p.text2, type: "solid", width: 1 },
          label: { color: p.text2, fontSize: 10, position: "insideStartTop", formatter: (d: { name: string }) => d.name },
          data: [{ yAxis: Math.round(heightValue(resort.elevation_m.summit, units)!), name: t("summit") }, { yAxis: Math.round(heightValue(resort.elevation_m.base, units)!), name: t("base") }] } },
      { type: "line", name: t("freezingLevel"), color: p.series[1], symbol: "none", lineStyle: { width: 2 }, data: conv(hourly.freezing_level_m, heightValue, 0) },
    ],
  });

  const wind = (p: Palette) => ({
    ...baseOption(p), grid: { ...grid, bottom: 4 },
    legend: { ...(baseOption(p).legend as object), data: [t("gust"), t("wind")] },
    tooltip: tip(p, (i) => [[t("gust"), fmtWind(hourly.gust_summit_kmh[i], units)], [t("wind"), fmtWind(hourly.wind_summit_kmh[i], units)]]),
    xAxis: x(p, true),
    yAxis: y(p, windUnit(units), { min: 0 }),
    series: [
      { type: "line", name: t("gust"), color: p.series[1], symbol: "none", lineStyle: { width: 2 }, data: conv(hourly.gust_summit_kmh, windValue, 0) },
      { type: "line", name: t("wind"), color: p.series[0], symbol: "none", lineStyle: { width: 2 }, areaStyle: { opacity: 0.1 }, data: conv(hourly.wind_summit_kmh, windValue, 0) },
    ],
  });

  const minWidth = 640;
  const block = (title: string, build: (p: Palette) => Record<string, unknown>, h: number) => (
    <div className="mt-4 first:mt-0">
      <h3 className="sticky left-0 mb-1 w-fit text-xs font-medium text-ink-2">{title}</h3>
      <EChart build={build} height={h} minWidth={minWidth} deps={deps} group={GROUP} ariaLabel={title} />
    </div>
  );
  return (
    <div className="scroll-x">
      {block(`${t("hourlySnow")} · ${t(level)}`, snow, 130)}
      {block(t("hourlyTemp"), temp, 170)}
      {block(t("hourlySnowLevel"), snowLevel, 190)}
      {block(t("hourlyWind"), wind, 180)}
    </div>
  );
}
