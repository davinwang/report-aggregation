// 财务数据 — a NEW module for the stock version: 关键指标 / 业绩 / 三大报表 / 公告披露.
// Route: /financials and /financials/:code
import { useMemo, useState } from "react";
import { Card, Input, Space, Table, Tabs, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getDisclosures, getEarnings, getFinancialIndicators, getStatements } from "@/api";
import type { FinancialIndicatorRow } from "@/types";
import PageContainer from "@/components/PageContainer";
import ProvenanceTag from "@/components/ProvenanceTag";
import PageRefresh from "@/components/PageRefresh";
import { fmtAmount, fmtDate, fmtNum, fmtPct } from "@/hooks/useRelativeTime";

// Common 东财 statement field codes → Chinese labels (fallback to the raw code).
const FIELD_LABELS: Record<string, string> = {
  MONETARYFUNDS: "货币资金", ACCOUNTS_RECE: "应收账款", INVENTORY: "存货",
  TOTAL_CURRENT_ASSETS: "流动资产合计", FIXED_ASSET: "固定资产", TOTAL_ASSETS: "资产总计",
  SHORT_LOAN: "短期借款", ACCOUNTS_PAYABLE: "应付账款", TOTAL_CURRENT_LIAB: "流动负债合计",
  TOTAL_LIABILITIES: "负债合计", TOTAL_EQUITY: "所有者权益合计", TOTAL_PARENT_EQUITY: "归母股东权益",
  OPERATE_INCOME: "营业总收入", OPERATE_COST: "营业总成本", OPERATE_EXPENSE: "销售费用",
  MANAGE_EXPENSE: "管理费用", RESEARCH_EXPENSE: "研发费用", FINANCE_EXPENSE: "财务费用",
  OPERATE_PROFIT: "营业利润", TOTAL_PROFIT: "利润总额", INCOME_TAX: "所得税",
  NETPROFIT: "净利润", PARENT_NETPROFIT: "归母净利润", BASIC_EPS: "基本每股收益",
  NETCASH_OPERATE: "经营活动现金流净额", NETCASH_INVEST: "投资活动现金流净额",
  NETCASH_FINANCE: "筹资活动现金流净额",
};

function StatementView({ code, type }: { code: string; type: "balance" | "income" | "cashflow" }) {
  const { data } = useQuery({
    queryKey: ["fin", "statements", code, type],
    queryFn: () => getStatements(code, type, "em", 8),
    enabled: !!code,
    staleTime: 60_000,
  });
  const periods = (data ?? []).map((d) => d.report_period);
  const rows = useMemo(() => {
    const first = data?.[0]?.data ?? {};
    const keys = Object.keys(FIELD_LABELS).filter((k) => k in first);
    return keys.map((k) => {
      const row: Record<string, unknown> = { key: k, field: FIELD_LABELS[k] };
      (data ?? []).forEach((d) => {
        const v = d.data[k];
        row[d.report_period] = typeof v === "number" ? fmtAmount(v) : (v as string) ?? "-";
      });
      return row;
    });
  }, [data]);

  const columns: ColumnsType<Record<string, unknown>> = [
    { title: "科目", dataIndex: "field", fixed: "left", width: 160 },
    ...periods.map((p) => ({ title: fmtDate(p, "YY/MM/DD"), dataIndex: p, width: 130, align: "right" as const })),
  ];

  if (!data?.length) return <Typography.Text type="secondary">暂无报表数据（请运行 financials_em 采集）</Typography.Text>;
  return <Table size="small" rowKey="key" columns={columns} dataSource={rows} pagination={false} scroll={{ x: "max-content" }} />;
}

export default function FinancialsPage() {
  const { code: codeParam } = useParams();
  const navigate = useNavigate();
  const code = codeParam || "";
  const [input, setInput] = useState("");

  const ind = useQuery({
    queryKey: ["fin", "indicators", code],
    queryFn: () => getFinancialIndicators(code),
    enabled: !!code,
    staleTime: 60_000,
  });
  const earn = useQuery({
    queryKey: ["fin", "earnings", code],
    queryFn: () => getEarnings(code),
    enabled: !!code,
    staleTime: 60_000,
  });
  const disc = useQuery({
    queryKey: ["fin", "disclosures", code],
    queryFn: () => getDisclosures(code, { size: 30 }).then((r) => r.data),
    enabled: !!code,
    staleTime: 60_000,
  });

  const indCols: ColumnsType<FinancialIndicatorRow> = [
    { title: "报告期", dataIndex: "report_period", render: (v: string) => fmtDate(v, "YYYY-MM-DD") },
    { title: "EPS", dataIndex: "eps", render: (v) => fmtNum(v) },
    { title: "BPS", dataIndex: "bps", render: (v) => fmtNum(v) },
    { title: "ROE%", dataIndex: "roe", render: (v) => fmtNum(v) },
    { title: "营收同比%", dataIndex: "revenue_yoy", render: (v) => fmtPct(v) },
    { title: "净利同比%", dataIndex: "net_profit_yoy", render: (v) => fmtPct(v) },
    { title: "毛利率%", dataIndex: "gross_margin", render: (v) => fmtNum(v) },
    { title: "净利率%", dataIndex: "net_margin", render: (v) => fmtNum(v) },
    { title: "资产负债率%", dataIndex: "debt_ratio", render: (v) => fmtNum(v) },
  ];

  return (
    <PageContainer
      title="财务数据"
      description="关键指标 / 业绩 / 三大报表 / 公告披露（来源：东方财富、巨潮资讯、新浪财经）"
      extra={<Space><ProvenanceTag source="em" /><PageRefresh queryKeys={[["fin"]]} feeds={["financials_em", "fin_indicators", "disclosures"]} /></Space>}
    >
      <Card size="small" style={{ marginBottom: 12 }}>
        <Input.Search
          placeholder="输入股票代码回车 (如 600519)"
          style={{ width: 280 }}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onSearch={(v) => v && navigate(`/financials/${v.trim()}`)}
          enterButton="查询"
        />
        {code && <Tag color="blue" style={{ marginLeft: 12 }}>{code}</Tag>}
      </Card>

      {!code ? (
        <Card size="small">
          <Typography.Text type="secondary">请输入股票代码查看财务数据。</Typography.Text>
        </Card>
      ) : (
        <Card size="small">
          <Tabs
            items={[
              {
                key: "ind",
                label: "关键指标",
                children: (
                  <Table<FinancialIndicatorRow>
                    size="small" rowKey="report_period" loading={ind.isFetching}
                    columns={indCols} dataSource={ind.data ?? []} pagination={false} scroll={{ x: "max-content" }}
                  />
                ),
              },
              {
                key: "earn",
                label: "业绩报表",
                children: (
                  <Table
                    size="small" rowKey="report_period" loading={earn.isFetching}
                    dataSource={(earn.data ?? []) as Record<string, unknown>[]}
                    pagination={false} scroll={{ x: "max-content" }}
                    columns={[
                      { title: "报告期", dataIndex: "report_period", render: (v: string) => fmtDate(v, "YYYY-MM-DD") },
                      { title: "营收", dataIndex: "revenue", render: (v) => fmtAmount(v as number) },
                      { title: "营收同比", dataIndex: "revenue_yoy", render: (v) => fmtPct(v as number) },
                      { title: "净利润", dataIndex: "net_profit", render: (v) => fmtAmount(v as number) },
                      { title: "净利同比", dataIndex: "net_profit_yoy", render: (v) => fmtPct(v as number) },
                      { title: "EPS", dataIndex: "eps", render: (v) => fmtNum(v as number) },
                      { title: "ROE%", dataIndex: "roe", render: (v) => fmtNum(v as number) },
                    ]}
                  />
                ),
              },
              { key: "balance", label: "资产负债表", children: <StatementView code={code} type="balance" /> },
              { key: "income", label: "利润表", children: <StatementView code={code} type="income" /> },
              { key: "cashflow", label: "现金流量表", children: <StatementView code={code} type="cashflow" /> },
              {
                key: "disc",
                label: "公告披露",
                children: (
                  <Table
                    size="small" rowKey={(r) => `${r.ann_date}-${r.title}`} loading={disc.isFetching}
                    dataSource={(disc.data ?? []) as Record<string, unknown>[]}
                    pagination={{ pageSize: 15 }}
                    columns={[
                      { title: "日期", dataIndex: "ann_date", width: 120 },
                      {
                        title: "标题", dataIndex: "title",
                        render: (t: string, r) =>
                          r.url ? <a href={String(r.url)} target="_blank" rel="noreferrer">{t}</a> : t,
                      },
                      { title: "类型", dataIndex: "category", width: 120, render: (v) => v ? <Tag>{v}</Tag> : "-" },
                    ]}
                  />
                ),
              },
            ]}
          />
        </Card>
      )}
    </PageContainer>
  );
}
