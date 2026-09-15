// T型报价 (T-board) — option chain: calls on the left, puts on the right, strikes in
// the middle. The ATM strike row (closest to spot) is highlighted.
import { Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { OptionBoard, OptionBoardRow } from "@/types";
import { fmtNum } from "@/hooks/useRelativeTime";
import { changeColor } from "@/styles/theme";

interface Props {
  board: OptionBoard;
  loading?: boolean;
  height?: number;
}

function num(v: number | null | undefined, digits = 1): string {
  return v == null ? "-" : fmtNum(v, digits);
}

function updown(v: number | null | undefined) {
  return (
    <span style={{ color: changeColor(v ?? null), fontVariantNumeric: "tabular-nums" }}>
      {v == null ? "-" : `${v > 0 ? "+" : ""}${fmtNum(v, 1)}`}
    </span>
  );
}

export default function OptionTBoard({ board, loading, height = 520 }: Props) {
  const columns: ColumnsType<OptionBoardRow> = [
    {
      title: "看涨期权 Call",
      children: [
        { title: "最新价", align: "right", width: 82, render: (_, r) => num(r.call?.last) },
        { title: "涨跌", align: "right", width: 80, render: (_, r) => updown(r.call?.updown) },
        { title: "成交量", align: "right", width: 82, render: (_, r) => num(r.call?.volume, 0) },
        { title: "持仓量", align: "right", width: 82, render: (_, r) => num(r.call?.oi, 0) },
      ],
    },
    {
      title: "行权价",
      dataIndex: "strike",
      align: "center",
      width: 96,
      render: (v: number) => (
        <Typography.Text strong style={{ fontVariantNumeric: "tabular-nums" }}>
          {fmtNum(v, 0)}
        </Typography.Text>
      ),
    },
    {
      title: "看跌期权 Put",
      children: [
        { title: "持仓量", align: "right", width: 82, render: (_, r) => num(r.put?.oi, 0) },
        { title: "成交量", align: "right", width: 82, render: (_, r) => num(r.put?.volume, 0) },
        { title: "涨跌", align: "right", width: 80, render: (_, r) => updown(r.put?.updown) },
        { title: "最新价", align: "right", width: 82, render: (_, r) => num(r.put?.last) },
      ],
    },
  ];

  return (
    <Table
      size="small"
      rowKey="strike"
      loading={loading}
      pagination={false}
      dataSource={board.rows}
      columns={columns}
      scroll={{ y: height, x: 800 }}
      locale={{ emptyText: "暂无期权数据" }}
      onRow={(r) =>
        r.strike === board.atm_strike
          ? { style: { background: "rgba(200,22,29,0.07)", fontWeight: 600 } }
          : {}
      }
    />
  );
}
