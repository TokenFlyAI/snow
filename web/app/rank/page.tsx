"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { LevelPicker, LoadState, PassBadges, RegionSelect, resortName, Updated } from "@/components/Bits";
import { useUser } from "@/components/Providers";
import { useIndex } from "@/lib/data";
import type { WindowKey } from "@/lib/types";
import { inRegion } from "@/lib/regions";
import { fmtSnow } from "@/lib/units";
import { WINDOWS, windowValue } from "@/lib/windows";

type PassFilter = "all" | "ikon" | "epic";
const PAGE = 40;

export default function Rank() {
  const { t, ready, lang, units, level } = useUser();
  const { data, loading, error } = useIndex();
  const [win, setWin] = useState<WindowKey>("7d");
  const [pass, setPass] = useState<PassFilter>("all");
  const [region, setRegion] = useState("all");
  const [all, setAll] = useState(false);

  const rows = useMemo(() => {
    if (!data) return [];
    return data.resorts
      .filter((r) => (pass === "all" || r.passes[pass]) && inRegion(region, r.region))
      .map((r) => ({ r, v: windowValue(r, win, level) }))
      .sort((a, b) => b.v.cm - a.v.cm);
  }, [data, win, pass, region, level]);
  if (!ready) return null;

  const shown = all ? rows : rows.slice(0, PAGE);
  // one scale for the whole list, wide enough for the highest whisker on screen
  const max = Math.max(1, ...shown.map((x) => Math.max(x.v.cm, x.v.high ?? 0)));
  const pct = (cm: number) => `${Math.min(100, (cm / max) * 100)}%`;
  const regionName = (id: string) => { const g = data?.regions.find((x) => x.id === id); return g ? (lang === "zh" ? g.name_zh : g.name) : id; };
  const used = new Set(data?.resorts.map((r) => r.region) ?? []);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold">{t("rankTitle")}</h1>
        <Updated iso={data?.generated_at} />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <div role="group" aria-label={t("rankTitle")} className="inline-flex gap-1.5">
          {WINDOWS.map((w) => <button key={w.key} className="chip" aria-pressed={win === w.key} onClick={() => setWin(w.key)}>{t(w.label)}</button>)}
        </div>
        <LevelPicker />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {(["all", "ikon", "epic"] as PassFilter[]).map((p) => (
          <button key={p} className="chip" aria-pressed={pass === p} onClick={() => setPass(p)}>{p === "all" ? t("all") : p === "ikon" ? "Ikon" : "Epic"}</button>
        ))}
        <RegionSelect value={region} onChange={(v) => { setRegion(v); setAll(false); }} regions={data?.regions ?? []} used={used} />
      </div>
      <p className="mt-3 text-xs leading-5 text-ink-3">{t("rankHint")}</p>
      <LoadState loading={loading} error={error} />

      {data && (
        <>
          <ol className="card mt-3 divide-y divide-line">
            {shown.map(({ r, v }, i) => (
              <li key={r.id}>
                <Link href={`/resort/${r.id}/`} className="flex items-center gap-3 px-4 py-3">
                  <span className="num w-6 text-sm text-ink-3">{i + 1}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium">{resortName(r, lang)}</span>
                      <PassBadges passes={r.passes} />
                    </div>
                    <div className="mt-0.5 truncate text-[11px] text-ink-3">{regionName(r.region)}</div>
                    <div className="relative mt-1.5 h-2" aria-hidden>
                      <div className="absolute inset-x-0 top-[1px] h-1.5 rounded-full bg-surface-2" />
                      <div className="absolute left-0 top-[1px] h-1.5 rounded-full" style={{ width: pct(v.cm), background: "var(--series-1)" }} />
                      {v.low !== null && v.high !== null && v.high - v.low > 0.05 && (
                        <>
                          <div className="absolute top-[3px] h-[2px]" style={{ left: pct(v.low), width: `calc(${pct(v.high)} - ${pct(v.low)})`, background: "var(--text-secondary)" }} />
                          <div className="absolute top-0 h-2 w-[2px]" style={{ left: pct(v.low), background: "var(--text-secondary)" }} />
                          <div className="absolute top-0 h-2 w-[2px]" style={{ left: `calc(${pct(v.high)} - 2px)`, background: "var(--text-secondary)" }} />
                        </>
                      )}
                    </div>
                  </div>
                  <div className="w-[4.5rem] text-right">
                    <div className="num text-base font-semibold">{fmtSnow(v.cm, units)}</div>
                    {v.low !== null && v.high !== null && (
                      <div className="num whitespace-nowrap text-[11px] text-ink-3">{fmtSnow(v.low, units, false)}–{fmtSnow(v.high, units, false)}</div>
                    )}
                  </div>
                </Link>
              </li>
            ))}
          </ol>
          {rows.length === 0 && <p className="py-10 text-center text-sm text-ink-3">–</p>}
          {!all && rows.length > PAGE && (
            <button className="chip mt-3" onClick={() => setAll(true)}>{t("showAll")} ({rows.length})</button>
          )}
        </>
      )}
    </div>
  );
}
