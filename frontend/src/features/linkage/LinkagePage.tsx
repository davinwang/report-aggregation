// 板块/指数联动 — 指数相关性矩阵 + 个股 Beta (vs 沪深300).
// Route: /linkage
import { useState } from "react";
import { Card, Col, Row, Segmented, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getLinkageBeta, getLinkageMatrix } from "@/api";
import type { BetaRow, LinkagePair } from "@/types";
import PageContainer from "@/components/PageContainer";
import RankingBar from "@/components/RankingBar";
import ProvenanceTag from "@/components/ProvenanceTag";
import StatCard from "@/components/StatCard";
import { DOWN_COLOR, UP_COLOR } from "@/styles/theme";
import { fmtNum } from "@/hooks/useRelativeTime";

function corrBg(v: number | null): string {
  if (v == null) return "transparent";
  const t = Math.min(1, Math.abs(v));
  return v >= 0
    ? `rgba(228,57,60,${(0.08 + 0.55 * t).toFixed(3)})`
    : `rgba(47,168,79,${(0.08 + 0.55 * t).toFixed(3)})`;
}

export default function LinkagePage() {
  const [window, setWindow] = useState(120);

  const { data: matrix, isFetching: mFetching } = useQuery({
    queryKey: ["linkage", "matrix", window],
    queryFn: () => getLinkageMatrix(window),
    staleTime: 120_000,
  });
  const { data: beta, isFetching: bFetching } = useQuery({
    queryKey: ["linkage", "beta", window],
    queryFn: () => getLinkageBeta({ window, limit: 100 }),
    staleTime: 120_000,
  });

  const codes = matrix?.codes ?? [];
  const names = matrix?.names ?? [];
  const mx = matrix?.matrix ?? [];
  const pairs = matrix?.pairs ?? [];
  const betas = beta?.rows ?? [];

  const matrixColumns: ColumnsType<number> = [
    {
      title: "指数",
      key: "name",
      width: 120,
      fixed: "left",
      render: (_: unknown, __: number, idx: number) => (
        <Typography.Text strong>{names[idx] ?? codes[idx]}</Typography.Text>
      ),
    },
    ...codes.map((_c, j) => ({
      title: names[j] ?? codes[j],
      key: `c${j}`,
      width: 92,
      align: "center" as const,
      render: (_: unknown, __: number, i: number) => {
        const v = mx[i]?.[j];
        return (
          <span
            style={{
              display: "inline-block",
              minWidth: 52,
              padding: "2px 4px",
              borderRadius: 3,
              background: corrBg(v),
              color: v != null && Math.abs(v) > 0.7 ? "#fff" : undefined,
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {v == null ? "-" : fmtNum(v, 2)}
          </span>
        );
      },
    })),
  ];

  const pairColumns: ColumnsType<LinkagePair> = [
    {
      title: "组合",
      key: "pair",
      render: (_, p) => (
        <span>
          {p.a_name} <span className="muted">×</span> {p.b_name}
        </span>
      ),
    },
    {
      title: "相关系数",
      dataIndex: "corr",
      align: "right",
      width: 100,
      render: (v: number) => (
        <span style={{ color: v >= 0 ? UP_COLOR : DOWN_COLOR, fontVariantNumeric: "tabular-nums" }}>
          {fmtNum(v, 3)}
        </span>
      ),
    },
  ];

  const betaColumns: ColumnsType<BetaRow> = [
    {
      title: "证券",
      dataIndex: "name",
      render: (name: string, r) => <Link to={`/stock/${r.code}`}>{name}</Link>,
    },
    {
      title: "β (Beta)",
      dataIndex: "beta",
      align: "right",
      width: 90,
      sorter: (a, b) => a.beta - b.beta,
      render: (v: number) => (
        <span style={{ color: v > 1.2 ? UP_COLOR : v < 0.8 ? DOWN_COLOR : undefined, fontVariantNumeric: "tabular-nums" }}>
          {fmtNum(v, 2)}
        </span>
      ),
    },
    { title: "ρ²", dataIndex: "r2", align: "right", width: 76, render: (v: number) => fmtNum(v, 2) },
    { title: "相关系数", dataIndex: "corr", align: "right", width: 90, render: (v: number) => fmtNum(v, 2) },
    { title: "年化波动", dataIndex: "vol", align: "right", width: 96, render: (v: number) => `${fmtNum(v * 100, 1)}%` },
    { title: "样本", dataIndex: "samples", align: "right", width: 70 },
  ];

  const strongest = pairs[0];

  return (
    <PageContainer
      title="板块/指数联动"
      description="指数间相关性矩阵 + 个股 Beta — 基于已采集日线收益（滚动窗口）"
      extra={
        <Space wrap>
          <ProvenanceTag source="exchange" date={matrix?.ref ?? null} />
          <Segmented
            size="small"
            value={window}
            onChange={(v) => setWindow(Number(v))}
            options={[
              { value: 60, label: "60日" },
              { value: 120, label: "120日" },
              { value: 250, label: "250日" },
            ]}
          />
        </Space>
      }
    >
      <div className="grid-cards" style={{ marginBottom: 12 }}>
        <StatCard title="样本交易日" value={matrix?.samples ?? "-"} footer={`窗口 ${window} 日`} loading={mFetching && !matrix} />
        <StatCard
          title="最强联动组合"
          value={strongest ? fmtNum(strongest.corr, 2) : "-"}
          footer={strongest ? `${strongest.a_name} × ${strongest.b_name}` : "-"}
          loading={mFetching && !matrix}
        />
        <StatCard title="覆盖指数" value={codes.length} footer="有完整历史行情的指数" loading={mFetching && !matrix} />
        <StatCard
          title="个股 Beta 样本"
          value={betas.length}
          footer={beta?.benchmark_name ? `基准 ${beta.benchmark_name}` : "需先采集 price_history"}
          loading={bFetching && !beta}
        />
      </div>

      <Card size="small" title={`指数相关性矩阵 (近${window}个交易日收益)`} style={{ marginBottom: 12 }}>
        {codes.length ? (
          <Table
            size="small"
            rowKey={(_: unknown, i?: number) => String(i)}
            loading={mFetching}
            dataSource={codes.map((_, i) => i)}
            columns={matrixColumns}
            pagination={false}
            scroll={{ x: 900 }}
          />
        ) : (
          <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
            暂无指数行情数据。请先采集 <Typography.Text code>index_daily</Typography.Text>。
          </Typography.Paragraph>
        )}
      </Card>

      <Row gutter={12}>
        <Col xs={24} xl={10}>
          <Card size="small" title="最强联动组合 (|ρ| Top10)" style={{ marginBottom: 12 }}>
            <Table
              size="small"
              rowKey={(p) => `${p.a}-${p.b}`}
              loading={mFetching}
              dataSource={pairs}
              columns={pairColumns}
              pagination={false}
              locale={{ emptyText: "暂无数据" }}
            />
          </Card>
          <Card size="small" title="Beta 分布 (Top15)">
            {betas.length ? (
              <RankingBar
                items={betas.slice(0, 15).map((b) => ({ name: b.name, value: b.beta }))}
                height={320}
              />
            ) : (
              <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
                暂无个股日线数据，采集 <Typography.Text code>price_history</Typography.Text> 后展示。
              </Typography.Paragraph>
            )}
          </Card>
        </Col>
        <Col xs={24} xl={14}>
          <Card size="small" title="个股 Beta 明细">
            <Table
              size="small"
              rowKey="code"
              loading={bFetching}
              dataSource={betas}
              columns={betaColumns}
              pagination={{ pageSize: 15, size: "small", showSizeChanger: false }}
              locale={{ emptyText: "暂无数据。请先采集 price_history（个股日线）。" }}
            />
            <Typography.Paragraph className="muted" style={{ margin: "10px 0 0", fontSize: 12 }}>
              <b>β</b> = 个股收益对基准收益的敏感度（β&gt;1 波动放大）；<b>ρ²</b> 为可解释方差比例；
              样本为与基准的共同交易日数量。窗口滚动更新，不做存储。
            </Typography.Paragraph>
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
