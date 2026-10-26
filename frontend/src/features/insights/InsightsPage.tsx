// 研报洞察 — 情绪分歧度 / 信号复盘 / 龙虎榜×研报联动 (rule-based, no LLM).
// Route: /insights. Three tabs, one page: each block is an independent query so
// switching tabs never refetches the others.
import { useState } from "react";
import { Card, Segmented, Space, Table, Tabs, Tag, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useQuery } from "@tanstack/react-query";
import { getLhbResearch, getReplay, getSentiment } from "@/api";
import type { LhbResearchRow, ReplayRow, SentimentRow } from "@/types";
import PageContainer from "@/components/PageContainer";
import PageRefresh from "@/components/PageRefresh";
import StatCard from "@/components/StatCard";
import { changeColor } from "@/styles/theme";

const pct = (v: number | null | undefined, digits = 1) =>
  v == null ? "-" : `${(v * 100).toFixed(digits)}%`;

const amt = (v: number | null | undefined) => {
  if (v == null) return "-";
  const abs = Math.abs(v);
  if (abs >= 1e8) return `${(v / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${(v / 1e4).toFixed(0)}万`;
  return v.toFixed(0);
};

const KIND_LABEL: Record<string, string> = {
  upgrade: "上调", downgrade: "下调", first: "首评", consensus: "一致",
};

function SentimentTab() {
  const [days, setDays] = useState(30);
  const [order, setOrder] = useState<"dispersion" | "consensus">("dispersion");
  const { data, isFetching } = useQuery({
    queryKey: ["insights", "sentiment", days, order],
    queryFn: () => getSentiment({ days, order }),
    staleTime: 60_000,
  });
  const rows = data?.rows ?? [];
  const market = data?.market ?? {
    stocks: 0, reports: 0, avg_consensus: null, high_dispersion: 0,
  };

  const columns: ColumnsType<SentimentRow> = [
    {
      title: "股票",
      dataIndex: "name",
      render: (v: string | null, r) => (
        <a href={`/stock/${r.code}`} target="_blank" rel="noreferrer">
          <Typography.Text strong>{v ?? r.code}</Typography.Text>
        </a>
      ),
    },
    {
      title: "分歧度",
      dataIndex: "dispersion",
      width: 100,
      align: "right",
      sorter: (a, b) => a.dispersion - b.dispersion,
      defaultSortOrder: order === "dispersion" ? "descend" : undefined,
      render: (v: number) => (
        <span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>{v.toFixed(2)}</span>
      ),
    },
    {
      title: "情绪分",
      dataIndex: "consensus",
      width: 90,
      align: "right",
      sorter: (a, b) => a.consensus - b.consensus,
      defaultSortOrder: order === "consensus" ? "descend" : undefined,
      render: (v: number) => (
        <span style={{ color: changeColor(v), fontVariantNumeric: "tabular-nums" }}>{v.toFixed(2)}</span>
      ),
    },
    {
      title: "结论",
      dataIndex: "label",
      width: 100,
      render: (v: string) => {
        const color = v.includes("多") ? "red" : v.includes("空") ? "green" : v === "重大分歧" ? "orange" : "default";
        return <Tag color={color} bordered={false}>{v}</Tag>;
      },
    },
    {
      title: "多/空/中性",
      key: "mix",
      width: 110,
      align: "right",
      render: (_, r) => (
        <span className="muted" style={{ fontVariantNumeric: "tabular-nums" }}>
          <span style={{ color: "#cf1322" }}>{r.bull}</span> / <span style={{ color: "#3f8600" }}>{r.bear}</span> / {r.neutral}
        </span>
      ),
    },
    {
      title: "机构数",
      dataIndex: "orgs",
      width: 80,
      align: "right",
      render: (v: number) => <span className="muted">{v}</span>,
    },
  ];

  return (
    <>
      <div className="grid-cards" style={{ marginBottom: 12 }}>
        <StatCard title="覆盖股票" value={market.stocks ?? 0} footer={`近${days}日 ≥2家机构研报`} loading={isFetching && !data} />
        <StatCard title="研报样本" value={market.reports ?? 0} footer="已归一化评级" loading={isFetching && !data} />
        <StatCard title="市场情绪均值" value={<span style={{ color: changeColor(market.avg_consensus ?? null) }}>{(market.avg_consensus ?? 0).toFixed(2)}</span>} footer="买入=+2 … 卖出=−2" loading={isFetching && !data} />
        <StatCard title="重大分歧股" value={market.high_dispersion ?? 0} footer="分歧度 ≥ 1.0" loading={isFetching && !data} />
      </div>
      <Card
        size="small"
        title="个股情绪与分歧度榜"
        extra={
          <Space wrap>
            <Segmented
              size="small"
              value={days}
              onChange={(v) => setDays(Number(v))}
              options={[{ value: 14, label: "14日" }, { value: 30, label: "30日" }, { value: 60, label: "60日" }]}
            />
            <Segmented
              size="small"
              value={order}
              onChange={(v) => setOrder(v as "dispersion" | "consensus")}
              options={[{ value: "dispersion", label: "按分歧" }, { value: "consensus", label: "按情绪" }]}
            />
          </Space>
        }
      >
        <Table
          size="small"
          rowKey="code"
          loading={isFetching}
          dataSource={rows}
          columns={columns}
          locale={{ emptyText: "暂无数据 — 需要先采集 research_reports，且同一股票近窗口内 ≥2 家机构覆盖" }}
          pagination={{ pageSize: 15, size: "small", showSizeChanger: false }}
        />
        <Typography.Paragraph className="muted" style={{ marginBottom: 0, marginTop: 8 }}>
          <b>分歧度</b> = 各机构评级打分的标准差（Diether et al. 2002：机构分歧大的股票未来收益系统性更低）；
          <b>情绪分</b> = 均分，&gt;0 偏多、&lt;0 偏空。单一机构覆盖的股票无分歧信息，不参与排名。
        </Typography.Paragraph>
      </Card>
    </>
  );
}

function ReplayTab() {
  const [horizon, setHorizon] = useState(20);
  const { data, isFetching } = useQuery({
    queryKey: ["insights", "replay", horizon],
    queryFn: () => getReplay({ horizon }),
    staleTime: 60_000,
  });
  const rows = data?.rows ?? [];
  const summary = data?.summary;

  const columns: ColumnsType<ReplayRow> = [
    {
      title: "信号日",
      dataIndex: "trade_date",
      width: 100,
      render: (v: string) => <span className="muted">{v.slice(5)}</span>,
    },
    {
      title: "股票",
      dataIndex: "name",
      render: (v: string | null, r) => (
        <a href={`/stock/${r.code}`} target="_blank" rel="noreferrer">
          <Typography.Text strong>{v ?? r.code}</Typography.Text>
        </a>
      ),
    },
    {
      title: "信号",
      key: "signal",
      width: 120,
      render: (_, r) => (
        <Space size={4}>
          <Tag color={r.bullish ? "red" : "green"} bordered={false}>
            {KIND_LABEL[r.kind] ?? r.kind}
          </Tag>
          {r.strength && <Tag bordered={false}>{r.strength}</Tag>}
        </Space>
      ),
    },
    {
      title: "个股",
      dataIndex: "stock_ret",
      width: 90,
      align: "right",
      render: (v: number) => (
        <span style={{ color: changeColor(v), fontVariantNumeric: "tabular-nums" }}>{pct(v)}</span>
      ),
    },
    {
      title: "沪深300",
      dataIndex: "bench_ret",
      width: 90,
      align: "right",
      render: (v: number) => <span className="muted" style={{ fontVariantNumeric: "tabular-nums" }}>{pct(v)}</span>,
    },
    {
      title: "超额",
      dataIndex: "excess",
      width: 90,
      align: "right",
      sorter: (a, b) => a.excess - b.excess,
      render: (v: number) => (
        <span style={{ color: changeColor(v), fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{pct(v)}</span>
      ),
    },
    {
      title: "结果",
      dataIndex: "hit",
      width: 70,
      render: (v: boolean) => (v ? <Tag color="gold">命中</Tag> : <Tag bordered={false}>未中</Tag>),
    },
  ];

  return (
    <>
      <div className="grid-cards" style={{ marginBottom: 12 }}>
        <StatCard title="复盘信号数" value={summary?.evaluated ?? 0} footer={`窗口已关闭 · 前${horizon}个交易日`} loading={isFetching && !data} />
        <StatCard title="命中数" value={summary?.hits ?? 0} footer="方向判断正确" loading={isFetching && !data} />
        <StatCard
          title="胜率"
          value={<span style={{ color: changeColor((summary?.win_rate ?? 0) - 0.5) }}>{pct(summary?.win_rate)}</span>}
          footer=">50% 即跑赢随机"
          loading={isFetching && !data}
        />
        <StatCard
          title="平均超额"
          value={<span style={{ color: changeColor(summary?.avg_excess ?? null) }}>{pct(summary?.avg_excess)}</span>}
          footer="个股收益 − 沪深300"
          loading={isFetching && !data}
        />
      </div>
      <Card
        size="small"
        title={`信号复盘 — ${horizon}个交易日回望`}
        extra={
          <Segmented
            size="small"
            value={horizon}
            onChange={(v) => setHorizon(Number(v))}
            options={[{ value: 20, label: "20日" }, { value: 60, label: "60日" }]}
          />
        }
      >
        <Table
          size="small"
          rowKey={(r) => `${r.code}-${r.trade_date}-${r.kind}`}
          loading={isFetching}
          dataSource={rows}
          columns={columns}
          locale={{ emptyText: "暂无已关闭窗口的信号 — 信号产生满 20/60 个交易日后自动进入复盘" }}
          pagination={{ pageSize: 15, size: "small", showSizeChanger: false }}
        />
        <Typography.Paragraph className="muted" style={{ marginBottom: 0, marginTop: 8 }}>
          <b>口径</b>：信号日收盘（前复权）买入，持有 {horizon} 个交易日，与同期沪深300比较。
          买入/增持类信号超额 &gt; 0 记命中；卖出/减持类超额 &lt; 0 记命中。这是"当时如果……"的真实答案，比回测曲线更直观。
        </Typography.Paragraph>
      </Card>
    </>
  );
}

function LhbTab() {
  const [direction, setDirection] = useState<"all" | "buy" | "sell">("all");
  const { data, isFetching } = useQuery({
    queryKey: ["insights", "lhb-research", direction],
    queryFn: () => getLhbResearch(direction === "all" ? {} : { direction }),
    staleTime: 60_000,
  });
  const rows = data?.rows ?? [];
  const summary = data?.summary;

  const columns: ColumnsType<LhbResearchRow> = [
    {
      title: "股票",
      dataIndex: "name",
      render: (v: string | null, r) => (
        <Space size={4}>
          <a href={`/stock/${r.code}`} target="_blank" rel="noreferrer">
            <Typography.Text strong>{v ?? r.code}</Typography.Text>
          </a>
          {r.coverage && <Tag color="purple" bordered={false}>双重信号</Tag>}
        </Space>
      ),
    },
    {
      title: "最近上榜",
      dataIndex: "last_lhb_date",
      width: 100,
      render: (v: string) => <span className="muted">{v.slice(5)}</span>,
    },
    { title: "次数", dataIndex: "lhb_events", width: 70, align: "right" },
    {
      title: "累计净买",
      dataIndex: "net_amt",
      width: 100,
      align: "right",
      sorter: (a, b) => a.net_amt - b.net_amt,
      render: (v: number) => (
        <span style={{ color: changeColor(v), fontVariantNumeric: "tabular-nums" }}>{amt(v)}</span>
      ),
    },
    {
      title: "研报覆盖",
      key: "coverage",
      width: 130,
      render: (_, r) =>
        r.coverage ? (
          <Tooltip title={`${r.coverage.first} ~ ${r.coverage.last}`}>
            <span style={{ fontVariantNumeric: "tabular-nums" }}>
              {r.coverage.reports}篇 / {r.coverage.orgs}机构
            </span>
          </Tooltip>
        ) : (
          <span className="muted">无覆盖</span>
        ),
    },
    {
      title: "上榜原因",
      dataIndex: "reasons",
      ellipsis: true,
      render: (v: string[]) => <span className="muted">{v.join("；")}</span>,
    },
  ];

  return (
    <>
      <div className="grid-cards" style={{ marginBottom: 12 }}>
        <StatCard title="上榜股票" value={summary?.lhb_stocks ?? 0} footer="近10个交易日" loading={isFetching && !data} />
        <StatCard title="双重信号" value={summary?.dual_signal ?? 0} footer="上榜 + 券商研报覆盖" loading={isFetching && !data} />
        <StatCard title="研报覆盖率" value={pct(summary?.covered_ratio)} footer="上榜股中有覆盖的比例" loading={isFetching && !data} />
        <StatCard
          title="上榜股净买合计"
          value={<span style={{ color: changeColor(summary?.net_total ?? null) }}>{amt(summary?.net_total)}</span>}
          footer="龙虎榜席位净买入"
          loading={isFetching && !data}
        />
      </div>
      <Card
        size="small"
        title="龙虎榜 × 研报联动"
        extra={
          <Segmented
            size="small"
            value={direction}
            onChange={(v) => setDirection(v as "all" | "buy" | "sell")}
            options={[{ value: "all", label: "全部" }, { value: "buy", label: "净买入" }, { value: "sell", label: "净卖出" }]}
          />
        }
      >
        <Table
          size="small"
          rowKey="code"
          loading={isFetching}
          dataSource={rows}
          columns={columns}
          locale={{ emptyText: "暂无数据 — 需要先采集 lhb 与 research_reports" }}
          pagination={{ pageSize: 15, size: "small", showSizeChanger: false }}
        />
        <Typography.Paragraph className="muted" style={{ marginBottom: 0, marginTop: 8 }}>
          <b>双重信号</b> = 龙虎榜资金异动 + 机构研报覆盖同期出现，即"聪明钱"与卖方关注点共振的股票（smart-money tracking）。
          研报覆盖窗口为上榜日前后的 30 天。
        </Typography.Paragraph>
      </Card>
    </>
  );
}

export default function InsightsPage() {
  return (
    <PageContainer
      title="研报洞察"
      description="情绪分歧度 · 信号复盘 · 龙虎榜联动 — 全部由已采集数据规则推导，无主观判断"
      extra={<PageRefresh queryKeys={[["insights"]]} feeds={["research_reports", "ratings_daily", "lhb"]} />}
    >
      <Tabs
        defaultActiveKey="sentiment"
        items={[
          { key: "sentiment", label: "情绪与分歧", children: <SentimentTab /> },
          { key: "replay", label: "信号复盘", children: <ReplayTab /> },
          { key: "lhb", label: "龙虎榜联动", children: <LhbTab /> },
        ]}
      />
    </PageContainer>
  );
}
