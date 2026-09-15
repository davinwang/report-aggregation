// 股指期货基差 — IF/IH/IC/IM term structure + front-month basis trend.
// The stock analog of the reference platform's 期限结构 (Back/Contango → 升水/贴水).
// Route: /basis
import { useState } from "react";
import { Card, Col, Row, Segmented, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useQuery } from "@tanstack/react-query";
import { getFuturesBasis } from "@/api";
import type { BasisContract, BasisOverviewRow } from "@/types";
import PageContainer from "@/components/PageContainer";
import LineChart from "@/components/LineChart";
import ProvenanceTag from "@/components/ProvenanceTag";
import StatCard from "@/components/StatCard";
import { fmtNum } from "@/hooks/useRelativeTime";
import { changeColor } from "@/styles/theme";

const DAY_OPTIONS = [
  { value: 20, label: "近1月" },
  { value: 60, label: "近3月" },
  { value: 120, label: "近半年" },
  { value: 250, label: "近1年" },
];

function stateTag(state: string | null) {
  if (!state) return <Tag>-</Tag>;
  const color = state === "升水" ? "red" : state === "贴水" ? "green" : "default";
  return <Tag color={color}>{state}</Tag>;
}

export default function BasisPage() {
  const [variety, setVariety] = useState("IF");
  const [days, setDays] = useState(60);

  const { data, isFetching, isError } = useQuery({
    queryKey: ["derivatives", "basis", variety, days],
    queryFn: () => getFuturesBasis({ variety, days }),
    staleTime: 60_000,
  });

  const ts = data?.termStructure;
  const hist = data?.history;
  const main = data?.overview.find((o) => o.variety === variety) ?? null;
  const empty = !isFetching && (isError || !ts?.contracts?.length);

  const columns: ColumnsType<BasisContract> = [
    { title: "合约", dataIndex: "symbol", width: 90, render: (v: string) => <Typography.Text strong>{v}</Typography.Text> },
    { title: "到期日", dataIndex: "expiry", width: 110 },
    { title: "剩余天数", dataIndex: "days_to_expiry", width: 90, align: "right" },
    { title: "收盘", dataIndex: "close", align: "right", render: (v: number | null) => fmtNum(v, 1) },
    { title: "结算价", dataIndex: "settle", align: "right", render: (v: number | null) => fmtNum(v, 1) },
    {
      title: "基差",
      dataIndex: "basis",
      align: "right",
      render: (v: number | null) => <span style={{ color: changeColor(v), fontVariantNumeric: "tabular-nums" }}>{fmtNum(v, 1)}</span>,
    },
    {
      title: "年化基差率",
      dataIndex: "basis_annualized",
      align: "right",
      render: (v: number | null) => (
        <span style={{ color: changeColor(v), fontVariantNumeric: "tabular-nums" }}>
          {v == null ? "-" : `${fmtNum(v, 2)}%`}
        </span>
      ),
    },
    { title: "成交量", dataIndex: "volume", align: "right", render: (v: number | null) => fmtNum(v, 0) },
    { title: "持仓量", dataIndex: "oi", align: "right", render: (v: number | null) => fmtNum(v, 0) },
  ];

  const overviewColumns: ColumnsType<BasisOverviewRow> = [
    { title: "品种", dataIndex: "variety", width: 70, render: (v: string) => <Typography.Text strong>{v}</Typography.Text> },
    { title: "标的指数", dataIndex: "underlying_name", width: 100 },
    { title: "主力合约", dataIndex: "symbol", width: 90 },
    { title: "现货", dataIndex: "spot", align: "right", render: (v: number | null) => fmtNum(v, 1) },
    {
      title: "基差",
      dataIndex: "basis",
      align: "right",
      render: (v: number | null) => <span style={{ color: changeColor(v) }}>{fmtNum(v, 1)}</span>,
    },
    {
      title: "年化基差率",
      dataIndex: "basis_annualized",
      align: "right",
      render: (v: number | null) => <span style={{ color: changeColor(v) }}>{v == null ? "-" : `${fmtNum(v, 2)}%`}</span>,
    },
    { title: "状态", dataIndex: "state", width: 70, render: (v: string | null) => stateTag(v) },
  ];

  return (
    <PageContainer
      title="股指期货基差"
      description="IF / IH / IC / IM 期现基差与年化基差率（升贴水），基差 = 期货结算价 − 标的指数收盘"
      extra={<ProvenanceTag source="exchange" date={ts?.trade_date} />}
    >
      <div className="grid-cards" style={{ marginBottom: 12 }}>
        <StatCard title={`${variety} 主力合约`} value={main?.symbol ?? "-"} footer={main?.underlying_name} loading={isFetching && !data} />
        <StatCard
          title="主力基差"
          value={fmtNum(main?.basis ?? null, 1)}
          change={null}
          footer={stateTag(main?.state ?? null)}
          loading={isFetching && !data}
        />
        <StatCard
          title="年化基差率"
          value={main?.basis_annualized == null ? "-" : `${fmtNum(main.basis_annualized, 2)}%`}
          footer={`剩余 ${main?.days_to_expiry ?? "-"} 天`}
          loading={isFetching && !data}
        />
        <StatCard title="标的指数收盘" value={fmtNum(ts?.spot ?? null, 2)} footer={ts?.trade_date ?? "-"} loading={isFetching && !data} />
      </div>

      <Card
        size="small"
        style={{ marginBottom: 12 }}
        title="基差走势（主力合约）"
        extra={
          <Space>
            <Segmented
              options={(data?.varieties ?? ["IF", "IH", "IC", "IM"]).map((v) => ({ value: v, label: v }))}
              value={variety}
              onChange={(v) => setVariety(String(v))}
            />
            <Select value={days} onChange={(v) => setDays(Number(v))} options={DAY_OPTIONS} style={{ width: 100 }} size="small" />
          </Space>
        }
      >
        {empty ? (
          <Typography.Paragraph type="secondary">
            暂无股指期货数据。请运行 <Typography.Text code>index_futures</Typography.Text> 采集
            （需先完成 <Typography.Text code>index_daily</Typography.Text> 以提供现货指数收盘价）。
          </Typography.Paragraph>
        ) : hist && hist.dates.length > 0 ? (
          <LineChart
            dates={hist.dates}
            series={[
              { name: "基差", data: hist.basis, area: true },
              { name: "年化基差率(%)", data: hist.basis_annualized, yAxisIndex: 1 },
            ]}
            yAxisNames={["基差", "%"]}
            zoom
            height={340}
          />
        ) : (
          <Typography.Paragraph type="secondary">该品种暂无基差历史。</Typography.Paragraph>
        )}
      </Card>

      <Row gutter={12}>
        <Col xs={24} xl={13}>
          <Card size="small" title={`${variety} 期限结构 (${ts?.trade_date ?? "-"})`}>
            <Table
              size="small"
              rowKey="symbol"
              loading={isFetching}
              pagination={false}
              dataSource={ts?.contracts ?? []}
              columns={columns}
              locale={{ emptyText: "暂无数据" }}
            />
          </Card>
        </Col>
        <Col xs={24} xl={11}>
          <Card size="small" title="各品种主力基差概览">
            <Table
              size="small"
              rowKey="variety"
              loading={isFetching}
              pagination={false}
              dataSource={data?.overview ?? []}
              columns={overviewColumns}
              locale={{ emptyText: "暂无数据" }}
            />
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
