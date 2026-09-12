// K-line chart: candlestick + MA/BOLL overlays + volume + a selectable sub-indicator.
// Data comes precomputed from the backend (/api/quant/series) as ECharts-ready arrays.
import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import type { QuantSeries } from "@/types";
import { useEchartsTheme } from "@/hooks/useEchartsTheme";
import { DOWN_COLOR, UP_COLOR } from "@/styles/theme";

interface Props {
  series: QuantSeries;
  sub?: string; // indicator key shown in the bottom pane, e.g. macd|kdj|rsi|vol
  height?: number;
}

// Overlay (drawn on the price pane) vs sub-pane indicators.
const OVERLAYS = ["ma", "ema", "boll", "boll_ext", "donchian", "keltner", "sar", "bbi"];

export default function KLineChart({ series, sub = "vol", height = 560 }: Props) {
  const { baseOption, palette } = useEchartsTheme();

  const option = useMemo(() => {
    const dates = series.dates;
    const candle = series.candle;
    const vols = series.volume.map((v, i) => {
      const [o, c] = candle[i] ?? [null, null];
      const up = c != null && o != null ? c >= o : true;
      return { value: v ?? 0, itemStyle: { color: up ? UP_COLOR : DOWN_COLOR } };
    });

    const grids = [
      { left: 60, right: 20, top: 20, height: "52%" },
      { left: 60, right: 20, top: "60%", height: "12%" },
      { left: 60, right: 20, top: "76%", height: "16%" },
    ];
    const xAxes = [0, 1, 2].map((i) => ({
      type: "category" as const,
      data: dates,
      gridIndex: i,
      boundaryGap: true,
      axisLine: baseOption.categoryAxis.axisLine,
      axisLabel: { show: i === 2, color: palette.textStyle.color },
      axisTick: { show: false },
      splitLine: { show: false },
      min: "dataMin",
      max: "dataMax",
    }));
    const yAxes = [
      { scale: true, gridIndex: 0, splitLine: baseOption.valueAxis.splitLine, axisLabel: { color: palette.textStyle.color } },
      { scale: true, gridIndex: 1, splitNumber: 2, axisLabel: { show: false }, splitLine: { show: false } },
      { scale: true, gridIndex: 2, splitNumber: 3, splitLine: { show: false }, axisLabel: { color: palette.textStyle.color } },
    ];

    // price pane series
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
    // overlays (ma/ema/boll/...)
    OVERLAYS.forEach((key) => {
      const frame = series.indicators[key];
      if (!frame) return;
      Object.entries(frame).forEach(([col, arr], idx) => {
        priceSeries.push({
          name: col.toUpperCase(),
          type: "line",
          data: arr,
          xAxisIndex: 0,
          yAxisIndex: 0,
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 1, color: palette.series[idx % palette.series.length] },
        });
      });
    });

    // volume pane
    const volSeries = [
      { name: "成交量", type: "bar" as const, data: vols, xAxisIndex: 1, yAxisIndex: 1 },
    ];

    // sub-indicator pane
    let subSeries: Record<string, unknown>[] = [];
    if (sub && sub !== "vol") {
      const frame = series.indicators[sub];
      if (frame) {
        subSeries = Object.entries(frame).map(([col, arr], idx) => ({
          name: col.toUpperCase(),
          type: col === "macd" ? "bar" : "line",
          data: arr,
          xAxisIndex: 2,
          yAxisIndex: 2,
          showSymbol: false,
          smooth: true,
          lineStyle: { width: 1, color: palette.series[idx % palette.series.length] },
          itemStyle: { color: palette.series[idx % palette.series.length] },
        }));
      }
    }

    return {
      animation: false,
      backgroundColor: "transparent",
      textStyle: baseOption.textStyle,
      tooltip: { ...baseOption.tooltip },
      axisPointer: { link: [{ xAxisIndex: "all" }], label: { backgroundColor: "#777" } },
      legend: {
        data: [...Object.keys(series.indicators).flatMap((k) =>
          Object.keys(series.indicators[k] || {}).map((c) => c.toUpperCase()),
        )].slice(0, 12),
        top: 0,
        right: 20,
        textStyle: { color: palette.textStyle.color, fontSize: 11 },
        inactiveColor: "#bbb",
      },
      grid: grids,
      xAxis: xAxes,
      yAxis: yAxes,
      dataZoom: [
        { type: "inside", xAxisIndex: [0, 1, 2], start: 60, end: 100 },
        { type: "slider", xAxisIndex: [0, 1, 2], bottom: 6, height: 16, start: 60, end: 100 },
      ],
      series: [...priceSeries, ...volSeries, ...subSeries],
    };
  }, [series, sub, baseOption, palette]);

  return <ReactECharts option={option} notMerge lazyUpdate style={{ height, width: "100%" }} />;
}
