"use client";
import { FollowButton, LevelPicker, LoadState, PassBadges, resortName, Updated } from "@/components/Bits";
import { DailyChart } from "@/components/charts/DailyChart";
import { HourlyCharts } from "@/components/charts/HourlyCharts";
import { ModelChart } from "@/components/charts/ModelChart";
import { useUser } from "@/components/Providers";
import { useResort } from "@/lib/data";
import { fmtDate } from "@/lib/i18n";
import { REGIONS, resortById } from "@/lib/resorts";
import type { Daily } from "@/lib/types";
import { fmtHeight, fmtPrecip, fmtSnow, fmtTemp, fmtWind } from "@/lib/units";

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="card mt-4 p-4">
      <h2 className="text-base font-semibold">{title}</h2>
      {hint && <p className="mb-3 mt-1 text-xs leading-5 text-ink-3">{hint}</p>}
      {children}
    </section>
  );
}

export default function ResortClient({ id }: { id: string }) {
  const { t, ready, lang, units, level } = useUser();
  const meta = resortById(id);
  const { data, loading, error } = useResort(id);
  if (!ready || !meta) return null;
  const region = REGIONS.find((r) => r.id === meta.region);
  const s = data?.summary;
  const confDot = (d: Daily) => ({ high: "var(--good)", medium: "var(--warning)", low: "var(--critical)" }[d.confidence]);

  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold leading-tight">{resortName(meta, lang)}</h1>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-ink-3">
            <span>{region ? (lang === "zh" ? region.name_zh : region.name) : meta.region}</span>
            <PassBadges passes={meta.passes} />
          </div>
          <p className="num mt-1.5 text-xs text-ink-2">
            {t("base")} {fmtHeight(meta.elevation_m.base, units, true)} · {t("mid")} {fmtHeight(meta.elevation_m.mid, units, true)} · {t("summit")} {fmtHeight(meta.elevation_m.summit, units, true)}
          </p>
          {meta.needs_review && <p className="mt-1 text-xs text-ink-3">⚠ {t("needsReview")}</p>}
        </div>
        <FollowButton id={id} />
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        <LevelPicker />
        <Updated iso={data?.generated_at} />
      </div>
      <LoadState loading={loading} error={error} />

      {data && s && (
        <>
          <div className="mt-3 grid grid-cols-4 gap-2">
            {([["next24h", s.snow_24h_cm], ["next72h", s.snow_72h_cm], ["next7d", s.snow_7d_cm], ["next16d", s.snow_16d_cm]] as const).map(([k, v]) => (
              <div key={k} className="card px-3 py-2.5">
                <div className="text-[11px] text-ink-3">{t(k)}</div>
                <div className="num text-xl font-semibold">{fmtSnow(v[level], units)}</div>
              </div>
            ))}
          </div>
          <p className="mt-2 text-sm text-ink-2">
            {s.next_snow
              ? <>{t("nextSnow")}: <b className="text-ink">{fmtDate(s.next_snow.date, lang)}</b> · {fmtSnow(s.next_snow.snow_cm[level], units)}</>
              : t("noSnowAhead")}
          </p>

          <Section title={`${t("daily")} · ${t(level)}`} hint={t("dailyHint")}>
            <DailyChart daily={data.daily} level={level} />
            <div className="scroll-x mt-4">
              <table className="data num">
                <thead>
                  <tr>
                    <th>{t("date")}</th><th>{t("night")}</th><th>{t("day")}</th><th>{t("total")}</th><th>{t("range")}</th>
                    <th>{t("quality")}</th><th>{t("confidence")}</th>
                    <th>{t("summit")} {t("tempHiLo")}</th><th>{t("base")} {t("tempHiLo")}</th>
                    <th>{t("snowLevel")}</th><th>{t("rainBase")}</th><th>{t("summitGust")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.daily.map((d) => (
                    <tr key={d.date} className={d.lead_days >= 10 ? "text-ink-3" : ""}>
                      <td>{d.lead_days === 0 ? t("today") : fmtDate(d.date, lang)}</td>
                      <td>{fmtSnow(d.snow_night_cm[level], units)}</td>
                      <td>{fmtSnow(d.snow_day_cm[level], units)}</td>
                      <td className="font-semibold">{fmtSnow(d.snow_cm[level], units)}</td>
                      <td>{fmtSnow(d.snow_low_cm[level], units, false)}–{fmtSnow(d.snow_high_cm[level], units)}</td>
                      <td>{d.quality === "none" ? "–" : t(d.quality)}</td>
                      <td><span aria-hidden className="mr-1.5 inline-block h-2 w-2 rounded-full" style={{ background: confDot(d) }} />{t(d.confidence)}</td>
                      <td>{fmtTemp(d.temp_max_c.summit, units)} / {fmtTemp(d.temp_min_c.summit, units)}</td>
                      <td>{fmtTemp(d.temp_max_c.base, units)} / {fmtTemp(d.temp_min_c.base, units)}</td>
                      <td>{d.snow_level_m.during_precip ? `${fmtHeight(d.snow_level_m.min, units).replace(/ \w+$/, "")}–${fmtHeight(d.snow_level_m.max, units)}` : "–"}</td>
                      <td>{(d.rain_base_mm ?? 0) >= 0.5 ? fmtPrecip(d.rain_base_mm, units) : "–"}</td>
                      <td>{fmtWind(d.gust_max_kmh, units)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-ink-3">{t("farOut")}</p>
          </Section>

          <Section title={`${t("models")} · ${t(level)}`} hint={t("modelsHint")}>
            <ModelChart doc={data} level={level} />
          </Section>

          <Section title={t("hourly")}>
            <HourlyCharts hourly={data.hourly} resort={data.resort} level={level} />
          </Section>
        </>
      )}
    </div>
  );
}
