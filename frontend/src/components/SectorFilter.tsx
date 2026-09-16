// Global sector (行业大类) filter bound to the UI store.
import { Select } from "antd";
import { useUIStore } from "@/stores/uiStore";

// Canonical industry groups (mirror backend INDUSTRY_GROUPS values).
export const SECTOR_GROUPS = [
  "金融地产",
  "消费服务",
  "科技成长",
  "医药生物",
  "先进制造",
  "新能源",
  "周期资源",
  "公用交运",
  "综合",
  "未分类",
];

interface Props {
  width?: number | string; // header uses the compact default; the mobile drawer stretches it
}

export default function SectorFilter({ width = 120 }: Props) {
  const sector = useUIStore((s) => s.sector);
  const setSector = useUIStore((s) => s.setSector);
  return (
    <Select
      size="small"
      allowClear
      placeholder="全部板块"
      value={sector ?? undefined}
      onChange={(v) => setSector(v ?? null)}
      options={SECTOR_GROUPS.map((g) => ({ value: g, label: g }))}
      style={{ width }}
      variant="filled"
    />
  );
}
