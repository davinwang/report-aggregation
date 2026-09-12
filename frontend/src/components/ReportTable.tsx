// Reusable research-report table (研报库 / 看板最新研报 / 个股研报).
import { Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Link } from "react-router-dom";
import type { ReportBrief } from "@/types";
import { fmtDate } from "@/hooks/useRelativeTime";

const RATING_COLOR: Record<string, string> = {
  买入: "red",
  增持: "volcano",
  中性: "default",
  减持: "green",
  卖出: "green",
};

interface Props {
  rows: ReportBrief[];
  loading?: boolean;
  showCode?: boolean;
  size?: "small" | "middle";
  pagination?: false | { current: number; pageSize: number; total: number; onChange: (p: number, s: number) => void };
  scrollY?: number;
}

export default function ReportTable({ rows, loading, showCode = true, size = "small", pagination = false, scrollY }: Props) {
  const columns: ColumnsType<ReportBrief> = [];
  if (showCode) {
    columns.push({
      title: "代码",
      dataIndex: "code",
      width: 92,
      render: (code: string, r) => <Link to={`/stock/${code}`}>{code} {r.name}</Link>,
    });
  }
  columns.push(
    {
      title: "标题",
      dataIndex: "title",
      ellipsis: true,
      render: (t: string, r) =>
        r.pdf_url ? (
          <a href={r.pdf_url} target="_blank" rel="noreferrer">
            <Typography.Text style={{ maxWidth: 420 }} ellipsis={{ tooltip: t }}>{t}</Typography.Text>
          </a>
        ) : (
          <Typography.Text style={{ maxWidth: 420 }} ellipsis={{ tooltip: t }}>{t}</Typography.Text>
        ),
    },
    { title: "机构", dataIndex: "org", width: 120, ellipsis: true },
    {
      title: "评级",
      dataIndex: "rating",
      width: 90,
      render: (v: string | null, r) =>
        v ? (
          <Tag color={RATING_COLOR[v] ?? "default"}>
            {v}
            {r.rating_change && r.rating_change !== "维持" ? ` · ${r.rating_change}` : ""}
          </Tag>
        ) : (
          "-"
        ),
    },
    {
      title: "目标价",
      width: 120,
      render: (_: unknown, r) => {
        if (r.target_price_low == null && r.target_price_high == null) return "-";
        if (r.target_price_low != null && r.target_price_high != null && r.target_price_low !== r.target_price_high)
          return `${r.target_price_low}~${r.target_price_high}`;
        return String(r.target_price_high ?? r.target_price_low);
      },
    },
    { title: "行业", dataIndex: "industry_group", width: 96, ellipsis: true, render: (v, r) => v || r.industry || "-" },
    { title: "日期", dataIndex: "publish_date", width: 104, render: (v: string) => fmtDate(v) },
  );

  return (
    <Table<ReportBrief>
      rowKey={(r) => `${r.id ?? ""}-${r.code}-${r.title}-${r.publish_date}`}
      size={size}
      loading={loading}
      columns={columns}
      dataSource={rows}
      pagination={pagination}
      scroll={scrollY ? { y: scrollY } : undefined}
    />
  );
}
