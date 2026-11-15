"use client";
import { fmtUpdated, tierKey } from "@/lib/i18n";
import { REGION_GROUPS } from "@/lib/regions";
import type { Level, ResortMeta } from "@/lib/types";
import { LEVELS } from "@/lib/types";
import { useUser } from "./Providers";

export function PassBadges({ passes }: { passes: ResortMeta["passes"] }) {
  const { t } = useUser();
  return (
    <span className="inline-flex flex-wrap gap-1">
      {(Object.keys(passes) as ("ikon" | "epic")[]).map((p) => (
        <span key={p} className="rounded-md border border-line bg-surface-2 px-1.5 py-0.5 text-[11px] leading-4 text-ink-2">
          {p === "ikon" ? "Ikon" : "Epic"} · {t(tierKey(passes[p]!))}
        </span>
      ))}
    </span>
  );
}

export function FollowButton({ id, compact = false }: { id: string; compact?: boolean }) {
  const { t, isFavorite, toggleFavorite } = useUser();
  const on = isFavorite(id);
  return (
    <button onClick={(e) => { e.preventDefault(); e.stopPropagation(); toggleFavorite(id); }}
      aria-pressed={on} aria-label={on ? t("unfollow") : t("follow")}
      className={`shrink-0 rounded-full border text-sm ${compact ? "h-8 w-8" : "h-9 px-3.5"} ${on
        ? "border-accent bg-accent text-accent-ink" : "border-line bg-surface text-ink-2"}`}>
      {compact ? (on ? "★" : "☆") : `${on ? "★" : "☆"} ${on ? t("following") : t("follow")}`}
    </button>
  );
}

export function LevelPicker() {
  const { t, level, setLevel } = useUser();
  return (
    <div role="group" aria-label={t("mountain")} className="inline-flex gap-1.5">
      {LEVELS.map((lv: Level) => (
        <button key={lv} className="chip" aria-pressed={level === lv} onClick={() => setLevel(lv)}>{t(lv)}</button>
      ))}
    </div>
  );
}

export function Updated({ iso }: { iso?: string | null }) {
  const { t, lang } = useUser();
  if (!iso) return null;
  return <span className="text-xs text-ink-3">{t("updated")} {fmtUpdated(iso, lang)}</span>;
}

/** Region filter: larger areas first, then single regions (only those that have resorts). */
export function RegionSelect({ value, onChange, regions, used }: {
  value: string; onChange: (v: string) => void;
  regions: { id: string; name: string; name_zh: string }[]; used: Set<string>;
}) {
  const { t, lang } = useUser();
  const name = (g: { name: string; name_zh: string }) => (lang === "zh" ? g.name_zh : g.name);
  const groups = REGION_GROUPS.filter((g) => g.regions.some((r) => used.has(r)));
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={t("region")}
      className="h-8 min-w-0 max-w-[13rem] rounded-full border border-line bg-surface px-3 text-[13px] text-ink-2">
      <option value="all">{t("allRegions")}</option>
      <optgroup label={t("regionGroups")}>
        {groups.map((g) => <option key={g.id} value={`g:${g.id}`}>{name(g)}</option>)}
      </optgroup>
      <optgroup label={t("regionsSingle")}>
        {regions.filter((g) => used.has(g.id)).map((g) => <option key={g.id} value={g.id}>{name(g)}</option>)}
      </optgroup>
    </select>
  );
}

export function LoadState({ loading, error }: { loading: boolean; error: string | null }) {
  const { t } = useUser();
  if (loading) return <p className="py-10 text-center text-sm text-ink-3">{t("loading")}</p>;
  if (error) return <p role="alert" className="card my-4 p-4 text-sm text-ink-2">⚠ {t("loadError")} <span className="text-ink-3">({error})</span></p>;
  return null;
}

export function resortName(r: { name: string; name_zh: string | null }, lang: "zh" | "en"): string {
  return lang === "zh" && r.name_zh ? r.name_zh : r.name;
}
