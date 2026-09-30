// K-line chart: candlestick + selectable overlays on the price grid + a volume grid +
// one grid per selected sub-indicator. Data comes precomputed from the backend
// (/api/quant/series) as ECharts-ready arrays.
//
// Layout is computed from the selection instead of hard-coded to three grids: price and
// volume take fixed shares and the remainder is split across however many sub-panes the
// user picked (1-4). The previous version had one fixed sub-pane at a fixed 52/12/16
// split, so any second indicator had to share that pane — putting MACD's zero axis and
// RSI's 30/70 bands on one scale, or dropping the extra indicator entirely.
import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import type { QuantSeries } from "@/types";
import { useEchartsTheme } from "@/hooks/useEchartsTheme";
import { DOWN_COLOR, UP_COLOR } from "@/styles/theme";

interface Props {
  series: QuantSeries;
  /** Indicator keys that each get their own grid below the volume pane, in order. */
  subs?: string[];
  /** Indicator keys overlaid on the price grid. The caller owns the list, because the
   *  toggles that drive it also decide what gets fetched. */
  overlays?: string[];
  height?: number;
  /** Zoom window start 0-100; the page resets it per symbol so a new code doesn't
   *  inherit the previous code's zoom level. */
  zoomStart?: number;
}

export const MAX_SUB_PANES = 4;
export const VOLUME_PANE = "vol";

/**
 * Which of an overlay's columns may be drawn on the price grid.
 *
 * ``null`` = every column is price-level, safe to overlay. Otherwise the explicit
 * allow-list. Overlay indicators mix price rails with derived columns on other scales —
 * 布林 %B/带宽, VWAP 偏离%, MA 乖离% — and plotting those alongside the candles rescales
 * the price axis until the candles flatten into a line. Keeping the allow-list here
 * means the fix is per-indicator rather than per-call-site.
 */
const OVERLAY_COLUMNS: Record<string, string[] | null> = {
  ma: null,
  ema: null,
  bbi: null,
  sar: ["sar"],
  donchian: ["don_up", "don_low", "don_mid"],
  keltner: ["kelt_mid", "kelt_up", "kelt_low"],
  boll: ["boll_mid", "boll_up", "boll_low"],
  vwap: ["vwap", "vwap_cum"],
  vwma: null,
};

/** Columns that must render as bars to read correctly (signed histogram). */
const BAR_COLUMNS = new Set(["macd"]);

function overlayColumn(key: string, col: string): boolean {
  const allowed = OVERLAY_COLUMNS[key];
  return allowed === undefined ? true : allowed === null || allowed.includes(col);
}

export default function KLineChart({
  series,
  subs = [VOLUME_PANE],
  overlays = ["ma"],
  height = 560,
  zoomStart = 60,
}: Props) {
  const { baseOption, palette } = useEchartsTheme();

  const option = useMemo(() => {
    const dates = series.dates;
    const candle = series.candle;
    const vols = series.volume.map((v, i) => {
      const [o, c] = candle[i] ?? [null, null];
      const up = c != null && o != null ? c >= o : true;
      return { value: v ?? 0, itemStyle: { color: up ? UP_COLOR : DOWN_COLOR } };
    });

    // ---- grid layout ----
    // All positions/sizes are PERCENTAGES of the chart container. An earlier version
    // advanced a pixel-based cursor by the numeric value of percent heights (46 → 46px),
    // so every grid stacked into the top ~90px of a 900px-tall chart and the panes drew
    // on top of each other. Keeping top/height in the same unit makes that impossible.
    const paneKeys = subs.length ? subs : [VOLUME_PANE];
    const subPaneKeys = paneKeys.filter((k) => k !== VOLUME_PANE);
    const TOP_PCT = 2.5;
    const GAP_PCT = 0.6;
    const PRICE_PCT = 46;
    const VOL_PCT = 11;
    const SUB_PCT = Math.max(
      8,
      (100 - TOP_PCT - PRICE_PCT - VOL_PCT - GAP_PCT * (subPaneKeys.length + 2)) / subPaneKeys.length,
    );
    const gridCount = subPaneKeys.length + 2;
    const gridIndexOf = (key: string) => (key === VOLUME_PANE ? 1 : 2 + subPaneKeys.indexOf(key));

    const grids: Record<string, unknown>[] = [];
    let cursor = TOP_PCT;
    for (const h of [PRICE_PCT, VOL_PCT, ...subPaneKeys.map(() => SUB_PCT)]) {
      grids.push({ left: 60, right: 20, top: `${cursor}%`, height: `${h}%` });
      cursor += h + GAP_PCT;
    }

    const xAxes = Array.from({ length: gridCount }, (_, i) => ({
      type: "category" as const,
      data: dates,
      gridIndex: i,
      boundaryGap: true,
      axisLine: baseOption.categoryAxis.axisLine,
      // Only the bottom grid labels the axis; the rest would be unreadable duplicates.
      axisLabel: { show: i === gridCount - 1, color: palette.textStyle.color },
      axisTick: { show: false },
      splitLine: { show: false },
      min: "dataMin" as const,
      max: "dataMax" as const,
    }));

    const yAxes = Array.from({ length: gridCount }, (_, i) => {
      if (i === 0) {
        return {
          scale: true,
          gridIndex: 0,
          splitLine: baseOption.valueAxis.splitLine,
          axisLabel: { color: palette.textStyle.color },
        };
      }
      if (i === 1) {
        // Volume labels would fight the price scale for the same gutter.
        return { scale: true, gridIndex: 1, splitNumber: 2, axisLabel: { show: false }, splitLine: { show: false } };
      }
      return {
        scale: true,
        gridIndex: i,
        splitNumber: 3,
        splitLine: { show: false },
        axisLabel: { color: palette.textStyle.color, fontSize: 10 },
      };
    });

    // ---- price pane ----
    const priceSeries: Record<string, unknown>[] = [
      {
        name: "K线",
        type: "candlestick",
        data: candle,
        xAxisIndex: 0,
        yAxisIndex: 0,
        itemStyle: {
          color: UP_COLOR,
          color0: DOWN_COLOR,
          borderColor: UP_COLOR,
          borderColor0: DOWN_COLOR,
        },
      },
    ];
    overlays.forEach((key) => {
      const frame = series.indicators[key];
      if (!frame) return;
      Object.entries(frame)
        .filter(([col]) => overlayColumn(key, col))
        .forEach(([col, arr], idx) => {
          priceSeries.push({
            name: col.toUpperCase(),
            type: "line",
            data: arr,
            xAxisIndex: 0,
            yAxisIndex: 0,
            smooth: key !== "sar",
            symbol: "none",
            showSymbol: false,
            lineStyle: {
              width: key === "sar" ? 1.5 : 1,
              type: key === "donchian" ? "dashed" : "solid",
              color: palette.series[idx % palette.series.length],
            },
          });
        });
    });

    const volSeries = [
      { name: "成交量", type: "bar" as const, data: vols, xAxisIndex: 1, yAxisIndex: 1 },
    ];

    // ---- sub-panes ----
    const subSeries: Record<string, unknown>[] = [];
    subPaneKeys.forEach((key) => {
      const frame = series.indicators[key];
      if (!frame) return;
      const gi = gridIndexOf(key);
      Object.entries(frame).forEach(([col, arr], idx) => {
        const color = palette.series[idx % palette.series.length];
        const isBar = BAR_COLUMNS.has(col);
        subSeries.push({
          name: col.toUpperCase(),
          type: isBar ? "bar" : "line",
          data: isBar ? signedBars(arr, color) : arr,
          xAxisIndex: gi,
          yAxisIndex: gi,
          showSymbol: false,
          symbol: "none",
          smooth: !isBar,
          // A gap in the middle of an oscillator otherwise drags the line to the axis.
          connectNulls: true,
          lineStyle: { width: 1, color },
          itemStyle: { color },
        });
      });
    });

    const legendNames = [
      ...overlays.flatMap((k) => Object.keys(series.indicators[k] ?? {})),
      "成交量",
      ...subPaneKeys.flatMap((k) => Object.keys(series.indicators[k] ?? {})),
    ].map((n) => n.toUpperCase());

    const zoomAxes = Array.from({ length: gridCount }, (_, i) => i);

    return {
      animation: false,
      backgroundColor: "transparent",
      textStyle: baseOption.textStyle,
      tooltip: { ...baseOption.tooltip },
      axisPointer: { link: [{ xAxisIndex: "all" }], label: { backgroundColor: "#777" } },
      legend: {
        data: legendNames,
        top: 0,
        right: 20,
        // The legend outgrows the gutter as soon as several panes are stacked.
        type: "scroll",
        textStyle: { color: palette.textStyle.color, fontSize: 11 },
        inactiveColor: "#bbb",
      },
      grid: grids,
      xAxis: xAxes,
      yAxis: yAxes,
      dataZoom: [
        { type: "inside", xAxisIndex: zoomAxes, start: zoomStart, end: 100 },
        { type: "slider", xAxisIndex: zoomAxes, bottom: 6, height: 16, start: zoomStart, end: 100 },
      ],
      series: [...priceSeries, ...volSeries, ...subSeries],
    };
  }, [series, subs, overlays, baseOption, palette, zoomStart]);

  return <ReactECharts option={option} notMerge lazyUpdate style={{ height, width: "100%" }} />;
}

/** Color a signed histogram by sign, the way every CN terminal draws MACD. */
function signedBars(data: (number | null)[], color: string): Record<string, unknown>[] {
  return data.map((v) => ({
    value: v,
    itemStyle: { color: v != null && v < 0 ? DOWN_COLOR : color },
  }));
}
