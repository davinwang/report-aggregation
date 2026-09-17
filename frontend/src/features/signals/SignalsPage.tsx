// 评级信号 — 规则驱动: 评级上调/下调 · 首次覆盖 · 一致评级.
// Derived from the 东财研报库 (no LLM — AI deferred). Route: /signals
import { useState } from "react";
import { Button, Card, Col, Row, Segmented, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SyncOutlined } from "@ant-design/icons";
import { getSignalSummary, getSignals, refreshSignals } from "@/api";
import type { SignalRow } from "@/types";
import PageContainer from "@/components/PageContainer";
import ProvenanceTag from "@/components/ProvenanceTag";
import StatCard from "@/components/StatCard";
import { SECTOR_GROUPS } from "@/components/SectorFilter";
import { msg } from "@/utils/message";
import { DOWN_COLOR, UP_COLOR } from "@/styles/theme";
import { fmtNum } from "@/hooks/useRelativeTime";

const KIND_META: Record<string, { label: string; color: string }> = {
  upgrade: { label: "评级上调", color: "red" },
  downgrade: { label: "评级下调", color: "green" },
  first: { label: "首次覆盖", color: "blue" },
  consensus: { label: "一致评级", color: "purple" },
};

const KIND_OPTIONS = [
  { value: "all", label: "全部" },
  { value: "upgrade", label: "评级上调" },
  { value: "downgrade", label: "评级下调" },
  { value: "first", label: "首次覆盖" },
  { value: "consensus", label: "一致评级" },
];

export default function SignalsPage() {
  const queryClient = useQueryClient();
  const [action, setAction] = useState("all");
  const [industry, setIndustry] = useState<string | undefined>(undefined);
  const [days, setDays] = useState(30);
  const [page, setPage] = useState(1);
  const size = 50;

  const { data: summary } = useQuery({
    queryKey: ["signals", "summary", days],
    queryFn: () => getSignalSummary(days),
    staleTime: 60_000,
  });
  const { data, isFetching, isError } = useQuery({
    queryKey: ["signals", "list", action, industry ?? "", days, page],
    queryFn: () =>
      getSignals({
        action: action === "all" ? undefined : action,
        industry,
        days,
        page,
        size,
      }),
    staleTime: 30_000,
  });

  const refresh = useMutation({
    mutationFn: () => refreshSignals(180),
    onSuccess: (res) => {
      const stats = (res as { data?: Record<string, number | string> })?.data ?? {};
      msg.success(
        `信号已重算：上调 ${stats.upgrade ?? 0} · 下调 ${stats.downgrade ?? 0} · 首次 ${stats.first ?? 0} · 一致 ${stats.consensus ?? 0}`,
      );
      queryClient.invalidateQueries({ queryKey: ["signals"] });
    },
    onError: () => msg.error("信号重算失败，请查看后端日志"),
  });

  const counts = summary?.counts ?? {};

  const columns: ColumnsType<SignalRow> = [
    { title: "日期", dataIndex: "trade_date", width: 108 },
    {
      title: "股票",
      dataIndex: "code",
      width: 150,
      render: (code: string, r) => <Link to={`/stock/${code}`}>{r.name ?? code}</Link>,
    },
    {
      title: "信号",
      dataIndex: "kind",
      width: 96,
      render: (k: string) => {
        const m = KIND_META[k] ?? { label: k, color: "default" };
        return <Tag color={m.color}>{m.label}</Tag>;
      },
    },
    {
      title: "方向",
      dataIndex: "direction",
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
    {
      title: "评分",
      dataIndex: "score",
      align: "right",
      width: 72,
      render: (v: number | null) => (v == null ? "-" : fmtNum(v, 0)),
    },
    { title: "行业", dataIndex: "industry_group", width: 96, render: (v: string | null) => v ?? "-" },
    { title: "理由", dataIndex: "reason", ellipsis: true, render: (v: string | null) => v ?? "-" },
  ];

  return (
    <PageContainer
      title="评级信号"
      description="规则驱动 · 基于东财研报库：评级上调/下调 · 首次覆盖 · 一致评级（近90日 ≥3 家机构同向覆盖）"
      extra={
        <Space wrap>
          <ProvenanceTag source="em" date={summary?.ref ?? null} />
          <Button
            size="small"
            icon={<SyncOutlined />}
            loading={refresh.isPending}
            onClick={() => refresh.mutate()}
          >
            重算信号
          </Button>
        </Space>
      }
    >
      <div className="grid-cards" style={{ marginBottom: 12 }}>
        <StatCard
          title={`评级上调 (近${days}日)`}
          value={counts.upgrade ?? 0}
          footer="机构对个股评级上调"
          loading={!summary}
        />
        <StatCard
          title={`评级下调 (近${days}日)`}
          value={counts.downgrade ?? 0}
          footer="机构对个股评级下调"
          loading={!summary}
        />
        <StatCard
          title={`首次覆盖 (近${days}日)`}
          value={counts.first ?? 0}
          footer="机构首次给出评级"
          loading={!summary}
        />
        <StatCard
          title="一致评级"
          value={counts.consensus ?? 0}
          footer={`≥3 家机构同向覆盖 · 截至 ${summary?.ref ?? "-"}`}
          loading={!summary}
        />
      </div>

      <Card
        size="small"
        title={`信号列表 ${data?.meta?.ref ? `· ${data.meta.ref}` : ""}`}
        extra={
          <Space wrap>
            <Segmented
              size="small"
              value={action}
              onChange={(v) => {
                setAction(String(v));
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
          rowKey={(r) => `${r.kind}-${r.code}-${r.trade_date}`}
          loading={isFetching}
          dataSource={isError ? [] : data?.rows ?? []}
          columns={columns}
          locale={{ emptyText: "暂无信号。请先采集 research_reports，再点击“重算信号”。" }}
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
          <Card size="small" title="信号类型说明">
            <Typography.Paragraph className="muted" style={{ marginBottom: 6 }}>
              <b>评级上调/下调</b>：同一机构对同一股票相邻两次评级的变动（买入 ⇌ 增持 ⇌ 中性 ⇌ 减持 ⇌ 卖出），
              以最近一次研报日期为信号日期。
            </Typography.Paragraph>
            <Typography.Paragraph className="muted" style={{ marginBottom: 6 }}>
              <b>首次覆盖</b>：机构首次对该股票给出评级。
            </Typography.Paragraph>
            <Typography.Paragraph className="muted" style={{ marginBottom: 0 }}>
              <b>一致评级</b>：近 90 日 ≥3 家机构覆盖，且最新评级中买入+增持占比 ≥60%（强：≥80%）；
              偏空信号需减持+卖出占比 ≥50%。
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
                { title: "信号数", dataIndex: "count", align: "right", width: 100 },
              ]}
              locale={{ emptyText: "暂无数据" }}
            />
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
