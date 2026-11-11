"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useUser } from "./Providers";

export function Header() {
  const { t, units, setUnits, lang, setLang, resolvedTheme, setTheme } = useUser();
  const path = usePathname();
  const tab = (href: string, label: string) => {
    const active = href === "/" ? path === "/" : path.startsWith(href);
    return (
      <Link href={href} aria-current={active ? "page" : undefined}
        className={`px-1 pb-2 text-sm border-b-2 ${active ? "border-ink text-ink font-semibold" : "border-transparent text-ink-2"}`}>
        {label}
      </Link>
    );
  };
  const btn = "h-8 min-w-8 px-2 rounded-lg border border-line bg-surface text-xs text-ink-2";
  return (
    <header className="sticky top-0 z-20 bg-bg/90 backdrop-blur border-b border-line">
      <div className="mx-auto max-w-3xl px-4 pt-3">
        <div className="flex items-center justify-between gap-2">
          <Link href="/" className="flex items-center gap-2 font-semibold text-lg">
            <span aria-hidden className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-accent text-accent-ink text-base">❄</span>
            {t("appName")}
          </Link>
          <div className="flex items-center gap-1.5">
            <button className={btn} onClick={() => setUnits(units === "imperial" ? "metric" : "imperial")}
              aria-label={t("units")} title={t("units")}>{units === "imperial" ? "in · °F" : "cm · °C"}</button>
            <button className={btn} onClick={() => setLang(lang === "zh" ? "en" : "zh")} aria-label="Language">
              {lang === "zh" ? "中" : "EN"}</button>
            <button className={btn} onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
              aria-label={t("theme")} title={t("theme")}>{resolvedTheme === "dark" ? "☾" : "☀"}</button>
          </div>
        </div>
        <nav className="mt-3 flex gap-5">
          {tab("/", t("myResorts"))}
          {tab("/resorts", t("allResorts"))}
          {tab("/about", t("about"))}
        </nav>
      </div>
    </header>
  );
}
