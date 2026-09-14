// 技术指标 — server-computed K-line + indicators for a stock/index.
// Route: /technical and /technical/:code
import { useState } from "react";
import { Card, Input, Segmented, Select, Space, Typography } from "antd";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getSeries } from "@/api";
import PageContainer from "@/components/PageContainer";
import KLineChart from "@/components/KLineChart";
import ProvenanceTag from "@/components/ProvenanceTag";

// Fetched indicator set (overlays + sub-pane candidates).
const FETCH_INDICATORS = "ma,boll,macd,kdj,rsi,dmi,cci,wr,bias,atr,obv,mavol";

const PRESETS = [
  { value: "sh000300", label: "沪深300" },
  { value: "sh000001", label: "上证指数" },
  { value: "sh000905", label: "中证500" },
  { value: "sh000016", label: "上证50" },
  { value: "sz399006", label: "创业板指" },
];

const SUB_OPTIONS = [
  { value: "vol", label: "成交量" },
  { value: "macd", label: "MACD" },
  { value: "kdj", label: "KDJ" },
  { value: "rsi", label: "RSI" },
  { value: "dmi", label: "DMI" },
  { value: "cci", label: "CCI" },
  { value: "wr", label: "WR" },
  { value: "bias", label: "BIAS" },
  { value: "atr", label: "ATR" },
  { value: "obv", label: "OBV" },
];

export default function TechnicalPage() {
  const { code: codeParam } = useParams();
  const navigate = useNavigate();
  const code = codeParam || "sh000300";
  const [sub, setSub] = useState("vol");
  const [period, setPeriod] = useState("1y");
  const [input, setInput] = useState("");

  const { data, isFetching, isError } = useQuery({
    queryKey: ["quant", "series", code, period],
    queryFn: () => getSeries({ code, indicators: FETCH_INDICATORS, period }),
    staleTime: 30_000,
  });

  const empty = !isFetching && (isError || !data || data.dates.length === 0);

  return (
    <PageContainer
      title="技术指标"
      description="K线 + 30+ 技术指标（服务端计算，前复权）"
      extra={<ProvenanceTag source="em" />}
    >
      <Card size="small" style={{ marginBottom: 12 }}>
        <Space wrap>
          <Segmented
            options={PRESETS}
            value={PRESETS.some((p) => p.value === code) ? code : undefined}
            onChange={(v) => navigate(`/technical/${v}`)}
          />
          <Input.Search
            placeholder="输入代码回车 (如 600519 / sh000300)"
            style={{ width: 240 }}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onSearch={(v) => v && navigate(`/technical/${v.trim()}`)}
          />
          <Select value={sub} onChange={setSub} options={SUB_OPTIONS} style={{ width: 120 }} size="middle" />
          <Select
            value={period}
            onChange={setPeriod}
            style={{ width: 120 }}
            options={[
              { value: "6m", label: "6个月" },
              { value: "1y", label: "1年" },
              { value: "2y", label: "2年" },
              { value: "3y", label: "3年" },
              { value: "5y", label: "5年" },
            ]}
          />
          <Typography.Text strong>{code}</Typography.Text>
        </Space>
      </Card>

      <Card size="small" loading={isFetching && !data}>
        {empty ? (
          <Typography.Paragraph type="secondary">
            暂无 {code} 的行情数据。请先运行 <Typography.Text code>price_history</Typography.Text> 采集，
            或确认代码是否正确（个股为6位代码，指数带 sh/sz 前缀）。
          </Typography.Paragraph>
        ) : (
          data && <KLineChart series={data} sub={sub} height={600} />
        )}
      </Card>
    </PageContainer>
  );
}
