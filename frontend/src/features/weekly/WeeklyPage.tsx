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
import PageRefresh from "@/components/PageRefresh";
import StatCard from "@/components/StatCard";
import { msg } from "@/utils/message";
import { useIsMobile } from "@/hooks/useIsMobile";
import { useUIStore } from "@/stores/uiStore";
import { BRAND, mixColor } from "@/styles/theme";

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

  // Amber heat scale for the org×industry count matrix: monochrome on purpose —
  // counts carry no up/down direction, so red/green would conflict with 红涨绿跌.
  const mode = useUIStore((s) => s.mode);
  const isMobile = useIsMobile();
  const cellBase = mode === "dark" ? "#10141b" : "#ffffff";
  const cellTint = (v: number) => {
    const mixT = 0.12 + 0.76 * (v / maxCell);
    return { bg: mixColor(cellBase, BRAND, mixT), strong: mixT > 0.6 };
  };

  // 手机上机构名收窄且不固定 — fixed:left 会占掉近半屏可视区，横向滚动没意义。
  const orgColWidth = isMobile ? 108 : 160;
  const industryColWidth = isMobile ? 56 : 84;
  const matrixColumns: ColumnsType<WeeklyMatrixRow> = [
    {
      title: "机构",
      dataIndex: "org",
      width: orgColWidth,
      fixed: isMobile ? undefined : "left",
      ellipsis: true,
      render: (v: string) => (
        <Typography.Text strong ellipsis style={{ maxWidth: orgColWidth - 24, display: "inline-block" }}>
          {v}
        </Typography.Text>
      ),
    },
    { title: "合计", dataIndex: "total", width: isMobile ? 48 : 72, align: "right", render: (v: number) => <b className="num">{v}</b> },
    ...groups.map((g) => ({
      title: (
        <span style={{ whiteSpace: "nowrap", fontSize: isMobile ? 12 : undefined }}>{g}</span>
      ),
      key: g,
      width: industryColWidth,
      align: "right" as const,
      render: (_: unknown, r: WeeklyMatrixRow) => {
        const v = r.by_group?.[g];
        return v ? <span className="num">{v}</span> : <span className="muted">·</span>;
      },
      onCell: (r: WeeklyMatrixRow) => {
        const v = r.by_group?.[g];
        if (!v) return {};
        const { bg, strong } = cellTint(v);
        return { style: { background: bg, ...(strong ? { color: "#fff" } : {}) } };
      },
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
          <span className="muted" style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
            少
            <span
              style={{
                width: 48,
                height: 8,
                borderRadius: 1,
                background: `linear-gradient(90deg, ${mixColor(cellBase, BRAND, 0.12)}, ${mixColor(cellBase, BRAND, 0.88)})`,
              }}
            />
            多
          </span>
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
          scroll={{ x: isMobile ? 108 + 48 + groups.length * industryColWidth : 900 }}
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
      extra={<Space><ProvenanceTag source="em" date={matrix?.week_key ?? null} /><PageRefresh queryKeys={[["weekly"]]} /></Space>}
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
