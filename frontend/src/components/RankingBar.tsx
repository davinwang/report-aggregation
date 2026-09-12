// Horizontal ranking bar (机构排行 / 准确率 / 资金流 etc.).
import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { useEchartsTheme } from "@/hooks/useEchartsTheme";
import { DOWN_COLOR, UP_COLOR } from "@/styles/theme";

export interface RankItem {
  name: string;
  value: number;
}

interface Props {
  items: RankItem[];
  height?: number;
  colorBySign?: boolean; // red positive / green negative
  unit?: string;
  onSelect?: (name: string) => void;
}

export default function RankingBar({ items, height = 360, colorBySign = false, unit = "", onSelect }: Props) {
  const { palette, baseOption } = useEchartsTheme();

  const option = useMemo(() => {
    const sorted = [...items].sort((a, b) => a.value - b.value); // ascending → largest on top
    return {
      backgroundColor: "transparent",
      grid: { left: 8, right: 32, top: 12, bottom: 12, containLabel: true },
      tooltip: { ...baseOption.tooltip, trigger: "item", formatter: (p: { name: string; value: number }) => `${p.name}: ${p.value}${unit}` },
      xAxis: { type: "value", splitLine: baseOption.valueAxis.splitLine, axisLabel: { color: palette.textStyle.color } },
      yAxis: {
        type: "category",
        data: sorted.map((i) => i.name),
        axisLine: baseOption.categoryAxis.axisLine,
        axisLabel: { color: palette.textStyle.color },
        axisTick: { show: false },
      },
      series: [
        {
          type: "bar",
          data: sorted.map((i) => ({
            value: i.value,
            itemStyle: { color: colorBySign ? (i.value >= 0 ? UP_COLOR : DOWN_COLOR) : palette.series[0] },
          })),
          barMaxWidth: 16,
          label: { show: true, position: "right", color: palette.textStyle.color, fontSize: 11, formatter: `{c}${unit}` },
        },
      ],
    };
  }, [items, palette, baseOption, colorBySign, unit]);

  const onEvents = useMemo(
    () => ({ click: (p: { name?: string }) => onSelect && p?.name && onSelect(p.name) }),
    [onSelect],
  );

  return <ReactECharts option={option} notMerge lazyUpdate style={{ height, width: "100%" }} onEvents={onEvents} />;
}
