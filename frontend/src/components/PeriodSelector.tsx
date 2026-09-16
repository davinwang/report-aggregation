// Global period-window selector (bound to the UI store). Transform of the reference's
// 期次窗口: for stocks the natural windows are 今日/本周/近两周/本月.
import { Select } from "antd";
import { useUIStore, type PeriodKey } from "@/stores/uiStore";

const OPTIONS: { value: PeriodKey; label: string }[] = [
  { value: "today", label: "今日" },
  { value: "week", label: "本周" },
  { value: "twoweek", label: "近两周" },
  { value: "month", label: "本月" },
];

interface Props {
  width?: number | string; // header uses the compact default; the mobile drawer stretches it
}

export default function PeriodSelector({ width = 100 }: Props) {
  const period = useUIStore((s) => s.period);
  const setPeriod = useUIStore((s) => s.setPeriod);
  return (
    <Select<PeriodKey>
      size="small"
      value={period}
      onChange={setPeriod}
      options={OPTIONS}
      style={{ width }}
      variant="filled"
    />
  );
}
