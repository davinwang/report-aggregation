// 研报库 — searchable, filterable, server-paginated research-report library with CSV export.
import { useState } from "react";
import { Button, Card, DatePicker, Input, Select, Space } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import dayjs, { Dayjs } from "dayjs";
import { getReports, getResearchFacets } from "@/api";
import PageContainer from "@/components/PageContainer";
import ReportTable from "@/components/ReportTable";
import ProvenanceTag from "@/components/ProvenanceTag";
import PageRefresh from "@/components/PageRefresh";
import { useExport } from "@/hooks/useExport";

const { RangePicker } = DatePicker;

export default function ResearchPage() {
  const [keyword, setKeyword] = useState("");
  const [org, setOrg] = useState<string | undefined>();
  const [industry, setIndustry] = useState<string | undefined>();
  const [rating, setRating] = useState<string | undefined>();
  const [range, setRange] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const exportCsv = useExport();

  const { data: facets } = useQuery({ queryKey: ["research", "facets"], queryFn: getResearchFacets, staleTime: 60_000 });

  const params = {
    keyword: keyword || undefined,
    org,
    industry,
    rating,
    start: range?.[0] ? range[0].format("YYYY-MM-DD") : undefined,
    end: range?.[1] ? range[1].format("YYYY-MM-DD") : undefined,
    page,
    size,
  };
  const { data, isFetching } = useQuery({
    queryKey: ["research", "reports", params],
    queryFn: () => getReports(params),
    placeholderData: (prev) => prev,
    staleTime: 15_000,
  });

  const rows = data?.rows ?? [];
  const total = data?.meta?.total ?? 0;

  return (
    <PageContainer
      title="研报库"
      description={`共 ${total} 篇研报 · 数据来源 东方财富/巨潮`}
      extra={
        <Space>
          <ProvenanceTag source="em" />
          <PageRefresh queryKeys={[["research"]]} />
          <Button
            size="small"
            icon={<DownloadOutlined />}
            disabled={!rows.length}
            onClick={() =>
              exportCsv(
                rows.map((r) => ({
                  代码: r.code, 名称: r.name, 标题: r.title, 机构: r.org, 评级: r.rating,
                  目标价下限: r.target_price_low, 目标价上限: r.target_price_high,
                  行业: r.industry_group ?? r.industry, 日期: r.publish_date, 链接: r.pdf_url,
                })),
                `研报库_${dayjs().format("YYYYMMDD")}`,
              )
            }
          >
            导出CSV
          </Button>
        </Space>
      }
    >
      <Card size="small" style={{ marginBottom: 12 }}>
        <Space wrap>
          <Input.Search
            allowClear
            placeholder="搜索标题/名称"
            style={{ width: 240 }}
            onSearch={(v) => { setKeyword(v); setPage(1); }}
          />
          <Select
            allowClear showSearch placeholder="机构" style={{ width: 180 }}
            value={org} onChange={(v) => { setOrg(v); setPage(1); }}
            options={(facets?.orgs ?? []).map((o) => ({ value: o, label: o }))}
            filterOption={(input, option) => String(option?.label ?? "").includes(input)}
          />
          <Select
            allowClear placeholder="行业" style={{ width: 140 }}
            value={industry} onChange={(v) => { setIndustry(v); setPage(1); }}
            options={(facets?.industries ?? []).map((o) => ({ value: o, label: o }))}
          />
          <Select
            allowClear placeholder="评级" style={{ width: 120 }}
            value={rating} onChange={(v) => { setRating(v); setPage(1); }}
            options={(facets?.ratings ?? []).map((o) => ({ value: o, label: o }))}
          />
          <RangePicker
            onChange={(v) => { setRange(v as [Dayjs | null, Dayjs | null] | null); setPage(1); }}
          />
        </Space>
      </Card>

      <Card size="small">
        <ReportTable
          rows={rows}
          loading={isFetching}
          pagination={{
            current: page,
            pageSize: size,
            total,
            onChange: (p, s) => { setPage(p); setSize(s); },
          }}
        />
      </Card>
    </PageContainer>
  );
}
