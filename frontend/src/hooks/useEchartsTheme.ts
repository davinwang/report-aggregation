// Provides theme-aware ECharts base options (axis/grid/tooltip colors) per UI mode.
import { useMemo } from "react";
import { echartsPalette } from "@/styles/theme";
import { useUIStore } from "@/stores/uiStore";

export function useEchartsTheme() {
  const mode = useUIStore((s) => s.mode);
  return useMemo(() => {
    const p = echartsPalette(mode);
    return {
      palette: p,
      baseOption: {
        backgroundColor: "transparent",
        textStyle: { color: p.textStyle.color, fontSize: 12 },
        tooltip: {
          trigger: "axis",
          axisPointer: { type: "cross" },
          backgroundColor: mode === "dark" ? "#141a23" : "rgba(255,255,255,0.96)",
          borderColor: p.splitLine.lineStyle.color,
          textStyle: { color: mode === "dark" ? "#d7dce3" : "#333", fontSize: 11 },
        },
        legend: { textStyle: { color: p.textStyle.color }, inactiveColor: "#bbb" },
        grid: { left: 56, right: 24, top: 32, bottom: 48, containLabel: true },
        categoryAxis: {
          axisLine: p.axisLine,
          axisLabel: { color: p.textStyle.color },
          splitLine: { show: false },
        },
        valueAxis: {
          axisLine: { show: false },
          axisLabel: { color: p.textStyle.color },
          splitLine: p.splitLine,
        },
      },
    };
  }, [mode]);
}
