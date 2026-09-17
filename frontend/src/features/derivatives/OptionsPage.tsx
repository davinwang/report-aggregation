// 股指期权 — CFFEX index options T型报价 (IO/MO/HO) with PCR sentiment.
// Route: /options
import { useState } from "react";
import { Card, Col, Row, Segmented, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useQuery } from "@tanstack/react-query";
import { getOptionsBoard } from "@/api";
import type { OptionOverviewRow } from "@/types";
import PageContainer from "@/components/PageContainer";
import OptionTBoard from "@/components/OptionTBoard";
import ProvenanceTag from "@/components/ProvenanceTag";
import PageRefresh from "@/components/PageRefresh";
import StatCard from "@/components/StatCard";
import { fmtNum } from "@/hooks/useRelativeTime";

const UNDERLYINGS = ["沪深300股指期权", "中证1000股指期权", "上证50股指期权"];

function monthLabel(m: string): string {
  return m.length === 4 ? `20${m.slice(0, 2)}-${m.slice(2)}` : m;
}

export default function OptionsPage() {
  const [underlying, setUnderlying] = useState(UNDERLYINGS[0]);
  const [month, setMonth] = useState<string | undefined>(undefined);

  const { data, isFetching, isError } = useQuery({
    queryKey: ["derivatives", "options", underlying, month ?? "auto"],
    queryFn: () => getOptionsBoard({ underlying, month }),
    staleTime: 60_000,
  });

  const board = data?.board;
  const totals = board?.totals ?? {};
  const empty = !isFetching && (isError || !board?.rows?.length);

  const columns: ColumnsType<OptionOverviewRow> = [
    { title: "标的", dataIndex: "underlying", render: (v: string) => <Typography.Text strong>{v}</Typography.Text> },
    { title: "品种", dataIndex: "variety", width: 60 },
    { title: "合约月", dataIndex: "month", width: 90, render: (v: string | null) => (v ? monthLabel(v) : "-") },
    { title: "现货", dataIndex: "spot", align: "right", render: (v: number | null) => fmtNum(v, 1) },
    { title: "ATM行权价", dataIndex: "atm_strike", align: "right", render: (v: number | null) => fmtNum(v, 0) },
    {
      title: "PCR(持仓)",
      dataIndex: "pcr_oi",
      align: "right",
      render: (v: number | null) => <span style={{ fontVariantNumeric: "tabular-nums" }}>{v == null ? "-" : fmtNum(v, 3)}</span>,
    },
    {
      title: "PCR(成交)",
      dataIndex: "pcr_volume",
      align: "right",
      render: (v: number | null) => <span style={{ fontVariantNumeric: "tabular-nums" }}>{v == null ? "-" : fmtNum(v, 3)}</span>,
    },
  ];

  // PCR > 1 ⇒ puts dominate (bearish hedging); < 1 ⇒ calls dominate.
  const pcrTag = (v: number | null | undefined) =>
    v == null ? <Tag>-</Tag> : <Tag color={v >= 1 ? "green" : "red"}>{v >= 1 ? "看跌占优" : "看涨占优"}</Tag>;

  return (
    <PageContainer
      title="股指期权"
      description="中金所股指期权 T型报价 — 行权价居中，看涨/看跌分列两侧（IO 沪深300 / MO 中证1000 / HO 上证50）"
      extra={<Space><ProvenanceTag source="exchange" date={board?.trade_date} /><PageRefresh queryKeys={[["derivatives", "options"]]} feeds={["index_options"]} /></Space>}
    >
      <div className="grid-cards" style={{ marginBottom: 12 }}>
        <StatCard title="标的指数" value={fmtNum(board?.spot ?? null, 2)} footer={board?.trade_date ?? "-"} loading={isFetching && !data} />
        <StatCard title="ATM 行权价" value={fmtNum(board?.atm_strike ?? null, 0)} footer={`合约 ${totals.contracts ?? "-"} 个`} loading={isFetching && !data} />
        <StatCard
          title="PCR (持仓量)"
          value={totals.pcr_oi == null ? "-" : fmtNum(totals.pcr_oi, 3)}
          footer={pcrTag(totals.pcr_oi)}
          loading={isFetching && !data}
        />
        <StatCard
          title="PCR (成交量)"
          value={totals.pcr_volume == null ? "-" : fmtNum(totals.pcr_volume, 3)}
          footer={pcrTag(totals.pcr_volume)}
          loading={isFetching && !data}
        />
      </div>

      <Card
        size="small"
        style={{ marginBottom: 12 }}
        title={`T型报价 ${board?.month ? `· ${monthLabel(board.month)}` : ""}`}
        extra={
          <Space wrap>
            <Segmented
              options={UNDERLYINGS.map((u) => ({ value: u, label: u.replace("股指期权", "") }))}
              value={underlying}
              onChange={(v) => {
                setUnderlying(String(v));
                setMonth(undefined);
              }}
            />
            <Select
              value={board?.month ?? undefined}
              onChange={(v) => setMonth(String(v))}
              style={{ width: 120 }}
              size="small"
              placeholder="合约月份"
              options={(board?.months ?? []).map((m) => ({ value: m, label: monthLabel(m) }))}
            />
          </Space>
        }
      >
        {empty ? (
          <Typography.Paragraph type="secondary">
            暂无期权数据。请运行 <Typography.Text code>index_options</Typography.Text> 采集
            （需先完成 <Typography.Text code>index_daily</Typography.Text> 以提供标的指数价格）。
          </Typography.Paragraph>
        ) : (
          board && <OptionTBoard board={board} loading={isFetching} height={480} />
        )}
      </Card>

      <Row gutter={12}>
        <Col xs={24} xl={14}>
          <Card size="small" title="各品种概览">
            <Table
              size="small"
              rowKey="underlying"
              loading={isFetching}
              pagination={false}
              dataSource={data?.overview ?? []}
              columns={columns}
              locale={{ emptyText: "暂无数据" }}
            />
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card size="small" title="指标说明">
            <Typography.Paragraph className="muted" style={{ marginBottom: 6 }}>
              <b>T型报价</b>：以行权价为中心，左侧为看涨期权(Call)、右侧为看跌期权(Put)；
              高亮行权价为最接近标的现价的 ATM 合约。
            </Typography.Paragraph>
            <Typography.Paragraph className="muted" style={{ marginBottom: 6 }}>
              <b>PCR (Put/Call Ratio)</b>：看跌/看涨之比。持仓量 PCR &gt; 1 通常反映避险/看跌情绪占优，
              &lt; 1 则看涨占优。
            </Typography.Paragraph>
            <Typography.Paragraph className="muted" style={{ marginBottom: 0 }}>
              <b>涨跌</b> = 最新价 − 昨结算价；数据来源为中金所公开行情快照。
            </Typography.Paragraph>
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
