// Provenance tag — shows the data source and (optionally) the data date.
// Mirrors the reference's useProvenanceTag: every card/table should disclose origin.
import { Tag, Tooltip } from "antd";

const SOURCE_LABEL: Record<string, string> = {
  em: "东方财富",
  sina: "新浪财经",
  cninfo: "巨潮资讯",
  exchange: "交易所",
};

interface Props {
  source?: string | null;
  date?: string | null;
}

export default function ProvenanceTag({ source, date }: Props) {
  if (!source && !date) return null;
  const label = source ? SOURCE_LABEL[source] || source : "";
  return (
    <Tooltip title={date ? `数据日期 ${date}` : undefined}>
      <Tag bordered={false} color="default" style={{ fontSize: 11, marginInlineEnd: 0 }}>
        {label}
        {date ? ` · ${date}` : ""}
      </Tag>
    </Tooltip>
  );
}
