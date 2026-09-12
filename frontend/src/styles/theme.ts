// Ant Design theme tokens (light/dark) + CN market color convention (红涨绿跌).
import type { ThemeConfig } from "antd";
import { theme as antdTheme } from "antd";

// CN convention: red = up, green = down.
export const UP_COLOR = "#e4393c";
export const DOWN_COLOR = "#2fa84f";
export const BRAND = "#c8161d"; // 国泰君安红-inspired brand accent

const shared = {
  borderRadius: 6,
  colorPrimary: BRAND,
  colorInfo: BRAND,
  fontSize: 13,
};

export const lightTheme: ThemeConfig = {
  algorithm: antdTheme.defaultAlgorithm,
  token: { ...shared, colorBgLayout: "#f5f6f8" },
};

export const darkTheme: ThemeConfig = {
  algorithm: antdTheme.darkAlgorithm,
  token: { ...shared, colorBgLayout: "#0f1115" },
};

// ECharts palette keyed by theme mode.
export function echartsPalette(mode: "light" | "dark") {
  const axis = mode === "dark" ? "#8c8c8c" : "#666";
  const split = mode === "dark" ? "#262a33" : "#eee";
  return {
    backgroundColor: "transparent",
    textStyle: { color: axis },
    axisLine: { lineStyle: { color: axis } },
    splitLine: { lineStyle: { color: split } },
    upColor: UP_COLOR,
    downColor: DOWN_COLOR,
    series: [BRAND, "#1677ff", "#faad14", "#722ed1", "#13c2c2", "#eb2f96"],
  };
}

export function changeColor(v: number | null | undefined): string {
  if (v == null) return "#999";
  if (v > 0) return UP_COLOR;
  if (v < 0) return DOWN_COLOR;
  return "#999";
}
