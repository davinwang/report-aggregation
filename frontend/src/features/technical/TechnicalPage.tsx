// 技术指标 — three tabs over the same security: its K-line chart, the cross-market
// technical signal matrix, and the indicator reference.
//
// Route: /technical and /technical/:code
//
// The chart tab fetches exactly the indicators the user has switched on (overlays +
// sub-panes), because /api/quant/series computes server-side and every extra indicator
// costs Python time on every request — the old build always fetched a fixed 12.
import { useMemo, useState } from "react";
import { Card, Input, Segmented, Select, Space, Switch, Tabs, Tooltip, Typography } from "antd";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getIndicatorCatalog, getSeries } from "@/api";
import type { BarFreq } from "@/types";
import PageContainer from "@/components/PageContainer";
import KLineChart, { MAX_SUB_PANES, VOLUME_PANE } from "@/components/KLineChart";
import ProvenanceTag from "@/components/ProvenanceTag";
import PageRefresh from "@/components/PageRefresh";
import IndicatorPicker from "./IndicatorPicker";
import IndicatorReference from "./IndicatorReference";
import SignalMatrixPanel from "./SignalMatrixPanel";
import { useUIStore } from "@/stores/uiStore";

const PRESETS: { value: string; label: string }[] = [
  { value: "sh000300", label: "沪深300" },
  { value: "sh000001", label: "上证指数" },
  { value: "sh000905", label: "中证500" },
  { value: "sh000852", label: "中证1000" },
  { value: "sh000016", label: "上证50" },
  { value: "sz399006", label: "创业板指" },
  { value: "sh000688", label: "科创50" },
  { value: "510300", label: "沪深300ETF" },
  { value: "512880", label: "证券ETF" },
];

const PERIODS = [
  { value: "6m", label: "6个月" },
  { value: "1y", label: "1年" },
  { value: "2y", label: "2年" },
  { value: "3y", label: "3年" },
  { value: "5y", label: "5年" },
];

const FREQS: { value: BarFreq; label: string }[] = [
  { value: "daily", label: "日线" },
  { value: "weekly", label: "周线" },
  { value: "monthly", label: "月线" },
];

// 指数 with a market prefix; everything else is a bare 6-digit code.
const ADJUSTS = [
  { value: "", label: "自动", disabled: true },
  { value: "qfq", label: "前复权" },
  { value: "hfq", label: "后复权" },
  { value: "raw", label: "不复权" },
  { value: "none", label: "原始" },
];

const DEFAULT_OVERLAYS = ["ma", "boll"];
const DEFAULT_SUBS = ["vol", "macd", "kdj"];

export default function TechnicalPage() {
  const { code: codeParam } = useParams();
  const navigate = useNavigate();
  const mode = useUIStore((s) => s.mode);
  const dark = mode === "dark";

  const code = codeParam || "sh000300";
  const [tab, setTab] = useState("chart");
  const [period, setPeriod] = useState("1y");
  const [freq, setFreq] = useState<BarFreq>("daily");
  const [adjust, setAdjust] = useState("");
  const [overlays, setOverlays] = useState<string[]>(DEFAULT_OVERLAYS);
  const [subs, setSubs] = useState<string[]>(DEFAULT_SUBS);
  const [input, setInput] = useState("");
  const [zoomStart, setZoomStart] = useState(60);

  const { data: catalog } = useQuery({
    queryKey: ["quant", "indicator-catalog"],
    queryFn: () => getIndicatorCatalog(),
    staleTime: 600_000,
  });

  // Only what's actually drawn gets computed server-side.
  const subKeys = subs.filter((k) => k !== VOLUME_PANE);
  const requested = useMemo(() => [...new Set([...overlays, ...subKeys])], [overlays, subKeys]);

  const { data, isFetching, isError } = useQuery({
    queryKey: ["quant", "series", code, period, freq, adjust, requested.join(",")],
    queryFn: () =>
      getSeries({
        code,
        indicators: requested.join(","),
        period,
        freq,
        ...(adjust ? { adjust } : {}),
      }),
    staleTime: 30_000,
  });

  const empty = !isFetching && (isError || !data || data.dates.length === 0);

  // A new symbol should open at the default zoom, not inherit the last code's window.
  const onCodeChange = (next: string) => {
    setZoomStart(60);
    navigate(`/technical/${next}`);
  };

  const chart = (
    <>
      <Card size="small" style={{ marginBottom: 12 }}>
        <Space direction="vertical" size={8} style={{ width: "100%" }}>
          <Space wrap>
            <Segmented
              size="small"
              options={PRESETS}
              value={PRESETS.some((p) => p.value === code) ? code : undefined}
              onChange={(v) => onCodeChange(String(v))}
            />
            <Input.Search
              size="small"
              placeholder="输入代码回车 (600519 / sh000300 / 510300 / 113050)"
              style={{ width: 280 }}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onSearch={(v) => v && onCodeChange(v.trim())}
            />
            <Segmented size="small" options={FREQS} value={freq} onChange={(v) => setFreq(v as BarFreq)} />
            <Select size="small" value={period} onChange={setPeriod} style={{ width: 96 }} options={PERIODS} />
            <Select
              size="small"
              value={adjust}
              onChange={setAdjust}
              style={{ width: 96 }}
              options={ADJUSTS}
            />
            <Tooltip title="指数不带复权概念，此项只对个股/ETF/转债有意义">
              <span>
                <Typography.Text className="muted" style={{ fontSize: 11 }}>复权</Typography.Text>
              </span>
            </Tooltip>
            <Typography.Text strong>{code}</Typography.Text>
          </Space>
          <IndicatorPicker
            catalog={catalog ?? []}
            overlays={overlays}
            subs={subs}
            loading={isFetching && !data}
            onOverlays={setOverlays}
            onSubs={setSubs}
          />
        </Space>
      </Card>

      <Card
        size="small"
        loading={isFetching && !data}
        extra={
          <Space size={6}>
            <Typography.Text className="muted" style={{ fontSize: 11 }}>
              缩放
            </Typography.Text>
            <Switch size="small" checked={zoomStart === 100} onChange={(on) => setZoomStart(on ? 100 : 60)} />
            <Typography.Text className="muted" style={{ fontSize: 11 }}>
              全区间
            </Typography.Text>
          </Space>
        }
      >
        {empty ? (
          <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
            暂无 {code} 的行情数据。请先运行 <Typography.Text code>price_history</Typography.Text> 采集，
            或确认代码是否正确（个股/ETF/转债为 6 位代码，指数带 sh/sz 前缀）。
          </Typography.Paragraph>
        ) : (
          data && (
            <KLineChart
              series={data}
              subs={subs}
              overlays={overlays}
              height={560 + MAX_SUB_PANES * 90}
              zoomStart={zoomStart}
            />
          )
        )}
      </Card>
    </>
  );

  return (
    <PageContainer
      title="技术指标"
      description={`K线 + ${catalog?.length ?? 42} 个技术指标（服务端计算）· 跨品种信号矩阵 · 日/周/月线`}
      extra={
        <Space>
          <ProvenanceTag source="em" />
          <PageRefresh
            queryKeys={[["quant", "series"], ["quant", "signal-matrix"], ["quant", "indicator-catalog"]]}
            feeds={["price_history", "index_daily", "etf_daily", "cov_bond_daily"]}
          />
        </Space>
      }
    >
      <Tabs
        activeKey={tab}
        onChange={setTab}
        size="small"
        items={[
          { key: "chart", label: "单标的图表", children: chart },
          { key: "matrix", label: "技术信号矩阵", children: <SignalMatrixPanel dark={dark} /> },
          { key: "ref", label: "指标说明", children: <IndicatorReference /> },
        ]}
      />
    </PageContainer>
  );
}
