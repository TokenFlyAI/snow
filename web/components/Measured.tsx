"use client";
import { useState } from "react";
import { useUser } from "@/components/Providers";
import { useObs } from "@/lib/data";
import { fmtDate, fmtUpdated } from "@/lib/i18n";
import type { ObsDay } from "@/lib/types";
import { fmtHeight, fmtPrecip, fmtSnow, fmtTemp } from "@/lib/units";

const SHOW_DAYS = 7;

/** What the nearby SNOTEL stations measured over the last week (obs/{id}.json). Renders nothing without a station. */
export function Measured({ id, hasObs }: { id: string; hasObs: boolean }) {
  const { t, lang, units } = useUser();
  const { data } = useObs(hasObs ? id : null);
  const [pick, setPick] = useState(0);
  if (!data || data.stations.length === 0) return null;
  const st = data.stations[Math.min(pick, data.stations.length - 1)];
  const days = st.days.slice(-SHOW_DAYS);
  const fell = (d: ObsDay) => d.flags.includes("depth_fell");
  const snow = (d: ObsDay, cm: number | null) =>
    fell(d) ? <span title={t("measuredDepthFell")}>–*</span> : fmtSnow(cm, units);

  return (
    <section className="card mt-4 p-4">
      <h2 className="text-base font-semibold">{t("measuredTitle")}</h2>
      <p className="mb-3 mt-1 text-xs leading-5 text-ink-3">{t("measuredHint")}</p>
      {data.stations.length > 1 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {data.stations.map((s, i) => (
            <button key={s.triplet} className="chip" aria-pressed={i === pick} onClick={() => setPick(i)}>{s.name}</button>
          ))}
        </div>
      )}
      <p className="num mb-2 text-xs text-ink-2">
        {t("measuredStation")} <b className="text-ink">{st.name}</b> · {fmtHeight(st.elevation_m, units, true)} · {t("measuredAway").replace("{km}", String(st.km))}
        {" · "}<span title={t("measuredGradeHint")}>{t(`measuredGrade${st.grade}` as "measuredGradeA")}</span>
      </p>
      <div className="scroll-x">
        <table className="data num">
          <thead>
            <tr>
              <th>{t("date")}</th><th>{t("night")}</th><th>{t("measuredNewSnow")}</th><th>{t("measuredLiquid")}</th>
              <th>{t("measuredDepth")}</th><th>{t("measuredTemp")}</th>
            </tr>
          </thead>
          <tbody>
            {days.map((d) => (
              <tr key={d.date}>
                <td>{fmtDate(d.date, lang)}{!d.complete && <span className="ml-1 text-ink-3">({t("measuredSoFar")})</span>}</td>
                <td>{snow(d, d.snow_night_cm)}</td>
                <td className="font-semibold">{snow(d, d.snow_cm)}</td>
                <td>{fmtPrecip(d.precip_mm, units)}</td>
                <td>{fmtSnow(d.depth_cm, units)}</td>
                <td>{fmtTemp(d.temp_max_c, units)} / {fmtTemp(d.temp_min_c, units)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs leading-5 text-ink-3">
        {t("measuredSource")} · {t("updated")} {fmtUpdated(data.generated_at, lang)}
        {days.some(fell) && <> · –* {t("measuredDepthFell")}</>}
      </p>
    </section>
  );
}
