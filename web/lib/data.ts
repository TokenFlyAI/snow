"use client";
import { useEffect, useState } from "react";
import type { Manifest, ResortDoc, ResortIndex } from "./types";

export const DATA_BASE = (process.env.NEXT_PUBLIC_DATA_BASE ?? "https://tokenflyai.github.io/snow/data/v1").replace(/\/$/, "");

export interface Loaded<T> { data: T | null; error: string | null; loading: boolean }

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${DATA_BASE}/${path}`, { cache: "no-cache" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as T;
}

function useJson<T>(path: string | null): Loaded<T> {
  const [state, set] = useState<Loaded<T>>({ data: null, error: null, loading: true });
  useEffect(() => {
    if (!path) return;
    let alive = true;
    set((s) => ({ ...s, loading: true }));
    getJson<T>(path)
      .then((data) => alive && set({ data, error: null, loading: false }))
      .catch((e: Error) => alive && set({ data: null, error: e.message, loading: false }));
    return () => { alive = false; };
  }, [path]);
  return state;
}

export const useIndex = () => useJson<ResortIndex>("resorts.json");
export const useResort = (id: string) => useJson<ResortDoc>(`resort/${id}.json`);
export const useManifest = () => useJson<Manifest>("manifest.json");
