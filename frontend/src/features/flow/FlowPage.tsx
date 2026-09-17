// 资金流向 — 沪深港通 (北向/南向) + 融资融券 + 龙虎榜.
// Route: /flow
import { useState } from "react";
import { Card, Col, Row, Segmented, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getFlowSummary, getLhb, getMargin, getNorthbound } from "@/api";
import type { LhbRow, NorthboundLatest } from "@/types";
import PageContainer from "@/components/PageContainer";
import LineChart from "@/components/LineChart";
import ProvenanceTag from "@/components/ProvenanceTag";
import PageRefresh from "@/components/PageRefresh";
import StatCard from "@/components/StatCard";
import { changeColor } from "@/styles/theme";
import { fmtAmount, fmtNum, fmtPct } from "@/hooks/useRelativeTime";

const NORTH_BOARDS = ["沪股通", "深股通"];
const SOUTH_BOARDS = ["港股通(沪)", "港股通(深)"];
const YI = 1e8;

// 沪深港通 net figures come in 亿元; margin & 龙虎榜 amounts come in 元.
function fmtYi(v?: number | null): string {
  if (v == null || Number.isNaN(v)) return "-";
  return `${v.toLocaleString("zh-CN", { maximumFractionDigits: 2, minimumFractionDigits: 2 })}亿`;
}

export default function FlowPage() {
  const [side, setSide] = useState<"north" | "south">("north");
  const [direction, setDirection] = useState<"all" | "buy" | "sell">("all");
  const [page, setPage] = useState(1);
  const size = 50;

  const { data: summary } = useQuery({
    queryKey: ["flow", "summary"],
    queryFn: getFlowSummary,
    staleTime: 60_000,
  });
  const { data: nb, isFetching: nbFetching } = useQuery({
    queryKey: ["flow", "northbound"],
    queryFn: () => getNorthbound(30),
    staleTime: 60_000,
  });
  const { data: mg, isFetching: mgFetching } = useQuery({
    queryKey: ["flow", "margin"],
    queryFn: () => getMargin(60),
    staleTime: 60_000,
  });
  const { data: lhb, isFetching: lhbFetching, isError: lhbError } = useQuery({
    queryKey: ["flow", "lhb", page, direction],
    queryFn: () => getLhb({ direction: direction === "all" ? undefined : direction, page, size }),
    staleTime: 30_000,
  });

  // ---- 沪深港通 ----
  const boards = side === "north" ? NORTH_BOARDS : SOUTH_BOARDS;
  const breadthSeries = boards.flatMap((b) => [
    { name: `${b} 上涨`, data: nb?.up?.[b] ?? [], type: "line" as const },
    { name: `${b} 下跌`, data: nb?.down?.[b] ?? [], type: "line" as const },
  ]);
  const latestRows: NorthboundLatest[] = (nb?.latest ?? []).filter((r) => boards.includes(r.board));

  const nbColumns: ColumnsType<NorthboundLatest> = [
    { title: "板块", dataIndex: "board", render: (v: string) => <Typography.Text strong>{v}</Typography.Text> },
    { title: "方向", dataIndex: "direction", width: 60, render: (v: string | null) => (v ? <Tag>{v}</Tag> : "-") },
    { title: "资金净流入", dataIndex: "net_inflow", align: "right", render: (v: number | null) => fmtYi(v) },
    { title: "成交净买额", dataIndex: "net_buy", align: "right", render: (v: number | null) => fmtYi(v) },
    {
      title: "上涨/持平/下跌",
      key: "breadth",
      align: "right",
      render: (_, r) => (
        <span>
          <span style={{ color: "#e4393c" }}>{r.up ?? "-"}</span>
          {" / "}
          {r.flat ?? "-"}
          {" / "}
          <span style={{ color: "#2fa84f" }}>{r.down ?? "-"}</span>
        </span>
      ),
    },
    { title: "相关指数", dataIndex: "index", width: 110, render: (v: string | null) => v ?? "-" },
    {
      title: "指数涨跌幅",
      dataIndex: "index_pct",
      align: "right",
      render: (v: number | null) => <span style={{ color: changeColor(v) }}>{fmtPct(v)}</span>,
    },
  ];

  // ---- 融资融券 ----
  const mgSeries = [
    { name: "融资余额(亿)", data: (mg?.sse.rzye ?? []).map((v) => (v == null ? null : v / YI)) },
    { name: "融资买入额(亿)", data: (mg?.sse.rzmre ?? []).map((v) => (v == null ? null : v / YI)) },
    { name: "融券余额(亿)", data: (mg?.sse.rqye ?? []).map((v) => (v == null ? null : v / YI)), yAxisIndex: 1 },
  ];
  const mgSnapshot = [
    ...(mg?.latest ? [{ exchange: "上交所 (SSE)", ...mg.latest }] : []),
    ...(mg?.szse ? [{ exchange: "深交所 (SZSE)", ...mg.szse }] : []),
  ];
  const mgColumns: ColumnsType<(typeof mgSnapshot)[number]> = [
    { title: "交易所", dataIndex: "exchange" },
    { title: "数据日期", dataIndex: "trade_date", width: 110 },
    { title: "融资余额", dataIndex: "rzye", align: "right", render: (v: number | null) => fmtAmount(v) },
    { title: "融资买入额", dataIndex: "rzmre", align: "right", render: (v: number | null) => fmtAmount(v) },
    { title: "融券余额", dataIndex: "rqye", align: "right", render: (v: number | null) => fmtAmount(v) },
    { title: "融资融券余额", dataIndex: "rzrqye", align: "right", render: (v: number | null) => fmtAmount(v) },
  ];

  // ---- 龙虎榜 ----
  const lhbColumns: ColumnsType<LhbRow> = [
    {
      title: "代码",
      dataIndex: "code",
      width: 90,
      render: (code: string, r) => <Link to={`/stock/${code}`}>{r.name ?? code}</Link>,
    },
    { title: "收盘价", dataIndex: "close", align: "right", width: 90, render: (v: number | null) => fmtNum(v, 2) },
    {
      title: "涨跌幅",
      dataIndex: "change_pct",
      align: "right",
      width: 90,
      render: (v: number | null) => <span style={{ color: changeColor(v) }}>{fmtPct(v)}</span>,
    },
    { title: "买入额", dataIndex: "buy_amt", align: "right", width: 110, render: (v: number | null) => fmtAmount(v) },
    { title: "卖出额", dataIndex: "sell_amt", align: "right", width: 110, render: (v: number | null) => fmtAmount(v) },
    {
      title: "净买额",
      dataIndex: "net_amt",
      align: "right",
      width: 110,
      sorter: false,
      render: (v: number | null) => <span style={{ color: changeColor(v), fontWeight: 600 }}>{fmtAmount(v)}</span>,
    },
    {
      title: "换手率",
      dataIndex: "turnover",
      align: "right",
      width: 90,
      render: (v: number | null) => (v == null ? "-" : `${fmtNum(v, 2)}%`),
    },
    { title: "上榜原因", dataIndex: "reason", ellipsis: true, render: (v: string | null) => v ?? "-" },
  ];

  const s = summary;

  return (
    <PageContainer
      title="资金流向"
      description="沪深港通 (北向/南向) · 融资融券 · 龙虎榜 — 交易所与东方财富公开数据"
      extra={<Space><ProvenanceTag source="exchange" date={nb?.ref ?? null} /><PageRefresh queryKeys={[["flow"]]} /></Space>}
    >
      <div className="grid-cards" style={{ marginBottom: 12 }}>
        <StatCard
          title="北向涨跌家数 (沪+深)"
          value={
            <span>
              <span style={{ color: "#e4393c" }}>{s?.north_up ?? "-"}</span>
              <span className="muted" style={{ fontSize: 14 }}> 涨 / </span>
              <span style={{ color: "#2fa84f" }}>{s?.north_down ?? "-"}</span>
              <span className="muted" style={{ fontSize: 14 }}> 跌</span>
            </span>
          }
          footer={`数据日期 ${s?.northbound_date ?? "-"}`}
          loading={!s && nbFetching}
        />
        <StatCard
          title="南向成交净买额 (港股通合计)"
          value={fmtYi(s?.southbound_net_buy)}
          footer="北向净流入自2024-08起暂停披露（仅剩涨跌家数）"
          loading={!s && nbFetching}
        />
        <StatCard
          title="沪市两融余额"
          value={fmtAmount(s?.margin_sse?.rzrqye)}
          footer={`深市 ${fmtAmount(s?.margin_szse?.rzrqye)} · ${s?.margin_sse?.trade_date ?? "-"}`}
          loading={!s && mgFetching}
        />
        <StatCard
          title="龙虎榜净买额"
          value={
            <span style={{ color: changeColor(s?.lhb_net_total) }}>{fmtAmount(s?.lhb_net_total)}</span>
          }
          footer={`数据日期 ${s?.lhb_date ?? "-"}`}
          loading={!s && lhbFetching}
        />
      </div>

      <Card
        size="small"
        style={{ marginBottom: 12 }}
        title="沪深港通 · 涨跌家数"
        extra={
          <Segmented
            size="small"
            value={side}
            onChange={(v) => setSide(v as "north" | "south")}
            options={[
              { value: "north", label: "北向 (沪股通/深股通)" },
              { value: "south", label: "南向 (港股通)" },
            ]}
          />
        }
      >
        {nb?.dates?.length ? (
          <LineChart dates={nb.dates} series={breadthSeries} height={260} yAxisNames={["家数", ""]} />
        ) : (
          <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
            暂无沪深港通数据。请运行 <Typography.Text code>northbound</Typography.Text> 采集。
          </Typography.Paragraph>
        )}
        {nb?.dates?.length === 1 && (
          <Typography.Paragraph type="secondary" style={{ margin: "8px 0 0", fontSize: 12 }}>
            涨跌家数为逐日累积数据（上游仅保留当日快照，收盘后冻结），当前仅 1 个交易日，趋势将随每日采集逐步展开。
          </Typography.Paragraph>
        )}
        <Table
          size="small"
          rowKey={(r) => `${r.trade_date}-${r.board}`}
          style={{ marginTop: 12 }}
          loading={nbFetching}
          pagination={false}
          dataSource={latestRows}
          columns={nbColumns}
          locale={{ emptyText: "暂无数据" }}
        />
      </Card>

      <Row gutter={12} style={{ marginBottom: 12 }}>
        <Col xs={24} xl={14}>
          <Card size="small" title="沪市融资融券余额趋势 (近60个交易日)" extra={<ProvenanceTag source="exchange" date={mg?.latest?.trade_date ?? null} />}>
            {mg?.dates?.length ? (
              <LineChart dates={mg.dates} series={mgSeries} height={280} yAxisNames={["亿元", "亿元"]} zoom />
            ) : (
              <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
                暂无融资融券数据。请运行 <Typography.Text code>margin</Typography.Text> 采集。
              </Typography.Paragraph>
            )}
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card size="small" title="两融最新快照" style={{ height: "100%" }}>
            <Table
              size="small"
              rowKey="exchange"
              loading={mgFetching}
              pagination={false}
              dataSource={mgSnapshot}
              columns={mgColumns}
              locale={{ emptyText: "暂无数据" }}
            />
            <Typography.Paragraph className="muted" style={{ margin: "10px 0 0", fontSize: 12 }}>
              融资余额反映杠杆做多意愿；融券余额反映做空/对冲需求。数据为沪深交易所每日披露（T+1）。
            </Typography.Paragraph>
          </Card>
        </Col>
      </Row>

      <Card
        size="small"
        title={`龙虎榜明细 ${lhb?.meta?.trade_date ? `· ${lhb.meta.trade_date}` : ""}`}
        extra={
          <Space wrap>
            <Tag bordered={false}>
              当日净买额合计 <b style={{ color: changeColor(lhb?.meta?.stats?.net_total ?? null) }}>{fmtAmount(lhb?.meta?.stats?.net_total ?? null)}</b>
            </Tag>
            <Segmented
              size="small"
              value={direction}
              onChange={(v) => {
                setDirection(v as "all" | "buy" | "sell");
                setPage(1);
              }}
              options={[
                { value: "all", label: "全部" },
                { value: "buy", label: "净买入" },
                { value: "sell", label: "净卖出" },
              ]}
            />
          </Space>
        }
      >
        <Table
          size="small"
          rowKey={(r) => `${r.code}-${r.reason}`}
          loading={lhbFetching}
          dataSource={lhbError ? [] : lhb?.rows ?? []}
          columns={lhbColumns}
          locale={{ emptyText: "暂无龙虎榜数据。请运行 lhb 采集。" }}
          pagination={{
            current: page,
            pageSize: size,
            total: lhb?.meta?.total ?? 0,
            showSizeChanger: false,
            onChange: setPage,
            size: "small",
          }}
        />
      </Card>
    </PageContainer>
  );
}
