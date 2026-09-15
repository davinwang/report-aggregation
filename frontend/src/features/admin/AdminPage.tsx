// 管理设置 — 运行配置 / 调度 / universe / 数据源 (no login; runs as admin).
// Route: /admin
import { useState } from "react";
import { Button, Card, Col, Descriptions, Row, Select, Space, Table, Tag, Typography } from "antd";
import { useMutation, useQuery } from "@tanstack/react-query";
import { PlayCircleOutlined } from "@ant-design/icons";
import { adminTriggerIngest, getAdminConfig, getOpsFeeds } from "@/api";
import PageContainer from "@/components/PageContainer";
import { msg } from "@/utils/message";

export default function AdminPage() {
  const [universe, setUniverse] = useState<string | undefined>(undefined);

  const { data: cfg, isFetching: cFetching } = useQuery({
    queryKey: ["admin", "config"],
    queryFn: getAdminConfig,
    staleTime: 60_000,
  });
  const { data: feeds, isFetching: fFetching } = useQuery({
    queryKey: ["ops", "feeds"],
    queryFn: getOpsFeeds,
    staleTime: 300_000,
  });

  const trigger = useMutation({
    mutationFn: (scope: string) => adminTriggerIngest(scope, universe),
    onSuccess: (_d, scope) => msg.success(`已调度 ${scope} 采集（universe=${universe ?? cfg?.universe ?? "默认"}）`),
    onError: () => msg.error("触发失败，请查看后端日志"),
  });

  const sched = cfg?.scheduler;

  return (
    <PageContainer
      title="管理设置"
      description="运行配置 · 调度状态 · universe — 配置项由环境变量驱动（修改后需重启服务）"
      extra={
        <Space wrap>
          <Select
            size="small"
            allowClear
            placeholder={`universe (默认 ${cfg?.universe ?? "hs300"})`}
            value={universe}
            onChange={(v) => setUniverse(v ?? undefined)}
            style={{ width: 180 }}
            options={(cfg?.universes ?? ["hs300", "zz500", "zz1000", "sz50"]).map((u) => ({ value: u, label: u }))}
          />
          <Button
            size="small"
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={trigger.isPending}
            onClick={() => trigger.mutate("all")}
          >
            全量采集
          </Button>
          <Button size="small" loading={trigger.isPending} onClick={() => trigger.mutate("bulk")}>
            仅批量源
          </Button>
          <Button size="small" loading={trigger.isPending} onClick={() => trigger.mutate("per_symbol")}>
            仅按标的
          </Button>
        </Space>
      }
    >
      <Row gutter={12} style={{ marginBottom: 12 }}>
        <Col xs={24} xl={12}>
          <Card size="small" title="运行配置" loading={cFetching && !cfg} style={{ height: "100%" }}>
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="应用">{cfg?.app ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="环境">
                <Tag color={cfg?.env === "production" ? "red" : "blue"}>{cfg?.env ?? "-"}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="默认 universe">{cfg?.universe ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="登录鉴权">
                {cfg?.auth_enabled ? <Tag color="warning">启用</Tag> : <Tag>已关闭（固定管理员）</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label="AI 功能 (FEATURE_AI)">
                {cfg?.feature_ai ? <Tag color="green">启用</Tag> : <Tag>关闭（Phase 3 后置）</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label="AkShare 参数">
                超时 {cfg?.akshare.timeout ?? "-"}s · 重试 {cfg?.akshare.max_retries ?? "-"} · 限速{" "}
                {cfg?.akshare.throttle_seconds ?? "-"}s
              </Descriptions.Item>
              <Descriptions.Item label="数据库">
                <Typography.Text code style={{ fontSize: 12 }}>
                  {cfg?.database.url ?? "-"}
                </Typography.Text>
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card size="small" title="调度器 (APScheduler)" loading={cFetching && !cfg} style={{ height: "100%" }}>
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="状态">
                {sched?.running ? <Tag color="success">运行中</Tag> : <Tag>未运行</Tag>}
                {sched && !sched.enabled && <Tag style={{ marginLeft: 6 }}>配置已禁用</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label="夜间任务 (cron)">
                <Typography.Text code>{sched?.cron ?? "-"}</Typography.Text>
                <span className="muted" style={{ marginLeft: 8 }}>（时区 {sched?.timezone ?? "-"}，A股收盘后）</span>
              </Descriptions.Item>
              <Descriptions.Item label="下次运行">
                {sched?.next_run_at ? sched.next_run_at.replace("T", " ").slice(0, 19) : "-"}
              </Descriptions.Item>
              <Descriptions.Item label="执行范围">
                全量 pipeline = 批量源（快照/指数/评级/池/资金）+ 按标的源（K线/研报/财报）
              </Descriptions.Item>
            </Descriptions>
            <Typography.Paragraph className="muted" style={{ margin: "10px 0 0", fontSize: 12 }}>
              提示：手动触发的任务在后台线程执行，进度通过 SSE（右上角“实时”）推送；同一时刻请避免多个写库任务并行
              （SQLite 单写者约束）。
            </Typography.Paragraph>
          </Card>
        </Col>
      </Row>

      <Card size="small" title="数据源注册表 (REGISTRY)">
        <Table
          size="small"
          rowKey="name"
          loading={fFetching}
          dataSource={feeds ?? []}
          pagination={false}
          columns={[
            { title: "名称", dataIndex: "name", width: 190, render: (v: string) => <Typography.Text code>{v}</Typography.Text> },
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
