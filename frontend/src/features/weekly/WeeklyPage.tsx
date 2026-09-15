// 周统计 — Tab1 友商报告与活动 / Tab2 机构×行业 矩阵 (周度研报分布).
// Route: /weekly
import { useState } from "react";
import { Button, Card, Select, Space, Table, Tabs, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SyncOutlined } from "@ant-design/icons";
import { getWeeklyMatrix, getWeeklyPeer, refreshWeekly } from "@/api";
import type { PeerRow, WeeklyMatrixRow } from "@/types";
import PageContainer from "@/components/PageContainer";
import ProvenanceTag from "@/components/ProvenanceTag";
import StatCard from "@/components/StatCard";
import { msg } from "@/utils/message";

export default function WeeklyPage() {
  const queryClient = useQueryClient();
  const [week, setWeek] = useState<string | undefined>(undefined);
  const [period, setPeriod] = useState<string | undefined>(undefined);

  const { data: matrix, isFetching: mFetching } = useQuery({
    queryKey: ["weekly", "matrix", week ?? "auto"],
    queryFn: () => getWeeklyMatrix(week),
    staleTime: 60_000,
  });
  const { data: peer, isFetching: pFetching } = useQuery({
    queryKey: ["weekly", "peer", period ?? "auto"],
    queryFn: () => getWeeklyPeer(period),
    staleTime: 60_000,
  });

  const refresh = useMutation({
    mutationFn: () => refreshWeekly(12),
    onSuccess: () => {
      msg.success("周统计矩阵已重算");
      queryClient.invalidateQueries({ queryKey: ["weekly"] });
    },
    onError: () => msg.error("重算失败，请查看后端日志"),
  });

  const groups = matrix?.groups ?? [];
  const maxCell = Math.max(1, ...(matrix?.orgs ?? []).flatMap((o) => Object.values(o.by_group)));

  const cell = (v: number | undefined) =>
    !v ? (
      <span className="muted">-</span>
    ) : (
      <span
        style={{
          display: "inline-block",
          minWidth: 26,
          padding: "0 4px",
          borderRadius: 3,
          background: `rgba(200,22,29,${(0.06 + 0.5 * (v / maxCell)).toFixed(3)})`,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {v}
      </span>
    );

  const matrixColumns: ColumnsType<WeeklyMatrixRow> = [
    { title: "机构", dataIndex: "org", width: 160, fixed: "left", render: (v: string) => <Typography.Text strong>{v}</Typography.Text> },
    { title: "合计", dataIndex: "total", width: 72, align: "right", render: (v: number) => <b>{v}</b> },
    ...groups.map((g) => ({
      title: g,
      key: g,
      width: 84,
      align: "right" as const,
      render: (_: unknown, r: WeeklyMatrixRow) => cell(r.by_group?.[g]),
    })),
  ];

  const peerColumns: ColumnsType<PeerRow> = [
    { title: "类型", dataIndex: "kind", width: 72, render: (v: string) => <Tag>{v === "event" ? "活动" : "报告"}</Tag> },
    { title: "行业", dataIndex: "industry_group", width: 96, render: (v: string | null) => v ?? "-" },
    { title: "来源", dataIndex: "source", width: 110, render: (v: string | null) => v ?? "-" },
    {
      title: "标题",
      dataIndex: "title",
      ellipsis: true,
      render: (v: string, r) => (r.url ? <a href={r.url} target="_blank" rel="noreferrer">{v}</a> : v),
    },
    {
      title: "我方覆盖",
      dataIndex: "covered_by_us",
      width: 90,
      render: (v: boolean | null) => (v == null ? "-" : v ? <Tag color="red">已覆盖</Tag> : <Tag>未覆盖</Tag>),
    },
  ];

  const tab2 = (
    <Card
      size="small"
      title={`机构 × 行业矩阵 ${matrix?.week_key ? `· 周截至 ${matrix.week_key}` : ""}`}
      extra={
        <Space wrap>
          <Select
            size="small"
            value={matrix?.week_key ?? undefined}
            onChange={(v) => setWeek(v)}
            style={{ width: 170 }}
            placeholder="选择周"
            options={(matrix?.weeks ?? []).map((w) => ({
              value: w.week_key,
              label: `${w.week_key} (${w.reports}篇)`,
            }))}
          />
          <Button size="small" icon={<SyncOutlined />} loading={refresh.isPending} onClick={() => refresh.mutate()}>
            重算矩阵
          </Button>
        </Space>
      }
    >
      {matrix?.orgs?.length ? (
        <Table
          size="small"
          rowKey="org"
          loading={mFetching}
          dataSource={matrix.orgs}
          columns={matrixColumns}
          pagination={{ pageSize: 20, size: "small", showSizeChanger: false }}
          scroll={{ x: 900 }}
          summary={() => (
            <Table.Summary.Row>
              <Table.Summary.Cell index={0}>
                <b>合计</b>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={1} align="right">
                <b>{matrix.orgs.reduce((a, o) => a + o.total, 0)}</b>
              </Table.Summary.Cell>
              {groups.map((g, i) => (
                <Table.Summary.Cell key={g} index={i + 2} align="right">
                  <b>{matrix.group_totals?.[g] ?? 0}</b>
                </Table.Summary.Cell>
              ))}
            </Table.Summary.Row>
          )}
        />
      ) : (
        <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
          暂无周统计。请先采集 <Typography.Text code>research_reports</Typography.Text>，再点击“重算矩阵”。
        </Typography.Paragraph>
      )}
    </Card>
  );

  const tab1 = (
    <Card
      size="small"
      title={`友商报告与活动 ${peer?.period_key ? `· ${peer.period_key}` : ""}`}
      extra={
        <Select
          size="small"
          value={peer?.period_key ?? undefined}
          onChange={(v) => setPeriod(v)}
          style={{ width: 170 }}
          placeholder="选择周期"
          options={(peer?.periods ?? []).map((p) => ({ value: p, label: p }))}
        />
      }
    >
      <Table
        size="small"
        rowKey="id"
        loading={pFetching}
        dataSource={peer?.rows ?? []}
        columns={peerColumns}
        pagination={{ pageSize: 20, size: "small", showSizeChanger: false }}
        locale={{ emptyText: "暂无友商报告/活动 — 上传功能将在 Phase 3 提供" }}
      />
    </Card>
  );

  const topGroup = groups[0];

  return (
    <PageContainer
      title="周统计"
      description="周度研报分布 — 机构×行业矩阵（自有研报库）与友商报告/活动（Phase 3 支持上传）"
      extra={<ProvenanceTag source="em" date={matrix?.week_key ?? null} />}
    >
      <div className="grid-cards" style={{ marginBottom: 12 }}>
        <StatCard
          title="研报数"
          value={matrix?.weeks?.find((w) => w.week_key === matrix.week_key)?.reports ?? 0}
          footer={matrix?.week_key ?? "-"}
          loading={mFetching && !matrix}
        />
        <StatCard title="覆盖机构" value={matrix?.orgs?.length ?? 0} footer="所选周有研报产出" loading={mFetching && !matrix} />
        <StatCard
          title="最活跃行业"
          value={topGroup ?? "-"}
          footer={topGroup ? `${matrix?.group_totals?.[topGroup] ?? 0} 篇` : "-"}
          loading={mFetching && !matrix}
        />
        <StatCard
          title="友商报告与活动"
          value={peer?.rows?.length ?? 0}
          footer={peer?.period_key ? `周期 ${peer.period_key}` : "Phase 3 支持上传"}
          loading={pFetching && !peer}
        />
      </div>

      <Tabs
        items={[
          { key: "matrix", label: "机构×行业矩阵", children: tab2 },
          { key: "peer", label: "友商报告与活动", children: tab1 },
        ]}
      />
    </PageContainer>
  );
}
