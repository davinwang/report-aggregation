// Header security search — type a code/name, jump to the stock detail page.
import { useState } from "react";
import { AutoComplete, Input } from "antd";
import { SearchOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getSecurities } from "@/api";

interface Props {
  width?: number | string; // header uses the compact default; the mobile drawer passes 100%
}

export default function SecuritySearch({ width = 240 }: Props) {
  const [kw, setKw] = useState("");
  const navigate = useNavigate();
  const { data } = useQuery({
    queryKey: ["meta", "securities", kw],
    queryFn: () => getSecurities({ keyword: kw, limit: 20 }),
    enabled: kw.trim().length > 0,
    staleTime: 30_000,
  });

  const options = (data ?? []).map((s) => ({
    value: s.code,
    label: (
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
        <span>
          {s.code} · {s.name}
        </span>
        <span className="muted">{s.industry_sw ?? s.type}</span>
      </div>
    ),
  }));

  return (
    <AutoComplete
      value={kw}
      options={options}
      style={{ width }}
      onSelect={(code: string) => {
        setKw("");
        navigate(`/stock/${code}`);
      }}
      onSearch={(v) => setKw(v)}
    >
      <Input
        size="small"
        allowClear
        prefix={<SearchOutlined style={{ color: "#999" }} />}
        placeholder="搜索股票代码/名称 (如 600519)"
      />
    </AutoComplete>
  );
}
