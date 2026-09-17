// 全市场速览 — 技术面矩阵 (股票×指标): 趋势/MACD/RSI 一览.
// Route: /market-overview
import { useMemo, useState } from "react";
import { Card, Segmented, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getMatrix } from "@/api";
import type { QuantMatrixRow } from "@/types";
import PageContainer from "@/components/PageContainer";
import ProvenanceTag from "@/components/ProvenanceTag";
import PageRefresh from "@/components/PageRefresh";
import StatCard from "@/components/StatCard";
import { DOWN_COLOR, UP_COLOR } from "@/styles/theme";
import { fmtNum } from "@/hooks/useRelativeTime";

const STATE_FILTERS = [
  { value: "all", label: "全部" },
  { value: "bull", label: "多头" },
  { value: "bear", label: "空头" },
  { value: "golden", label: "MACD金叉" },
  { value: "dead", label: "MACD死叉" },
];

export default function MarketOverviewPage() {
  const [scope, setScope] = useState("index+active");
  const [limit, setLimit] = useState(60);
  const [filter, setFilter] = useState("all");

  const { data, isFetching, isError } = useQuery({
    queryKey: ["quant", "matrix", scope, limit],
    queryFn: () => getMatrix({ limit, scope }),
    staleTime: 60_000,
  });

  const rows = data ?? [];
  const stats = useMemo(() => {
    const bull = rows.filter((r) => r.trend === "多").length;
    const golden = rows.filter((r) => r.macd === "金叉").length;
    const strong = rows.filter((r) => r.rsi === "强").length;
    return { bull, bear: rows.length - bull, golden, dead: rows.length - golden, strong };
  }, [rows]);

  const filtered = useMemo(() => {
    switch (filter) {
      case "bull":
        return rows.filter((r) => r.trend === "多");
      case "bear":
        return rows.filter((r) => r.trend === "空");
      case "golden":
        return rows.filter((r) => r.macd === "金叉");
      case "dead":
        return rows.filter((r) => r.macd === "死叉");
      default:
        return rows;
    }
  }, [rows, filter]);

  const columns: ColumnsType<QuantMatrixRow> = [
    {
      title: "证券",
      dataIndex: "name",
      width: 160,
      fixed: "left",
      render: (name: string, r) => <Link to={`/technical/${r.code}`}>{name}</Link>,
    },
    { title: "代码", dataIndex: "code", width: 90, render: (c: string) => <span className="muted">{c}</span> },
    { title: "现价", dataIndex: "close", align: "right", width: 92, render: (v: number | null) => fmtNum(v, 2) },
    { title: "MA20", dataIndex: "ma20", align: "right", width: 92, render: (v: number | null) => fmtNum(v, 2) },
    {
      title: "趋势",
      dataIndex: "trend",
      width: 76,
      render: (v: string) => <Tag color={v === "多" ? "red" : "green"}>{v === "多" ? "多头" : "空头"}</Tag>,
    },
    {
      title: "MACD",
      dataIndex: "macd",
      width: 80,
      render: (v: string) => <span style={{ color: v === "金叉" ? UP_COLOR : DOWN_COLOR }}>{v}</span>,
    },
    { title: "RSI12", dataIndex: "rsi12", align: "right", width: 80, render: (v: number | null) => fmtNum(v, 1) },
    {
      title: "RSI状态",
      dataIndex: "rsi",
      width: 80,
      render: (v: string) => (
        <Tag color={v === "强" ? "volcano" : v === "弱" ? "cyan" : "default"}>{v}</Tag>
      ),
    },
  ];

  return (
    <PageContainer
      title="全市场速览"
      description="技术面矩阵 — 指数 + 活跃个股的 趋势 / MACD / RSI 状态一览（基于已采集日线）"
      extra={<Space><ProvenanceTag source="em" /><PageRefresh queryKeys={[["quant", "matrix"]]} feeds={["price_history"]} /></Space>}
    >
      <div className="grid-cards" style={{ marginBottom: 12 }}>
        <StatCard
          title="多头占比"
          value={rows.length ? `${Math.round((100 * stats.bull) / rows.length)}%` : "-"}
          footer={`多头 ${stats.bull} / 空头 ${stats.bear}`}
          loading={isFetching && !data}
        />
        <StatCard
          title="MACD 金叉"
          value={stats.golden}
          footer={`死叉 ${stats.dead}`}
          loading={isFetching && !data}
        />
        <StatCard title="RSI 强势" value={stats.strong} footer={`合计 ${rows.length} 只`} loading={isFetching && !data} />
        <StatCard
          title="覆盖范围"
          value={scope === "index" ? "仅指数" : "指数+活跃"}
          footer={`上限 ${limit} 只`}
          loading={isFetching && !data}
        />
      </div>

      <Card
        size="small"
        title="技术面矩阵"
        extra={
          <Space wrap>
            <Segmented
              size="small"
              value={filter}
              onChange={(v) => setFilter(String(v))}
              options={STATE_FILTERS}
            />
            <Select
              size="small"
              value={scope}
              onChange={setScope}
              style={{ width: 130 }}
              options={[
                { value: "index", label: "仅指数" },
                { value: "index+active", label: "指数+活跃股" },
              ]}
            />
            <Select
              size="small"
              value={limit}
              onChange={setLimit}
              style={{ width: 100 }}
              options={[30, 60, 120, 300].map((n) => ({ value: n, label: `Top${n}` }))}
            />
          </Space>
        }
      >
        {rows.length ? (
          <Table
            size="small"
            rowKey="code"
            loading={isFetching}
            dataSource={isError ? [] : filtered}
            columns={columns}
            scroll={{ x: 800 }}
            pagination={{ pageSize: 30, size: "small", showSizeChanger: false }}
          />
        ) : (
          <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
            暂无日线数据。请先采集 <Typography.Text code>price_history</Typography.Text>（个股日线，
            按 universe）后再查看矩阵。
          </Typography.Paragraph>
        )}
      </Card>
    </PageContainer>
  );
}
