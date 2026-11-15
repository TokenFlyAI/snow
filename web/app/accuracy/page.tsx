"use client";
import { useMemo, useState } from "react";
import { LoadState, Updated } from "@/components/Bits";
import { axisStyle, baseOption, EChart, type Palette } from "@/components/charts/EChart";
import { useUser } from "@/components/Providers";
import { DATA_BASE, useVerification } from "@/lib/data";
import { fmtDate } from "@/lib/i18n";
import { REGIONS, resortById } from "@/lib/resorts";
import type { LeadScores, VerificationGroup } from "@/lib/types";
import { fmtSnow, snowUnit, snowValue } from "@/lib/units";

const REPO = "https://github.com/TokenFlyAI/snow";
/** Lines on the error chart: our blend and the raw models people know. */
const LINES: { key: string; models: string[]; label: string; slot: number }[] = [
  { key: "ours", models: [], label: "", slot: 0 },
  { key: "nbm", models: ["ncep_nbm_conus"], label: "NBM", slot: 2 },
  { key: "ecmwf", models: ["ecmwf_ifs", "ecmwf_ifs025"], label: "ECMWF", slot: 1 },
  { key: "gfs", models: ["gfs_global"], label: "GFS", slot: 3 },
];
const FEW_DAYS = 14;

/** MAE of a raw model at one lead (the 9 km and 0.25 deg ECMWF pooled by pair count). */
function modelMae(s: LeadScores | undefined, ids: string[]): number | null {
  let n = 0, sum = 0;
  for (const id of ids) {
    const m = s?.models?.[id];
    if (m && m.n) { n += m.n; sum += m.snow_mae_cm * m.n; }
  }
  return n ? sum / n : null;
}

export default function Accuracy() {
  const { t, ready, lang, units } = useUser();
  const { data, loading, error } = useVerification();
  const [win, setWin] = useState<"30d" | "season">("30d");
  const [scope, setScope] = useState("overall");
  const [resort, setResort] = useState<string | null>(null);

  const w = data?.windows[win];
  const group: VerificationGroup | undefined = !w ? undefined
    : scope === "overall" ? w.overall
    : scope.startsWith("r:") ? w.regions[scope.slice(2)] : w.resorts[scope.slice(2)];
  const leads = (data?.leads ?? []).map((k) => String(k)).filter((k) => !!group?.leads[k]);
  const chartLeads = leads.filter((k) => group?.leads[k].snow_mae_cm != null);   // day 10: probabilities only
  const recentResorts = useMemo(() => Array.from(new Set((data?.recent ?? []).map((r) => r.resort_id))).sort(), [data]);
  const pick = resort && recentResorts.includes(resort) ? resort : recentResorts[0];
  const rows = (data?.recent ?? []).filter((r) => r.resort_id === pick).slice().reverse();
  const name = (id: string) => { const m = resortById(id); return m ? (lang === "zh" && m.name_zh ? m.name_zh : m.name) : id; };
  const regionName = (id: string) => { const r = REGIONS.find((x) => x.id === id); return r ? (lang === "zh" ? r.name_zh : r.name) : id; };
  const season = data?.windows.season;
  if (!ready) return null;

  const build = (p: Palette) => ({
    ...baseOption(p),
    grid: { left: 4, right: 12, top: 52, bottom: 4, containLabel: true },
    tooltip: { ...(baseOption(p).tooltip as object), axisPointer: { type: "line", lineStyle: { color: p.line } },
      valueFormatter: (v: number | null) => (v == null ? "–" : `${v.toFixed(1)} ${snowUnit(units)}`) },
    xAxis: { type: "category", data: chartLeads.map((k) => (lang === "zh" ? `提前 ${k} 天` : `${k} day${k === "1" ? "" : "s"}`)), ...axisStyle(p) },
    yAxis: { type: "value", min: 0, name: snowUnit(units), nameTextStyle: { color: p.muted, fontSize: 11, align: "right" }, ...axisStyle(p), axisLine: { show: false } },
    series: LINES.map((l) => ({
      name: l.key === "ours" ? t("accOurs") : l.label, type: "line", symbol: "circle", symbolSize: 6, connectNulls: true,
      color: l.key === "ours" ? p.text : p.series[l.slot], lineStyle: { width: l.key === "ours" ? 2.5 : 1.5 },
      data: chartLeads.map((k) => {
        const s = group?.leads[k];
        const cm = l.key === "ours" ? s?.snow_mae_cm ?? null : modelMae(s, l.models);
        const v = snowValue(cm, units);
        return v == null ? null : +v.toFixed(2);
      }),
    })),
  });

  const rel = data?.windows[win].overall.reliability_15 ?? [];
  const buildRel = (p: Palette) => ({
    ...baseOption(p),
    grid: { left: 4, right: 12, top: 32, bottom: 28, containLabel: true },
    tooltip: { ...(baseOption(p).tooltip as object), trigger: "item",
      formatter: (x: { data: [number, number, number] }) => `${t("accRelSaid")} ${Math.round(x.data[0])}% → ${t("accRelHappened")} ${Math.round(x.data[1])}% (n=${x.data[2]})` },
    xAxis: { type: "value", min: 0, max: 100, name: t("accRelX"), nameLocation: "middle", nameGap: 26, nameTextStyle: { color: p.muted, fontSize: 11 }, ...axisStyle(p) },
    yAxis: { type: "value", min: 0, max: 100, name: t("accRelY"), nameGap: 12, nameTextStyle: { color: p.muted, fontSize: 11, align: "left", padding: [0, 0, 0, -24] }, ...axisStyle(p), axisLine: { show: false } },
    series: [
      { type: "line", data: [[0, 0], [100, 100]], symbol: "none", lineStyle: { color: p.line, type: "dashed", width: 1 }, tooltip: { show: false }, silent: true },
      { type: "line", data: rel.map((b) => [100 * b.forecast, 100 * b.observed, b.n]), color: p.text, symbol: "circle",
        symbolSize: (d: number[]) => Math.max(5, Math.min(16, 4 + Math.sqrt(d[2]))), lineStyle: { width: 2 } },
    ],
  });

  const pct = (x: number | null | undefined) => (x == null ? "–" : `${Math.round(100 * x)}%`);
  /** Errors keep one decimal: whole inches would hide the differences that matter here. */
  const err = (cm: number | null | undefined) => (cm == null ? "–" : units === "imperial" ? `${(cm / 2.54).toFixed(1)}″` : `${cm.toFixed(1)} cm`);
  const signed = (cm: number | null | undefined) => (cm == null ? "–" : `${cm > 0 ? "+" : cm < 0 ? "−" : ""}${err(Math.abs(cm))}`);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold">{t("accTitle")}</h1>
        <Updated iso={data?.generated_at} />
      </div>
      <p className="mt-2 text-xs leading-5 text-ink-3">{t("accIntro")}</p>
      <LoadState loading={loading} error={error} />

      {data && season && (
        <>
          {season.ski_days < FEW_DAYS && (
            <p className="card mt-3 p-4 text-sm leading-6 text-ink-2">
              {t("accFew").replace("{d}", String(season.ski_days)).replace("{r}", String(season.n_resorts))}
            </p>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {(["30d", "season"] as const).map((k) => (
              <button key={k} className="chip" aria-pressed={win === k} onClick={() => setWin(k)}>{t(k === "30d" ? "acc30d" : "accSeason")}</button>
            ))}
            <select className="chip" value={scope} onChange={(e) => setScope(e.target.value)} aria-label={t("accScope")}>
              <option value="overall">{t("accAllStations")}</option>
              <optgroup label={t("accRegions")}>
                {Object.keys(w?.regions ?? {}).map((id) => <option key={id} value={`r:${id}`}>{regionName(id)}</option>)}
              </optgroup>
              <optgroup label={t("accResorts")}>
                {Object.keys(w?.resorts ?? {}).sort((a, b) => name(a).localeCompare(name(b))).map((id) => <option key={id} value={`s:${id}`}>{name(id)}</option>)}
              </optgroup>
            </select>
          </div>

          <section className="card mt-4 p-4">
            <h2 className="text-base font-semibold">{t("accErrTitle")}</h2>
            <p className="mb-3 mt-1 text-xs leading-5 text-ink-3">{t("accErrHint")}</p>
            {chartLeads.length ? (
              <EChart build={build} height={240} deps={[group, units, lang]} ariaLabel={t("accErrTitle")} />
            ) : <p className="py-6 text-center text-sm text-ink-3">{t("accNoData")}</p>}
            {leads.length > 0 && (
              <div className="scroll-x mt-4">
                <table className="data num">
                  <thead>
                    <tr><th>{t("accLead")}</th><th>{t("accPairs")}</th><th>{t("accMae")}</th><th>{t("accBias")}</th>
                      <th>{t("accBig")}</th><th>{t("accCover")}</th><th>{t("accBrier")}</th><th>{t("accSkill")}</th></tr>
                  </thead>
                  <tbody>
                    {leads.map((k) => {
                      const s = group!.leads[k];
                      return (
                        <tr key={k}>
                          <td>{lang === "zh" ? `${k} 天` : `${k} d`}</td>
                          <td>{s.snow_n ?? s.n}</td>
                          <td className="font-semibold">{err(s.snow_mae_cm)}</td>
                          <td>{signed(s.snow_bias_cm)}</td>
                          <td title={s.big ? `${t("accHits")} ${s.big.hits} · ${t("accMisses")} ${s.big.misses} · ${t("accFalse")} ${s.big.false_alarms}` : undefined}>
                            {s.big && s.big.hits + s.big.misses + s.big.false_alarms ? `${s.big.hits}/${s.big.hits + s.big.misses}` : "–"}
                          </td>
                          <td>{pct(s.coverage?.ensemble_10_90 ?? s.coverage?.range)}</td>
                          <td>{s.brier_15 == null ? "–" : s.brier_15.toFixed(3)}</td>
                          <td>{s.skill_vs_nbm == null ? "–" : `${s.skill_vs_nbm > 0 ? "+" : ""}${Math.round(100 * s.skill_vs_nbm)}%`}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <p className="mt-3 text-xs leading-5 text-ink-3">{t("accTableHint")}</p>
          </section>

          {scope === "overall" && rel.length > 0 && (
            <section className="card mt-4 p-4">
              <h2 className="text-base font-semibold">{t("accRelTitle").replace("{t}", fmtSnow(15, units))}</h2>
              <p className="mb-3 mt-1 text-xs leading-5 text-ink-3">{t("accRelHint")}</p>
              <EChart build={buildRel} height={260} deps={[rel, lang]} ariaLabel={t("accRelTitle")} />
            </section>
          )}

          {recentResorts.length > 0 && (
            <section className="card mt-4 p-4">
              <h2 className="text-base font-semibold">{t("accDaysTitle")}</h2>
              <p className="mb-3 mt-1 text-xs leading-5 text-ink-3">{t("accDaysHint")}</p>
              <select className="chip mb-3" value={pick} onChange={(e) => setResort(e.target.value)} aria-label={t("accResorts")}>
                {recentResorts.map((id) => <option key={id} value={id}>{name(id)}</option>)}
              </select>
              <div className="scroll-x">
                <table className="data num">
                  <thead><tr><th>{t("date")}</th><th>{t("accMeasured")}</th><th>{t("accFc1")}</th><th>{t("accFc3")}</th></tr></thead>
                  <tbody>
                    {rows.map((r) => {
                      const f = (k: string) => {
                        const x = r.forecast[k];
                        return x ? <>{fmtSnow(x.snow_cm, units)}{x.low_cm != null && x.high_cm != null && <span className="ml-1 text-ink-3">({fmtSnow(x.low_cm, units, false)}–{fmtSnow(x.high_cm, units)})</span>}</> : "–";
                      };
                      const fell = r.flags.includes("depth_fell");
                      return (
                        <tr key={r.date}>
                          <td>{fmtDate(r.date, lang)}</td>
                          <td className="font-semibold">{fell ? <span title={t("measuredDepthFell")}>–*</span> : fmtSnow(r.obs_snow_cm, units)}</td>
                          <td>{f("1")}</td>
                          <td>{f("3")}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <section className="card mt-4 p-4 text-xs leading-5 text-ink-2">
            <h2 className="text-base font-semibold text-ink">{t("accCheck")}</h2>
            <p className="mt-1 text-ink-3">{t("accCheckHint")}</p>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              <li><a className="underline" href={`${DATA_BASE}/verification.json`}>verification.json</a> · {t("accDlScores")}</li>
              <li><a className="underline" href={`${REPO}/tree/archive`} target="_blank" rel="noopener noreferrer">{t("accDlArchive")}</a></li>
              <li><a className="underline" href={`${REPO}/blob/main/data/stations.yaml`} target="_blank" rel="noopener noreferrer">{t("accDlStations")}</a></li>
              <li><a className="underline" href={`${REPO}/blob/main/pipeline/verify/score.py`} target="_blank" rel="noopener noreferrer">{t("accDlMethod")}</a></li>
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
