// Generic multi-series line/bar chart (ECharts) with an optional secondary y-axis.
// Used by basis / flow / accuracy pages where the backend returns ECharts-ready arrays.
import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { useEchartsTheme } from "@/hooks/useEchartsTheme";

export interface LineSeries {
  name: string;
  data: (number | null)[];
  type?: "line" | "bar";
  yAxisIndex?: number;
  area?: boolean;
}

interface Props {
  dates: string[];
  series: LineSeries[];
  height?: number;
  yAxisNames?: [string, string];
  zoom?: boolean;
}

export default function LineChart({ dates, series, height = 320, yAxisNames, zoom = false }: Props) {
  const { baseOption, palette } = useEchartsTheme();

  const option = useMemo(() => {
    const dual = series.some((s) => s.yAxisIndex === 1);
    // A line needs ≥2 points to draw anything: with sparse history (e.g. a single
    // session of 涨跌家数) a symbol-less series renders as an empty plot even though
    // the data is there. Show markers while the series is short, clean lines after.
    const sparse = dates.length <= 31;
    const yAxes = dual
      ? [
          { ...baseOption.valueAxis, scale: true, name: yAxisNames?.[0], nameTextStyle: { color: palette.textStyle.color } },
          { ...baseOption.valueAxis, scale: true, name: yAxisNames?.[1], position: "right", nameTextStyle: { color: palette.textStyle.color } },
        ]
      : [{ ...baseOption.valueAxis, scale: true, name: yAxisNames?.[0], nameTextStyle: { color: palette.textStyle.color } }];

    return {
      animation: false,
      backgroundColor: "transparent",
      textStyle: baseOption.textStyle,
      tooltip: { ...baseOption.tooltip },
      legend: { ...baseOption.legend, top: 0, right: 16, data: series.map((s) => s.name) },
      grid: { left: 56, right: dual ? 64 : 24, top: 36, bottom: zoom ? 56 : 32, containLabel: true },
      xAxis: { type: "category", data: dates, boundaryGap: series.some((s) => s.type === "bar"), ...baseOption.categoryAxis },
      yAxis: yAxes,
      dataZoom: zoom
        ? [
            { type: "inside", start: 50, end: 100 },
            { type: "slider", bottom: 8, height: 16, start: 50, end: 100 },
          ]
        : undefined,
      series: series.map((s, i) => ({
        name: s.name,
        type: s.type ?? "line",
        data: s.data,
        yAxisIndex: s.yAxisIndex ?? 0,
        smooth: s.type !== "bar",
        showSymbol: sparse,
        connectNulls: true,
        lineStyle: { width: 1.6, color: palette.series[i % palette.series.length] },
        itemStyle: { color: palette.series[i % palette.series.length] },
        areaStyle: s.area ? { opacity: 0.12 } : undefined,
      })),
    };
  }, [dates, series, baseOption, palette, yAxisNames, zoom]);

  return <ReactECharts option={option} notMerge lazyUpdate style={{ height, width: "100%" }} />;
}
