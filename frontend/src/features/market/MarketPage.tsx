// 市场看板 (default home) — indices, sector heatmap, rating summary, top rating moves,
// and the latest research reports for the selected period/sector.
import { Alert, Card, Col, Empty, List, Row, Space, Statistic, Tag } from "antd";
import { useQuery } from "@tanstack/react-query";
import { getDashboard } from "@/api";
import { useUIStore } from "@/stores/uiStore";
import PageContainer from "@/components/PageContainer";
import StatCard from "@/components/StatCard";
import ChangeText from "@/components/ChangeText";
import HeatmapChart from "@/components/HeatmapChart";
import ReportTable from "@/components/ReportTable";
import FreshnessBadge from "@/components/FreshnessBadge";
import ProvenanceTag from "@/components/ProvenanceTag";
import PageRefresh from "@/components/PageRefresh";
import { fmtAmount } from "@/hooks/useRelativeTime";
import type { SignalItem } from "@/types";
import { Link } from "react-router-dom";

export default function MarketPage() {
  const period = useUIStore((s) => s.period);
  const sector = useUIStore((s) => s.sector);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["market", "dashboard", period, sector],
    queryFn: () => getDashboard({ period, sector }),
    staleTime: 30_000,
    retry: 1,
  });

  const isEmpty =
    !data || (data.indices.length === 0 && data.latestReports.length === 0 && data.sectorHeatmap.length === 0);

  return (
    <PageContainer
      title="市场看板"
      description={data ? `${data.window.label} · ${data.window.start} ~ ${data.window.end}` : "加载中…"}
      extra={
        <Space>
          {data && <FreshnessBadge feed="行情" freshness={data.freshness?.["spot_snapshot"]} />}
          <ProvenanceTag source="em" date={data?.latestTradeDate} />
          <PageRefresh queryKeys={[["market"]]} feeds={["index_daily", "industry_boards"]} />
        </Space>
      }
    >
      {isError && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 12 }}
          message="无法连接后端"
          description="请确认后端已启动 (uvicorn app.main:app --port 8000)，且已完成一次数据采集。"
        />
      )}

      {isEmpty && !isLoading && !isError && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="暂无数据 — 请先运行数据采集"
          description={
            <div>
              在 <code>backend/</code> 下执行：
              <br />
              <code>python -m app.ingestion.pipeline --feed security_master</code>
              <br />
              <code>python -m app.ingestion.pipeline --all --universe hs300</code>
              <br />
              采集完成后刷新本页即可看到指数、行业热力、评级与研报数据。
            </div>
          }
        />
      )}

      {/* 指数行情 */}
      <div className="grid-cards" style={{ marginBottom: 12 }}>
        {(data?.indices ?? []).map((idx) => (
          <StatCard
            key={idx.code}
            title={idx.name}
            value={idx.close?.toFixed(2) ?? "-"}
            change={idx.change_pct}
            footer={idx.trade_date}
            loading={isLoading}
          />
        ))}
      </div>

      <Row gutter={12}>
        <Col xs={24} lg={14}>
          <Card
            size="small"
            title="行业热力图"
            style={{ marginBottom: 12 }}
            extra={<span className="muted">红涨绿跌</span>}
          >
            {data?.sectorHeatmap?.length ? (
              <HeatmapChart
                items={data.sectorHeatmap.map((s) => ({ name: s.name, value: s.change_pct, group: s.group }))}
                height={420}
              />
            ) : (
              <Empty description="暂无行业数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>

          <Card size="small" title="最新研报" style={{ marginBottom: 12 }}>
            <ReportTable rows={data?.latestReports ?? []} loading={isLoading} scrollY={320} />
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card size="small" title="评级分布" style={{ marginBottom: 12 }}>
            <Row gutter={8}>
              <Col span={12}>
                <Statistic title="本期评级数" value={data?.ratingSummary?.total ?? 0} />
              </Col>
              <Col span={12}>
                <Statistic title="覆盖机构" value={data?.ratingSummary?.orgs ?? 0} />
              </Col>
            </Row>
            <div style={{ marginTop: 12 }}>
              <Space wrap>
                {Object.entries(data?.ratingSummary?.by_rating ?? {}).map(([k, v]) => (
                  <Tag key={k} color="blue">
                    {k}: {v}
                  </Tag>
                ))}
              </Space>
            </div>
          </Card>

          <Card size="small" title="评级异动" style={{ marginBottom: 12 }}>
            {(() => {
              const items: (SignalItem & { up: boolean })[] = [
                ...(data?.topUpgrades ?? []).map((s) => ({ ...s, up: true })),
                ...(data?.topDowngrades ?? []).map((s) => ({ ...s, up: false })),
              ].slice(0, 12);
              if (!items.length)
                return <Empty description="暂无评级异动" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
              return (
                <List
                  size="small"
                  dataSource={items}
                  renderItem={(s) => (
                    <List.Item style={{ padding: "6px 0" }}>
                      <Space size={6} wrap>
                        <Tag color={s.up ? "red" : "green"} style={{ marginInlineEnd: 0 }}>
                          {s.up ? "上调" : "下调"}
                        </Tag>
                        <Link to={`/stock/${s.code}`}>{s.name ?? s.code}</Link>
                        {s.strength && <Tag bordered={false}>{s.strength}</Tag>}
                        <span className="muted">{s.reason}</span>
                      </Space>
                    </List.Item>
                  )}
                />
              );
            })()}
          </Card>

          <Card size="small" title="资金/成交概览">
            <Space direction="vertical" size={4} style={{ width: "100%" }}>
              {(data?.indices ?? []).slice(0, 4).map((idx) => (
                <div key={idx.code} style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>{idx.name}</span>
                  <Space>
                    <span className="muted">成交 {fmtAmount(idx.volume)}</span>
                    <ChangeText value={idx.change_pct} />
                  </Space>
                </div>
              ))}
            </Space>
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
