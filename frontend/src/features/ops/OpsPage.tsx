// 运营数据 — 采集新鲜度 / 批次日志 / 手动触发 (no login; runs as admin).
// Route: /ops
import { useState } from "react";
import { Button, Card, Col, Row, Segmented, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PlayCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import { getOpsFeeds, getOpsFreshness, getOpsIngestions, triggerIngest } from "@/api";
import type { FreshnessRow, IngestionRow } from "@/types";
import PageContainer from "@/components/PageContainer";
import StatCard from "@/components/StatCard";
import { msg } from "@/utils/message";
import { relTime } from "@/hooks/useRelativeTime";

const STATUS_TAG: Record<string, string> = { ok: "success", empty: "default", partial: "warning", error: "error" };

export default function OpsPage() {
  const queryClient = useQueryClient();
  const [errorsOnly, setErrorsOnly] = useState("all");

  const { data: freshness, isFetching: fFetching } = useQuery({
    queryKey: ["ops", "freshness"],
    queryFn: getOpsFreshness,
    staleTime: 30_000,
  });
  const { data: ingestions, isFetching: iFetching } = useQuery({
    queryKey: ["ops", "ingestions"],
    queryFn: () => getOpsIngestions(100),
    staleTime: 30_000,
  });
  const { data: feeds } = useQuery({ queryKey: ["ops", "feeds"], queryFn: getOpsFeeds, staleTime: 300_000 });

  const trigger = useMutation({
    mutationFn: (scope: string) => triggerIngest(scope),
    onSuccess: (_d, scope) => {
      msg.success(`已调度采集任务 (${scope}) — 进度将通过 SSE 实时推送`);
      queryClient.invalidateQueries({ queryKey: ["ops"] });
    },
    onError: () => msg.error("触发失败，请查看后端日志"),
  });

  const rows = ingestions ?? [];
  const failed = rows.filter((r) => r.status === "error").length;
  const shown = errorsOnly === "errors" ? rows.filter((r) => r.status === "error") : rows;
  const latestData = (freshness ?? [])
    .map((f) => f.latest_data_date)
    .filter((d): d is string => Boolean(d))
    .sort()
    .pop();

  const freshColumns: ColumnsType<FreshnessRow> = [
    { title: "数据源", dataIndex: "feed", render: (v: string) => <Typography.Text strong>{v}</Typography.Text> },
    {
      title: "最近成功",
      dataIndex: "last_success_at",
      width: 130,
      render: (v: string | null) => (v ? relTime(v) : "-"),
    },
    { title: "最新数据日期", dataIndex: "latest_data_date", width: 120, render: (v: string | null) => v ?? "-" },
    { title: "累计行数", dataIndex: "rows_total", align: "right", width: 100, render: (v: number) => v?.toLocaleString() },
    {
      title: "落后",
      dataIndex: "weeks_behind",
      width: 80,
      align: "center",
      render: (v: number | null) =>
        v == null ? "-" : v > 0 ? <Tag color="warning">{v}周</Tag> : <Tag color="success">正常</Tag>,
    },
    { title: "备注", dataIndex: "note", ellipsis: true, render: (v: string | null) => v ?? "-" },
  ];

  const ingColumns: ColumnsType<IngestionRow> = [
    { title: "时间", dataIndex: "started_at", width: 150, render: (v: string | null) => (v ? v.replace("T", " ").slice(0, 19) : "-") },
    { title: "数据源", dataIndex: "feed", width: 130 },
    {
      title: "状态",
      dataIndex: "status",
      width: 80,
      render: (v: string) => <Tag color={STATUS_TAG[v] ?? "default"}>{v}</Tag>,
    },
    { title: "采集", dataIndex: "rows_seen", align: "right", width: 90 },
    { title: "写入", dataIndex: "rows_upserted", align: "right", width: 90 },
    { title: "耗时", dataIndex: "latency_ms", align: "right", width: 90, render: (v: number | null) => (v == null ? "-" : `${(v / 1000).toFixed(1)}s`) },
    { title: "错误", dataIndex: "error", ellipsis: true, render: (v: string | null) => (v ? <span style={{ color: "#e4393c" }}>{v}</span> : "-") },
  ];

  return (
    <PageContainer
      title="运营数据"
      description="采集新鲜度 · 批次日志 · 手动触发（登录已关闭，默认以管理员身份运行）"
      extra={
        <Space wrap>
          <Button size="small" icon={<ReloadOutlined />} onClick={() => queryClient.invalidateQueries({ queryKey: ["ops"] })}>
            刷新
          </Button>
          <Button size="small" type="primary" icon={<PlayCircleOutlined />} loading={trigger.isPending} onClick={() => trigger.mutate("all")}>
            全量采集
          </Button>
        </Space>
      }
    >
      <div className="grid-cards" style={{ marginBottom: 12 }}>
        <StatCard title="数据源" value={freshness?.length ?? 0} footer={`${feeds?.length ?? 0} 个已注册`} loading={fFetching && !freshness} />
        <StatCard title="最新数据日期" value={latestData ?? "-"} footer="所有数据源最大值" loading={fFetching && !freshness} />
        <StatCard title="最近批次" value={rows.length} footer="近100条日志" loading={iFetching && !ingestions} />
        <StatCard
          title="失败批次"
          value={failed}
          footer={failed ? "请在日志中查看错误" : "运行正常"}
          loading={iFetching && !ingestions}
        />
      </div>

      <Row gutter={12} style={{ marginBottom: 12 }}>
        <Col xs={24} xl={11}>
          <Card
            size="small"
            title="数据新鲜度"
            extra={<Typography.Text className="muted" style={{ fontSize: 12 }}>FreshnessBadge 数据源</Typography.Text>}
            style={{ height: "100%" }}
          >
            <Table
              size="small"
              rowKey="feed"
              loading={fFetching}
              dataSource={freshness ?? []}
              columns={freshColumns}
              pagination={false}
              locale={{ emptyText: "暂无采集记录" }}
            />
          </Card>
        </Col>
        <Col xs={24} xl={13}>
          <Card
            size="small"
            title="采集日志"
            extra={
              <Segmented
                size="small"
                value={errorsOnly}
                onChange={(v) => setErrorsOnly(String(v))}
                options={[
                  { value: "all", label: "全部" },
                  { value: "errors", label: "仅失败" },
                ]}
              />
            }
            style={{ height: "100%" }}
          >
            <Table
              size="small"
              rowKey="id"
              loading={iFetching}
              dataSource={shown}
              columns={ingColumns}
              pagination={{ pageSize: 10, size: "small", showSizeChanger: false }}
              locale={{ emptyText: "暂无采集日志" }}
            />
          </Card>
        </Col>
      </Row>

      <Card size="small" title="已注册数据源">
        <Table
          size="small"
          rowKey="name"
          dataSource={feeds ?? []}
          pagination={false}
          columns={[
            { title: "名称", dataIndex: "name", width: 180, render: (v: string) => <Typography.Text code>{v}</Typography.Text> },
            { title: "说明", dataIndex: "description", ellipsis: true },
            {
              title: "模式",
              dataIndex: "per_symbol",
              width: 100,
              render: (v: boolean) => (v ? <Tag color="blue">按标的</Tag> : <Tag>批量</Tag>),
            },
          ]}
          locale={{ emptyText: "暂无数据源" }}
        />
      </Card>
    </PageContainer>
  );
}
