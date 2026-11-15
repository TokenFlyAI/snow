"use client";
import { fmtDate } from "@/lib/i18n";
import type { CumulativeDay, Level } from "@/lib/types";
import { fmtSnow, snowUnit, snowValue } from "@/lib/units";
import { useUser } from "../Providers";
import { axisStyle, baseOption, EChart, type Palette } from "./EChart";

/**
 * Snowfall accumulated from today on: the forecast line inside two shaded ranges of the
 * ensemble members' own accumulations (min-max, and 10-90 %). The fan opens with lead time.
 */
export function CumulativeChart({ days, level }: { days: CumulativeDay[]; level: Level }) {
  const { t, lang, units } = useUser();
  const labels = days.map((d) => fmtDate(d.date, lang));

  const build = (p: Palette) => {
    const num = (cm: number | null | undefined) => { const v = snowValue(cm, units); return v === null ? null : +v.toFixed(2); };
    const col = (k: "min" | "p10" | "cm" | "p90" | "max") => days.map((d) => num(d[k][level]));
    const [lo, p10, fc, p90, hi] = [col("min"), col("p10"), col("cm"), col("p90"), col("max")];
    const diff = (a: (number | null)[], b: (number | null)[]) => a.map((v, i) => (v === null || b[i] === null ? null : +(v - (b[i] as number)).toFixed(2)));
    const blue = p.series[0];
    const row = (k: string, v: string) => `<div style="display:flex;justify-content:space-between;gap:16px"><span>${k}</span><b>${v}</b></div>`;
    const base = baseOption(p);
    const hidden = { type: "line", symbol: "none", silent: true, lineStyle: { opacity: 0 }, tooltip: { show: false } };
    const last = days.length - 1;
    const end = (value: number, color: string, weight: number) => ({
      show: true, formatter: () => String(value), color, fontSize: 11, fontWeight: weight, distance: 4,
    });
    // labels closer than this to the forecast value would sit on top of it
    const gap = Math.max((hi[last] ?? 0) * 0.07, units === "imperial" ? 1 : 2);
    const showHigh = (hi[last] ?? 0) - (fc[last] ?? 0) >= gap;
    const showLow = (fc[last] ?? 0) - (lo[last] ?? 0) >= gap;
    return {
      ...base,
      grid: { left: 4, right: 34, top: 50, bottom: 4, containLabel: true },
      legend: { ...(base.legend as object), data: [t("cumForecast"), t("cumBand"), t("cumMinMax")] },
      tooltip: {
        ...(base.tooltip as object),
        axisPointer: { type: "line", lineStyle: { color: p.line } },
        formatter: (params: { dataIndex: number }[]) => {
          const d = days[params[0].dataIndex];
          return `<b>${fmtDate(d.date, lang)}</b>`
            + row(t("cumForecast"), fmtSnow(d.cm[level], units))
            + row(t("cumBand"), `${fmtSnow(d.p10[level], units, false)}–${fmtSnow(d.p90[level], units)}`)
            + row(t("cumMinMax"), `${fmtSnow(d.min[level], units, false)}–${fmtSnow(d.max[level], units)}`)
            + `<div style="color:${p.muted};margin-top:4px">${d.n_members} ${t("members")}</div>`;
        },
      },
      xAxis: {
        type: "category", data: labels, boundaryGap: false, ...axisStyle(p),
        // the whole fan has to fit a phone screen, so labels thin out instead of the chart scrolling
        axisLabel: { color: p.muted, fontSize: 11, interval: "auto", hideOverlap: true, formatter: (v: string) => v.replace(" ", "\n") },
      },
      yAxis: { type: "value", name: snowUnit(units), nameTextStyle: { color: p.muted, fontSize: 11, align: "right" }, min: 0, minInterval: 1,
        ...axisStyle(p), axisLine: { show: false } },
      series: [
        // each range = an invisible lower line plus the stacked difference drawn as an area
        { ...hidden, name: "min", stack: "outer", z: 1, data: lo,
          endLabel: showLow ? end(Math.round(lo[last] ?? 0), p.muted, 400) : undefined },
        { ...hidden, name: t("cumMinMax"), stack: "outer", z: 1, color: blue,
          areaStyle: { color: blue, opacity: 0.16 }, itemStyle: { color: blue, opacity: 0.3 }, data: diff(hi, lo),
          endLabel: showHigh ? end(Math.round(hi[last] ?? 0), p.muted, 400) : undefined },
        { ...hidden, name: "p10", stack: "inner", z: 2, data: p10 },
        { ...hidden, name: t("cumBand"), stack: "inner", z: 2, color: blue,
          areaStyle: { color: blue, opacity: 0.32 }, itemStyle: { color: blue, opacity: 0.55 }, data: diff(p90, p10) },
        { name: t("cumForecast"), type: "line", symbol: "none", z: 3, color: blue, lineStyle: { color: blue, width: 2.5 }, data: fc,
          // the numbers that matter, at the right edge: forecast, most, least
          endLabel: end(Math.round(fc[last] ?? 0), p.text, 600) },
      ],
    };
  };
  return (
    <EChart build={build} height={260} deps={[days, level, units, lang]}
      ariaLabel={`${t("cumTitle")} (${t(level)})`} />
  );
}
