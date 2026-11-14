"use client";
import { fmtDate, fmtProb } from "@/lib/i18n";
import type { DayEntry, Level } from "@/lib/types";
import { fmtSnow, fmtThreshold, snowUnit, snowValue } from "@/lib/units";
import { useUser } from "../Providers";
import { axisStyle, baseOption, EChart, type Palette } from "./EChart";

/**
 * Ski days D+0..D+9: stacked overnight + daytime snowfall from the blend.
 * All 16 days: the ensemble 10-90 % band and median behind the bars.
 * Days 11-16 carry no bar: only the band (the table below gives the probabilities).
 */
export function DailyChart({ daily, level }: { daily: DayEntry[]; level: Level }) {
  const { t, lang, units } = useUser();
  const labels = daily.map((d) => fmtDate(d.date, lang));
  const firstProb = daily.findIndex((d) => d.kind === "prob");

  const build = (p: Palette) => {
    const num = (cm: number | null | undefined) => { const v = snowValue(cm, units); return v === null ? null : +v.toFixed(2); };
    const night = daily.map((d) => (d.kind === "point" ? num(d.snow_night_cm[level]) ?? 0 : null));
    const day = daily.map((d) => (d.kind === "point" ? num(d.snow_day_cm[level]) ?? 0 : null));
    const lo = daily.map((d) => (d.ens ? num(d.ens.p10[level]) : null));
    const hi = daily.map((d) => (d.ens ? num(d.ens.p90[level]) : null));
    const med = daily.map((d) => (d.ens ? num(d.ens.p50[level]) : null));
    const hasEns = med.some((v) => v !== null);
    const bar = (v: number | null, color: string, top: boolean) => (v === null ? "-" : {
      value: v, itemStyle: { color, borderColor: p.surface, borderWidth: 1, borderRadius: top ? [4, 4, 0, 0] : 0 },
    });
    const labelMin = units === "imperial" ? 1 : 2.5;
    const row = (k: string, v: string) => `<div style="display:flex;justify-content:space-between;gap:16px"><span>${k}</span><b>${v}</b></div>`;
    const base = baseOption(p);
    return {
      ...base,
      grid: { left: 4, right: 8, top: hasEns ? 64 : 50, bottom: 4, containLabel: true },
      legend: { ...(base.legend as object), data: hasEns ? [t("night"), t("day"), t("ensBand"), t("ensMedian")] : [t("night"), t("day")] },
      tooltip: {
        ...(base.tooltip as object),
        formatter: (params: { dataIndex: number }[]) => {
          const d = daily[params[0].dataIndex];
          let html = `<b>${fmtDate(d.date, lang)}</b>`;
          if (d.kind === "point") {
            html += row(t("night"), fmtSnow(d.snow_night_cm[level], units)) + row(t("day"), fmtSnow(d.snow_day_cm[level], units))
              + row(t("total"), fmtSnow(d.snow_cm[level], units))
              + row(d.range_source === "ensemble" ? t("ensBand") : t("rangeFromModels"),
                `${fmtSnow(d.snow_low_cm[level], units, false)}–${fmtSnow(d.snow_high_cm[level], units)}`)
              + row(t("confidence"), t(d.confidence));
          }
          if (d.ens) {
            if (d.kind === "prob") {
              html += row(t("ensBand"), `${fmtSnow(d.ens.p10[level], units, false)}–${fmtSnow(d.ens.p90[level], units)}`);
            }
            html += row(t("ensMedian"), fmtSnow(d.ens.p50[level], units));
            for (const thr of Object.keys(d.ens.prob)) {
              html += row(`≥ ${fmtThreshold(thr, units)} ${t("probAtLeast")}`, fmtProb(d.ens.prob[thr][level]));
            }
            html += `<div style="color:${p.muted};margin-top:4px">${d.ens.n_members} ${t("members")}</div>`;
          }
          return html;
        },
      },
      xAxis: {
        type: "category", data: labels, ...axisStyle(p),
        axisLabel: { color: p.muted, fontSize: 11, interval: 0, formatter: (v: string) => v.replace(" ", "\n") },
      },
      yAxis: { type: "value", name: snowUnit(units), nameTextStyle: { color: p.muted, fontSize: 11, align: "right" }, minInterval: 1, ...axisStyle(p), axisLine: { show: false },
        max: (v: { max: number }) => Math.ceil(Math.max(v.max, units === "imperial" ? 2 : 5) * 1.12) },
      series: [
        // ensemble 10-90 % band: an invisible lower line plus the stacked difference as the filled area
        { name: "ens-low", type: "line", stack: "band", symbol: "none", silent: true, z: 1,
          lineStyle: { opacity: 0 }, tooltip: { show: false }, data: lo },
        { name: t("ensBand"), type: "line", stack: "band", symbol: "none", silent: true, z: 1, color: p.muted,
          lineStyle: { opacity: 0 }, areaStyle: { color: p.muted, opacity: 0.28 }, itemStyle: { color: p.muted, opacity: 0.45 },
          data: hi.map((v, i) => (v === null || lo[i] === null ? null : +(v - (lo[i] as number)).toFixed(2))),
          markArea: firstProb > 0 ? {
            silent: true, itemStyle: { color: p.grid, opacity: 0.45 },
            label: { show: true, position: "insideTop", color: p.muted, fontSize: 11, formatter: t("farOut") },
            data: [[{ xAxis: labels[firstProb] }, { xAxis: labels[labels.length - 1] }]],
          } : undefined },
        { name: t("night"), type: "bar", stack: "snow", barMaxWidth: 22, color: p.series[0], z: 2,
          data: night.map((v, i) => bar(v, p.series[0], (day[i] ?? 0) < 0.005)) },
        { name: t("day"), type: "bar", stack: "snow", barMaxWidth: 22, color: p.series[1], z: 2,
          data: day.map((v) => bar(v, p.series[1], true)) },
        { name: t("ensMedian"), type: "line", symbol: "none", z: 3, color: p.text2,
          lineStyle: { color: p.text2, width: 1.5, type: "dashed" }, data: med },
        {
          // the blend total as a selective direct label above the bar
          type: "custom", name: "total", silent: true, z: 5, tooltip: { show: false },
          encode: { x: 0, y: 1 },
          data: daily.map((d, i) => [i, d.kind === "point" ? (night[i] ?? 0) + (day[i] ?? 0) : 0, d.kind === "point" ? 1 : 0]),
          renderItem: (_: unknown, api: { value: (i: number) => number; coord: (v: number[]) => number[] }) => {
            const i = api.value(0), tot = api.value(1);
            if (!api.value(2) || tot < labelMin) return { type: "group", children: [] };
            const top = api.coord([i, tot]);
            return { type: "text", style: { text: String(Math.round(tot)), x: top[0], y: top[1] - 5, textAlign: "center", textVerticalAlign: "bottom",
              fill: p.text, fontSize: 11, fontWeight: 600, stroke: p.surface, lineWidth: 3 } };
          },
        },
      ],
    };
  };
  const minWidth = Math.max(daily.length * 38, 320);
  return (
    <div className="scroll-x">
      <EChart build={build} height={270} minWidth={minWidth} deps={[daily, level, units, lang]}
        ariaLabel={`${t("daily")} (${t(level)})`} />
    </div>
  );
}
