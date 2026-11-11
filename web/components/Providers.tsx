"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { t as translate, type Key, type Lang } from "@/lib/i18n";
import { DEFAULT_STATE, LocalStore, type Theme, type UserState, type UserStore } from "@/lib/store";
import type { Level } from "@/lib/types";
import type { Units } from "@/lib/units";

interface Ctx extends UserState {
  ready: boolean;
  resolvedTheme: "light" | "dark";
  t: (k: Key) => string;
  isFavorite: (id: string) => boolean;
  toggleFavorite: (id: string) => void;
  setUnits: (u: Units) => void;
  setLang: (l: Lang) => void;
  setTheme: (t: Theme) => void;
  setLevel: (l: Level) => void;
}

const UserContext = createContext<Ctx | null>(null);
const store: UserStore = new LocalStore();

function resolve(theme: Theme): "light" | "dark" {
  if (theme !== "system") return theme;
  return typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<UserState>(DEFAULT_STATE);
  const [ready, setReady] = useState(false);
  const [resolvedTheme, setResolved] = useState<"light" | "dark">("light");

  useEffect(() => { setState(store.load()); setReady(true); }, []);

  useEffect(() => {
    if (!ready) return;
    const apply = () => {
      const r = resolve(state.theme);
      setResolved(r);
      document.documentElement.dataset.theme = r;
      document.documentElement.lang = state.lang === "zh" ? "zh-CN" : "en";
    };
    apply();
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [state.theme, state.lang, ready]);

  const update = useCallback((patch: Partial<UserState>) => {
    setState((prev) => { const next = { ...prev, ...patch }; store.save(next); return next; });
  }, []);

  const value = useMemo<Ctx>(() => ({
    ...state, ready, resolvedTheme,
    t: (k) => translate(k, state.lang),
    isFavorite: (id) => state.favorites.includes(id),
    toggleFavorite: (id) => update({
      favorites: state.favorites.includes(id) ? state.favorites.filter((x) => x !== id) : [...state.favorites, id],
    }),
    setUnits: (units) => update({ units }),
    setLang: (lang) => update({ lang }),
    setTheme: (theme) => update({ theme }),
    setLevel: (level) => update({ level }),
  }), [state, ready, resolvedTheme, update]);

  return <UserContext.Provider value={value}>{children}</UserContext.Provider>;
}

export function useUser(): Ctx {
  const ctx = useContext(UserContext);
  if (!ctx) throw new Error("useUser outside Providers");
  return ctx;
}
