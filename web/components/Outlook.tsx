"use client";
import { fmtProb, fmtRange } from "@/lib/i18n";
import type { OutlookWeek, ProbDay, Level } from "@/lib/types";
import { fmtDate } from "@/lib/i18n";
import { fmtSnow, fmtThreshold, thresholdKeys } from "@/lib/units";
import { useUser } from "./Providers";

/** A probability as a number with a thin single-hue meter (the number is the label, the bar is the picture). */
function Meter({ p }: { p: number | null | undefined }) {
  const v = p === null || p === undefined ? 0 : Math.max(0, Math.min(1, p));
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 min-w-10 flex-1 rounded-full bg-surface-2" aria-hidden>
        <div className="h-1.5 rounded-full" style={{ width: `${v * 100}%`, background: "var(--series-1)" }} />
      </div>
      <span className="num w-10 text-right text-sm font-semibold">{fmtProb(p)}</span>
    </div>
  );
}

/** Days 11-16: chance of at least 2.5 cm / 15 cm per ski day, no point values. */
export function ProbDays({ days, level }: { days: ProbDay[]; level: Level }) {
  const { t, lang, units } = useUser();
  if (days.length === 0) return null;
  const thresholds = thresholdKeys(days[0].ens.prob);
  return (
    <div className="mt-5">
      <h3 className="text-sm font-semibold">{t("probTitle")}</h3>
      <p className="mb-2 mt-1 text-xs leading-5 text-ink-3">{t("probHint")}</p>
      <div className="scroll-x">
        <table className="data num">
          <thead>
            <tr>
              <th>{t("date")}</th>
              {thresholds.map((thr) => <th key={thr}>≥ {fmtThreshold(thr, units)}</th>)}
              <th>{t("median")}</th><th>10%–90%</th><th>{t("members")}</th>
            </tr>
          </thead>
          <tbody>
            {days.map((d) => (
              <tr key={d.date}>
                <td>{fmtDate(d.date, lang)}</td>
                {thresholds.map((thr) => <td key={thr} className="font-semibold">{fmtProb(d.ens.prob[thr][level])}</td>)}
                <td>{fmtSnow(d.ens.p50[level], units)}</td>
                <td>{fmtSnow(d.ens.p10[level], units, false)}–{fmtSnow(d.ens.p90[level], units)}</td>
                <td className="text-ink-3">{d.ens.n_members}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Weeks 3-5 from the 35-day ensembles, worded as probabilities of a weekly total. */
export function OutlookWeeks({ weeks }: { weeks: OutlookWeek[] }) {
  const { t, units } = useUser();
  if (weeks.length === 0) return null;
  return (
    <ul className="grid gap-3 sm:grid-cols-3">
      {weeks.map((w) => (
        <li key={w.week} className="rounded-xl border border-line p-3">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-sm font-semibold">{t("week").replace("{n}", String(w.week))}</span>
            <span className="num text-xs text-ink-3">{fmtRange(w.start, w.end)}</span>
          </div>
          <dl className="mt-2 space-y-1.5">
            {thresholdKeys(w.prob).map((thr) => (
              <div key={thr} className="grid grid-cols-[4.5rem_1fr] items-center gap-2">
                <dt className="num text-xs text-ink-2">≥ {fmtThreshold(thr, units)}</dt>
                <dd><Meter p={w.prob[thr]} /></dd>
              </div>
            ))}
          </dl>
          <p className="num mt-2 text-xs text-ink-3">
            {t("median")} {fmtSnow(w.p50_cm, units)} · 10%–90% {fmtSnow(w.p10_cm, units, false)}–{fmtSnow(w.p90_cm, units)} · {w.n_members} {t("members")}
          </p>
        </li>
      ))}
    </ul>
  );
}
