// 资讯舆情 — 东财全球快讯 + 财联社电报, 规则情绪标注 (利好/中性/利空) + 关联个股.
// 无 LLM — 情绪为词表规则派生 (与平台"无 AI、规则可解释"哲学一致)。Route: /news
import { useState } from "react";
import { Card, DatePicker, Input, List, Select, Space, Tag, Typography } from "antd";
import { LinkOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import dayjs, { Dayjs } from "dayjs";
import { getNews, getNewsSummary } from "@/api";
import type { NewsItem } from "@/types";
import PageContainer from "@/components/PageContainer";
import FreshnessBadge from "@/components/FreshnessBadge";
import ProvenanceTag from "@/components/ProvenanceTag";
import StatCard from "@/components/StatCard";

const { RangePicker } = DatePicker;
const { Paragraph, Text } = Typography;

const SOURCE_META: Record<string, { label: string; color: string }> = {
  em: { label: "东财快讯", color: "geekblue" },
  cls: { label: "财联社", color: "orange" },
};

// 中国色惯例: 利好红 / 利空绿 / 中性灰 (与平台 UP_COLOR/DOWN_COLOR 同向).
const SENTIMENT_COLOR: Record<string, string> = { 利好: "red", 利空: "green", 中性: "default" };

const SENTIMENT_OPTIONS = [
  { value: "利好", label: "利好" },
  { value: "中性", label: "中性" },
  { value: "利空", label: "利空" },
];

const SOURCE_OPTIONS = [
  { value: "em", label: "东财快讯" },
  { value: "cls", label: "财联社" },
];

function itemTime(publishAt: string): string {
  const t = dayjs(publishAt);
  if (!t.isValid()) return publishAt;
  return t.isSame(dayjs(), "day") ? t.format("HH:mm") : t.format("MM-DD HH:mm");
}

export default function NewsPage() {
  const [keyword, setKeyword] = useState("");
  const [sentiment, setSentiment] = useState<string | undefined>();
  const [source, setSource] = useState<string | undefined>();
  const [range, setRange] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(30);

  const { data: summary } = useQuery({
    queryKey: ["news", "summary", 1],
    queryFn: () => getNewsSummary(1),
    staleTime: 60_000,
  });

  const params = {
    q: keyword || undefined,
    sentiment,
    source,
    start: range?.[0] ? range[0].format("YYYY-MM-DD") : undefined,
    end: range?.[1] ? range[1].format("YYYY-MM-DD") : undefined,
    page,
    size,
  };
  const { data, isFetching } = useQuery({
    queryKey: ["news", "list", params],
    queryFn: () => getNews(params),
    placeholderData: (prev) => prev,
    staleTime: 30_000,
  });

  const rows: NewsItem[] = data?.rows ?? [];
  const total = data?.meta?.total ?? 0;
  const counts = summary?.data?.by_sentiment ?? {};

  return (
    <PageContainer
      title="资讯舆情"
      description={`共 ${total} 条快讯 · 数据来源 东方财富/财联社 · 情绪为词表规则标注`}
      extra={
        <Space size={6}>
          <FreshnessBadge feed="资讯" freshness={summary?.freshness} />
          <ProvenanceTag source="em" />
        </Space>
      }
    >
      <div className="grid-cards" style={{ marginBottom: 12 }}>
        <StatCard
          title="当日快讯"
          value={summary?.data?.total ?? 0}
          footer={`截至 ${summary?.data?.ref ?? "-"}`}
          loading={!summary}
        />
        <StatCard title="利好" value={counts["利好"] ?? 0} footer="词表命中正面词" loading={!summary} />
        <StatCard title="利空" value={counts["利空"] ?? 0} footer="词表命中负面词" loading={!summary} />
        <StatCard title="中性" value={counts["中性"] ?? 0} footer="无显著情绪倾向" loading={!summary} />
      </div>

      <Card size="small" style={{ marginBottom: 12 }}>
        <Space wrap>
          <Input.Search
            allowClear
            placeholder="搜索标题/内容"
            style={{ width: 240 }}
            onSearch={(v) => {
              setKeyword(v);
              setPage(1);
            }}
          />
          <Select
            allowClear
            placeholder="情绪"
            style={{ width: 110 }}
            value={sentiment}
            onChange={(v) => {
              setSentiment(v);
              setPage(1);
            }}
            options={SENTIMENT_OPTIONS}
          />
          <Select
            allowClear
            placeholder="来源"
            style={{ width: 130 }}
            value={source}
            onChange={(v) => {
              setSource(v);
              setPage(1);
            }}
            options={SOURCE_OPTIONS}
          />
          <RangePicker
            onChange={(v) => {
              setRange(v as [Dayjs | null, Dayjs | null] | null);
              setPage(1);
            }}
          />
        </Space>
      </Card>

      <Card size="small">
        <List
          loading={isFetching && !rows.length}
          itemLayout="vertical"
          size="small"
          dataSource={rows}
          rowKey={(r) => r.id}
          renderItem={(r) => {
            const src = SOURCE_META[r.source] ?? { label: r.source, color: "default" };
            return (
              <List.Item
                key={r.id}
                style={{ padding: "10px 4px" }}
                actions={r.related_codes.map((s) => (
                  <a key={s.code} href={`/stock/${s.code}`} style={{ fontSize: 12 }}>
                    {s.name}
                  </a>
                ))}
              >
                <List.Item.Meta
                  title={
                    <Space size={6} wrap>
                      <span className="num" style={{ fontSize: 12, color: "var(--srp-brand)" }}>
                        {itemTime(r.publish_at)}
                      </span>
                      <Tag color={src.color} style={{ fontSize: 11, marginInlineEnd: 0 }}>
                        {src.label}
                      </Tag>
                      {r.sentiment && (
                        <Tag
                          color={SENTIMENT_COLOR[r.sentiment]}
                          style={{ fontSize: 11, marginInlineEnd: 0 }}
                        >
                          {r.sentiment}
                        </Tag>
                      )}
                      <Text strong style={{ fontSize: 13 }}>
                        {r.title}
                      </Text>
                      {r.url && (
                        <a href={r.url} target="_blank" rel="noreferrer" aria-label="原文链接">
                          <LinkOutlined style={{ fontSize: 12 }} />
                        </a>
                      )}
                    </Space>
                  }
                  description={
                    r.content ? (
                      <Paragraph
                        type="secondary"
                        style={{ fontSize: 12, marginBottom: 0, whiteSpace: "pre-wrap" }}
                        ellipsis={{ rows: 3, expandable: true, symbol: "展开" }}
                      >
                        {r.content}
                      </Paragraph>
                    ) : null
                  }
                />
              </List.Item>
            );
          }}
          pagination={{
            current: page,
            pageSize: size,
            total,
            showSizeChanger: true,
            pageSizeOptions: [20, 30, 50, 100],
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, s) => {
              setPage(p);
              setSize(s);
            },
          }}
        />
      </Card>
    </PageContainer>
  );
}
