/**
 * User state lives behind one interface so the storage can change later:
 * today LocalStore (browser localStorage, no account); phase 5 adds a
 * Supabase-backed store that syncs the same shape across devices and merges
 * whatever was saved locally on first sign-in.
 */
import type { Lang } from "./i18n";
import type { Level } from "./types";
import type { Units } from "./units";

export type Theme = "system" | "light" | "dark";

export interface UserState {
  favorites: string[];
  units: Units;
  lang: Lang;
  theme: Theme;
  level: Level;
}

export const DEFAULT_STATE: UserState = { favorites: [], units: "imperial", lang: "zh", theme: "system", level: "mid" };

export interface UserStore {
  load(): UserState;
  save(state: UserState): void;
}

const KEY = "snow.user.v1";

export class LocalStore implements UserStore {
  load(): UserState {
    try {
      const raw = window.localStorage.getItem(KEY);
      if (!raw) return { ...DEFAULT_STATE };
      const p = JSON.parse(raw) as Partial<UserState>;
      return {
        favorites: Array.isArray(p.favorites) ? p.favorites.filter((x) => typeof x === "string") : [],
        units: p.units === "metric" ? "metric" : "imperial",
        lang: p.lang === "en" ? "en" : "zh",
        theme: p.theme === "light" || p.theme === "dark" ? p.theme : "system",
        level: p.level === "base" || p.level === "summit" ? p.level : "mid",
      };
    } catch {
      return { ...DEFAULT_STATE };
    }
  }
  save(state: UserState): void {
    try { window.localStorage.setItem(KEY, JSON.stringify(state)); } catch { /* private mode: keep in memory */ }
  }
}
