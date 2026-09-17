// 评级胜率 — 机构/分析师评级命中率与净技能值 (20/60交易日 vs 沪深300).
// Route: /accuracy
import { useState } from "react";
import { Button, Card, Col, Row, Segmented, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SyncOutlined } from "@ant-design/icons";
import { getAccuracyLeaderboard, refreshAccuracy } from "@/api";
import type { AccuracyRow } from "@/types";
import PageContainer from "@/components/PageContainer";
import RankingBar from "@/components/RankingBar";
import StatCard from "@/components/StatCard";
import { msg } from "@/utils/message";
import { changeColor } from "@/styles/theme";

const pct = (v: number | null | undefined, digits = 1) =>
  v == null ? "-" : `${(v * 100).toFixed(digits)}%`;

export default function AccuracyPage() {
  const queryClient = useQueryClient();
  const [horizon, setHorizon] = useState(20);
  const [by, setBy] = useState<"org" | "analyst">("org");
  const [minEvents, setMinEvents] = useState(5);

  const { data, isFetching, isError } = useQuery({
    queryKey: ["accuracy", "leaderboard", horizon, by, minEvents],
    queryFn: () => getAccuracyLeaderboard({ horizon, by, min_events: minEvents }),
    staleTime: 60_000,
  });

  const refresh = useMutation({
    mutationFn: () => refreshAccuracy(180),
    onSuccess: () => {
      msg.success("准确率快照已重算（20/60日 × 机构/分析师）");
      queryClient.invalidateQueries({ queryKey: ["accuracy"] });
    },
    onError: () => msg.error("重算失败，请查看后端日志"),
  });

  const rows = data?.rows ?? [];
  const summary = data?.summary ?? {};
  const subjectLabel = by === "org" ? "机构" : "分析师";

  const columns: ColumnsType<AccuracyRow> = [
    {
      title: "排名",
      dataIndex: "rank",
      width: 64,
      render: (v: number) => (v <= 3 ? <Tag color={["gold", "silver", "#cd7f32"][v - 1]}>{v}</Tag> : v),
    },
    { title: subjectLabel, dataIndex: "subject", render: (v: string) => <Typography.Text strong>{v}</Typography.Text> },
    {
      title: "命中/总数",
      key: "sample",
      width: 110,
      align: "right",
      render: (_, r) => (
        <span style={{ fontVariantNumeric: "tabular-nums" }}>
          {r.hits} / {r.total}
        </span>
      ),
    },
    {
      title: "命中率",
      dataIndex: "hit_rate",
      width: 96,
      align: "right",
      sorter: (a, b) => (a.hit_rate ?? 0) - (b.hit_rate ?? 0),
      render: (v: number | null) => <span style={{ fontVariantNumeric: "tabular-nums" }}>{pct(v)}</span>,
    },
    {
      title: "净技能值",
      dataIndex: "net_skill",
      width: 110,
      align: "right",
      sorter: (a, b) => (a.net_skill ?? 0) - (b.net_skill ?? 0),
      render: (v: number | null) => (
        <span style={{ color: changeColor(v), fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
          {v == null ? "-" : pct(v)}
        </span>
      ),
    },
    {
      title: "环比",
      dataIndex: "prev_delta",
      width: 90,
      align: "right",
      render: (v: number | null) =>
        v == null ? (
          <span className="muted">-</span>
        ) : (
          <span style={{ color: changeColor(v) }}>
            {v > 0 ? "↑" : v < 0 ? "↓" : "→"} {pct(Math.abs(v))}
          </span>
        ),
    },
  ];

  return (
    <PageContainer
      title="评级胜率"
      description={`评级命中率与净技能值 — 未来 ${horizon} 个交易日相对沪深300的超额方向判断`}
      extra={
        <Space wrap>
          {data?.ref && <Tag bordered={false}>截至 {data.ref}</Tag>}
          <Button
            size="small"
            icon={<SyncOutlined />}
            loading={refresh.isPending}
            onClick={() => refresh.mutate()}
          >
            重算快照
          </Button>
        </Space>
      }
    >
      <div className="grid-cards" style={{ marginBottom: 12 }}>
        <StatCard title={`覆盖${subjectLabel}数`} value={summary.subjects ?? 0} footer={`样本≥${minEvents}次`} loading={isFetching && !data} />
        <StatCard title="评估事件数" value={summary.events ?? 0} footer={`近180日评级 · 前${horizon}日验证`} loading={isFetching && !data} />
        <StatCard title="总命中率" value={pct(summary.hit_rate)} footer={`${summary.hits ?? 0} 次命中`} loading={isFetching && !data} />
        <StatCard
          title="净技能值"
          value={
            <span style={{ color: changeColor(summary.net_skill ?? null) }}>{pct(summary.net_skill)}</span>
          }
          footer="命中率 − 未命中率"
          loading={isFetching && !data}
        />
      </div>

      <Row gutter={12} style={{ marginBottom: 12 }}>
        <Col xs={24} xl={10}>
          <Card
            size="small"
            title={`净技能值 Top10 (前${horizon}日)`}
            extra={
              <Segmented
                size="small"
                value={horizon}
                onChange={(v) => setHorizon(Number(v))}
                options={[
                  { value: 20, label: "20日" },
                  { value: 60, label: "60日" },
                ]}
              />
            }
          >
            {rows.length ? (
              <RankingBar
                items={rows.slice(0, 10).map((r) => ({ name: r.subject, value: Number((100 * (r.net_skill ?? 0)).toFixed(1)) }))}
                colorBySign
                unit="%"
                height={300}
              />
            ) : (
              <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
                暂无准确率快照。请先采集 <Typography.Text code>price_history</Typography.Text>（个股日线）与
                <Typography.Text code>research_reports</Typography.Text>，再点击“重算快照”。
              </Typography.Paragraph>
            )}
          </Card>
        </Col>
        <Col xs={24} xl={14}>
          <Card
            size="small"
            title={`${subjectLabel}排行榜`}
            extra={
              <Space wrap>
                <Segmented
                  size="small"
                  value={by}
                  onChange={(v) => setBy(v as "org" | "analyst")}
                  options={[
                    { value: "org", label: "按机构" },
                    { value: "analyst", label: "按分析师" },
                  ]}
                />
                <Select
                  size="small"
                  value={minEvents}
                  onChange={setMinEvents}
                  style={{ width: 120 }}
                  options={[
                    { value: 1, label: "样本≥1" },
                    { value: 5, label: "样本≥5" },
                    { value: 10, label: "样本≥10" },
                    { value: 20, label: "样本≥20" },
                  ]}
                />
              </Space>
            }
          >
            <Table
              size="small"
              rowKey="subject"
              loading={isFetching}
              dataSource={isError ? [] : rows}
              columns={columns}
              locale={{ emptyText: "暂无数据，请确认行情与研报已完成采集" }}
              pagination={{ pageSize: 15, size: "small", showSizeChanger: false }}
            />
          </Card>
        </Col>
      </Row>

      <Card size="small" title="评估口径说明">
        <Typography.Paragraph className="muted" style={{ marginBottom: 6 }}>
          <b>样本</b>：近 180 日机构评级（同一机构对同一股票的多次评级只取最早一次）。
        </Typography.Paragraph>
        <Typography.Paragraph className="muted" style={{ marginBottom: 6 }}>
          <b>命中</b>：买入/增持 → 个股（前复权）未来 {horizon} 个交易日收益 <i>跑赢</i> 沪深300；
          减持/卖出 → <i>跑输</i>。中性/未评级不计入。
        </Typography.Paragraph>
        <Typography.Paragraph className="muted" style={{ marginBottom: 0 }}>
          <b>净技能值</b> = 命中率 − (1 − 命中率)，&gt;0 表示具备正向选择能力；环比为相对上一次快照的变化。
        </Typography.Paragraph>
      </Card>
    </PageContainer>
  );
}
