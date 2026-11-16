"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { LoadState, PassBadges, RegionSelect, resortName, Updated } from "@/components/Bits";
import { useUser } from "@/components/Providers";
import { DATA_BASE, usePlanner } from "@/lib/data";
import { fmtDate, fmtProb } from "@/lib/i18n";
import {
  type Advice, type PlannerDay, type PlannerResort, LIFTS_CLOSE_H, MIN_SCORE, RANK_MAX_AHEAD,
  addDays, advice, daysBetween, decodePlanner, isWeekend, resortNow, weekday,
} from "@/lib/planner";
import { CITIES, CITY_GROUPS, CLOSURES, DEFAULT_HOURS, FROM_KEY, HOURS, cityById, cityName, fmtDrive, savedCity, useDrive } from "@/lib/drive";
import { PASS_FILTERS, type PassFilter, onPass, passName } from "@/lib/passes";
import { inRegion, normalizeArea, regionLabel } from "@/lib/regions";
import { fmtSnow, fmtThreshold } from "@/lib/units";

type When = "next" | "weekend";
const PAGE = 12;
const WIND_KMH = 70;

interface Row { r: PlannerResort; d: PlannerDay; ahead: number; adv: Advice }

/** Filters live in the URL so a plan can be shared; the home city is also remembered on this device. */
function readQuery(): { pass: PassFilter; area: string; when: When; from: string; hours: number } {
  const q = new URLSearchParams(typeof window === "undefined" ? "" : window.location.search);
  const pass = q.get("pass");
  const from = q.has("from") ? q.get("from") ?? "" : savedCity();
  const hours = Number(q.get("hours"));
  return {
    pass: (PASS_FILTERS as string[]).includes(pass ?? "") ? (pass as PassFilter) : "all",
    area: normalizeArea(q.get("area")),
    when: q.get("when") === "weekend" ? "weekend" : "next",
    from: cityById(from) ? from : "",
    hours: (HOURS as readonly number[]).includes(hours) ? hours : DEFAULT_HOURS,
  };
}

export default function Plan() {
  const { t, ready, lang, units } = useUser();
  const { data, loading, error } = usePlanner();
  const [pass, setPass] = useState<PassFilter>("all");
  const [area, setArea] = useState("all");
  const [when, setWhen] = useState<When>("next");
  const [from, setFrom] = useState("");
  const [hours, setHours] = useState<number>(DEFAULT_HOURS);
  const [more, setMore] = useState(false);
  const [copied, setCopied] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const q = readQuery();
    setPass(q.pass); setArea(q.area); setWhen(q.when); setFrom(q.from); setHours(q.hours); setLoaded(true);
  }, []);
  useEffect(() => {
    if (!loaded) return;
    const q = new URLSearchParams();
    if (pass !== "all") q.set("pass", pass);
    if (area !== "all") q.set("area", area);
    if (when !== "next") q.set("when", when);
    if (from) q.set("from", from);
    if (from && hours !== DEFAULT_HOURS) q.set("hours", String(hours));
    const s = q.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${s ? `?${s}` : ""}`);
    try { if (from) localStorage.setItem(FROM_KEY, from); else localStorage.removeItem(FROM_KEY); } catch { /* private mode */ }
  }, [pass, area, when, from, hours, loaded]);

  const drive = useDrive(from);
  const mins = from && drive ? drive.minutes[from] ?? {} : null;
  const via = from && drive ? drive.via[from] ?? {} : {};

  const resorts = useMemo(() => (data ? decodePlanner(data) : []), [data]);
  const picked = useMemo(
    () => resorts.filter((r) => onPass(pass, r.id, r.passes) && inRegion(area, r.region)
      && (!from || (mins !== null && (mins[r.id] ?? Infinity) <= hours * 60))),
    [resorts, pass, area, from, mins, hours],
  );

  // ---- best bets: resort x day, up to RANK_MAX_AHEAD days ahead -----------------------------
  const { rows, weekendAhead, blockedN } = useMemo(() => {
    const out: Row[] = [];
    let weekendAhead = Infinity;
    let blockedN = 0;
    for (const r of picked) {
      const now = resortNow(r.timezone);
      for (const d of r.days) {
        const ahead = daysBetween(now.date, d.date);
        if (ahead < 0 || (ahead === 0 && now.hour >= LIFTS_CLOSE_H)) continue;
        if (when === "weekend") {
          if (!isWeekend(d.date)) continue;
          weekendAhead = Math.min(weekendAhead, ahead);
        }
        if (ahead > RANK_MAX_AHEAD || d.score < MIN_SCORE) continue;
        if (!onPass(pass, r.id, r.passes, d.date)) { blockedN++; continue; }      // a blackout date of the product
        out.push({ r, d, ahead, adv: advice(d, ahead) });
      }
    }
    out.sort((a, b) => b.d.score - a.d.score);
    return { rows: out, weekendAhead, blockedN };
  }, [picked, when, pass]);

  // ---- further out: region x day, best chance of 15 cm+ ------------------------------------
  const further = useMemo(() => {
    const cells = new Map<string, Map<string, number>>();       // region -> date -> best p15
    const dates = new Set<string>();
    for (const r of picked) {
      const today = resortNow(r.timezone).date;
      const put = (date: string, p: number | null) => {
        const ahead = daysBetween(today, date);
        if (ahead <= RANK_MAX_AHEAD || p === null) return;
        if (when === "weekend" && !isWeekend(date)) return;
        if (!onPass(pass, r.id, r.passes, date)) return;
        dates.add(date);
        const m = cells.get(r.region) ?? new Map<string, number>();
        m.set(date, Math.max(m.get(date) ?? 0, p));
        cells.set(r.region, m);
      };
      r.days.forEach((d) => put(d.date, d.p15));
      r.probDays.forEach((d) => put(d.date, d.p15));
    }
    const cols = Array.from(dates).sort();
    // regions with no real chance on any day are left out (unless it is the one region picked)
    const regionOrder = (data?.regions ?? []).map((g) => g.id).filter((id) => {
      const m = cells.get(id);
      return m && (area === id || Math.max(...Array.from(m.values())) >= 0.05);
    });
    return { cols, regions: regionOrder, cells };
  }, [picked, when, data, area, pass]);

  if (!ready) return null;
  const shown = more ? rows.slice(0, 40) : rows.slice(0, PAGE);
  const regionName = (id: string) => { const g = data?.regions.find((x) => x.id === id); return g ? (lang === "zh" ? g.name_zh : g.name) : id; };
  const used = new Set(resorts.map((r) => r.region));
  const six = fmtThreshold(15, units);
  const areaName = area === "all" ? t("planAllAreas") : regionLabel(area, lang, data?.regions ?? []);
  const chanceLabel = units === "imperial" ? t("planChance6") : t("planChance15");
  const fmtD = (iso: string) => fmtDate(iso, lang);
  const share = async () => {
    try { await navigator.clipboard.writeText(window.location.href); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* ignore */ }
  };
  const weekendFar = when === "weekend" && Number.isFinite(weekendAhead) && weekendAhead > RANK_MAX_AHEAD;
  const firstWeekend = further.cols.find((c) => isWeekend(c));

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold">{t("planTitle")}</h1>
        <Updated iso={data?.generated_at} />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {(["next", "weekend"] as When[]).map((w) => (
          <button key={w} className="chip" aria-pressed={when === w} onClick={() => { setWhen(w); setMore(false); }}>
            {w === "next" ? t("planNext") : t("planWeekend")}
          </button>
        ))}
        <button className="chip ml-auto" onClick={share}>{copied ? t("planCopied") : t("planShare")}</button>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {PASS_FILTERS.map((p) => (
          <button key={p} className="chip" aria-pressed={pass === p} onClick={() => { setPass(p); setMore(false); }}>
            {p === "all" ? t("all") : passName(p)}
          </button>
        ))}
        <RegionSelect value={area} onChange={(v) => { setArea(v); setMore(false); }} regions={data?.regions ?? []} used={used} />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className="text-[13px] text-ink-3">{t("planFrom")}</span>
        <CitySelect value={from} onChange={(v) => { setFrom(v); setMore(false); }} />
        {from && HOURS.map((h) => (
          <button key={h} className="chip" aria-pressed={hours === h} onClick={() => { setHours(h); setMore(false); }}>
            {t("planWithinH").replace("{h}", String(h))}
          </button>
        ))}
      </div>
      <p className="mt-3 text-xs leading-5 text-ink-3">{t("planHint")}</p>
      {from && <p className="mt-1 text-xs leading-5 text-ink-3">{t("planDriveHint")}</p>}
      <LoadState loading={loading || (!!from && !drive)} error={error} />

      {data && (!from || drive) && (
        <>
          <h2 className="mt-5 text-sm font-semibold">{t("planBest")}</h2>
          {weekendFar ? (
            <p className="card mt-2 p-4 text-sm leading-6 text-ink-2">
              {t("planWeekendFar").replace("{n}", String(weekendAhead))
                .replace("{d}", firstWeekend ? fmtD(addDays(firstWeekend, -2)) : "–")}
            </p>
          ) : rows.length === 0 ? (
            <p className="card mt-2 p-4 text-sm text-ink-3">
              {from ? t("planNoneNear").replace("{c}", cityName(cityById(from)!, lang)).replace("{h}", String(hours)) : t("planNone")}
            </p>
          ) : (
            <ol className="card mt-2 divide-y divide-line">
              {shown.map(({ r, d, ahead, adv }) => (
                <li key={`${r.id}-${d.date}`}>
                  <Link href={`/resort/${r.id}/`} className="flex gap-3 px-4 py-3">
                    <div className="flex w-11 shrink-0 flex-col items-center pt-0.5">
                      <span className="num text-lg font-semibold leading-6">{d.score}</span>
                      <span className="text-[10px] leading-3 text-ink-3">{t("planScore")}</span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="truncate text-sm font-medium">{resortName(r, lang)}</span>
                        <span className="num shrink-0 text-sm text-ink-2">{ahead === 0 ? t("today") : fmtD(d.date)}</span>
                      </div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-ink-3">
                        <span>{regionName(r.region)}</span>
                        <PassBadges passes={r.passes} />
                        {mins?.[r.id] != null && <span className="num text-ink-2">{t("planDrive").replace("{t}", fmtDrive(mins[r.id], lang))}</span>}
                        {via[r.id] && (
                          <span title={t("planDetourHint").replace("{p}", via[r.id].map((c) => CLOSURES[c] ?? c).join(", "))}
                            className="rounded-md border border-line px-1.5 leading-4 text-ink-2">{t("planDetour")}</span>
                        )}
                      </div>
                      <div className="mt-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[13px] text-ink-2">
                        <span><span className="num font-semibold text-ink">{fmtSnow(d.night, units)}</span> {t("planOvernight")}</span>
                        {d.fresh - d.night >= 0.6 && (
                          <span title={t("planYesterdayHint")}><span className="num">+{fmtSnow(2 * (d.fresh - d.night), units)}</span> {t("planYesterday")}</span>
                        )}
                        <span>
                          <span className="num">{fmtSnow(d.cm, units)}</span> {t("planDayTotal")}
                          {d.low !== null && d.high !== null && <span className="num text-ink-3"> ({fmtSnow(d.low, units, false)}–{fmtSnow(d.high, units, false)})</span>}
                        </span>
                        {d.p15 !== null && <span><span className="num">{fmtProb(d.p15)}</span> {chanceLabel}</span>}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px]">
                        {adv && <AdviceChip adv={adv} />}
                        {(d.quality === "powder" || d.quality === "heavy") && <Tag>{t(d.quality)}</Tag>}
                        {(d.gust ?? 0) > WIND_KMH && <Tag warn>{t("planWind")}</Tag>}
                        {d.rain_mid ? <Tag warn>{t("planRain")}</Tag> : (d.rain ?? 0) >= 2 ? <Tag warn>{t("planRainBase")}</Tag> : null}
                      </div>
                    </div>
                  </Link>
                </li>
              ))}
            </ol>
          )}
          {!weekendFar && blockedN > 0 && pass !== "all" && (
            <p className="mt-2 text-xs text-ink-3">{t("planBlocked").replace("{n}", String(blockedN)).replace("{p}", passName(pass))}</p>
          )}
          {!weekendFar && !more && rows.length > PAGE && (
            <button className="chip mt-3" onClick={() => setMore(true)}>{t("planShowMore")} ({Math.min(rows.length, 40) - PAGE})</button>
          )}

          {further.cols.length > 0 && (
            <section className="mt-6">
              <h2 className="text-sm font-semibold">{t("planFurther")}</h2>
              <p className="mt-1 text-xs leading-5 text-ink-3">{t("planFurtherHint").replace("{t}", six)}</p>
              <div className="scroll-x card mt-2">
                <table className="w-full border-collapse text-[12px]">
                  <thead>
                    <tr className="text-ink-3">
                      <th className="sticky left-0 z-10 bg-surface px-3 py-2 text-left font-normal">{t("region")}</th>
                      {further.cols.map((c) => (
                        <th key={c} className={`num whitespace-nowrap px-1.5 py-2 text-center font-normal ${weekday(c) === 0 || weekday(c) === 6 ? "text-ink" : ""}`}>
                          {fmtDate(c, lang, true)}<br />{Number(c.slice(5, 7))}/{Number(c.slice(8))}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {further.regions.map((g) => (
                      <tr key={g} className="border-t border-line">
                        <th className="sticky left-0 z-10 max-w-[9rem] truncate bg-surface px-3 py-1.5 text-left font-normal text-ink-2">{regionName(g)}</th>
                        {further.cols.map((c) => {
                          const p = further.cells.get(g)?.get(c);
                          return (
                            <td key={c} className="num px-1 py-1 text-center">
                              {p === undefined ? <span className="text-ink-3">·</span> : (
                                <span className="inline-block min-w-[2.6rem] rounded-md px-1 py-0.5"
                                  style={{ background: `color-mix(in srgb, var(--series-1) ${Math.round(Math.min(1, p) * 70)}%, transparent)`, color: p >= 0.5 ? "var(--accent-ink)" : undefined }}>
                                  {fmtProb(p)}
                                </span>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <CalendarFeed pass={pass} area={area} areaName={areaName} six={six} />

          <details className="card mt-3 p-4 text-xs leading-5 text-ink-2">
            <summary className="cursor-pointer text-sm font-medium text-ink">{t("planHow")}</summary>
            <p className="mt-2">{t("planHowText").replaceAll("{t}", six)}</p>
          </details>
        </>
      )}
    </div>
  );
}

/** Home city for the drive-time filter, grouped like data/cities.yaml. */
function CitySelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { t, lang } = useUser();
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={t("planFrom")}
      className="h-8 min-w-0 max-w-[13rem] rounded-full border border-line bg-surface px-3 text-[13px] text-ink-2">
      <option value="">{t("planAnywhere")}</option>
      {CITY_GROUPS.map((g) => {
        const cs = CITIES.filter((c) => c.group === g.id).sort((a, b) => cityName(a, lang).localeCompare(cityName(b, lang), lang));
        return cs.length ? (
          <optgroup key={g.id} label={lang === "zh" ? g.name_zh : g.name}>
            {cs.map((c) => <option key={c.id} value={c.id}>{cityName(c, lang)}</option>)}
          </optgroup>
        ) : null;
      })}
    </select>
  );
}

/** Calendar subscription (pipeline/publish/ics.py): one feed per language x pass x area. */
function CalendarFeed({ pass, area, areaName, six }: { pass: PassFilter; area: string; areaName: string; six: string }) {
  const { t, lang } = useUser();
  const [copied, setCopied] = useState(false);
  const slug = area.startsWith("g:") ? `g-${area.slice(2)}` : area;
  const base = DATA_BASE.startsWith("/") && typeof window !== "undefined" ? `${window.location.origin}${DATA_BASE}` : DATA_BASE;
  const url = `${base}/ics/${lang}/${pass}/${slug}.ics`;
  const webcal = url.replace(/^https?:/, "webcal:");
  const copy = () => navigator.clipboard?.writeText(url).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); });
  const pn = pass === "all" ? t("all") : passName(pass);
  return (
    <details className="card mt-6 p-4 text-xs leading-5 text-ink-2">
      <summary className="cursor-pointer text-sm font-medium text-ink">{t("planCal")}</summary>
      <p className="mt-2">{t("planCalText").replace("{f}", `${pn} · ${areaName}`).replace("{t}", six)}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <a className="chip" href={webcal}>{t("planCalApple")}</a>
        <a className="chip" href={`https://calendar.google.com/calendar/r?cid=${encodeURIComponent(webcal)}`} target="_blank" rel="noopener noreferrer">{t("planCalGoogle")}</a>
        <button className="chip" onClick={copy}>{copied ? t("planCopied") : t("planCalCopy")}</button>
      </div>
      <p className="mt-2 break-all text-ink-3">{url}</p>
    </details>
  );
}

function Tag({ children, warn = false }: { children: React.ReactNode; warn?: boolean }) {
  return (
    <span className={`rounded-md border px-1.5 py-0.5 leading-4 ${warn ? "border-[color:var(--series-4)] text-ink-2" : "border-line bg-surface-2 text-ink-2"}`}>
      {warn ? "⚠ " : ""}{children}
    </span>
  );
}

function AdviceChip({ adv }: { adv: NonNullable<Advice> }) {
  const { t, lang } = useUser();
  if (adv.kind === "go") return <span className="rounded-md bg-accent px-1.5 py-0.5 font-semibold leading-4 text-accent-ink">{t("planGo")}</span>;
  if (adv.kind === "likely") return <span className="rounded-md border border-accent px-1.5 py-0.5 leading-4 text-ink">{t("planLikely")}</span>;
  return <span className="rounded-md border border-line px-1.5 py-0.5 leading-4 text-ink-2">{t("planWait").replace("{d}", fmtDate(adv.decideOn!, lang))}</span>;
}
