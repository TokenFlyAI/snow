"use client";
import { useUser } from "@/components/Providers";
import { fmtRange } from "@/lib/i18n";
import { PRODUCTS, productAccess, type ProductAccess } from "@/lib/passes";
import type { ResortMeta } from "@/lib/types";

/** Ikon Base / Epic Local access at this resort (data/pass_products.yaml), under the pass badges. */
export function PassProducts({ id, passes }: { id: string; passes: ResortMeta["passes"] }) {
  const { t, lang } = useUser();
  const rows = PRODUCTS.filter((p) => passes[p.pass]).map((p) => ({ ...p, a: productAccess(p.id, id) }));
  if (!rows.length) return null;
  const days = (a: ProductAccess) =>
    a.days === "unlimited" ? t("unlimited")
      : (a.shared ? t("passShared") : a.consecutive ? t("passConsecutive") : t("passDaysN")).replace("{n}", String(a.days));
  const ranges = (a: ProductAccess) =>
    a.blackout.map(([x, y]) => (x === y ? fmtRange(x, y).split("–")[0] : fmtRange(x, y))).join(lang === "zh" ? "、" : ", ");
  return (
    <ul className="mt-1 space-y-0.5 text-xs text-ink-2">
      {rows.map(({ id: pid, name, a }) => (
        <li key={pid} className={a ? "" : "text-ink-3"}>
          {name}{lang === "zh" ? "：" : ": "}
          {a ? <>{days(a)}{a.blackout.length > 0 && <span className="text-ink-3"> · {t("passBlackout")} <span className="num">{ranges(a)}</span></span>}</> : t("passNotOn")}
        </li>
      ))}
    </ul>
  );
}
