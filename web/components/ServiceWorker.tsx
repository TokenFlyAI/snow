"use client";
import { useEffect } from "react";

export function ServiceWorker() {
  useEffect(() => {
    if (!("serviceWorker" in navigator) || process.env.NODE_ENV !== "production") return;
    const base = process.env.NEXT_PUBLIC_BASE_PATH ?? "/snow";
    navigator.serviceWorker.register(`${base}/sw.js`, { scope: `${base}/` }).catch(() => { /* offline support is optional */ });
  }, []);
  return null;
}
