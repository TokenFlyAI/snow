"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { FollowButton, PassBadges, resortName } from "@/components/Bits";
import { useUser } from "@/components/Providers";
import { useIndex } from "@/lib/data";
import { REGIONS, RESORTS } from "@/lib/resorts";
import { fmtSnow } from "@/lib/units";

type PassFilter = "all" | "ikon" | "epic";

export default function Resorts() {
  const { t, ready, lang, units, level } = useUser();
  const { data } = useIndex();
  const [pass, setPass] = useState<PassFilter>("all");
  const [q, setQ] = useState("");

  const groups = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const list = RESORTS.filter((r) => (pass === "all" || r.passes[pass]) && (!needle
      || r.name.toLowerCase().includes(needle) || (r.name_zh ?? "").includes(needle) || (r.state ?? "").toLowerCase() === needle));
    return REGIONS.map((reg) => ({ reg, items: list.filter((r) => r.region === reg.id) })).filter((g) => g.items.length > 0);
  }, [pass, q]);
  if (!ready) return null;
  const summary = (id: string) => data?.resorts.find((r) => r.id === id)?.summary;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        {(["all", "ikon", "epic"] as PassFilter[]).map((p) => (
          <button key={p} className="chip" aria-pressed={pass === p} onClick={() => setPass(p)}>
            {p === "all" ? t("all") : p === "ikon" ? "Ikon" : "Epic"}
          </button>
        ))}
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")} aria-label={t("search")}
          className="h-9 min-w-0 flex-1 rounded-full border border-line bg-surface px-4 text-sm placeholder:text-ink-3" />
      </div>

      {groups.map(({ reg, items }) => (
        <section key={reg.id} className="mt-5">
          <h2 className="mb-2 text-sm font-semibold text-ink-2">{lang === "zh" ? reg.name_zh : reg.name}</h2>
          <ul className="card divide-y divide-line">
            {items.map((r) => {
              const s = summary(r.id);
              return (
                <li key={r.id} className="flex items-center gap-3 px-4 py-3">
                  <Link href={`/resort/${r.id}/`} className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">{resortName(r, lang)}</div>
                    <div className="mt-1"><PassBadges passes={r.passes} /></div>
                  </Link>
                  <div className="text-right">
                    <div className="num text-base font-semibold">{s ? fmtSnow(s.snow_7d_cm[level], units) : "–"}</div>
                    <div className="text-[11px] text-ink-3">{t("next7d")}</div>
                  </div>
                  <FollowButton id={r.id} compact />
                </li>
              );
            })}
          </ul>
        </section>
      ))}
      {groups.length === 0 && <p className="py-10 text-center text-sm text-ink-3">–</p>}
    </div>
  );
}
