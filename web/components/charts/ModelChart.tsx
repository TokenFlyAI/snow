"use client";
import { useState } from "react";
import { fmtDate } from "@/lib/i18n";
import type { Level, ResortDoc } from "@/lib/types";
import { fmtSnow, snowUnit, snowValue } from "@/lib/units";
import { useUser } from "../Providers";
import { axisStyle, baseOption, EChart, type Palette } from "./EChart";

/** Fixed colour slot per model so a colour always means the same model. */
const SLOT: Record<string, number> = {
  ecmwf_ifs025: 0, gfs_global: 1, ncep_nbm_conus: 2, icon_seamless: 3,
  ecmwf_aifs025_single: 4, gem_global: 5, ncep_hrrr_conus: 6, gem_hrdps_continental: 6, jma_seamless: 6, ncep_rrfs_conus: 7,
};

export function ModelChart({ doc, level }: { doc: ResortDoc; level: Level }) {
  const { t, lang, units } = useUser();
  const [view, setView] = useState<"chart" | "table">("chart");
  const models = doc.models.filter((m) => m.status === "ok" && doc.by_model_daily_cm[m.id])
    .sort((a, b) => (SLOT[a.id] ?? 9) - (SLOT[b.id] ?? 9));
  const days = doc.daily;
  const labels = days.map((d) => fmtDate(d.date, lang));

  const build = (p: Palette) => ({
    ...baseOption(p),
    grid: { left: 4, right: 8, top: 56, bottom: 4, containLabel: true },
    legend: { ...(baseOption(p).legend as object), type: "scroll", pageIconColor: p.text2, pageTextStyle: { color: p.muted } },
    tooltip: {
      ...(baseOption(p).tooltip as object),
      formatter: (params: { dataIndex: number }[]) => {
        const i = params[0].dataIndex;
        const row = (k: string, v: string, c?: string) =>
          `<div style="display:flex;justify-content:space-between;gap:16px"><span>${c ? `<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${c};margin-right:6px"></span>` : ""}${k}</span><b>${v}</b></div>`;
        return `<b>${labels[i]}</b>` + row(t("blend"), fmtSnow(days[i].snow_cm[level], units))
          + models.map((m) => row(m.label, fmtSnow(doc.by_model_daily_cm[m.id][level][i], units), p.series[SLOT[m.id] ?? 0])).join("");
      },
    },
    xAxis: { type: "category", data: labels, ...axisStyle(p),
      axisLabel: { color: p.muted, fontSize: 11, interval: 0, formatter: (v: string) => v.replace(" ", "\n") } },
    yAxis: { type: "value", name: snowUnit(units), nameTextStyle: { color: p.muted, fontSize: 11, align: "right" }, minInterval: 1, ...axisStyle(p), axisLine: { show: false } },
    series: [
      ...models.map((m) => ({
        name: m.label, type: "bar", barMaxWidth: 6, barGap: "15%", barCategoryGap: "24%",
        color: p.series[SLOT[m.id] ?? 0],
        itemStyle: { borderRadius: [2, 2, 0, 0] },
        data: doc.by_model_daily_cm[m.id][level].map((v) => { const x = snowValue(v, units); return x === null ? null : +x.toFixed(2); }),
      })),
      { name: t("blend"), type: "line", step: "middle", symbol: "none", color: p.text, lineStyle: { width: 2, color: p.text }, z: 6,
        data: days.map((d) => { const x = snowValue(d.snow_cm[level], units); return x === null ? null : +x.toFixed(2); }) },
    ],
  });

  const minWidth = Math.max(days.length * (models.length * 7 + 14), 320);
  return (
    <div>
      <div className="mb-2 flex justify-end gap-1.5">
        <button className="chip" aria-pressed={view === "chart"} onClick={() => setView("chart")}>{t("chart")}</button>
        <button className="chip" aria-pressed={view === "table"} onClick={() => setView("table")}>{t("table")}</button>
      </div>
      {view === "chart" ? (
        <div className="scroll-x">
          <EChart build={build} height={290} minWidth={minWidth} deps={[doc, level, units, lang]} ariaLabel={t("models")} />
        </div>
      ) : (
        <div className="scroll-x">
          <table className="data num">
            <thead><tr><th>{snowUnit(units)}</th>{days.map((d) => <th key={d.date}>{fmtDate(d.date, lang)}</th>)}</tr></thead>
            <tbody>
              <tr><td className="font-semibold">{t("blend")}</td>{days.map((d) => <td key={d.date} className="font-semibold">{fmtSnow(d.snow_cm[level], units, false)}</td>)}</tr>
              {models.map((m) => (
                <tr key={m.id}><td>{m.label}</td>
                  {doc.by_model_daily_cm[m.id][level].map((v, i) => <td key={i} className={v === null ? "text-ink-3" : ""}>{fmtSnow(v, units, false)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-3">
        {doc.models.map((m) => (
          <li key={m.id}>
            <span className="text-ink-2">{m.label}</span>{" "}
            {m.status === "ok"
              ? `${t("horizon")} ${Math.round((m.horizon_h ?? 0) / 24)}d`
              : <span>⚠ {t("modelMissing")}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
