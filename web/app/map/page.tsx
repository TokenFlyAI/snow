"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { LevelPicker, LoadState, RegionSelect, PassBadges, resortName, Updated } from "@/components/Bits";
import { SNOW_RAMP, SnowMap, type MapPoint } from "@/components/map/SnowMap";
import { useUser } from "@/components/Providers";
import { ResortCard } from "@/components/ResortCard";
import { useIndex } from "@/lib/data";
import type { WindowKey } from "@/lib/types";
import { inRegion, regionLabel } from "@/lib/regions";
import { fmtSnow, snowUnit } from "@/lib/units";
import { WINDOWS, windowValue } from "@/lib/windows";

/** Class lower bounds. Round numbers in the unit on screen; the map itself always works in cm. */
const BREAKS = { metric: [1, 5, 15, 30, 60], imperial: [0.5, 2, 6, 12, 24] };

export default function MapPage() {
  const { t, ready, lang, units, level, resolvedTheme } = useUser();
  const { data, loading, error } = useIndex();
  const [win, setWin] = useState<WindowKey>("7d");
  const [region, setRegion] = useState("all");
  const [selected, setSelected] = useState<string | null>(null);
  const [mapError, setMapError] = useState(false);

  const breaks = BREAKS[units];
  const breaksCm = useMemo(() => (units === "imperial" ? BREAKS.imperial.map((b) => b * 2.54) : BREAKS.metric), [units]);
  const rows = useMemo(() => (data ? data.resorts.map((r) => ({ r, v: windowValue(r, win, level) })) : []), [data, win, level]);
  const points: MapPoint[] = useMemo(() => rows.map(({ r, v }) => ({
    id: r.id, name: resortName(r, lang), lon: r.lon, lat: r.lat, cm: v.cm, label: fmtSnow(v.cm, units),
    inView: inRegion(region, r.region),
  })), [rows, lang, units, region]);
  if (!ready) return null;

  const theme = resolvedTheme === "dark" ? "dark" : "light";
  const ramp = SNOW_RAMP[theme];
  const used = new Set(data?.resorts.map((r) => r.region) ?? []);
  const regionOf = (id: string) => data?.regions.find((g) => g.id === id);
  const list = rows.filter(({ r }) => inRegion(region, r.region)).sort((a, b) => b.v.cm - a.v.cm);
  const sel = selected ? data?.resorts.find((r) => r.id === selected) : undefined;
  const classLabel = (i: number) => (i < 0 ? `< ${breaks[0]}` : i === breaks.length - 1 ? `${breaks[i]}+` : `${breaks[i]}–${breaks[i + 1]}`);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold">{t("mapTitle")}</h1>
        <Updated iso={data?.generated_at} />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <div role="group" aria-label={t("mapLegend")} className="inline-flex gap-1.5">
          {WINDOWS.map((w) => <button key={w.key} className="chip" aria-pressed={win === w.key} onClick={() => setWin(w.key)}>{t(w.label)}</button>)}
        </div>
        <LevelPicker />
        <RegionSelect value={region} onChange={(v) => { setRegion(v); setSelected(null); }} regions={data?.regions ?? []} used={used} />
      </div>
      <p className="mt-2 text-xs leading-5 text-ink-3">{t("mapHint")}</p>
      <LoadState loading={loading} error={error} />

      {data && (
        <>
          <div className="mt-3">
            <SnowMap points={points} breaksCm={breaksCm} fitKey={region} selectedId={selected}
              onSelect={setSelected} onError={() => setMapError(true)} />
          </div>
          {mapError && <p role="alert" className="mt-2 text-xs text-ink-3">⚠ {t("mapError")}</p>}

          {/* legend: the classes, in the unit on screen */}
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-ink-2">
            <span className="text-ink-3">{t("mapLegend")} ({snowUnit(units)})</span>
            {[-1, 0, 1, 2, 3, 4].map((i) => (
              <span key={i} className="num inline-flex items-center gap-1">
                <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-full border border-line" style={{ background: i < 0 ? ramp.none : ramp.steps[i] }} />
                {classLabel(i)}
              </span>
            ))}
          </div>

          {sel && (
            <div className="mt-3"><ResortCard r={sel} region={regionOf(sel.region)} /></div>
          )}

          <section className="mt-5">
            <h2 className="mb-2 text-sm font-semibold text-ink-2">
              {region === "all" ? t("allRegions") : regionLabel(region, lang, data?.regions ?? [])}
              {" · "}{list.length} {t("resortsCount")} · {t(WINDOWS.find((w) => w.key === win)!.label)} · {t(level)}
            </h2>
            <ul className="card divide-y divide-line">
              {(region === "all" ? list.slice(0, 30) : list).map(({ r, v }) => (
                <li key={r.id}>
                  <Link prefetch={false} href={`/resort/${r.id}/`} onMouseEnter={() => setSelected(r.id)}
                    className="flex items-center gap-3 px-4 py-2.5">
                    <span aria-hidden className="inline-block h-3 w-3 shrink-0 rounded-full border border-line"
                      style={{ background: v.cm < breaksCm[0] ? ramp.none : ramp.steps[breaksCm.filter((b) => v.cm >= b).length - 1] }} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">{resortName(r, lang)}</div>
                      <div className="mt-0.5"><PassBadges passes={r.passes} /></div>
                    </div>
                    <div className="text-right">
                      <div className="num text-base font-semibold">{fmtSnow(v.cm, units)}</div>
                      {v.low !== null && v.high !== null && (
                        <div className="num whitespace-nowrap text-[11px] text-ink-3">{fmtSnow(v.low, units, false)}–{fmtSnow(v.high, units, false)}</div>
                      )}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
            {region === "all" && list.length > 30 && (
              <Link href="/rank/" className="mt-3 inline-block text-sm text-ink-2 underline decoration-line underline-offset-4">{t("seeAll")} →</Link>
            )}
          </section>
        </>
      )}
    </div>
  );
}
