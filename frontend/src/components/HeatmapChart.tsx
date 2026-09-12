// Sector heatmap (treemap) colored by change % using CN convention (红涨绿跌).
import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { useEchartsTheme } from "@/hooks/useEchartsTheme";
import { DOWN_COLOR, UP_COLOR } from "@/styles/theme";

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

function heatColor(v: number | null): string {
  if (v == null) return "#9e9e9e";
  const clamped = Math.max(-5, Math.min(5, v));
  const t = Math.abs(clamped) / 5; // 0..1 intensity
  return clamped >= 0 ? mix("#ffffff", UP_COLOR, 0.35 + 0.65 * t) : mix("#ffffff", DOWN_COLOR, 0.35 + 0.65 * t);
}

interface Props {
  items: HeatItem[];
  height?: number;
  onSelect?: (name: string) => void;
}

export default function HeatmapChart({ items, height = 360, onSelect }: Props) {
  const { palette } = useEchartsTheme();

  const option = useMemo(() => {
    const changeOf = new Map(items.map((i) => [i.name, i.value] as const));
    const fmt = (p: { name: string }) => (changeOf.get(p.name) ?? 0).toFixed(2);
    return {
      backgroundColor: "transparent",
      tooltip: { formatter: (p: { name: string }) => `${p.name}<br/>涨跌幅: ${fmt(p)}%` },
      series: [
        {
          type: "treemap",
          roam: false,
          nodeClick: false,
          breadcrumb: { show: false },
          label: {
            show: true,
            formatter: (p: { name: string }) => `${p.name}\n${fmt(p)}%`,
            color: "#111",
            fontSize: 11,
          },
          itemStyle: { borderColor: palette.backgroundColor || "#fff", borderWidth: 1, gapWidth: 1 },
          data: items.map((it) => ({
            name: it.name,
            value: Math.abs(it.value ?? 0) + 0.5, // area weight (avoid zero-area tiles)
            itemStyle: { color: heatColor(it.value) },
          })),
        },
      ],
    };
  }, [items, palette]);

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
