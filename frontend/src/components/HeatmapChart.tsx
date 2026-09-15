// Sector heatmap (treemap) colored by change % using CN convention (红涨绿跌).
// Label density adapts to tile size: large tiles show name + %, medium tiles show
// the name only, tiny tiles stay unlabeled; text color follows fill intensity.
import { useMemo } from "react";
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

export default function HeatmapChart({ items, height = 360, onSelect }: Props) {
  const { palette } = useEchartsTheme();
  const dark = palette.mode === "dark";

  const option = useMemo(() => {
    const changeOf = new Map(items.map((i) => [i.name, i.value] as const));
    const fmt = (p: { name: string }) => (changeOf.get(p.name) ?? 0).toFixed(2);
    const weights = items.map((it) => Math.abs(it.value ?? 0) + 0.5);
    const maxW = Math.max(...weights, 1e-6);

    const data = items.map((it, idx) => {
      // sqrt: label font scales with the tile's linear dimension, not its area.
      const size = Math.sqrt(weights[idx] / maxW); // 0..1
      const intensity = Math.min(Math.abs(it.value ?? 0), 5) / 5;
      const strongFill = 0.3 + 0.7 * intensity > 0.55;
      const textMain = strongFill ? "#ffffff" : dark ? "#d7dce3" : "#1a1a1a";
      const textSub = strongFill
        ? "rgba(255,255,255,0.78)"
        : dark
          ? "rgba(215,220,227,0.72)"
          : "rgba(0,0,0,0.58)";
      const pct = `${(it.value ?? 0).toFixed(2)}%`;

      let label: Record<string, unknown>;
      if (size < 0.18) {
        label = { show: false };
      } else if (size < 0.45) {
        label = {
          show: true,
          formatter: it.name,
          color: textMain,
          fontSize: Math.max(9, Math.round(8 + 6 * size)),
        };
      } else {
        const nameSize = Math.round(11 + 9 * size); // 12..20
        const pctSize = Math.max(10, nameSize - 4);
        label = {
          show: true,
          formatter: `{n|${it.name}}\n{v|${pct}}`,
          rich: {
            n: { fontSize: nameSize, fontWeight: 600, color: textMain, lineHeight: nameSize + 5 },
            v: { fontSize: pctSize, fontFamily: MONO_FONT, color: textSub, lineHeight: pctSize + 4 },
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
  }, [items, palette, dark]);

  const onEvents = useMemo(
    () => ({
      click: (params: { name?: string }) => {
        if (onSelect && params?.name) onSelect(params.name);
      },
    }),
    [onSelect],
  );

  return <ReactECharts option={option} notMerge lazyUpdate style={{ height, width: "100%" }} onEvents={onEvents} />;
}
