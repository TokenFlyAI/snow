"use client";
import "maplibre-gl/dist/maplibre-gl.css";
import type { GeoJSONSource, Map as MlMap } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import { useUser } from "../Providers";

export interface MapPoint { id: string; name: string; lon: number; lat: number; cm: number; label: string; inView: boolean }

/** Free vector basemaps, no key: OpenFreeMap (OpenMapTiles schema, OpenStreetMap data). */
const STYLE = { light: "https://tiles.openfreemap.org/styles/positron", dark: "https://tiles.openfreemap.org/styles/dark" };

/**
 * Snowfall classes: one hue (blue), light -> dark on the light map and dark -> light on the dark map,
 * so "more snow" always moves away from the surface. "No snow" is a neutral grey, not a blue.
 */
export const SNOW_RAMP = {
  light: { none: "#b4b3ad", steps: ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"], ring: "#fcfcfb", text: "#0b0b0b", halo: "#fcfcfb" },
  dark: { none: "#5d5c56", steps: ["#184f95", "#256abf", "#3987e5", "#86b6ef", "#cde2fb"], ring: "#111110", text: "#f0efec", halo: "#111110" },
};

function colorExpr(breaksCm: number[], theme: "light" | "dark"): unknown[] {
  const ramp = SNOW_RAMP[theme];
  const expr: unknown[] = ["step", ["get", "cm"], ramp.none];
  breaksCm.forEach((b, i) => expr.push(b, ramp.steps[Math.min(i, ramp.steps.length - 1)]));
  return expr;
}

function featureCollection(points: MapPoint[]) {
  return {
    type: "FeatureCollection" as const,
    features: points.map((p) => ({
      type: "Feature" as const, id: p.id,
      geometry: { type: "Point" as const, coordinates: [p.lon, p.lat] },
      properties: { id: p.id, name: p.name, cm: p.cm, label: p.label },
    })),
  };
}

interface Props {
  points: MapPoint[];
  /** class lower bounds in cm, ascending (5 values) */
  breaksCm: number[];
  /** changes when the map should re-fit to the points flagged `inView` */
  fitKey: string;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onError: () => void;
}

type Theme = "light" | "dark";
interface Latest {
  points: MapPoint[]; breaksCm: number[]; theme: Theme; selectedId: string | null;
  onSelect: (id: string | null) => void; onError: () => void;
}

export function SnowMap({ points, breaksCm, fitKey, selectedId, onSelect, onError }: Props) {
  const { resolvedTheme } = useUser();
  const theme: Theme = resolvedTheme === "dark" ? "dark" : "light";
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<MlMap | null>(null);
  const [ready, setReady] = useState(0);            // bumps every time a style (and our layers) finished loading
  const latest = useRef<Latest>({ points, breaksCm, theme, selectedId, onSelect, onError });
  latest.current = { points, breaksCm, theme, selectedId, onSelect, onError };

  // ---- create the map once -------------------------------------------------
  useEffect(() => {
    let dead = false;
    let m: MlMap | null = null;
    (async () => {
      const ml = (await import("maplibre-gl")).default;
      if (dead || !box.current) return;
      m = new ml.Map({
        container: box.current, style: STYLE[latest.current.theme], center: [-105, 44], zoom: 2.2,
        attributionControl: { compact: true }, dragRotate: false, pitchWithRotate: false, maxZoom: 12,
      });
      m.touchZoomRotate.disableRotation();
      m.addControl(new ml.NavigationControl({ showCompass: false }), "top-right");
      map.current = m;

      const addLayers = () => {
        if (!m || m.getSource("resorts")) return;
        const cur = latest.current;
        const ramp = SNOW_RAMP[cur.theme];
        m.addSource("resorts", { type: "geojson", data: featureCollection(cur.points), promoteId: "id" });
        m.addLayer({
          id: "resorts-dot", type: "circle", source: "resorts",
          layout: { "circle-sort-key": ["get", "cm"] },
          paint: {
            "circle-color": colorExpr(cur.breaksCm, cur.theme) as never,
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 4, 4, 6, 8, 10] as never,
            "circle-stroke-color": ramp.ring, "circle-stroke-width": 1.5,
          },
        });
        m.addLayer({
          id: "resorts-selected", type: "circle", source: "resorts", filter: ["==", ["get", "id"], cur.selectedId ?? ""],
          paint: {
            "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": ramp.text, "circle-stroke-width": 2.5,
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 7, 4, 9, 8, 13] as never,
          },
        });
        m.addLayer({
          id: "resorts-label", type: "symbol", source: "resorts", minzoom: 5.2,
          layout: {
            "text-field": ["concat", ["get", "name"], "\n", ["get", "label"]] as never,
            "text-font": ["Noto Sans Regular"], "text-size": 11, "text-offset": [0, 1.1], "text-anchor": "top",
            "symbol-sort-key": ["-", 0, ["get", "cm"]] as never,
          },
          paint: { "text-color": ramp.text, "text-halo-color": ramp.halo, "text-halo-width": 1.4 },
        });
        setReady((n) => n + 1);
      };
      m.on("style.load", addLayers);
      // the compact attribution opens itself on narrow screens and covers a third of the map: start closed
      m.once("idle", () => {
        const el = box.current?.querySelector(".maplibregl-ctrl-attrib");
        el?.classList.remove("maplibregl-compact-show");
        el?.removeAttribute("open");                    // it is a <details>: "open" is what shows the text
      });
      m.on("click", (e) => {
        if (!m) return;
        const hit = m.queryRenderedFeatures([[e.point.x - 8, e.point.y - 8], [e.point.x + 8, e.point.y + 8]], { layers: ["resorts-dot"] });
        // the highest total wins when dots overlap
        const best = hit.sort((a, b) => (b.properties?.cm ?? 0) - (a.properties?.cm ?? 0))[0];
        latest.current.onSelect(best ? String(best.properties?.id) : null);
      });
      m.on("mousemove", (e) => {
        if (!m || !m.getLayer("resorts-dot")) return;
        m.getCanvas().style.cursor = m.queryRenderedFeatures(e.point, { layers: ["resorts-dot"] }).length ? "pointer" : "";
      });
      let failed = false;
      m.on("error", (e) => {
        // a missing basemap must not hide the data: report once, the list below still works
        const msg = String((e as { error?: { message?: string } }).error?.message ?? "");
        if (!failed && !m?.isStyleLoaded() && /style|fetch|load/i.test(msg)) { failed = true; latest.current.onError(); }
      });
    })().catch(() => latest.current.onError());
    return () => { dead = true; m?.remove(); map.current = null; };
  }, []);

  // ---- theme: swap the basemap, layers are re-added on style.load ------------
  const firstTheme = useRef(theme);
  useEffect(() => {
    if (!map.current || firstTheme.current === theme) return;
    firstTheme.current = theme;
    map.current.setStyle(STYLE[theme]);
  }, [theme]);

  // ---- data / classes --------------------------------------------------------
  useEffect(() => {
    const m = map.current;
    if (!m || !ready || !m.getSource("resorts")) return;
    (m.getSource("resorts") as GeoJSONSource).setData(featureCollection(points));
    m.setPaintProperty("resorts-dot", "circle-color", colorExpr(breaksCm, theme) as never);
  }, [points, breaksCm, theme, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready || !m.getLayer("resorts-selected")) return;
    m.setFilter("resorts-selected", ["==", ["get", "id"], selectedId ?? ""]);
  }, [selectedId, ready]);

  // ---- fit to the chosen region ----------------------------------------------
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const pts = latest.current.points.filter((p) => p.inView);
    if (pts.length === 0) return;
    let w = 180, e = -180, s = 90, n = -90;
    for (const p of pts) { w = Math.min(w, p.lon); e = Math.max(e, p.lon); s = Math.min(s, p.lat); n = Math.max(n, p.lat); }
    if (e - w > 200) { m.easeTo({ center: [-40, 35], zoom: 0.6, duration: 0 }); return; }   // the whole world
    m.fitBounds([[w, s], [e, n]], { padding: 48, maxZoom: 8.5, duration: 400 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey, ready > 0]);

  return <div ref={box} className="h-[52vh] min-h-[320px] w-full overflow-hidden rounded-[14px] border border-line" />;
}
