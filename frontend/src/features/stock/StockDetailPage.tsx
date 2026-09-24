// 个股详情 — aggregate view: quote, financial snapshot, recent research, ratings, K-line.
// Route: /stock/:code
import { useMemo } from "react";
import { Button, Card, Col, Descriptions, Row, Space, Table, Tag, Typography } from "antd";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getSeries, getStockDetail, getStockFlow } from "@/api";
import type { StockFlowRow } from "@/types";
import PageContainer from "@/components/PageContainer";
import StatCard from "@/components/StatCard";
import ReportTable from "@/components/ReportTable";
import KLineChart from "@/components/KLineChart";
import ProvenanceTag from "@/components/ProvenanceTag";
import PageRefresh from "@/components/PageRefresh";
import { fmtAmount, fmtDate, fmtNum, fmtPct } from "@/hooks/useRelativeTime";
import { DOWN_COLOR, UP_COLOR } from "@/styles/theme";

export default function StockDetailPage() {
  const { code = "" } = useParams();
  const detail = useQuery({ queryKey: ["stock", code], queryFn: () => getStockDetail(code), enabled: !!code });
  const series = useQuery({
    queryKey: ["quant", "series", code, "6m"],
    queryFn: () => getSeries({ code, indicators: "ma,boll,macd", period: "6m" }),
    enabled: !!code,
    staleTime: 30_000,
  });
  const flow = useQuery({
    queryKey: ["stock", "flow", code],
    queryFn: () => getStockFlow(code, 30),
    enabled: !!code,
    staleTime: 60_000,
  });

  const d = detail.data;
  const q = d?.quote;
  const f = d?.financials;

  // Aggregate per-report earnings forecasts into one EPS/PE row per year (mean of reports that carry it).
  const forecastRows = useMemo(() => {
    const acc: Record<string, { eps: number[]; pe: number[] }> = {};
    for (const r of d?.reports ?? []) {
      for (const [year, v] of Object.entries(r.forecast_json ?? {})) {
        const slot = (acc[year] ??= { eps: [], pe: [] });
        if (v?.eps != null) slot.eps.push(v.eps);
        if (v?.pe != null) slot.pe.push(v.pe);
      }
    }
    const avg = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
    return Object.keys(acc)
      .sort()
      .map((year) => ({
        year,
        eps: avg(acc[year].eps),
        pe: avg(acc[year].pe),
        reports: acc[year].eps.length,
      }));
  }, [d?.reports]);

  return (
    <PageContainer
      title={
        d ? (
          <Space>
            {d.security.name}
            <Typography.Text type="secondary">{d.security.code}</Typography.Text>
            {d.security.industry_sw && <Tag>{d.security.industry_sw}</Tag>}
            {d.security.industry_group && <Tag color="blue">{d.security.industry_group}</Tag>}
          </Space>
        ) : (
          "个股详情"
        )
      }
      description={q?.trade_date ? `行情日期 ${q.trade_date}` : undefined}
      extra={
        <Space>
          <ProvenanceTag source="em" />
          <PageRefresh queryKeys={[["quant", "series"], ["stock"]]} feeds={["price_history", "financials_em", "fin_indicators", "research_reports", "stock_flow"]} />
          <Link to={`/technical/${code}`}><Button size="small">技术指标</Button></Link>
          <Link to={`/financials/${code}`}><Button size="small">财务数据</Button></Link>
        </Space>
      }
    >
      {detail.isError && (
        <Card size="small">
          <Typography.Text type="danger">未找到该证券或后端不可用（{code}）。</Typography.Text>
        </Card>
      )}

      <div className="grid-cards" style={{ marginBottom: 12 }}>
        <StatCard title="最新价" value={q?.close?.toFixed(2) ?? "-"} change={q?.change_pct} loading={detail.isLoading} />
        <StatCard title="成交额" value={fmtAmount(q?.amount)} loading={detail.isLoading} />
        <StatCard title="换手率" value={q?.turnover_rate != null ? `${fmtNum(q.turnover_rate)}%` : "-"} loading={detail.isLoading} />
        <StatCard title="ROE" value={f?.roe != null ? `${fmtNum(f.roe)}%` : "-"} loading={detail.isLoading} />
        <StatCard title="净利润同比" value={f?.net_profit_yoy != null ? fmtPct(f.net_profit_yoy) : "-"} loading={detail.isLoading} />
      </div>

      <Row gutter={12}>
        <Col xs={24} lg={14}>
          <Card size="small" title="走势 (前复权)" style={{ marginBottom: 12 }} loading={series.isFetching && !series.data}>
            {series.data && series.data.dates.length > 0 ? (
              <KLineChart series={series.data} sub="macd" height={420} />
            ) : (
              <Typography.Text type="secondary">暂无行情数据（请运行 price_history 采集）。</Typography.Text>
            )}
          </Card>

          <Card size="small" title={`最新研报 (${d?.report_total ?? 0})`}>
            <ReportTable rows={d?.reports ?? []} loading={detail.isLoading} showCode={false} scrollY={320} />
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card size="small" title="公司概况" style={{ marginBottom: 12 }}>
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="代码">{d?.security.code ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="交易所">{d?.security.exchange || "-"}</Descriptions.Item>
              <Descriptions.Item label="行业">{d?.security.industry_sw || "-"}</Descriptions.Item>
              <Descriptions.Item label="板块">{d?.security.industry_group || "-"}</Descriptions.Item>
              <Descriptions.Item label="EPS">{f?.eps != null ? fmtNum(f.eps) : "-"}</Descriptions.Item>
              <Descriptions.Item label="毛利率">{f?.gross_margin != null ? `${fmtNum(f.gross_margin)}%` : "-"}</Descriptions.Item>
              <Descriptions.Item label="资产负债率">{f?.debt_ratio != null ? `${fmtNum(f.debt_ratio)}%` : "-"}</Descriptions.Item>
            </Descriptions>
          </Card>

          <Card size="small" title="盈利预测 (研报均值)" style={{ marginBottom: 12 }}>
            {forecastRows.length ? (
              <Table
                size="small"
                rowKey="year"
                pagination={false}
                dataSource={forecastRows}
                columns={[
                  { title: "年度", dataIndex: "year", width: 80, render: (v: string) => `${v}E` },
                  {
                    title: "EPS (元)",
                    dataIndex: "eps",
                    align: "right",
                    render: (v: number | null) => fmtNum(v),
                  },
                  { title: "PE (倍)", dataIndex: "pe", align: "right", render: (v: number | null) => fmtNum(v) },
                  {
                    title: "样本",
                    dataIndex: "reports",
                    align: "right",
                    width: 64,
                    render: (v: number) => (
                      <Typography.Text type="secondary">{v} 篇</Typography.Text>
                    ),
                  },
                ]}
              />
            ) : (
              <Typography.Text type="secondary">
                暂无盈利预测（请运行 research_reports 采集；仅展示研报库前 10 篇的均值）。
              </Typography.Text>
            )}
          </Card>

          <Card size="small" title="资金流向 (近30日)" style={{ marginBottom: 12 }}>
            {flow.data && flow.data.length ? (
              <Table
                size="small"
                rowKey="trade_date"
                pagination={false}
                scroll={{ y: 240 }}
                dataSource={flow.data as StockFlowRow[]}
                columns={[
                  { title: "日期", dataIndex: "trade_date", width: 100 },
                  {
                    title: "主力净流入",
                    dataIndex: "main_net_inflow",
                    align: "right",
                    width: 110,
                    render: (v: number | null) => {
                      if (v == null) return "-";
                      const color = v >= 0 ? UP_COLOR : DOWN_COLOR;
                      return <span style={{ color }}>{fmtAmount(v)}</span>;
                    },
                  },
                  {
                    title: "占比",
                    dataIndex: "main_net_inflow_pct",
                    align: "right",
                    width: 76,
                    render: (v: number | null) => (v != null ? `${fmtNum(v)}%` : "-"),
                  },
                  {
                    title: "超大单",
                    dataIndex: "super_large_net",
                    align: "right",
                    width: 96,
                    render: (v: number | null) => (v != null ? fmtAmount(v) : "-"),
                  },
                ]}
              />
            ) : (
              <Typography.Text type="secondary">
                {flow.isFetching ? "加载中…" : "暂无资金流数据（请运行 stock_flow 采集）。"}
              </Typography.Text>
            )}
          </Card>

          <Card size="small" title="近期评级">
            <Table
              size="small"
              rowKey={(r) => `${r.trade_date}-${r.org}-${r.analyst}`}
              loading={detail.isLoading}
              pagination={{ pageSize: 8 }}
              dataSource={d?.ratings ?? []}
              columns={[
                { title: "日期", dataIndex: "trade_date", width: 100, render: (v: string) => fmtDate(v) },
                { title: "机构", dataIndex: "org", ellipsis: true },
                { title: "评级", dataIndex: "rating", width: 76, render: (v: string) => (v ? <Tag color="red">{v}</Tag> : "-") },
                { title: "变动", dataIndex: "rating_change", width: 64 },
                {
                  title: "目标价", width: 110,
                  render: (_: unknown, r) =>
                    r.target_low != null || r.target_high != null
                      ? `${r.target_low ?? ""}${r.target_high != null && r.target_high !== r.target_low ? `~${r.target_high}` : ""}`
                      : "-",
                },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
