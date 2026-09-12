// Data-freshness badge — surfaces how current a feed is (critical given AkShare drift).
import { Badge, Tooltip } from "antd";
import type { Freshness } from "@/types";
import { relTime } from "@/hooks/useRelativeTime";

interface Props {
  feed?: string;
  freshness?: Freshness | null;
  compact?: boolean;
}

function status(f?: Freshness | null): "success" | "warning" | "error" | "default" {
  if (!f || !f.latest_data_date) return "default";
  const wb = f.weeks_behind ?? 0;
  if (wb <= 1) return "success";
  if (wb <= 4) return "warning";
  return "error";
}

export default function FreshnessBadge({ feed, freshness, compact }: Props) {
  const st = status(freshness);
  const text = freshness?.latest_data_date ?? "无数据";
  const tip = freshness
    ? `${feed ?? ""} 数据日期 ${freshness.latest_data_date ?? "-"} · 更新于 ${relTime(
        freshness.last_success_at,
      )} · 落后 ${freshness.weeks_behind ?? 0} 周`
    : "暂无新鲜度信息";
  return (
    <Tooltip title={tip}>
      <span style={{ fontSize: 12 }}>
        <Badge status={st} />
        {!compact && <span style={{ marginLeft: 6 }}>{text}</span>}
      </span>
    </Tooltip>
  );
}
