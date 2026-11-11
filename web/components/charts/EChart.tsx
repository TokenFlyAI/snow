"use client";
import { BarChart, CustomChart, LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";
import { useUser } from "../Providers";

echarts.use([BarChart, LineChart, CustomChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, CanvasRenderer]);

export interface Palette {
  surface: string; text: string; text2: string; muted: string; grid: string; line: string;
  series: string[];
}

export function readPalette(): Palette {
  const css = getComputedStyle(document.documentElement);
  const v = (n: string) => css.getPropertyValue(n).trim();
  return {
    surface: v("--surface"), text: v("--text-primary"), text2: v("--text-secondary"), muted: v("--text-muted"),
    grid: v("--grid"), line: v("--line"),
    series: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => v(`--series-${i}`)),
  };
}

/** Shared look: recessive hairline grid, text tokens for all labels, axis tooltip. */
export function baseOption(p: Palette): Record<string, unknown> {
  return {
    animation: false,
    textStyle: { color: p.text2, fontFamily: "inherit" },
    grid: { left: 4, right: 8, top: 28, bottom: 4, containLabel: true },
    tooltip: {
      trigger: "axis", confine: true, backgroundColor: p.surface, borderColor: p.line, borderWidth: 1,
      textStyle: { color: p.text, fontSize: 12 }, axisPointer: { type: "shadow", shadowStyle: { color: p.grid, opacity: 0.5 } },
    },
    legend: { top: 0, left: 0, itemWidth: 10, itemHeight: 10, icon: "roundRect", textStyle: { color: p.text2, fontSize: 12 } },
  };
}

export const axisStyle = (p: Palette) => ({
  axisLine: { lineStyle: { color: p.line } }, axisTick: { show: false },
  axisLabel: { color: p.muted, fontSize: 11 }, splitLine: { lineStyle: { color: p.grid, width: 1 } },
});

interface Props {
  build: (p: Palette) => Record<string, unknown>;
  height: number;
  deps: unknown[];
  group?: string;
  minWidth?: number;
  ariaLabel: string;
}

export function EChart({ build, height, deps, group, minWidth, ariaLabel }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const { resolvedTheme } = useUser();

  useEffect(() => {
    if (!ref.current) return;
    const c = echarts.init(ref.current, undefined, { renderer: "canvas" });
    chart.current = c;
    if (group) { c.group = group; echarts.connect(group); }
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(ref.current);
    return () => { ro.disconnect(); c.dispose(); chart.current = null; };
  }, [group]);

  useEffect(() => {
    // read CSS variables after the theme attribute has been applied
    const id = requestAnimationFrame(() => chart.current?.setOption(build(readPalette()), true));
    return () => cancelAnimationFrame(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedTheme, ...deps]);

  return <div ref={ref} role="img" aria-label={ariaLabel} style={{ height, minWidth, width: "100%" }} />;
}
