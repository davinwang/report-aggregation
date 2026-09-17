// 平台总览 — site map + system status board (analog of the reference /overview).
import { Badge, Card, Col, Row, Space, Table, Tag, Typography } from "antd";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getHealthDeep } from "@/api";
import PageContainer from "@/components/PageContainer";
import { relTime } from "@/hooks/useRelativeTime";

const MODULES: { group: string; items: { to: string; label: string; phase: number }[] }[] = [
  {
    group: "首页",
    items: [{ to: "/overview", label: "平台总览", phase: 1 }],
  },
  {
    group: "数据看板",
    items: [
      { to: "/market", label: "市场看板", phase: 1 },
      { to: "/news", label: "资讯舆情", phase: 2 },
    ],
  },
  {
    group: "研报中心",
    items: [
      { to: "/research", label: "研报库", phase: 1 },
      { to: "/signals", label: "评级信号", phase: 2 },
      { to: "/accuracy", label: "评级胜率", phase: 2 },
      { to: "/weekly", label: "周统计", phase: 2 },
    ],
  },
  {
    group: "行情与技术",
    items: [
      { to: "/technical", label: "技术指标", phase: 1 },
      { to: "/market-overview", label: "全市场速览", phase: 2 },
    ],
  },
  {
    group: "衍生品",
    items: [
      { to: "/basis", label: "股指期货基差", phase: 2 },
      { to: "/options", label: "股指期权", phase: 2 },
    ],
  },
  {
    group: "财务与资金",
    items: [
      { to: "/financials", label: "财务数据", phase: 1 },
      { to: "/flow", label: "资金流向", phase: 2 },
      { to: "/linkage", label: "板块联动", phase: 2 },
    ],
  },
  {
    group: "工具",
    items: [
      { to: "/chat", label: "AI助手", phase: 3 },
      { to: "/admin", label: "管理设置", phase: 3 },
    ],
  },
];

const PHASE_COLOR: Record<number, string> = { 1: "green", 2: "blue", 3: "purple" };

export default function OverviewPage() {
  const { data } = useQuery({ queryKey: ["health", "deep"], queryFn: getHealthDeep, refetchInterval: 30_000 });
  const counts = (data?.checks?.database?.counts ?? {}) as Record<string, number>;
  const freshness = Object.entries(data?.freshness ?? {});

  return (
    <PageContainer
      title="平台总览"
      description="站点地图 + 系统运行状态"
      extra={
        <Space>
          <Badge status={data?.status === "ok" ? "success" : data?.status === "degraded" ? "warning" : "error"} />
          <span>{data?.status ?? "unknown"}</span>
          <Tag>v0.1 · React + FastAPI</Tag>
        </Space>
      }
    >
      <Row gutter={12}>
        <Col xs={24} lg={14}>
          {MODULES.map((g) => (
            <Card key={g.group} size="small" title={g.group} style={{ marginBottom: 12 }}>
              <Space wrap size={[8, 8]}>
                {g.items.map((it) => (
                  <Link key={it.to} to={it.to}>
                    <Tag color={PHASE_COLOR[it.phase]} style={{ cursor: "pointer", padding: "4px 10px", fontSize: 13 }}>
                      {it.label} · P{it.phase}
                    </Tag>
                  </Link>
                ))}
              </Space>
            </Card>
          ))}
        </Col>

        <Col xs={24} lg={10}>
          <Card size="small" title="数据规模" style={{ marginBottom: 12 }}>
            <Table
              size="small"
              pagination={false}
              rowKey="k"
              dataSource={Object.entries(counts).map(([k, v]) => ({ k, v }))}
              columns={[
                { title: "表", dataIndex: "k" },
                { title: "行数", dataIndex: "v", align: "right", render: (v: number) => (v ?? 0).toLocaleString() },
              ]}
            />
          </Card>

          <Card size="small" title="数据新鲜度" style={{ marginBottom: 12 }}>
            <Table
              size="small"
              pagination={false}
              rowKey="feed"
              dataSource={freshness.map(([feed, f]) => ({
                feed,
                latest_data_date: f.latest_data_date,
                last_success_at: f.last_success_at,
                weeks_behind: f.weeks_behind,
              }))}
              columns={[
                { title: "数据源", dataIndex: "feed" },
                { title: "数据日期", dataIndex: "latest_data_date", render: (v) => (v as string) || "-" },
                { title: "更新", dataIndex: "last_success_at", render: (v) => relTime(v as string) },
                { title: "落后(周)", dataIndex: "weeks_behind", align: "right", render: (v) => (v as number) ?? "-" },
              ]}
            />
          </Card>

          <Card size="small" title="运行环境">
            <Typography.Paragraph style={{ marginBottom: 4 }}>
              环境: <Tag>{data?.env}</Tag> Universe: <Tag>{data?.universe}</Tag>
            </Typography.Paragraph>
            <Typography.Paragraph className="muted" style={{ marginBottom: 0 }}>
              调度: {String((data?.checks?.scheduler as Record<string, unknown>)?.cron ?? "-")} · AkShare:{" "}
              {String((data?.checks?.dependencies as Record<string, unknown>)?.akshare ?? "未安装")}
            </Typography.Paragraph>
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
