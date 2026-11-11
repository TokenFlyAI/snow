"use client";
import Link from "next/link";
import { LevelPicker, LoadState, PassBadges, resortName, Updated } from "@/components/Bits";
import { useUser } from "@/components/Providers";
import { ResortCard } from "@/components/ResortCard";
import { useIndex } from "@/lib/data";
import { fmtSnow } from "@/lib/units";

export default function Home() {
  const { t, ready, favorites, lang, units, level } = useUser();
  const { data, loading, error } = useIndex();
  if (!ready) return null;
  const regionOf = (id: string) => data?.regions.find((r) => r.id === id);
  const mine = data ? favorites.map((id) => data.resorts.find((r) => r.id === id)).filter((r): r is NonNullable<typeof r> => !!r) : [];
  const ranked = data ? [...data.resorts].sort((a, b) => (b.summary.snow_7d_cm[level] ?? 0) - (a.summary.snow_7d_cm[level] ?? 0)) : [];

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <LevelPicker />
        <Updated iso={data?.generated_at} />
      </div>
      <LoadState loading={loading} error={error} />

      {data && (
        <>
          <section className="mt-4">
            <h2 className="mb-2 text-sm font-semibold text-ink-2">{t("myResorts")}</h2>
            {mine.length === 0 ? (
              <div className="card p-5 text-center">
                <p className="font-medium">{t("noFavorites")}</p>
                <p className="mx-auto mt-1 max-w-sm text-sm text-ink-3">{t("noFavoritesHint")}</p>
                <Link href="/resorts/" className="mt-4 inline-block rounded-full bg-accent px-5 py-2 text-sm font-medium text-accent-ink">{t("pickResorts")}</Link>
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {mine.map((r) => <ResortCard key={r.id} r={r} region={regionOf(r.region)} />)}
              </div>
            )}
          </section>

          <section className="mt-8">
            <h2 className="mb-2 text-sm font-semibold text-ink-2">{t("leaderboard")} · {t(level)}</h2>
            <ol className="card divide-y divide-line">
              {ranked.map((r, i) => {
                const v = r.summary.snow_7d_cm[level] ?? 0;
                const max = Math.max(ranked[0]?.summary.snow_7d_cm[level] ?? 0, 1);
                return (
                  <li key={r.id}>
                    <Link href={`/resort/${r.id}/`} className="flex items-center gap-3 px-4 py-3">
                      <span className="num w-5 text-sm text-ink-3">{i + 1}</span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="truncate text-sm font-medium">{resortName(r, lang)}</span>
                          <PassBadges passes={r.passes} />
                        </div>
                        <div className="mt-1.5 h-1.5 rounded-full bg-surface-2">
                          <div className="h-1.5 rounded-full" style={{ width: `${(v / max) * 100}%`, background: "var(--series-1)" }} />
                        </div>
                      </div>
                      <span className="num w-14 text-right text-base font-semibold">{fmtSnow(v, units)}</span>
                    </Link>
                  </li>
                );
              })}
            </ol>
          </section>
        </>
      )}
    </div>
  );
}
