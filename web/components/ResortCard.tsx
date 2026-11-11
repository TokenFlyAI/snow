"use client";
import Link from "next/link";
import { fmtDate } from "@/lib/i18n";
import type { IndexResort, Region } from "@/lib/types";
import { fmtSnow } from "@/lib/units";
import { FollowButton, PassBadges, resortName } from "./Bits";
import { useUser } from "./Providers";

function Spark({ values, dates }: { values: (number | null)[]; dates: string[] }) {
  const { units, lang } = useUser();
  const max = Math.max(10, ...values.map((v) => v ?? 0));     // 10 cm floor: a dusting must not look like a dump
  return (
    <div className="flex h-10 items-end gap-[3px]" aria-hidden>
      {values.map((v, i) => (
        <div key={i} title={`${fmtDate(dates[i] ?? "", lang)} · ${fmtSnow(v, units)}`} className="flex-1 rounded-t-[3px]"
          style={{ height: `${Math.max(((v ?? 0) / max) * 100, 4)}%`, background: (v ?? 0) >= 0.5 ? "var(--series-1)" : "var(--line)", opacity: i >= 10 ? 0.5 : 1 }} />
      ))}
    </div>
  );
}

export function ResortCard({ r, region }: { r: IndexResort; region?: Region }) {
  const { t, lang, units, level } = useUser();
  const s = r.summary;
  const cell = (label: string, cm: number | null, strong = false) => (
    <div>
      <div className="text-[11px] text-ink-3">{label}</div>
      <div className={`num ${strong ? "text-2xl font-semibold" : "text-lg font-medium"}`}>{fmtSnow(cm, units)}</div>
    </div>
  );
  return (
    <Link href={`/resort/${r.id}/`} className="card block p-4 transition-colors hover:border-ink-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-base font-semibold">{resortName(r, lang)}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-3">
            <span>{region ? (lang === "zh" ? region.name_zh : region.name) : r.region}</span>
            <PassBadges passes={r.passes} />
          </div>
        </div>
        <FollowButton id={r.id} compact />
      </div>
      <div className="mt-3 grid grid-cols-4 gap-2">
        {cell(t("next24h"), s.snow_24h_cm[level], true)}
        {cell(t("next72h"), s.snow_72h_cm[level])}
        {cell(t("next7d"), s.snow_7d_cm[level])}
        {cell(t("next16d"), s.snow_16d_cm[level])}
      </div>
      <div className="mt-3"><Spark values={s.daily_mid_cm} dates={r.dates} /></div>
      <p className="mt-2 text-xs text-ink-2">
        {s.next_snow
          ? <>{t("nextSnow")}: <b className="text-ink">{fmtDate(s.next_snow.date, lang)}</b> · {fmtSnow(s.next_snow.snow_cm[level], units)}</>
          : t("noSnowAhead")}
      </p>
    </Link>
  );
}
