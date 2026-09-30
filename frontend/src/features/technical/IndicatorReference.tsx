// 指标说明 — the backend's indicator catalog rendered as reference cards.
//
// Sourced from /api/quant/indicator-catalog rather than hard-coded, so a formula change in
// the engine shows up here without a frontend edit, and an indicator that exists but is
// missing metadata fails loudly in the catalog's own test instead of silently vanishing
// from the docs.
import { useMemo, useState } from "react";
import { Card, Empty, Input, Segmented, Space, Table, Tag, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useQuery } from "@tanstack/react-query";
import { getIndicatorCatalog } from "@/api";
import type { IndicatorMeta } from "@/types";

export default function IndicatorReference() {
  const [q, setQ] = useState("");
  const [pane, setPane] = useState("all");

  const { data, isFetching } = useQuery({
    queryKey: ["quant", "indicator-catalog"],
    queryFn: () => getIndicatorCatalog(),
    staleTime: 600_000,
  });

  const items = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (data ?? []).filter((item) => {
      if (pane !== "all" && item.pane !== pane) return false;
      if (!needle) return true;
      return (
        item.label.toLowerCase().includes(needle) ||
        item.key.toLowerCase().includes(needle) ||
        item.desc.toLowerCase().includes(needle) ||
        item.aliases.some((a) => a.toLowerCase().includes(needle))
      );
    });
  }, [data, q, pane]);

  const groups = useMemo(
    () => [...new Set((data ?? []).map((i) => i.group))],
    [data],
  );

  const columns: ColumnsType<IndicatorMeta> = [
    {
      title: "指标",
      dataIndex: "label",
      width: 190,
      fixed: "left",
      render: (label: string, r) => (
        <span>
          <b>{label}</b>
          <Typography.Text type="secondary" style={{ marginLeft: 6, fontSize: 11 }}>
            {r.key}
          </Typography.Text>
        </span>
      ),
    },
    {
      title: "分类",
      dataIndex: "group",
      width: 72,
      render: (g: string) => <Tag style={{ marginInlineEnd: 0 }}>{g}</Tag>,
    },
    {
      title: "位置",
      dataIndex: "pane",
      width: 66,
      render: (p: string) => (
        <Tag color={p === "main" ? "volcano" : "cyan"} style={{ marginInlineEnd: 0 }}>
          {p === "main" ? "主图" : "副图"}
        </Tag>
      ),
    },
    {
      title: "输出线",
      dataIndex: "columns",
      width: 190,
      render: (cols: string[]) => (
        <Tooltip title={cols.join(" / ")}>
          <Typography.Text className="muted" ellipsis style={{ maxWidth: 180, fontSize: 11 }}>
            {cols.join(" / ")}
          </Typography.Text>
        </Tooltip>
      ),
    },
    {
      title: "默认参数",
      dataIndex: "params",
      width: 150,
      render: (params: Record<string, unknown>) => (
        <Typography.Text className="muted" style={{ fontSize: 11 }}>
          {Object.entries(params)
            .map(([k, v]) => `${k}=${Array.isArray(v) ? v.join("/") : String(v)}`)
            .join("  ") || "-"}
        </Typography.Text>
      ),
    },
    { title: "说明", dataIndex: "desc", render: (d: string) => <span style={{ lineHeight: 1.7 }}>{d}</span> },
  ];

  return (
    <Card
      size="small"
      title="指标说明与公式口径"
      extra={
        <Space wrap size={6}>
          <Input.Search
            size="small"
            allowClear
            placeholder="搜索指标 / 别名 / 公式"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            style={{ width: 200 }}
          />
          <Segmented
            size="small"
            value={pane}
            onChange={(v) => setPane(String(v))}
            options={[
              { value: "all", label: "全部" },
              { value: "main", label: "主图" },
              { value: "sub", label: "副图" },
            ]}
          />
        </Space>
      }
    >
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        共 {data?.length ?? 0} 个指标，分为 {groups.length} 类：{groups.join(" · ")}。
        公式口径按通达信/同花顺的通用定义实现，与行情终端可能存在细微差异，数值仅供内部研究参考，不构成投资建议。
      </Typography.Paragraph>
      <Table
        size="small"
        rowKey="key"
        loading={isFetching}
        dataSource={items}
        columns={columns}
        scroll={{ x: 900 }}
        pagination={false}
      />
      {!items.length && !isFetching && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的指标" />}
    </Card>
  );
}
