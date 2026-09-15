// Bloomberg-terminal-inspired theme: dark-first palette, amber accent, sharp edges,
// dense spacing. CN market color convention (红涨绿跌) stays enforced at this layer.
import type { ThemeConfig } from "antd";
import { theme as antdTheme } from "antd";

// CN convention: red = up, green = down.
export const UP_COLOR = "#e4393c";
export const DOWN_COLOR = "#2fa84f";

// Terminal identity colors.
export const BRAND = "#fa8000"; // Bloomberg-style amber accent
export const LINK_COLOR = "#3fb6ff"; // cyan link accent (dark mode)
export const MONO_FONT =
  '"JetBrains Mono", "SFMono-Regular", "Roboto Mono", Consolas, "Liberation Mono", monospace';

const shared = {
  borderRadius: 2,
  fontSize: 12,
  controlHeight: 26,
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
};

export const lightTheme: ThemeConfig = {
  algorithm: antdTheme.defaultAlgorithm,
  token: {
    ...shared,
    colorPrimary: "#d9730a",
    colorInfo: "#d9730a",
    colorLink: "#0b6bcb",
    colorBgLayout: "#e9ebef",
    colorBorderSecondary: "#e3e6eb",
  },
  components: {
    Layout: { headerBg: "#ffffff", headerHeight: 46, headerPadding: "0 14px", siderBg: "#ffffff" },
    Menu: {
      itemHeight: 34,
      groupTitleFontSize: 11,
      itemSelectedBg: "rgba(217,115,10,0.12)",
      itemSelectedColor: "#b45f06",
    },
    Card: { headerFontSize: 12, headerHeight: 36, paddingLG: 12 },
    Table: {
      headerBg: "#f3f4f7",
      headerColor: "#5f6672",
      headerSplitColor: "transparent",
      cellPaddingBlock: 6,
      cellPaddingInline: 10,
      rowHoverBg: "#f6f7f9",
    },
    Statistic: { titleFontSize: 11, contentFontSize: 20 },
  },
};

export const darkTheme: ThemeConfig = {
  algorithm: antdTheme.darkAlgorithm,
  token: {
    ...shared,
    colorPrimary: BRAND,
    colorInfo: BRAND,
    colorLink: LINK_COLOR,
    colorTextBase: "#d7dce3",
    colorBgBase: "#000000",
    colorBgLayout: "#000000",
    colorBgContainer: "#0b0e13",
    colorBgElevated: "#141a23",
    colorBorder: "#232a36",
    colorBorderSecondary: "#171d27",
    colorFillSecondary: "#141a23",
    colorText: "#d7dce3",
    colorTextSecondary: "#9aa3af",
    colorTextTertiary: "#6b7382",
    colorBgSpotlight: "#1a212c",
  },
  components: {
    Layout: { headerBg: "#000000", headerHeight: 46, headerPadding: "0 14px", siderBg: "#05070a", bodyBg: "#000000" },
    Menu: {
      itemHeight: 34,
      groupTitleFontSize: 11,
      itemBg: "transparent",
      subMenuItemBg: "transparent",
      itemColor: "#9aa3af",
      itemHoverColor: "#e8ecf1",
      itemSelectedBg: "rgba(250,128,0,0.16)",
      itemSelectedColor: "#ffa733",
      groupTitleColor: "#59616e",
      darkItemBg: "transparent",
      darkSubMenuItemBg: "transparent",
      darkItemColor: "#9aa3af",
      darkItemHoverColor: "#e8ecf1",
      darkItemSelectedBg: "rgba(250,128,0,0.16)",
      darkItemSelectedColor: "#ffa733",
      darkGroupTitleColor: "#59616e",
    },
    Card: { headerFontSize: 12, headerHeight: 36, paddingLG: 12 },
    Table: {
      headerBg: "#10141b",
      headerColor: "#8a919e",
      headerSplitColor: "transparent",
      borderColor: "#1b212c",
      rowHoverBg: "#10151d",
      cellPaddingBlock: 6,
      cellPaddingInline: 10,
    },
    Segmented: { trackBg: "#10141b", itemSelectedBg: "rgba(250,128,0,0.18)" },
    Statistic: { titleFontSize: 11, contentFontSize: 20 },
    Tabs: { inkBarColor: BRAND, itemSelectedColor: BRAND },
    Tag: { defaultBg: "#141a23", defaultColor: "#9aa3af" },
  },
};

// ECharts palette keyed by theme mode.
export function echartsPalette(mode: "light" | "dark") {
  const dark = mode === "dark";
  const axis = dark ? "#7d8590" : "#667085";
  const split = dark ? "#1b212c" : "#e8eaee";
  return {
    mode,
    backgroundColor: "transparent",
    textStyle: { color: axis, fontFamily: MONO_FONT, fontSize: 11 },
    axisLine: { lineStyle: { color: dark ? "#2a313d" : "#c7ccd4" } },
    splitLine: { lineStyle: { color: split } },
    upColor: UP_COLOR,
    downColor: DOWN_COLOR,
    // Zero-intensity base for heatmap-style charts (panel color, not white).
    base: dark ? "#141a23" : "#ffffff",
    series: dark
      ? [BRAND, LINK_COLOR, "#c678dd", "#f6c343", "#34d399", "#f47067"]
      : ["#d9730a", "#1677ff", "#722ed1", "#faad14", "#13c2c2", "#eb2f96"],
  };
}

export function changeColor(v: number | null | undefined): string {
  if (v == null) return "#999";
  if (v > 0) return UP_COLOR;
  if (v < 0) return DOWN_COLOR;
  return "#999";
}

// Hex color mixing for heat scales (heatmap fills, matrix cell tints).
export function hexToRgb(h: string): [number, number, number] {
  const s = h.replace("#", "");
  return [parseInt(s.slice(0, 2), 16), parseInt(s.slice(2, 4), 16), parseInt(s.slice(4, 6), 16)];
}

export function mixColor(a: string, b: string, t: number): string {
  const pa = hexToRgb(a);
  const pb = hexToRgb(b);
  const c = pa.map((x, i) => Math.round(x + (pb[i] - x) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}
