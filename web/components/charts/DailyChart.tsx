"use client";
import { fmtDate } from "@/lib/i18n";
import type { Daily, Level } from "@/lib/types";
import { fmtSnow, snowUnit, snowValue } from "@/lib/units";
import { useUser } from "../Providers";
import { axisStyle, baseOption, EChart, type Palette } from "./EChart";

/** Stacked overnight + daytime snowfall per ski day, with the model range as a whisker. */
export function DailyChart({ daily, level }: { daily: Daily[]; level: Level }) {
  const { t, lang, units } = useUser();
  const labels = daily.map((d) => fmtDate(d.date, lang));
  const far = (i: number) => daily[i].lead_days >= 10;

  const build = (p: Palette) => {
    const night = daily.map((d) => snowValue(d.snow_night_cm[level], units) ?? 0);
    const day = daily.map((d) => snowValue(d.snow_day_cm[level], units) ?? 0);
    const item = (v: number, i: number, color: string, top: boolean) => ({
      value: +v.toFixed(2),
      itemStyle: { color, opacity: far(i) ? 0.5 : 1, borderColor: p.surface, borderWidth: 1, borderRadius: top ? [4, 4, 0, 0] : 0 },
    });
    const labelMin = units === "imperial" ? 1 : 2.5;
    return {
      ...baseOption(p),
      grid: { left: 4, right: 8, top: 50, bottom: 4, containLabel: true },
      legend: { ...(baseOption(p).legend as object), data: [t("night"), t("day")] },
      tooltip: {
        ...(baseOption(p).tooltip as object),
        formatter: (params: { dataIndex: number }[]) => {
          const d = daily[params[0].dataIndex];
          const row = (k: string, v: string) => `<div style="display:flex;justify-content:space-between;gap:16px"><span>${k}</span><b>${v}</b></div>`;
          return `<b>${fmtDate(d.date, lang)}</b>`
            + row(t("night"), fmtSnow(d.snow_night_cm[level], units)) + row(t("day"), fmtSnow(d.snow_day_cm[level], units))
            + row(t("total"), fmtSnow(d.snow_cm[level], units))
            + row(t("range"), `${fmtSnow(d.snow_low_cm[level], units, false)}–${fmtSnow(d.snow_high_cm[level], units)}`)
            + row(t("confidence"), t(d.confidence))
            + (far(params[0].dataIndex) ? `<div style="color:${p.muted};margin-top:4px">${t("farOut")}</div>` : "");
        },
      },
      xAxis: {
        type: "category", data: labels, ...axisStyle(p),
        axisLabel: { color: p.muted, fontSize: 11, interval: 0, formatter: (v: string) => v.replace(" ", "\n") },
      },
      yAxis: { type: "value", name: snowUnit(units), nameTextStyle: { color: p.muted, fontSize: 11, align: "right" }, minInterval: 1, ...axisStyle(p), axisLine: { show: false },
        max: (v: { max: number }) => Math.ceil(Math.max(v.max, units === "imperial" ? 2 : 5) * 1.12) },
      series: [
        { name: t("night"), type: "bar", stack: "snow", barMaxWidth: 24, color: p.series[0],
          data: night.map((v, i) => item(v, i, p.series[0], day[i] < 0.005)) },
        { name: t("day"), type: "bar", stack: "snow", barMaxWidth: 24, color: p.series[1],
          data: day.map((v, i) => item(v, i, p.series[1], true)) },
        {
          // 10-90 % range across models + the total as a selective direct label
          type: "custom", name: t("range"), silent: true, z: 5, tooltip: { show: false },
          encode: { x: 0, y: [1, 2, 3] },        // axis extent must include the top of the whisker
          data: daily.map((d, i) => [i, snowValue(d.snow_low_cm[level], units) ?? 0, snowValue(d.snow_high_cm[level], units) ?? 0, night[i] + day[i]]),
          renderItem: (_: unknown, api: { value: (i: number) => number; coord: (v: number[]) => number[] }) => {
            const i = api.value(0), lo = api.value(1), hi = api.value(2), tot = api.value(3);
            const a = api.coord([i, lo]), b = api.coord([i, hi]), top = api.coord([i, Math.max(hi, tot)]);
            const children: unknown[] = [];
            if (hi - lo > 0.05) {
              const style = { stroke: p.text2, lineWidth: 1.5, opacity: 0.9 };
              children.push({ type: "line", shape: { x1: a[0], y1: a[1], x2: b[0], y2: b[1] }, style });
              children.push({ type: "line", shape: { x1: b[0] - 4, y1: b[1], x2: b[0] + 4, y2: b[1] }, style });
              children.push({ type: "line", shape: { x1: a[0] - 4, y1: a[1], x2: a[0] + 4, y2: a[1] }, style });
            }
            if (tot >= labelMin) {
              children.push({ type: "text", style: { text: String(Math.round(tot)), x: top[0], y: top[1] - 6, textAlign: "center", textVerticalAlign: "bottom", fill: p.text, fontSize: 11, fontWeight: 600 } });
            }
            return { type: "group", children };
          },
        },
      ],
    };
  };
  const minWidth = Math.max(daily.length * 38, 320);
  return (
    <div className="scroll-x">
      <EChart build={build} height={250} minWidth={minWidth} deps={[daily, level, units, lang]}
        ariaLabel={`${t("daily")} (${t(level)})`} />
    </div>
  );
}
