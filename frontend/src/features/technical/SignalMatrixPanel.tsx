// 技术信号矩阵 — 品种 × 指标 的方向表决表 + 净方向排序.
//
// Each column is one rule that turns an indicator reading into 偏多/偏空/中性/弃权. The
// point of the table is that 弃权 and 无数据 are *visible and excluded* rather than
// quietly folded into 中性: a 超买 reading ("超买还可以更超买") and a 震荡 reading are very
// different pieces of information, and a missing column is different from both. Every
// cell carries the rule's own 口径 note on hover so no cell is a bare unexplained colour.
//
// Rows that are 低流动 or 滞后/停牌 stay in the table (their readings are real) but are
// excluded from the summary tally, with the reason shown on the row — a 停牌 name's
// indicators describe a price that hasn't traded in a week.
import { useMemo, useState } from "react";
import { Alert, Card, Empty, Segmented, Select, Space, Table, Tag, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getIndicatorCatalog, getSignalMatrix, getSignalRules } from "@/api";
import type {
  BarFreq,
  IndicatorMeta,
  SignalCell,
  SignalMatrixPayload,
  SignalMatrixRow,
  SignalRule,
  SignalScope,
  SignalState,
} from "@/types";
import StatCard from "@/components/StatCard";
import { DOWN_COLOR, UP_COLOR } from "@/styles/theme";
import { fmtNum } from "@/hooks/useRelativeTime";
import {
  STATE_FULL,
  STATE_GLYPH,
  breadthSegments,
  cellStyle,
  extreme,
  filterRows,
  sortRows,
  type SortKey,
  type ViewFilter,
} from "./matrixView";

const SCOPES: { value: SignalScope; label: string }[] = [
  { value: "index", label: "宽基指数" },
  { value: "index+all", label: "全部指数" },
  { value: "etf", label: "ETF" },
  { value: "bond", label: "可转债" },
  { value: "stock", label: "个股" },
  { value: "all", label: "全品种" },
];

const FREQS: { value: BarFreq; label: string }[] = [
  { value: "daily", label: "日线" },
  { value: "weekly", label: "周线" },
  { value: "monthly", label: "月线" },
];

const SORTS: { value: SortKey; label: string }[] = [
  { value: "net", label: "净方向" },
  { value: "name", label: "名称" },
  { value: "change", label: "涨跌幅" },
  { value: "turnover", label: "成交额" },
];

const VIEW_FILTERS: { value: ViewFilter; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "bull", label: "偏多" },
  { value: "bear", label: "偏空" },
  { value: "split", label: "分歧" },
  { value: "flat", label: "无方向" },
];

/** ETF and 可转债 books are an order of magnitude thinner than 沪深300 constituents. */
const FLOOR_DEFAULT = 5e7;
const FLOOR_THIN = 1e7;

export default function SignalMatrixPanel({ dark }: { dark: boolean }) {
  const [scope, setScope] = useState<SignalScope>("index");
  const [freq, setFreq] = useState<BarFreq>("daily");
  const [limit, setLimit] = useState(60);
  const [view, setView] = useState<ViewFilter>("all");
  const [sortBy, setSortBy] = useState<SortKey>("net");
  const [onlyColumns, setOnlyColumns] = useState<string[]>([]);

  // 宽基/个股 are deep enough to justify a tighter liquidity gate; ETF/可转债 are not.
  const floor = scope === "etf" || scope === "bond" ? FLOOR_THIN : FLOOR_DEFAULT;

  const { data, isFetching, isError } = useQuery({
    queryKey: ["quant", "signal-matrix", scope, freq, limit, floor],
    queryFn: () => getSignalMatrix({ scope, freq, limit, liquidity_floor: floor }),
    staleTime: 60_000,
  });
  const { data: catalog } = useQuery({
    queryKey: ["quant", "indicator-catalog"],
    queryFn: () => getIndicatorCatalog(),
    staleTime: 600_000,
  });
  const { data: rules } = useQuery({
    queryKey: ["quant", "signal-rules"],
    queryFn: () => getSignalRules(),
    staleTime: 600_000,
  });

  const rows = useMemo(() => data?.rows ?? [], [data]);
  const columns = data?.columns ?? [];
  const summary = data?.summary;

  const shown = useMemo(
    () => sortRows(filterRows(rows, view), sortBy),
    [rows, view, sortBy],
  );
  // Excluded rows keep real readings but must not be crowned as 最强/最弱.
  const strongest = useMemo(() => extreme(rows, 1), [rows]);
  const weakest = useMemo(() => extreme(rows, -1), [rows]);

  const columnDefs: ColumnsType<SignalMatrixRow> = useMemo(() => {
    const meta = new Map((catalog ?? []).map((c: IndicatorMeta) => [c.key, c]));
    const ruleMap = new Map((rules ?? []).map((r: SignalRule) => [r.key, r]));
    const visible = columns.filter((c) => !onlyColumns.length || onlyColumns.includes(c.key));
    return visible.map((col) => ({
      title: (
        <Tooltip title={<RuleTip rule={ruleMap.get(col.key)} meta={meta.get(col.key)} tally={summary?.columns[col.key]} />}>
          <span style={{ cursor: "help", whiteSpace: "nowrap" }}>
            {col.label}
            {summary?.columns[col.key] && (
              <Typography.Text type="secondary" style={{ marginLeft: 4, fontSize: 10 }}>
                {summary.columns[col.key].net > 0 ? "+" : ""}
                {summary.columns[col.key].net}
              </Typography.Text>
            )}
          </span>
        </Tooltip>
      ),
      key: col.key,
      width: 62,
      align: "center" as const,
      render: (_: unknown, row: SignalMatrixRow) => <Cell cell={row.signals[col.key]} dark={dark} />,
    }));
  }, [columns, onlyColumns, catalog, rules, summary, dark]);

  const columnsAll: ColumnsType<SignalMatrixRow> = useMemo(
    () => [
      {
        title: "品种",
        dataIndex: "name",
        width: 150,
        fixed: "left",
        render: (name: string, r) => (
          <Tooltip title={r.excluded ? `不参与表决：${r.excluded}` : undefined}>
            <span>
              <Link to={`/technical/${r.code}`}>{name}</Link>
              {r.excluded && (
                <Tag style={{ marginLeft: 4, fontSize: 10, lineHeight: "14px" }}>{r.excluded}</Tag>
              )}
            </span>
          </Tooltip>
        ),
      },
      { title: "代码", dataIndex: "code", width: 86, render: (c: string) => <span className="muted">{c}</span> },
      {
        title: "现价",
        dataIndex: "close",
        align: "right",
        width: 84,
        sorter: (a, b) => (a.close ?? 0) - (b.close ?? 0),
        render: (v: number | null) => fmtNum(v, 3),
      },
      {
        title: "涨跌幅",
        dataIndex: "change_pct",
        align: "right",
        width: 80,
        render: (v: number | null) => (
          <span style={{ color: v == null ? undefined : v > 0 ? UP_COLOR : v < 0 ? DOWN_COLOR : undefined }}>
            {v == null ? "-" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`}
          </span>
        ),
      },
      {
        title: "净方向",
        dataIndex: "net",
        width: 96,
        align: "right",
        sorter: (a, b) => a.net - b.net,
        defaultSortOrder: sortBy === "net" ? "descend" : null,
        render: (net: number, r: SignalMatrixRow) => (
          <Tooltip
            title={
              r.voted === 0
                ? `${r.voted} 个指标参与表决，没有可用的方向`
                : `偏多 ${r.bulls} · 偏空 ${r.bears} · 中性 ${r.neutrals} · 弃权 ${r.abstains}（共 ${r.voted} 个参与表决）`
            }
          >
            <span style={{ color: net > 0 ? UP_COLOR : net < 0 ? DOWN_COLOR : undefined }}>
              {net > 0 ? "+" : ""}
              {net.toFixed(1)}
              <Typography.Text type="secondary" style={{ marginLeft: 4, fontSize: 10 }}>
                {r.bulls}/{r.bears}
              </Typography.Text>
            </span>
          </Tooltip>
        ),
      },
      ...columnDefs,
    ],
    [columnDefs, sortBy],
  );

  const breadth = summary?.breadth;

  return (
    <>
      <div className="grid-cards" style={{ marginBottom: 12 }}>
        <StatCard
          title="全市场净方向"
          value={
            summary ? (
              <span style={{ color: summary.market_net > 0 ? UP_COLOR : summary.market_net < 0 ? DOWN_COLOR : undefined }}>
                {summary.market_verdict}
              </span>
            ) : "-"
          }
          footer={
            summary
              ? `多 ${summary.breadth.bull} · 空 ${summary.breadth.bear} · 分歧 ${summary.breadth.split}（共 ${summary.participating} 只）`
              : ""
          }
          loading={isFetching && !data}
        />
        <StatCard
          title="参与表决"
          value={summary?.participating ?? "-"}
          footer={
            summary
              ? `${summary.excluded?.["低流动"] ?? 0} 低流动 · ${summary.excluded?.["滞后/停牌"] ?? 0} 停牌/滞后（已剔除）`
              : ""
          }
          loading={isFetching && !data}
        />
        <StatCard
          title="最强 / 最弱"
          value={strongest?.name || "-"}
          footer={weakest ? `最弱 ${weakest.name} ${weakest.net}` : "没有可用的表决"}
          loading={isFetching && !data}
        />
        <StatCard
          title="数据截至"
          value={data?.as_of ?? "-"}
          footer={`${FREQ_LABEL[freq]} · ${scopeLabel(scope)} · 上限 ${limit}`}
          loading={isFetching && !data}
        />
      </div>

      <Card
        size="small"
        title="技术信号矩阵"
        extra={
          <Space wrap size={6}>
            <Segmented size="small" options={SCOPES} value={scope} onChange={(v) => setScope(v as SignalScope)} />
            <Segmented size="small" options={FREQS} value={freq} onChange={(v) => setFreq(v as BarFreq)} />
            <Select
              size="small"
              value={onlyColumns}
              onChange={setOnlyColumns}
              mode="multiple"
              allowClear
              maxTagCount={2}
              placeholder="筛选列"
              style={{ minWidth: 150 }}
              options={(rules ?? []).map((r) => ({ value: r.key, label: r.label }))}
            />
            <Select
              size="small"
              value={sortBy}
              onChange={setSortBy}
              style={{ width: 96 }}
              options={SORTS}
            />
            <Select
              size="small"
              value={limit}
              onChange={setLimit}
              style={{ width: 88 }}
              options={[30, 60, 120, 300].map((n) => ({ value: n, label: `Top${n}` }))}
            />
            <Segmented size="small" options={VIEW_FILTERS} value={view} onChange={(v) => setView(v as ViewFilter)} />
          </Space>
        }
      >
        {isError && (
          <Alert
            type="error"
            showIcon
            style={{ marginBottom: 10 }}
            message="信号矩阵没能加载出来"
            description="这不是「暂无数据」，是没取到数据。请稍后重试，或检查后端是否在运行。"
          />
        )}
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 10 }}
          message={
            <Space size={6} wrap>
              <span>表决口径：</span>
              <LegendChip state="bull" dark={dark} />
              <LegendChip state="bear" dark={dark} />
              <LegendChip state="neutral" dark={dark} />
              <LegendChip state="abstain" dark={dark} />
              <Typography.Text type="secondary">
                弃权与无数据不计入分母（超买超卖、无趋势、样本不足、指标不适用）
              </Typography.Text>
            </Space>
          }
        />
        <Table
          size="small"
          rowKey="code"
          loading={isFetching}
          dataSource={shown}
          columns={columnsAll}
          scroll={{ x: 200 + columnsAll.length * 62 }}
          pagination={{ pageSize: 40, size: "small", showSizeChanger: false }}
          rowClassName={(r) => (r.excluded ? "row-muted" : "")}
        />
        {!rows.length && !isFetching && (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <span>
                该范围内还没有行情数据。请先运行{" "}
                <Typography.Text code>{scope === "etf" ? "etf_daily" : scope === "bond" ? "cov_bond_daily" : "price_history"}</Typography.Text>{" "}
                采集后再查看矩阵。
              </span>
            }
          />
        )}
      </Card>

      {breadth && breadth.flat + breadth.bull + breadth.bear + breadth.split > 0 && (
        <BreadthBar summary={summary!} dark={dark} />
      )}
    </>
  );
}

const FREQ_LABEL: Record<BarFreq, string> = { daily: "日线", weekly: "周线", monthly: "月线" };

function scopeLabel(scope: string): string {
  return SCOPES.find((s) => s.value === scope)?.label ?? scope;
}

function Cell({ cell, dark }: { cell?: SignalCell; dark: boolean }) {
  if (!cell) return <span className="muted">-</span>;
  return (
    <Tooltip title={cell.note}>
      <span
        style={{
          display: "inline-block",
          minWidth: 34,
          padding: "1px 4px",
          borderRadius: 2,
          fontSize: 11,
          cursor: "help",
          ...cellStyle(cell.state, dark),
        }}
      >
        {STATE_GLYPH[cell.state]}
      </span>
    </Tooltip>
  );
}

function LegendChip({ state, dark }: { state: SignalState; dark: boolean }) {
  return (
    <span style={{ fontSize: 11, padding: "1px 5px", borderRadius: 2, ...cellStyle(state, dark) }}>
      {STATE_GLYPH[state]}
      {STATE_FULL[state].slice(1)}
    </span>
  );
}

function RuleTip({
  rule,
  meta,
  tally,
}: {
  rule?: SignalRule;
  meta?: IndicatorMeta;
  tally?: { bull: number; bear: number; neutral: number; abstain: number; na: number; abstain_pct: number };
}) {
  return (
    <div style={{ maxWidth: 300 }}>
      <div style={{ marginBottom: 4 }}>
        <b>{rule?.label ?? meta?.label}</b>
      </div>
      <div style={{ lineHeight: 1.6, marginBottom: 6 }}>{rule?.doc ?? meta?.desc}</div>
      {meta && (
        <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>
          底层指标 {meta.label}（{meta.key}）
        </div>
      )}
      {tally && (
        <div style={{ fontSize: 11 }}>
          本列：多 {tally.bull} · 空 {tally.bear} · 中 {tally.neutral} · 弃权 {tally.abstain}（
          {tally.abstain_pct}%）· 无数据 {tally.na}
        </div>
      )}
    </div>
  );
}

/** Breadth strip: one segment per verdict, sized by count. Reading it tells you whether
 *  the market net is broad or a handful of names dragging it. */
function BreadthBar({ summary, dark }: { summary: SignalMatrixPayload["summary"]; dark: boolean }) {
  const b = summary.breadth;
  const total = b.bull + b.bear + b.split + b.flat;
  if (!total) return null;
  const colors: Record<string, string> = {
    偏多: UP_COLOR,
    偏空: DOWN_COLOR,
    分歧: dark ? "#c678dd" : "#722ed1",
    无方向: dark ? "#4a525f" : "#c7ccd4",
  };
  const segs = breadthSegments(b);
  return (
    <Card size="small" style={{ marginTop: 12 }} title="涨跌广度">
      <div style={{ display: "flex", height: 16, borderRadius: 2, overflow: "hidden" }}>
        {segs.map((s) => (
          <Tooltip key={s.label} title={`${s.label} ${s.n} 只`}>
            <div style={{ width: `${(100 * s.n) / total}%`, background: colors[s.label] }} />
          </Tooltip>
        ))}
      </div>
      <Space size={12} wrap style={{ marginTop: 6 }}>
        {segs.map((s) => (
          <span key={s.label} style={{ fontSize: 11 }}>
            <span style={{ display: "inline-block", width: 8, height: 8, background: colors[s.label], marginRight: 4 }} />
            {s.label} {s.n}
          </span>
        ))}
        {summary.no_vote > 0 && (
          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
            {summary.no_vote} 只所有指标都弃权或无数据，没有可用的表决
          </Typography.Text>
        )}
      </Space>
    </Card>
  );
}
