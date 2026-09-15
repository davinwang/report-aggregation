// Sector heatmap (treemap) colored by change % using CN convention (红涨绿跌).
// Labels adapt to each tile's *pixel* footprint (container width is measured via
// ResizeObserver; squarified tiles are ~square, so side ≈ sqrt(area share)):
// roomy tiles show name + %, tight tiles show the full name only, slivers stay
// unlabeled — a tile too small for the whole name never shows a truncated %.
import { useEffect, useMemo, useRef, useState } from "react";
import ReactECharts from "echarts-for-react";
import { useEchartsTheme } from "@/hooks/useEchartsTheme";
import { DOWN_COLOR, MONO_FONT, UP_COLOR } from "@/styles/theme";

export interface HeatItem {
  name: string;
  value: number | null; // change %
  group?: string | null;
}

function hexToRgb(h: string): number[] {
  const s = h.replace("#", "");
  return [parseInt(s.slice(0, 2), 16), parseInt(s.slice(2, 4), 16), parseInt(s.slice(4, 6), 16)];
}

function mix(a: string, b: string, t: number): string {
  const pa = hexToRgb(a);
  const pb = hexToRgb(b);
  const c = pa.map((x, i) => Math.round(x + (pb[i] - x) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

function heatColor(v: number | null, base: string): string {
  if (v == null) return "#9e9e9e";
  const clamped = Math.max(-5, Math.min(5, v));
  const t = Math.abs(clamped) / 5; // 0..1 intensity
  return clamped >= 0 ? mix(base, UP_COLOR, 0.3 + 0.7 * t) : mix(base, DOWN_COLOR, 0.3 + 0.7 * t);
}

interface Props {
  items: HeatItem[];
  height?: number;
  onSelect?: (name: string) => void;
}

// Label plan for one tile: "full" = name + %, "name" = name only, "off" = hidden.
interface LabelPlan {
  mode: "full" | "name" | "off";
  nameFs: number;
  pctFs: number;
}

const NAME_FS_MAX = 13; // caps keep a dense treemap readable
const PCT_FS_MAX = 11;

function planLabel(name: string, pct: string, side: number): LabelPlan {
  const availW = side - 8; // intra-tile padding + gap
  const availH = side - 6;
  const chars = Math.max(name.length, 1); // CJK glyphs are ~1em wide
  if (availW < 20 || availH < 14) return { mode: "off", nameFs: 0, pctFs: 0 };

  // Full tier: both lines must fit *completely* — never a truncated %.
  const nameFs = Math.min(NAME_FS_MAX, Math.floor(availW / chars), Math.floor(availH / 3.1));
  const pctFs = Math.min(PCT_FS_MAX, nameFs - 1);
  const pctW = Math.ceil(pctFs * 0.62 * pct.length); // monospace advance ≈ 0.6em
  if (nameFs >= 10 && pctFs >= 9 && pctW <= availW && nameFs + pctFs + 8 <= availH) {
    return { mode: "full", nameFs, pctFs };
  }

  // Name-only tier: shown only when the whole name fits (min 9px for CJK).
  const onlyFs = Math.min(12, Math.floor(availW / chars), Math.floor(availH / 1.7));
  if (onlyFs >= 9) return { mode: "name", nameFs: onlyFs, pctFs: 0 };

  return { mode: "off", nameFs: 0, pctFs: 0 };
}

export default function HeatmapChart({ items, height = 360, onSelect }: Props) {
  const { palette } = useEchartsTheme();
  const dark = palette.mode === "dark";
  const wrapRef = useRef<HTMLDivElement>(null);
  const [boxW, setBoxW] = useState(0);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 0;
      setBoxW((prev) => (Math.abs(prev - w) > 2 ? w : prev));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const option = useMemo(() => {
    const changeOf = new Map(items.map((i) => [i.name, i.value] as const));
    const fmt = (p: { name: string }) => (changeOf.get(p.name) ?? 0).toFixed(2);
    const weights = items.map((it) => Math.abs(it.value ?? 0) + 0.5);
    const totalW = weights.reduce((a, b) => a + b, 0) || 1;
    const chartW = boxW || 720; // first-frame estimate before ResizeObserver reports
    const chartArea = chartW * height;

    const data = items.map((it, idx) => {
      // Estimate the tile's linear pixel size from its area share, then pick
      // the richest label tier that provably fits inside that box.
      const side = Math.sqrt((weights[idx] / totalW) * chartArea);
      const intensity = Math.min(Math.abs(it.value ?? 0), 5) / 5;
      const strongFill = 0.3 + 0.7 * intensity > 0.55;
      const textMain = strongFill ? "#ffffff" : dark ? "#d7dce3" : "#1a1a1a";
      const textSub = strongFill
        ? "rgba(255,255,255,0.78)"
        : dark
          ? "rgba(215,220,227,0.72)"
          : "rgba(0,0,0,0.58)";
      const pct = `${(it.value ?? 0).toFixed(2)}%`;
      const plan = planLabel(it.name, pct, side);

      let label: Record<string, unknown>;
      if (plan.mode === "off") {
        label = { show: false };
      } else if (plan.mode === "name") {
        label = {
          show: true,
          formatter: it.name,
          color: textMain,
          fontSize: plan.nameFs,
          overflow: "truncate",
          width: Math.max(12, Math.floor(side) - 4),
        };
      } else {
        label = {
          show: true,
          formatter: `{n|${it.name}}\n{v|${pct}}`,
          rich: {
            n: { fontSize: plan.nameFs, fontWeight: 600, color: textMain, lineHeight: plan.nameFs + 4 },
            v: { fontSize: plan.pctFs, fontFamily: MONO_FONT, color: textSub, lineHeight: plan.pctFs + 4 },
          },
        };
      }

      return {
        name: it.name,
        value: weights[idx], // area weight (avoid zero-area tiles)
        itemStyle: { color: heatColor(it.value, palette.base) },
        label,
      };
    });

    return {
      backgroundColor: "transparent",
      tooltip: { formatter: (p: { name: string }) => `${p.name}<br/>涨跌幅: ${fmt(p)}%` },
      series: [
        {
          type: "treemap",
          roam: false,
          nodeClick: false,
          breadcrumb: { show: false },
          itemStyle: { borderColor: dark ? "#000" : "#fff", borderWidth: 0, gapWidth: 2, borderRadius: 2 },
          data,
        },
      ],
    };
  }, [items, palette, dark, boxW, height]);

  const onEvents = useMemo(
    () => ({
      click: (params: { name?: string }) => {
        if (onSelect && params?.name) onSelect(params.name);
      },
    }),
    [onSelect],
  );

  return (
    <div ref={wrapRef} style={{ width: "100%" }}>
      <ReactECharts option={option} notMerge lazyUpdate style={{ height, width: "100%" }} onEvents={onEvents} />
    </div>
  );
}
