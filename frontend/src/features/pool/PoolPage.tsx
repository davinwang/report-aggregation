// 机构推荐池 — sina 上调/下调/首次评级名单 (Phase 1 gap fill).
// Written by the recommend_pool ingest feed; read-only here. Route: /pool
import { useState } from "react";
import { Card, Col, Row, Segmented, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getPoolList, getPoolSummary } from "@/api";
import type { PoolRow } from "@/types";
import PageContainer from "@/components/PageContainer";
import ProvenanceTag from "@/components/ProvenanceTag";
import PageRefresh from "@/components/PageRefresh";
import StatCard from "@/components/StatCard";
import { SECTOR_GROUPS } from "@/components/SectorFilter";
import { DOWN_COLOR, UP_COLOR } from "@/styles/theme";
import { fmtNum } from "@/hooks/useRelativeTime";

const KIND_META: Record<string, { label: string; color: string }> = {
  upgrade: { label: "评级上调", color: "red" },
  downgrade: { label: "评级下调", color: "green" },
  first: { label: "首次评级", color: "blue" },
};

const KIND_OPTIONS = [
  { value: "all", label: "全部" },
  { value: "upgrade", label: "评级上调" },
  { value: "downgrade", label: "评级下调" },
  { value: "first", label: "首次评级" },
];

export default function PoolPage() {
  const [kind, setKind] = useState("all");
  const [industry, setIndustry] = useState<string | undefined>(undefined);
  const [days, setDays] = useState(30);
  const [page, setPage] = useState(1);
  const size = 50;

  const { data: summary } = useQuery({
    queryKey: ["pool", "summary", days],
    queryFn: () => getPoolSummary(days),
    staleTime: 60_000,
  });
  const { data, isFetching, isError } = useQuery({
    queryKey: ["pool", "list", kind, industry ?? "", days, page],
    queryFn: () =>
      getPoolList({
        kind: kind === "all" ? undefined : kind,
        industry,
        days,
        page,
        size,
      }),
    staleTime: 30_000,
  });

  const counts = summary?.counts ?? {};

  const columns: ColumnsType<PoolRow> = [
    { title: "日期", dataIndex: "trade_date", width: 108 },
    {
      title: "股票",
      dataIndex: "code",
      width: 150,
      render: (code: string, r) => <Link to={`/stock/${code}`}>{r.name ?? code}</Link>,
    },
    {
      title: "池",
      dataIndex: "kind",
      width: 96,
      render: (k: string) => {
        const m = KIND_META[k] ?? { label: k, color: "default" };
        return <Tag color={m.color}>{m.label}</Tag>;
      },
    },
    {
      title: "评级",
      dataIndex: "rating",
      width: 76,
      render: (v: string | null) => {
        if (!v) return "-";
        const color = v === "卖出" || v === "减持" ? DOWN_COLOR : v === "买入" || v === "增持" ? UP_COLOR : "#999";
        return <span style={{ color }}>{v}</span>;
      },
    },
    {
      title: "强度",
      dataIndex: "strength",
      width: 64,
      render: (v: string | null) =>
        v ? <Tag color={v === "强" ? "volcano" : v === "中" ? "orange" : "default"}>{v}</Tag> : "-",
    },
    { title: "机构", dataIndex: "org", width: 110, ellipsis: true, render: (v: string | null) => v ?? "-" },
    {
      title: "目标价",
      dataIndex: "target_price",
      align: "right",
      width: 88,
      render: (v: number | null) => (v != null ? fmtNum(v) : "-"),
    },
    { title: "行业", dataIndex: "industry_group", width: 96, render: (v: string | null) => v ?? "-" },
    { title: "分析师", dataIndex: "analysts", ellipsis: true, render: (v: string | null) => v ?? "-" },
  ];

  return (
    <PageContainer
      title="机构推荐池"
      description="新浪 · 上调评级 / 下调评级 / 首次评级 三池汇总（近30日窗口锚定最新交易日）"
      extra={
        <Space wrap>
          <ProvenanceTag source="sina" date={summary?.ref ?? null} />
          <PageRefresh queryKeys={[["pool"]]} feeds={["recommend_pool"]} />
        </Space>
      }
    >
      <div className="grid-cards" style={{ marginBottom: 12 }}>
        <StatCard
          title={`评级上调 (近${days}日)`}
          value={counts.upgrade ?? 0}
          footer="机构上调评级名单"
          loading={!summary}
        />
        <StatCard
          title={`评级下调 (近${days}日)`}
          value={counts.downgrade ?? 0}
          footer="机构下调评级名单"
          loading={!summary}
        />
        <StatCard
          title={`首次评级 (近${days}日)`}
          value={counts.first ?? 0}
          footer="机构首次覆盖名单"
          loading={!summary}
        />
        <StatCard
          title="合计"
          value={summary?.total ?? 0}
          footer={`截至 ${summary?.ref ?? "-"}`}
          loading={!summary}
        />
      </div>

      <Card
        size="small"
        title={`推荐池 ${data?.meta?.ref ? `· ${data.meta.ref}` : ""}`}
        extra={
          <Space wrap>
            <Segmented
              size="small"
              value={kind}
              onChange={(v) => {
                setKind(String(v));
                setPage(1);
              }}
              options={KIND_OPTIONS}
            />
            <Select
              size="small"
              allowClear
              placeholder="全部行业"
              value={industry}
              onChange={(v) => {
                setIndustry(v ?? undefined);
                setPage(1);
              }}
              options={SECTOR_GROUPS.map((g) => ({ value: g, label: g }))}
              style={{ width: 130 }}
            />
            <Segmented
              size="small"
              value={days}
              onChange={(v) => {
                setDays(Number(v));
                setPage(1);
              }}
              options={[
                { value: 30, label: "30日" },
                { value: 90, label: "90日" },
                { value: 180, label: "180日" },
              ]}
            />
          </Space>
        }
      >
        <Table
          size="small"
          rowKey="id"
          loading={isFetching}
          dataSource={isError ? [] : data?.rows ?? []}
          columns={columns}
          locale={{ emptyText: "暂无数据。请先运行 recommend_pool 采集（新浪三池）。" }}
          pagination={{
            current: page,
            pageSize: size,
            total: data?.meta?.total ?? 0,
            showSizeChanger: false,
            onChange: setPage,
            size: "small",
          }}
        />
      </Card>

      <Row gutter={12} style={{ marginTop: 12 }}>
        <Col xs={24} xl={12}>
          <Card size="small" title="池说明">
            <Typography.Paragraph className="muted" style={{ marginBottom: 6 }}>
              <b>评级上调/下调</b>：机构对同一股票相邻两次评级的变动方向（买入 ⇌ 增持 ⇌ 中性 ⇌ 减持 ⇌ 卖出），
              与评级信号同源但以新浪推荐池口径独立入库。
            </Typography.Paragraph>
            <Typography.Paragraph className="muted" style={{ marginBottom: 0 }}>
              <b>首次评级</b>：机构首次对该股票给出评级。数据每日采集，窗口锚定最新交易日。
            </Typography.Paragraph>
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card size="small" title={`行业分布 (近${days}日)`}>
            <Table
              size="small"
              rowKey="industry"
              pagination={false}
              dataSource={summary?.industries ?? []}
              columns={[
                { title: "行业", dataIndex: "industry" },
                { title: "条数", dataIndex: "count", align: "right", width: 100 },
              ]}
              locale={{ emptyText: "暂无数据" }}
            />
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
